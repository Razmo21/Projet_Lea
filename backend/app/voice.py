"""Bounded offline STT/TTS adapters. No network, microphone, database or server."""

from __future__ import annotations

import array
import hashlib
import io
import json
import os
import re
import subprocess
import time
import wave
from pathlib import Path, PureWindowsPath

from .model_registry import (
    LoadedModelRegistry,
    PiperInstalledVoice,
    PocketTTSInstalledVoice,
    VoiceFile,
)

MAX_SECONDS = 120
MAX_WAV_BYTES = 16_000 * 2 * MAX_SECONDS + 44
MAX_SPEECH_TEXT = 6000


class VoiceError(RuntimeError):
    """Safe diagnostic that may be displayed without exposing audio or local paths."""


class VoiceEngineError(VoiceError):
    """Safe availability failure that the local controller reports as HTTP 503."""


def asset_path(registry: LoadedModelRegistry, asset: VoiceFile, *, verify: bool = True) -> Path:
    """Confine vocal files to their dedicated folders, refusing every reparse component."""
    root = registry.project_root
    parts = PureWindowsPath(asset.path).parts
    if parts[:2] not in (("models", "voice"), ("runtime", "voice")):
        raise VoiceError("Un fichier vocal sort du dossier autorisé.")
    path = root
    for part in parts:
        path = path / part
        try:
            info = path.lstat()
            if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise VoiceError("Les liens ne sont pas autorisés pour les moteurs vocaux.")
        except OSError as error:
            raise VoiceError("Moteur vocal indisponible. Vérifie son installation locale.") from error
    if not path.is_file():
        raise VoiceError("Fichier vocal indisponible.")
    if verify:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != asset.sha256:
            raise VoiceError("L’intégrité d’un fichier vocal n’est pas confirmée.")
    return path


def voice_status(registry: LoadedModelRegistry) -> dict:
    """Inspect installation without loading an engine, probing a mic or reading SQLite."""
    config = registry.document.voice
    if config is None:
        return {"stt": False, "tts": False, "voices": [], "max_seconds": MAX_SECONDS}
    stt = True
    try:
        asset_path(registry, config.stt.executable, verify=False)
        asset_path(registry, config.stt.model, verify=False)
    except VoiceError:
        stt = False
    voices = []
    for voice in config.tts.voices:
        try:
            asset_path(registry, voice.model, verify=False)
            asset_path(registry, voice.config, verify=False)
            if isinstance(voice, PocketTTSInstalledVoice):
                asset_path(registry, voice.tokenizer, verify=False)
                asset_path(registry, voice.voice_state, verify=False)
            voices.append({
                "id": voice.id,
                "label": voice.label,
                "engine": voice.engine,
                "supports_rate": voice.supports_rate,
            })
        except VoiceError:
            continue
    return {
        "stt": stt,
        "tts": bool(voices),
        "voices": voices,
        "max_seconds": MAX_SECONDS,
        "stt_engine": config.stt.engine,
        "tts_engines": sorted({voice["engine"] for voice in voices}),
    }


def validate_wav(audio: bytes) -> float:
    """Accept only a canonical bounded mono PCM16/16kHz recording, never a media pathname."""
    if len(audio) < 44 or len(audio) > MAX_WAV_BYTES:
        raise VoiceError("Enregistrement vide ou trop long (120 secondes maximum).")
    try:
        with wave.open(io.BytesIO(audio), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, 16000, "NONE"):
                raise VoiceError("Le format audio attendu est WAV mono 16 kHz, 16 bits.")
            duration = stream.getnframes() / 16000
            pcm = stream.readframes(stream.getnframes())
            if len(pcm) != stream.getnframes() * 2 or not 0.2 <= duration <= MAX_SECONDS:
                raise VoiceError("Enregistrement vide, incomplet ou trop long.")
    except (wave.Error, EOFError) as error:
        raise VoiceError("L’enregistrement audio est illisible.") from error
    samples = array.array("h", pcm)
    # A silent buffer is not a transcription request: Whisper can hallucinate on silence.
    if not samples or max(abs(sample) for sample in samples) < 16:
        raise VoiceError("Aucune voix audible dans cet enregistrement.")
    return duration


def transcribe(registry: LoadedModelRegistry, audio: bytes, language: str) -> dict:
    """Run Whisper CPU once with pipe input/output; no raw recording is written to disk."""
    duration = validate_wav(audio)
    if language not in ("fr", "en") or registry.document.voice is None:
        raise VoiceError("Langue ou moteur de transcription indisponible.")
    config = registry.document.voice.stt
    executable = asset_path(registry, config.executable)
    model = asset_path(registry, config.model)
    started = time.monotonic()
    try:
        result = subprocess.run(
            # On Windows, '-of -' writes to CON, not the redirected pipe. A fixed
            # output label enables stdout segment callbacks; no -o* file flag is set.
            [str(executable), "-m", str(model), "-f", "-", "-l", language,
             "-t", str(config.threads), "-ng", "-nt", "-nf", "-of", "lea-stdout"],
            input=audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VoiceError("La transcription locale a échoué ou dépassé son délai.") from error
    text = result.stdout.decode("utf-8", errors="strict").strip()
    if result.returncode != 0 or not text or len(text) > 12000 or "\x00" in text:
        raise VoiceError("Le moteur local n’a pas produit de transcription exploitable.")
    # Only a numeric timing leaves stderr; engine diagnostics never expose the recording.
    timing = re.search(rb"load time\s*=\s*([0-9.]+)\s*ms", result.stderr)
    return {"text": text, "audio_seconds": duration,
            "load_ms": round(float(timing.group(1))) if timing else None,
            "processing_ms": round((time.monotonic() - started) * 1000)}


def speech_text(text: str) -> tuple[str, bool]:
    """Announce omitted code/long text without paraphrasing or claiming a complete reading."""
    if not isinstance(text, str) or not text.strip() or len(text) > 32000 or "\x00" in text:
        raise VoiceError("Texte de lecture vide ou trop long.")
    # Do not speak hidden reasoning, even if a caller supplied an invalid response.
    if re.search(r"<\s*/?\s*think\b|/no_think|/think", text, re.I):
        raise VoiceError("Ce contenu ne peut pas être lu oralement.")
    omitted = bool(re.search(r"```|~~~", text))
    clean = re.sub(r"(```|~~~).*?(?:\1|\Z)", "\nBloc technique disponible dans l’historique.\n", text, flags=re.S)
    clean = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|>|[-*+]\s)\s*", "", clean)
    clean = clean.replace("**", "").replace("__", "").replace("`", "")
    # Unfenced logs/code also need an honest boundary, not hundreds of spoken lines.
    if len(clean) > MAX_SPEECH_TEXT or len(clean.splitlines()) > 60:
        clean = clean[:MAX_SPEECH_TEXT].rsplit(" ", 1)[0]
        clean = "\n".join(clean.splitlines()[:60])
        omitted = True
    if omitted:
        clean += "\nLecture partielle : consulte l’historique pour le contenu complet et les détails techniques."
    return clean.strip(), omitted


def _synthesize_piper(
    registry: LoadedModelRegistry,
    voice: PiperInstalledVoice,
    text: str,
    rate: float,
    threads: int,
) -> dict:
    """Run the retained SIWIS/Piper path with its real native rate control."""
    model_path = asset_path(registry, voice.model)
    config_path = asset_path(registry, voice.config)
    clean, partial = speech_text(text)
    started = time.monotonic()
    import onnxruntime
    from piper import PiperVoice, SynthesisConfig
    from piper.config import PiperConfig, PhonemeType

    # Only the installed eSpeak French voice is supported; no automatic language package.
    metadata = PiperConfig.from_dict(json.loads(config_path.read_text(encoding="utf-8")))
    if metadata.phoneme_type != PhonemeType.ESPEAK or not metadata.espeak_voice.startswith("fr"):
        raise VoiceError("Cette voix locale n’est pas une voix française compatible.")
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = onnxruntime.InferenceSession(str(model_path), sess_options=options, providers=["CPUExecutionProvider"])
    engine = PiperVoice(session=session, config=metadata, use_tashkeel=False)
    loaded = time.monotonic()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        engine.synthesize_wav(clean, target, syn_config=SynthesisConfig(length_scale=1.0 / rate))
    audio = buffer.getvalue()
    if len(audio) > 24 * 1024 * 1024 or len(audio) <= 44:
        raise VoiceError("La réponse audio est trop longue ou vide.")
    return {
        "audio": audio,
        "partial": partial,
        "engine": voice.engine,
        "rate_applied": rate,
        "load_ms": round((loaded - started) * 1000),
        "processing_ms": round((time.monotonic() - started) * 1000),
    }


def _synthesize_pocket_tts(
    registry: LoadedModelRegistry,
    voice: PocketTTSInstalledVoice,
    text: str,
    rate: float,
) -> dict:
    """Generate the selected Pocket TTS voice on CPU and return one in-memory PCM WAV."""

    if float(rate) != 1.0:
        raise VoiceError(
            "La vitesse est fixe à 1× avec Léa — Voix naturelle française. "
            "Choisis SIWIS — Voix classique pour régler la vitesse."
        )
    asset_path(registry, voice.model)
    config_path = asset_path(registry, voice.config)
    asset_path(registry, voice.tokenizer)
    voice_state_path = asset_path(registry, voice.voice_state)
    config_text = config_path.read_text(encoding="utf-8")
    if any(prefix in config_text for prefix in ("hf://", "http://", "https://")):
        raise VoiceError("La configuration de la voix naturelle n’est pas entièrement locale.")
    clean, partial = speech_text(text)

    # Runtime synthesis must never contact a package index or model hub.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["KPOCKET_TTS_ERROR_WITHOUT_EOS"] = "1"

    import torch
    from pocket_tts import TTSModel

    started = time.monotonic()
    model = TTSModel.load_model(config=config_path)
    if model.device.type != "cpu" or model.sample_rate != 24_000:
        raise VoiceError("La voix naturelle n’a pas chargé son moteur CPU français attendu.")
    state = model.get_state_for_audio_prompt(voice_state_path)
    loaded = time.monotonic()
    generated = time.monotonic()
    first_chunk_ms = None
    chunks = []
    sample_count = 0
    for chunk in model.generate_audio_stream(state, clean):
        tensor = chunk.detach().cpu().float().reshape(-1)
        if first_chunk_ms is None:
            first_chunk_ms = round((time.monotonic() - generated) * 1000)
        sample_count += tensor.numel()
        if sample_count * 2 + 44 > 24 * 1024 * 1024:
            raise VoiceError("La réponse audio est trop longue.")
        chunks.append(tensor)
    if not chunks:
        raise VoiceError("La voix naturelle n’a produit aucun son.")
    waveform = torch.cat(chunks)
    if not bool(torch.isfinite(waveform).all()):
        raise VoiceError("La voix naturelle a produit un signal audio invalide.")
    pcm = waveform.clamp(-1, 1).mul(32_767).round().to(torch.int16).numpy().astype("<i2", copy=False)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setparams((1, 2, model.sample_rate, 0, "NONE", "not compressed"))
        target.writeframes(pcm.tobytes())
    return {
        "audio": buffer.getvalue(),
        "partial": partial,
        "engine": voice.engine,
        "rate_applied": 1.0,
        "load_ms": round((loaded - started) * 1000),
        "first_chunk_ms": first_chunk_ms,
        "processing_ms": round((time.monotonic() - started) * 1000),
    }


def synthesize(registry: LoadedModelRegistry, text: str, voice_id: str, rate: float) -> dict:
    """Dispatch one configured local voice without fallback or persistent workers."""

    if registry.document.voice is None or not isinstance(rate, (int, float)) or isinstance(rate, bool) or not 0.75 <= rate <= 1.5:
        raise VoiceError("Réglage vocal indisponible ou invalide.")
    config = registry.document.voice.tts
    voice = next((item for item in config.voices if item.id == voice_id), None)
    if voice is None:
        raise VoiceError("La voix sélectionnée n’est pas installée.")
    try:
        if isinstance(voice, PiperInstalledVoice):
            return _synthesize_piper(registry, voice, text, rate, config.threads)
        if isinstance(voice, PocketTTSInstalledVoice):
            return _synthesize_pocket_tts(registry, voice, text, rate)
    except VoiceError:
        raise
    except Exception as error:
        if isinstance(voice, PocketTTSInstalledVoice):
            raise VoiceEngineError(
                "La synthèse avec Léa — Voix naturelle française a échoué. "
                "La réponse reste dans l’historique ; réessaie ou sélectionne SIWIS — Voix classique."
            ) from error
        raise VoiceEngineError(
            "La synthèse avec SIWIS — Voix classique a échoué. "
            "La réponse reste dans l’historique."
        ) from error
    raise VoiceError("Moteur vocal non pris en charge.")

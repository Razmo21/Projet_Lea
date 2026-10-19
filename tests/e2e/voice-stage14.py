"""Real offline engine measurements using synthetic French, never a user's microphone.

Run with runtime/voice/.venv/Scripts/python.exe -B tests/e2e/voice-stage14.py.
The only saved WAV is an explicitly generated fixture for the browser test.
"""

import asyncio
import base64
import io
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.resources import WindowsCounters, gpu_memory

OUT = ROOT / '.test-runtime/stage14-20261017'
ORIGIN = 'http://127.0.0.1:5173'


def call(action, payload=None):
    """Exercise the actual loopback controller, including origin and payload checks."""
    request = urllib.request.Request(ORIGIN + '/api/voice/' + action,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Origin': ORIGIN, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=200) as response:
        return json.load(response)


def measure(action, payload):
    """Reuse stage13 OS counters; sampling exists only for this diagnostic operation."""
    counters = WindowsCounters()
    initial_ram, _ = counters.sample()
    initial_gpu = asyncio.run(gpu_memory())
    samples = []
    done = threading.Event()

    def sample():
        """Bound the diagnostic sampler to one test operation."""
        while not done.wait(.5): samples.append(counters.sample())

    thread = threading.Thread(target=sample, daemon=True); thread.start()
    started = time.monotonic()
    try:
        result = call(action, payload)
    finally:
        elapsed = time.monotonic() - started
        done.set(); thread.join(timeout=2)
    final_gpu = asyncio.run(gpu_memory())
    readings = [ram['available_bytes'] for ram, _ in samples if ram]
    cpus = [cpu for _, cpu in samples if cpu is not None]
    stats = {'wall_seconds': round(elapsed, 3), 'peak_system_ram_delta_mib': round((initial_ram['available_bytes'] - min(readings)) / 1024**2, 1) if readings and initial_ram else None,
             'system_cpu_peak_percent': max(cpus) if cpus else None,
             'gpu_before_mib': initial_gpu['used_bytes'] / 1024**2 if initial_gpu else None,
             'gpu_after_mib': final_gpu['used_bytes'] / 1024**2 if final_gpu else None,
             'engine_load_ms': result.get('load_ms'), 'engine_processing_ms': result.get('processing_ms')}
    return result, stats


def mono16(audio):
    """Resample a synthetic fixture; production capture uses browser OfflineAudioContext."""
    with wave.open(io.BytesIO(audio), 'rb') as stream:
        rate = stream.getframerate()
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2')
    resampled = np.interp(np.arange(int(len(samples) * 16000 / rate)) * rate / 16000, np.arange(len(samples)), samples).astype('<i2')
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed')); target.writeframes(resampled.tobytes())
    return output.getvalue()


def wav_seconds(audio):
    """Read the actual duration used to prove Piper's native rate control."""
    with wave.open(io.BytesIO(audio), 'rb') as stream:
        return stream.getnframes() / stream.getframerate()


def main():
    """Measure both TTS engines and round-trip synthetic speech through real STT."""
    OUT.mkdir(parents=True, exist_ok=True)
    status = call('status')
    assert status['stt'] and status['tts']
    voices = status['voices']
    assert [voice['id'] for voice in voices] == ['lea_voice', 'fr-siwis']
    voice = voices[0]['id']
    if '--programming-fixture' in sys.argv:
        # An explicit generated fixture, not a captured microphone recording.
        sentence = 'Lis les instructions du projet. Corrige l’addition puis lance la commande de test indiquée. Ne modifie pas les tests.'
        sound = call('speak', {'text': sentence, 'voice_id': voice, 'rate': 1.0})
        recording = mono16(base64.b64decode(sound['audio']))
        (OUT / 'synthetic-programming.wav').write_bytes(recording)
        print(json.dumps({'synthetic': True, 'seconds': (len(recording) - 44) / 32000, 'text': sentence}, ensure_ascii=True))
        return
    with urllib.request.urlopen('http://127.0.0.1:8000/api/models/status') as response:
        profile = json.load(response)['active_profile_id']
    sentences = [
        'Combien font deux plus deux ? Réponds uniquement par le nombre.',
        'Bonjour Léa. Le microphone fonctionne uniquement lorsque je clique sur le bouton. La transcription reste locale et je peux modifier mon brouillon avant de l’envoyer.',
        'Lis le projet puis vérifie les tests. Ne modifie aucun fichier sans comprendre sa fonction. La validation du résultat est obligatoire et le checkpoint doit rester disponible. ' * 3,
    ]
    for selected in voices:
        results = []
        for index, sentence in enumerate(sentences):
            sound, tts = measure('speak', {'text': sentence, 'voice_id': selected['id'], 'rate': 1.0})
            assert sound['engine'] == selected['engine'] and sound['rate_applied'] == 1.0
            recording = mono16(base64.b64decode(sound['audio']))
            transcription, stt = measure('transcribe', {'audio': base64.b64encode(recording).decode(), 'language': 'fr'})
            assert transcription['text'].strip()
            if selected['id'] == 'lea_voice' and index == 0:
                (OUT / 'synthetic-question.wav').write_bytes(recording)
            row = {'profile': profile, 'voice': selected, 'synthetic': True,
                   'duration': transcription['audio_seconds'], 'source': sentence,
                   'transcription': transcription['text'], 'tts': tts, 'stt': stt}
            results.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)
        if selected['supports_rate']:
            slow = call('speak', {'text': sentences[0], 'voice_id': selected['id'], 'rate': .8})
            fast = call('speak', {'text': sentences[0], 'voice_id': selected['id'], 'rate': 1.2})
            rate_check = {'slow_seconds': wav_seconds(base64.b64decode(slow['audio'])),
                          'fast_seconds': wav_seconds(base64.b64decode(fast['audio']))}
            assert rate_check['fast_seconds'] < rate_check['slow_seconds']
        else:
            try:
                call('speak', {'text': sentences[0], 'voice_id': selected['id'], 'rate': 1.2})
                raise AssertionError('Pocket TTS accepted a fictitious rate')
            except urllib.error.HTTPError as error:
                assert error.code == 422
            rate_check = {'fixed_rate': 1.0, 'unsupported_rate_rejected': True}
        output = {'voice': selected, 'rate_check': rate_check, 'results': results}
        (OUT / f'engines-{profile}-{selected["id"]}.json').write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8'
        )


if __name__ == '__main__': main()

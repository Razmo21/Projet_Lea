"""Install the three pinned Pocket TTS assets after an explicit admin command."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runtime" / "voice" / "downloads" / "huggingface"
DESTINATION = ROOT / "models" / "voice" / "pocket-tts" / "french"


@dataclass(frozen=True)
class Asset:
    """Describe one immutable upstream file and its permanent local destination."""

    repo_id: str
    filename: str
    revision: str
    destination: str
    size: int
    sha256: str


ASSETS = (
    Asset(
        "kyutai/pocket-tts",
        "languages/french/model.safetensors",
        "d0ebc5deb50bc6b225f686782f124dd37e2dca0a",
        "model.safetensors",
        219_029_196,
        "dd5fe98f5577ecfd56db9af8057cd05fe20cbc91560042aec8a56cfb01c34995",
    ),
    Asset(
        "kyutai/pocket-tts-without-voice-cloning",
        "languages/french/tokenizer.json",
        "8843db76457a91db32077edf8dfcd1c0e3e755fd",
        "tokenizer.json",
        246_403,
        "6211acffe9cb95172f71f0051f18e26ea305b2b32ea00b331ee976551c70887f",
    ),
    Asset(
        "kyutai/pocket-tts-without-voice-cloning",
        "languages/french/embeddings/estelle.safetensors",
        "4e1e0a3e611c51c0b4ed8174fc10f32a54644303",
        "estelle.safetensors",
        8_259_384,
        "f763800c6865a7c13e3368db7c24345d7ab22abd06c2ca40a3428d14c5357248",
    ),
)


def digest(path: Path) -> str:
    """Hash a file incrementally so the large model is never duplicated in memory."""

    value = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def require_expected(path: Path, size: int, sha256: str) -> None:
    """Reject incomplete or substituted assets before they become runnable."""

    if not path.is_file() or path.stat().st_size != size or digest(path) != sha256:
        raise RuntimeError(f"Ressource Pocket TTS invalide : {path.name}")


def install_asset(asset: Asset) -> None:
    """Download to the isolated cache and atomically copy a verified regular file."""

    target = DESTINATION / asset.destination
    if target.exists():
        require_expected(target, asset.size, asset.sha256)
        print(f"Vérifié : {target}")
        return
    source = Path(hf_hub_download(
        repo_id=asset.repo_id,
        filename=asset.filename,
        revision=asset.revision,
        cache_dir=CACHE,
    ))
    require_expected(source, asset.size, asset.sha256)
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=DESTINATION, suffix=".partial", delete=False) as temporary:
        temporary_path = Path(temporary.name)
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, temporary, length=1024 * 1024)
    try:
        require_expected(temporary_path, asset.size, asset.sha256)
        temporary_path.replace(target)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"Installé : {target}")


def install_config() -> None:
    """Copy the reviewed offline YAML without embedding Hub or temporary paths."""

    source = ROOT / "tools" / "voice" / "pocket-tts-french.yaml"
    target = DESTINATION / "config.yaml"
    expected = "a6b3976608d7339532b2ee0098a42b49fd07bec36c9a4e704ad27071a0effa0a"
    require_expected(source, 1300, expected)
    if target.exists():
        require_expected(target, 1300, expected)
    else:
        DESTINATION.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        require_expected(target, 1300, expected)
    print(f"Vérifié : {target}")


def main() -> None:
    """Install only the selected French variant and its official voice state."""

    for asset in ASSETS:
        install_asset(asset)
    install_config()


if __name__ == "__main__":
    main()

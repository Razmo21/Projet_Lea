"""Expose la configuration validée aux lanceurs locaux, sans démarrer de service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.model_registry import RegistryError, load_model_registry  # noqa: E402
from app.inference import inference_adapter  # noqa: E402


def main() -> int:
    """Émet un JSON unique ou une erreur explicite pour le propriétaire PowerShell."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    arguments = parser.parse_args()
    try:
        registry = load_model_registry(arguments.registry, project_root=arguments.project_root)
        document = registry.launcher_document()
        for profile in document["profiles"]:
            if profile["enabled"]:
                profile["launch"] = inference_adapter(registry, profile["id"]).launch_command()
        print(json.dumps(document, ensure_ascii=True))
    except RegistryError as error:
        # stdout reste lisible sous Windows PowerShell 5.1, même avec ErrorAction Stop.
        print(json.dumps({"error": str(error)}, ensure_ascii=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

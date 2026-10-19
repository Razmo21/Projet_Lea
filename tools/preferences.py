"""Pont ponctuel Vite/SQLite : aucune écoute réseau et aucun lancement de modèle."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pydantic import ValidationError  # noqa: E402
from app.database import Database  # noqa: E402
from app.model_registry import RegistryError, load_model_registry  # noqa: E402
from app.preferences import (  # noqa: E402
    PreferenceChange,
    PreferencesConflict,
    PreferencesError,
    PreferencesStore,
)
from app.voice import voice_status  # noqa: E402


def main() -> None:
    """Émet un statut JSON borné ; seules deux opérations fixes sont acceptées."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("read", "save"))
    action = parser.parse_args().action
    status = 200
    try:
        change = None
        if action == "save":
            payload = sys.stdin.buffer.read(1025)
            if len(payload) > 1024:
                raise ValueError("Requête trop grande.")
            change = PreferenceChange.model_validate_json(payload)
        # La capacité appartient au registre ; le choix utilisateur reste dans SQLite.
        registry = load_model_registry(os.environ.get("LEA_MODEL_REGISTRY") or None)
        general = registry.profile("general")
        available = general.enabled and general.model.reasoning_control == "think_directives"
        if change is not None and change.general_reasoning is not None and not available:
            raise PreferencesError("Le modèle Général configuré ne propose pas ce réglage de raisonnement.")
        if change is not None and change.voice_id is not None:
            if change.voice_id not in {voice["id"] for voice in voice_status(registry)["voices"]}:
                raise ValueError("La voix choisie n’est pas installée.")
        database = Database()
        database.initialize(recover_generations=False)
        store = PreferencesStore(database)
        preferences = store.save(change) if change is not None else store.read()
        body = preferences.model_dump()
        body["general_reasoning_available"] = available
    except RegistryError:
        status, body = 503, {"detail": "La configuration locale des modèles est invalide. Paramètres non confirmés."}
    except (ValidationError, ValueError):
        status, body = 422, {"detail": "Préférence invalide : vérifiez le réglage, son type et la révision."}
    except PreferencesConflict as error:
        status, body = 409, {"detail": str(error)}
    except PreferencesError as error:
        status, body = 503, {"detail": str(error)}
    except (OSError, RuntimeError, sqlite3.Error):
        status, body = 503, {"detail": "Le stockage des préférences est indisponible. Aucun changement confirmé."}
    print(json.dumps({"status": status, "body": body}, ensure_ascii=True))


if __name__ == "__main__":
    main()

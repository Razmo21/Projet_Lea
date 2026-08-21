from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ModelControllerError(RuntimeError):
    """Signale une bascule locale refusée ou échouée sans exposer les journaux."""


class ModelController(Protocol):
    """Contrat minimal du gestionnaire de processus utilisé par l'API."""

    async def activate(self, profile_id: str) -> str:
        """Retourne le profil réellement actif après activation ou rollback."""


class PowerShellModelController:
    """Délègue la propriété des PID au lanceur PowerShell durci existant."""

    def __init__(self, project_root: str | Path = PROJECT_ROOT) -> None:
        """Fige le script autorisé sous la racine locale du projet."""

        self.project_root = Path(project_root).resolve()
        self.script_path = self.project_root / "lea.ps1"
        if not self.script_path.is_file():
            raise ModelControllerError("Le gestionnaire local de Léa est introuvable.")

    async def activate(self, profile_id: str) -> str:
        """Exécute une commande fixe sans shell ni argument fourni par le modèle."""

        process = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            "switch-model",
            "-ProfileId",
            profile_id,
            "-Json",
            cwd=str(self.project_root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return_code = await process.wait()
        if return_code != 0:
            # Les détails restent dans les journaux locaux ; l'API ne divulgue
            # ni chemin, ni ligne de commande, ni sortie système au navigateur.
            raise ModelControllerError(
                "Le changement de profil a échoué ; l'ancien profil a été restauré si possible."
            )
        try:
            state = json.loads(
                (self.project_root / ".lea" / "processes.json").read_text(
                    encoding="utf-8-sig"
                )
            )
            active_profile_id = state["components"]["model"]["profileId"]
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ModelControllerError(
                "Le gestionnaire local n'a pas confirmé le profil actif."
            ) from error
        return str(active_profile_id)

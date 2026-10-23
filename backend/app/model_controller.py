"""Profile lifecycle controller for Léa's direct and agentic model topologies."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

from .inference import inference_adapter
from .model_registry import LoadedModelRegistry, load_model_registry
from .openhands_runtime import OpenHandsRuntime, OpenHandsRuntimeError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL_EXECUTABLE = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)


class ModelControllerError(RuntimeError):
    """Signals a safe model-switch failure without exposing local command output."""


class ModelController(Protocol):
    """Defines the small activation contract consumed by the HTTP API."""

    async def activate(self, profile_id: str, previous_profile_id: str) -> str:
        """Return the profile confirmed active after a complete activation or rollback."""


class PowerShellModelController:
    """Switches declared direct profiles and Programming through their process owners."""

    def __init__(
        self,
        project_root: str | Path = PROJECT_ROOT,
        registry: LoadedModelRegistry | None = None,
        openhands_runtime: OpenHandsRuntime | None = None,
    ) -> None:
        """Freeze trusted local scripts and the central model registry for this controller instance."""

        self.project_root = Path(project_root).resolve()
        self.script_path = self.project_root / "lea.ps1"
        self.development_script = self.project_root / "tools" / "openhands" / "development_runtime.py"
        self.python_path = self.project_root / "backend" / ".venv" / "Scripts" / "python.exe"
        self.registry = registry or load_model_registry(project_root=self.project_root)
        self.openhands_runtime = openhands_runtime or OpenHandsRuntime(self.registry)
        if not self.script_path.is_file():
            raise ModelControllerError("Le gestionnaire local de Léa est introuvable.")
        if not self.development_script.is_file() or not self.python_path.is_file():
            raise ModelControllerError("Le runtime Programmation local est introuvable.")

    async def _run(self, *arguments: str, capture_output: bool = False) -> str:
        """Execute one fixed local lifecycle command and keep detailed output off the HTTP surface."""

        try:
            process = await asyncio.create_subprocess_exec(
                *arguments,
                cwd=str(self.project_root),
                stdin=asyncio.subprocess.DEVNULL,
                # A model launched by lea.ps1 inherits stdout unless this parent
                # deliberately discards it; otherwise communicate() never sees EOF.
                stdout=asyncio.subprocess.PIPE if capture_output else asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE if capture_output else asyncio.subprocess.DEVNULL,
            )
        except OSError as error:
            raise ModelControllerError("Le gestionnaire local de modèle ne peut pas démarrer.") from error
        try:
            if capture_output:
                stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=300)
            else:
                await asyncio.wait_for(process.wait(), timeout=300)
                stdout = b""
        except TimeoutError as error:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise ModelControllerError("Le changement de profil dépasse le délai autorisé.") from error
        if process.returncode != 0:
            raise ModelControllerError("Le gestionnaire local de modèle a échoué.")
        return stdout.decode("utf-8", errors="replace")

    async def _direct_script(
        self,
        action: str,
        *,
        profile_id: str | None = None,
        capture_output: bool = False,
    ) -> dict[str, object] | None:
        """Delegate direct-model transitions to the PID-hardened PowerShell owner."""

        arguments = [
            str(POWERSHELL_EXECUTABLE),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            action,
            "-RegistryPath",
            str(self.registry.registry_path),
        ]
        if profile_id is not None:
            arguments.extend(("-ProfileId", profile_id))
        if capture_output:
            arguments.append("-Json")
        output = await self._run(*arguments, capture_output=capture_output)
        if not capture_output:
            return None
        try:
            payload = json.loads(output)
        except (TypeError, ValueError) as error:
            raise ModelControllerError("Le runtime direct n’a pas confirmé son état.") from error
        if not isinstance(payload, dict):
            raise ModelControllerError("Le runtime direct a retourné un état invalide.")
        return payload

    async def _development_script(self, action: str) -> dict[str, object]:
        """Invoke the Programming process owner and require its JSON confirmation."""

        output = await self._run(
            str(self.python_path),
            "-B",
            str(self.development_script),
            action,
            "--registry",
            str(self.registry.registry_path),
            "--json",
            capture_output=True,
        )
        try:
            payload = json.loads(output)
        except (TypeError, ValueError) as error:
            raise ModelControllerError("Le runtime Programmation n’a pas confirmé son état.") from error
        if not isinstance(payload, dict):
            raise ModelControllerError("Le runtime Programmation a retourné un état invalide.")
        return payload

    async def _direct_ready(self, profile_id: str) -> bool:
        """Confirm the alias served by the shared direct llama.cpp endpoint."""

        return await inference_adapter(self.registry, profile_id).is_ready()

    async def _restore_direct(self, profile_id: str) -> None:
        """Stop confirmed Programming services before restoring one declared direct profile."""

        try:
            await self.openhands_runtime.stop_idle_agent_server()
        except OpenHandsRuntimeError as error:
            raise ModelControllerError("L’Agent Server OpenHands ne peut pas être arrêté en sécurité.") from error
        await self._development_script("stop")
        await self._direct_script("start-model", profile_id=profile_id)

    async def activate(self, profile_id: str, previous_profile_id: str) -> str:
        """Activate one profile and restore the exact preceding profile on failure."""

        try:
            profile = self.registry.profile(profile_id)
            previous_profile = self.registry.profile(previous_profile_id)
        except RuntimeError as error:
            raise ModelControllerError("Le profil demandé est inconnu.") from error
        if not profile.enabled:
            raise ModelControllerError("Le profil demandé est désactivé.")
        if profile.id == previous_profile.id:
            return profile.id
        if profile.agent_engine == "direct":
            if previous_profile.agent_engine == "direct":
                # stdout reste fermé : un serveur enfant ne peut ainsi retenir
                # le pipe du contrôleur. L'alias servi confirme ensuite la cible.
                await self._direct_script("switch-model", profile_id=profile.id)
                if not await self._direct_ready(profile.id):
                    raise ModelControllerError(
                        "Le nouveau profil n’est pas prêt ; l’ancien profil a été restauré."
                    )
            else:
                try:
                    await self._restore_direct(profile.id)
                except ModelControllerError as error:
                    try:
                        restored = await self._development_script("start")
                        if restored.get("state") != "ready":
                            raise ModelControllerError(
                                "Le modèle Programmation précédent n’est pas prêt."
                            )
                        readiness = await self.openhands_runtime.wait_until_ready(
                            require_agent_server=False
                        )
                        if not readiness.profile_ready:
                            raise ModelControllerError(readiness.message)
                    except (ModelControllerError, OpenHandsRuntimeError) as rollback_error:
                        raise ModelControllerError(
                            "Le profil direct a échoué et le retour Programmation n’a pas pu être confirmé."
                        ) from rollback_error
                    raise error
            return profile.id
        if profile.id != "development" or profile.agent_engine != "OpenHands":
            raise ModelControllerError("Le profil demandé ne possède pas de cycle de vie local autorisé.")
        try:
            # Docker Desktop est exclusivement vérifié ici : ce contrôleur ne
            # le lance jamais, conformément au contrat de l’étape 10.
            await self.openhands_runtime.require_run_prerequisites()
            await self._direct_script("stop-model")
            started = await self._development_script("start")
            if started.get("state") != "ready":
                raise ModelControllerError("Le modèle Programmation n’est pas prêt.")
            # Activation loads the model only. The explicit run owns creation
            # of its Agent Server and verification of the native tools.
            readiness = await self.openhands_runtime.wait_until_ready(require_agent_server=False)
            if not readiness.profile_ready:
                raise ModelControllerError(readiness.message)
            return profile.id
        except (ModelControllerError, OpenHandsRuntimeError) as error:
            # Un échec après l'arrêt du profil direct précédent ne doit jamais
            # laisser l'utilisateur sans modèle. Chaque cible reste vérifiée
            # par son propriétaire de processus.
            try:
                await self._development_script("stop")
                await self._direct_script("start-model", profile_id=previous_profile.id)
            except (ModelControllerError, OpenHandsRuntimeError) as rollback_error:
                raise ModelControllerError(
                    "Le profil Programmation a échoué et le profil précédent n’a pas pu être restauré."
                ) from rollback_error
            if isinstance(error, OpenHandsRuntimeError):
                raise ModelControllerError(str(error)) from error
            raise

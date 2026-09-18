"""Profile lifecycle controller for the two local Léa model topologies."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Protocol

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

    async def activate(self, profile_id: str) -> str:
        """Return the profile confirmed active after a complete activation or rollback."""


class PowerShellModelController:
    """Switches General and Programming through their respective local process owners."""

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

    async def _general_script(self, action: str) -> None:
        """Delegate General's process to the existing PID-hardened PowerShell owner only."""

        await self._run(
            str(POWERSHELL_EXECUTABLE),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.script_path),
            action,
        )

    async def _development_script(self, action: str) -> dict[str, object]:
        """Invoke Qwen's stateful helper and require a JSON confirmation from its own owner."""

        output = await self._run(
            str(self.python_path),
            str(self.development_script),
            action,
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

    async def _restore_general(self) -> None:
        """Stop only confirmed Programming services before restoring the known General runtime."""

        try:
            await self.openhands_runtime.stop_idle_agent_server()
        except OpenHandsRuntimeError as error:
            raise ModelControllerError("L’Agent Server OpenHands ne peut pas être arrêté en sécurité.") from error
        await self._development_script("stop")
        await self._general_script("start-model")

    async def activate(self, profile_id: str) -> str:
        """Activate one declared profile with a General rollback when Programming cannot become ready."""

        try:
            profile = self.registry.profile(profile_id)
        except RuntimeError as error:
            raise ModelControllerError("Le profil demandé est inconnu.") from error
        if profile.id == "general":
            await self._restore_general()
            return "general"
        if profile.id != "development" or profile.agent_engine != "OpenHands":
            raise ModelControllerError("Le profil demandé ne possède pas de cycle de vie local autorisé.")
        idle_handle = None
        try:
            # Docker Desktop est exclusivement vérifié ici : ce contrôleur ne
            # le lance jamais, conformément au contrat de l’étape 10.
            await self.openhands_runtime.require_docker()
            await self._general_script("stop-model")
            started = await self._development_script("start")
            if started.get("state") != "ready":
                raise ModelControllerError("Qwen Programmation n’est pas prêt.")
            idle_handle = await self.openhands_runtime.start_agent_server()
            # Health can precede the native tool registry by a brief interval,
            # so the runtime returns only a bounded, verified readiness state.
            readiness = await self.openhands_runtime.wait_until_ready()
            if not readiness.profile_ready:
                raise ModelControllerError(readiness.message)
            return "development"
        except (ModelControllerError, OpenHandsRuntimeError) as error:
            # A failure after General stopped must never strand the user with no
            # model. Every cleanup target below is verified by its own owner.
            try:
                if idle_handle is not None:
                    await self.openhands_runtime.stop_agent_server(idle_handle)
                await self._development_script("stop")
                await self._general_script("start-model")
            except (ModelControllerError, OpenHandsRuntimeError) as rollback_error:
                raise ModelControllerError(
                    "Le profil Programmation a échoué et le retour Général n’a pas pu être confirmé."
                ) from rollback_error
            if isinstance(error, OpenHandsRuntimeError):
                raise ModelControllerError(str(error)) from error
            raise

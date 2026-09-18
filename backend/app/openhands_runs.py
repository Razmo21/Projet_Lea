"""Persistent lifecycle management for one OpenHands SDK run at a time.

The manager owns the SDK child process and its labelled Agent Server container.
It deliberately marks a run cancelled or timed out only after that container
has stopped, so a late tool call cannot silently mutate a project afterwards.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

from .checkpoints import (
    CheckpointConflictError,
    CheckpointError,
    CheckpointService,
    InternalGitMountpoint,
)
from .database import Database
from .openhands_evidence import PROJECT_ACTION_TOOL_NAMES, public_failure_summary
from .model_registry import LoadedModelRegistry, ModelProfile
from .openhands_runtime import AgentServerHandle, OpenHandsRuntime, OpenHandsRuntimeError
from .workspace import FrozenProject, WorkspaceGuard, WorkspacePathError


FINAL_RUN_STATES = frozenset({"completed", "failed", "cancelled", "limit_reached"})
class OpenHandsRunError(RuntimeError):
    """Reports a controlled agent-run lifecycle failure without exposing SDK or Docker internals."""


class ManagedProcess(Protocol):
    """Describe the small subprocess surface needed for safe cancellation in unit tests and production."""

    returncode: int | None

    async def wait(self) -> int:
        """Wait for the SDK child to exit and return its process code."""

        ...

    def terminate(self) -> None:
        """Request graceful termination of the SDK child owned by this manager."""

        ...

    def kill(self) -> None:
        """Force-stop the SDK child only after graceful termination times out."""

        ...


ProcessStarter = Callable[..., Awaitable[ManagedProcess]]
FinishedCallback = Callable[[], Awaitable[None]]


@dataclass
class ActiveOpenHandsRun:
    """Keep mutable process ownership private while project identity remains frozen."""

    run_id: str
    frozen: FrozenProject
    checkpoint_id: str
    handle: AgentServerHandle
    internal_git_mountpoint: InternalGitMountpoint | None
    process: ManagedProcess
    directory: Path
    on_finished: FinishedCallback
    desired_state: str | None = None
    completion: asyncio.Event = field(default_factory=asyncio.Event)
    finalization_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    monitor_task: asyncio.Task[None] | None = None
    finalization_error: str | None = None
    finalized: bool = False


class OpenHandsRunManager:
    """Starts OpenHands only after a checkpoint and finalizes it only after agent shutdown."""

    def __init__(
        self,
        database: Database,
        guard: WorkspaceGuard,
        checkpoints: CheckpointService,
        runtime: OpenHandsRuntime,
        registry: LoadedModelRegistry,
        runtime_root: str | Path,
        *,
        runner_script: str | Path | None = None,
        process_starter: ProcessStarter | None = None,
    ) -> None:
        """Freeze trusted dependencies and the backend-owned directory for runner state files."""

        self.database = database
        self.guard = guard
        self.checkpoints = checkpoints
        self.runtime = runtime
        self.registry = registry
        self.runtime_root = Path(runtime_root)
        self.runner_script = Path(runner_script) if runner_script is not None else (
            registry.project_root / "tools" / "openhands" / "run_lea_agent.py"
        )
        self._process_starter = process_starter or asyncio.create_subprocess_exec
        self._lock = asyncio.Lock()
        self._active: ActiveOpenHandsRun | None = None

    @staticmethod
    def _canonical_run_id(run_id: str) -> str:
        """Canonicalize every run ID before it is used as a filesystem directory name."""

        try:
            return str(UUID(run_id))
        except (TypeError, ValueError, AttributeError) as error:
            raise OpenHandsRunError("Identifiant de run OpenHands invalide.") from error

    def _run_directory(self, run_id: str, *, create: bool) -> Path:
        """Resolve a UUID-only directory strictly below the private runtime root."""

        canonical = self._canonical_run_id(run_id)
        root = self.runtime_root.resolve(strict=False)
        directory = root / canonical
        if create:
            directory.mkdir(parents=True, exist_ok=False)
        try:
            resolved = directory.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=False))
        except (OSError, ValueError) as error:
            raise OpenHandsRunError("Le stockage local du run OpenHands est indisponible.") from error
        return resolved

    @staticmethod
    def _write_text_atomically(path: Path, content: str) -> None:
        """Publish a UTF-8 task file atomically so the SDK never reads a partial request."""

        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        """Read one bounded runner record and treat interrupted or malformed files as absent."""

        try:
            if not path.is_file() or path.stat().st_size > 128 * 1024:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _result_summary(value: object, fallback: str) -> str:
        """Bound a public final answer without retaining raw SDK error text or hidden reasoning."""

        if isinstance(value, str):
            summary = value.replace("\x00", "").strip()
            if summary:
                return summary[:8_000]
        return fallback

    @staticmethod
    async def _terminate_process(process: ManagedProcess) -> None:
        """Terminate the SDK client promptly; container shutdown remains the mutation safety boundary."""

        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                return
            await asyncio.wait_for(process.wait(), timeout=10)

    async def _spawn_runner(
        self,
        run_id: str,
        profile: ModelProfile,
        directory: Path,
    ) -> ManagedProcess:
        """Launch only the registry-pinned SDK interpreter with backend-owned input/output paths."""

        if not self.runner_script.is_file():
            raise OpenHandsRunError("Le runner OpenHands de Léa est introuvable.")
        task_path = directory / "task.txt"
        session_path = directory / "session.json"
        result_path = directory / "result.json"
        return await self._process_starter(
            str(self.registry.openhands_sdk_python()),
            str(self.runner_script),
            "--server-url",
            self.runtime.agent_server_url,
            "--model-alias",
            profile.runtime.alias,
            "--context-size",
            str(profile.context_tokens),
            "--run-id",
            run_id,
            "--task-path",
            str(task_path),
            "--session-path",
            str(session_path),
            "--result-path",
            str(result_path),
            "--timeout-seconds",
            str(self.registry.document.agent_policy.max_duration_seconds),
            cwd=str(self.registry.project_root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def start(
        self,
        task: str,
        profile: ModelProfile,
        frozen: FrozenProject,
        on_finished: FinishedCallback,
    ) -> dict[str, Any]:
        """Create a persistent frozen run, checkpoint it, then hand the project to OpenHands once."""

        if profile.id != "development" or profile.agent_engine != "OpenHands":
            raise OpenHandsRunError("Le profil Programmation OpenHands est requis.")
        normalized_task = task.strip()
        if not normalized_task or "\x00" in normalized_task or len(normalized_task.encode("utf-8")) > 16_384:
            raise OpenHandsRunError("La tâche OpenHands est invalide.")
        async with self._lock:
            if self._active is not None:
                raise OpenHandsRunError("Un run OpenHands est déjà actif.")
            run_id = str(uuid4())
            self.database.create_agent_run(run_id, frozen.project_id, profile.id, normalized_task)
            try:
                checkpoint = self.checkpoints.create(run_id, frozen)
            except (CheckpointError, WorkspacePathError) as error:
                self.database.update_agent_run(
                    run_id,
                    state="failed",
                    result_summary="Le checkpoint initial du projet a échoué.",
                )
                raise OpenHandsRunError("Le checkpoint initial du projet a échoué.") from error
            checkpoint_id = str(checkpoint["checkpoint_id"])
            directory: Path | None = None
            handle: AgentServerHandle | None = None
            try:
                directory = self._run_directory(run_id, create=True)
                self._write_text_atomically(directory / "task.txt", normalized_task)
                await self.runtime.stop_idle_agent_server()
                handle = await self.runtime.start_agent_server(
                    run_id=run_id,
                    project_path=frozen.workspace_path.path,
                )
                internal_git_mountpoint = self.checkpoints.capture_empty_internal_git_mountpoint(
                    checkpoint_id,
                    frozen,
                )
                process = await self._spawn_runner(run_id, profile, directory)
            except (
                OSError,
                OpenHandsRuntimeError,
                OpenHandsRunError,
                WorkspacePathError,
            ) as error:
                if handle is not None:
                    try:
                        await self.runtime.stop_agent_server(handle)
                    except OpenHandsRuntimeError as stop_error:
                        # Do not publish a terminal state while a verified run
                        # container might still execute a delayed tool action.
                        raise OpenHandsRunError(
                            "Le conteneur OpenHands de démarrage ne peut pas être arrêté en sécurité."
                        ) from stop_error
                try:
                    # No run can begin until this branch exits. Finalizing the
                    # initial snapshot keeps the persisted failed run and its
                    # checkpoint coherent even when launch failed early.
                    self.checkpoints.complete(checkpoint_id, frozen)
                except (CheckpointError, WorkspacePathError):
                    pass
                self.database.update_agent_run(
                    run_id,
                    state="failed",
                    result_summary="Le run OpenHands n'a pas pu démarrer.",
                )
                raise OpenHandsRunError("Le run OpenHands n'a pas pu démarrer.") from error
            active = ActiveOpenHandsRun(
                run_id=run_id,
                frozen=frozen,
                checkpoint_id=checkpoint_id,
                handle=handle,
                internal_git_mountpoint=internal_git_mountpoint,
                process=process,
                directory=directory,
                on_finished=on_finished,
            )
            self.database.update_agent_run(run_id, state="running")
            self._active = active
            active.monitor_task = asyncio.create_task(self._monitor(active))
            return self.database.get_agent_run(run_id)

    def _runner_record(self, active: ActiveOpenHandsRun) -> tuple[str | None, str, str, str]:
        """Map the runner's technical stop and evidence verdict to separate public states."""

        session = self._read_json(active.directory / "session.json")
        session_id = session.get("session_id") if isinstance(session, dict) else None
        result = self._read_json(active.directory / "result.json")
        requested_state = active.desired_state
        if requested_state == "cancelled":
            return (
                session_id if isinstance(session_id, str) else None,
                "cancelled",
                "failed",
                "Le run OpenHands a été annulé après l'arrêt du serveur.",
            )
        if result is None:
            return (
                session_id if isinstance(session_id, str) else None,
                "failed",
                "failed",
                "Le run OpenHands s'est arrêté sans résultat final exploitable.",
            )
        runner_state = result.get("state")
        if runner_state not in {"completed", "failed", "limit_reached"}:
            runner_state = "failed"
        session_value = result.get("session_id")
        if isinstance(session_value, str):
            session_id = session_value
        if runner_state == "completed":
            validation_status = result.get("validation_status")
            tool_names = result.get("tool_names")
            has_project_tool = isinstance(tool_names, list) and any(
                isinstance(tool_name, str)
                and tool_name.casefold() in PROJECT_ACTION_TOOL_NAMES
                for tool_name in tool_names
            )
            if validation_status == "validated" and has_project_tool:
                summary = self._result_summary(
                    result.get("result_summary"),
                    "Le run OpenHands est terminé.",
                )
                return (
                    session_id if isinstance(session_id, str) else None,
                    "completed",
                    "validated",
                    summary,
                )
            # A malformed or legacy child verdict is an explicit public
            # failure. Its checkpoint remains available for rollback.
            failure_code = result.get("failure_code")
            return (
                session_id if isinstance(session_id, str) else None,
                "failed",
                "failed",
                public_failure_summary(failure_code),
            )
        if runner_state == "limit_reached":
            return (
                session_id if isinstance(session_id, str) else None,
                "limit_reached",
                "failed",
                "Le run OpenHands a atteint sa limite et a été arrêté.",
            )
        failure_code = result.get("failure_code")
        return (
            session_id if isinstance(session_id, str) else None,
            "failed",
            "failed",
            public_failure_summary(failure_code),
        )

    def _session_id_from_directory(self, run_id: str) -> str | None:
        """Read an optional runner session without making recovery depend on a surviving state file."""

        try:
            session = self._read_json(self._run_directory(run_id, create=False) / "session.json")
        except OpenHandsRunError:
            return None
        value = session.get("session_id") if isinstance(session, dict) else None
        return value if isinstance(value, str) else None

    async def _monitor(self, active: ActiveOpenHandsRun) -> None:
        """Wait for the SDK child and always route terminal publication through verified server shutdown."""

        try:
            await active.process.wait()
            await self._finalize(active)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The run stays non-terminal when its Agent Server cannot be
            # verified and stopped. This is safer than claiming cancellation.
            active.finalization_error = "Le run OpenHands ne peut pas être arrêté en sécurité."

    async def _finalize(self, active: ActiveOpenHandsRun) -> None:
        """Stop the exact container before snapshotting and publishing any terminal SQLite state."""

        async with active.finalization_lock:
            if active.finalized:
                return
            try:
                await self.runtime.stop_agent_server(active.handle)
            except OpenHandsRuntimeError as error:
                active.finalization_error = "Le run OpenHands ne peut pas être arrêté en sécurité."
                raise OpenHandsRunError(active.finalization_error) from error
            # Docker Desktop can leave the empty host-side nested mountpoint
            # after its private `/workspace/.git` tmpfs disappears.  Remove
            # only the fingerprint captured before the SDK could act; every
            # other path remains visible to the checkpoint inventory.
            self.checkpoints.discard_empty_internal_git_mountpoint(
                active.checkpoint_id,
                active.frozen,
                active.internal_git_mountpoint,
            )
            session_id, state, validation_status, summary = self._runner_record(active)
            try:
                self.checkpoints.complete(active.checkpoint_id, active.frozen)
            except (CheckpointError, WorkspacePathError) as error:
                state = "failed"
                validation_status = "failed"
                summary = "Le checkpoint final du projet a échoué."
                active.finalization_error = summary
                # The container is already stopped; publishing this failure is
                # safe and prevents a misleading successful run.
            self.database.update_agent_run(
                active.run_id,
                state=state,
                validation_status=validation_status,
                openhands_session_id=session_id,
                result_summary=summary,
            )
            active.finalized = True
            try:
                # Programming remains active after a normal run. Restore the
                # no-project readiness server without ever mounting a project.
                await self.runtime.start_agent_server()
            except OpenHandsRuntimeError:
                # A later profile activation will surface readiness honestly;
                # a completed run is still truthful because its container stopped.
                pass
            async with self._lock:
                if self._active is active:
                    self._active = None
            try:
                await active.on_finished()
            finally:
                active.completion.set()

    async def get(self, run_id: str) -> dict[str, Any]:
        """Read a durable run record; in-memory ownership never changes its persisted project ID."""

        return self.database.get_agent_run(self._canonical_run_id(run_id))

    async def wait_for_completion(self, run_id: str, *, timeout_seconds: float = 30) -> dict[str, Any]:
        """Wait for a backend-owned run in tests or shutdown code without exposing its process handle."""

        canonical = self._canonical_run_id(run_id)
        async with self._lock:
            active = self._active if self._active is not None and self._active.run_id == canonical else None
        if active is not None:
            try:
                await asyncio.wait_for(active.completion.wait(), timeout=timeout_seconds)
            except TimeoutError as error:
                raise OpenHandsRunError("Le run OpenHands est encore en cours.") from error
        return self.database.get_agent_run(canonical)

    def list(self) -> list[dict[str, Any]]:
        """List only compact persisted run records, leaving detailed events in OpenHands storage."""

        return self.database.list_agent_runs()

    async def cancel(self, run_id: str) -> dict[str, Any]:
        """Cancel a run only after its SDK client and verified Agent Server have both stopped."""

        canonical = self._canonical_run_id(run_id)
        async with self._lock:
            active = self._active if self._active is not None and self._active.run_id == canonical else None
        if active is None:
            record = self.database.get_agent_run(canonical)
            if record["state"] in FINAL_RUN_STATES:
                return record
            raise OpenHandsRunError("Le run OpenHands n'est pas contrôlé par cette instance.")
        active.desired_state = "cancelled"
        await self._terminate_process(active.process)
        try:
            await asyncio.wait_for(active.completion.wait(), timeout=90)
        except TimeoutError as error:
            raise OpenHandsRunError("L'annulation attend encore l'arrêt vérifié du run OpenHands.") from error
        if active.finalization_error is not None and not active.finalized:
            raise OpenHandsRunError(active.finalization_error)
        return self.database.get_agent_run(canonical)

    async def close(self) -> None:
        """Stop a backend-owned active run during FastAPI shutdown without touching unrelated processes."""

        async with self._lock:
            active = self._active
        if active is None:
            return
        active.desired_state = "cancelled"
        await self._terminate_process(active.process)
        try:
            await asyncio.wait_for(active.completion.wait(), timeout=90)
        except TimeoutError:
            # Do not force a terminal DB state if the container could not be
            # verified. Startup recovery will retry the owned run safely.
            return

    def _persist_recovery_project_failure(self, record: dict[str, Any], checkpoint_id: str) -> None:
        """Publish a safe interrupted-run failure after its owned container is confirmed stopped.

        A completed checkpoint can expose a clear conflict to the user.  A
        `ready` checkpoint has no truthful after-snapshot, so it is instead
        marked failed and never offered as a synthetic diff or rollback.
        """

        checkpoint = self.database.get_project_checkpoint(checkpoint_id)
        if checkpoint["state"] == "completed":
            self.checkpoints.record_conflict(
                checkpoint_id,
                "Le projet figé a changé avant la reprise du backend.",
            )
        elif checkpoint["state"] == "ready":
            self.database.transition_project_checkpoint(
                checkpoint_id,
                "failed",
                expected_states={"ready"},
                error="Le projet figé n'a pas pu être revalidé après redémarrage.",
            )
        self.database.update_agent_run(
            record["run_id"],
            state="failed",
            result_summary="Le run OpenHands a été interrompu et son projet figé a changé.",
        )

    async def recover(self) -> None:
        """Finalize interrupted persisted runs only after their exact labelled container is stopped."""

        for record in self.database.list_incomplete_agent_runs():
            checkpoint_id = record.get("checkpoint_id")
            if not isinstance(checkpoint_id, str):
                # The checkpoint is created before any run container can be
                # started, so an interrupted pre-checkpoint row is safe to end.
                self.database.update_agent_run(
                    record["run_id"],
                    state="failed",
                    result_summary="Le run OpenHands a été interrompu avant son checkpoint initial.",
                )
                continue
            try:
                checkpoint = self.database.get_project_checkpoint(checkpoint_id)
                if checkpoint["run_id"] != record["run_id"] or checkpoint["project_id"] != record["project_id"]:
                    raise CheckpointError("Le checkpoint de reprise ne correspond pas au run interrompu.")
                mount_path = self.guard.project_lexical_path(str(checkpoint["project_relative_path"]))
                handle = await self.runtime.find_run_agent_server(record["run_id"], mount_path)
                if handle is not None:
                    await self.runtime.stop_agent_server(handle)
            except (OpenHandsRuntimeError, OpenHandsRunError, WorkspacePathError, CheckpointError):
                # Un conteneur non vérifiable reste volontairement non-terminal:
                # le backend ne prétend pas avoir arrêté une mutation inconnue.
                continue
            try:
                frozen = self.guard.freeze_project(
                    str(checkpoint["project_id"]), str(checkpoint["project_relative_path"])
                )
                self.checkpoints.validate_checkpoint_project(checkpoint_id, frozen)
            except (CheckpointConflictError, WorkspacePathError):
                # The deterministic container has already been stopped (or was
                # absent).  It is now safe to make the identity conflict visible.
                self._persist_recovery_project_failure(record, checkpoint_id)
                continue
            try:
                checkpoint = self.database.get_project_checkpoint(checkpoint_id)
                if checkpoint["state"] == "ready":
                    self.checkpoints.complete(checkpoint_id, frozen)
                session_id = self._session_id_from_directory(record["run_id"])
                self.database.update_agent_run(
                    record["run_id"],
                    state="failed",
                    openhands_session_id=session_id,
                    result_summary="Le run OpenHands a été interrompu par le redémarrage du backend.",
                )
            except (OpenHandsRunError, WorkspacePathError, CheckpointError):
                # Container shutdown was verified above, so this terminal state
                # cannot mask a delayed tool mutation even if the final snapshot failed.
                self.database.update_agent_run(
                    record["run_id"],
                    state="failed",
                    result_summary="Le run OpenHands a été interrompu et son checkpoint final a échoué.",
                )

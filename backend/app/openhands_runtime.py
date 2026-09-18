"""Local OpenHands readiness checks used by the Programming profile.

This module deliberately never starts Docker Desktop.  Docker is an explicit
user prerequisite; the orchestrator only verifies the local engine, Qwen and
the minimal Agent Server before it permits an OpenHands run.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Protocol
from uuid import UUID

import httpx

from .model_registry import LoadedModelRegistry


DOCKER_REQUIRED_MESSAGE = (
    "Le profil Programmation nécessite Docker Desktop. Démarre Docker puis réessaie."
)
QWEN_UNAVAILABLE_MESSAGE = "Le modèle local du profil Programmation n’est pas prêt."
AGENT_SERVER_UNAVAILABLE_MESSAGE = "L’Agent Server OpenHands n’est pas prêt."
AGENT_LABEL = "com.projet-lea.openhands.managed"
AGENT_MODE_LABEL = "com.projet-lea.openhands.mode"
AGENT_RUN_LABEL = "com.projet-lea.openhands.run-id"
AGENT_SERVER_MODE_IDLE = "idle"
AGENT_SERVER_MODE_RUN = "run"
AGENT_CONTAINER_WORKSPACE = "/workspace"
AGENT_GIT_OVERLAY_PATH = f"{AGENT_CONTAINER_WORKSPACE}/.git"
AGENT_GIT_OVERLAY_OPTIONS = "rw,noexec,nosuid,size=16m"
AGENT_SERVER_USER = "openhands"
AGENT_SERVER_NETWORK_MODE = "bridge"
AGENT_SERVER_ENTRYPOINT = ["tini", "--", "/usr/local/bin/openhands-agent-server"]
AGENT_SERVER_TOOL_MODULES = (
    "openhands.tools.terminal.definition,"
    "openhands.tools.file_editor.definition,"
    "openhands.tools.task_tracker.definition"
)
# The synchronous SDK hook is bind-mounted outside the project.  This exact
# digest is deliberately source-controlled: a changed policy cannot silently
# start a run until its reviewed constant and tests are updated together.
AGENT_TERMINAL_POLICY_SOURCE = Path("tools/openhands/terminal_policy.py")
AGENT_TERMINAL_POLICY_CONTAINER_PATH = "/opt/lea-terminal-policy.py"
AGENT_TERMINAL_POLICY_COMMAND = f"/usr/local/bin/python3 {AGENT_TERMINAL_POLICY_CONTAINER_PATH}"
AGENT_TERMINAL_POLICY_SHA256 = "b0ebd0c377027fe3cf564ef6f101b9c3800fab9948905dbf82270b71edf277f2"
AGENT_POLICY_WORKSPACE_ENV = "LEA_OPENHANDS_POLICY_WORKSPACE"
AGENT_POLICY_WORKSPACE_PATH = AGENT_CONTAINER_WORKSPACE


class OpenHandsRuntimeError(RuntimeError):
    """Reports a controlled local prerequisite failure without command output."""


class DockerProbe(Protocol):
    """Allows tests to replace the fixed Docker version command safely."""

    async def __call__(self) -> bool:
        """Return whether Docker's local Linux engine is usable for a run."""

        ...


@dataclass(frozen=True)
class DevelopmentReadiness:
    """Contains only public local readiness state; paths and process IDs stay private."""

    docker_available: bool
    agent_server_available: bool
    qwen_available: bool
    profile_ready: bool
    message: str

    def public(self) -> dict[str, bool | str]:
        """Serialize the stable API representation without implementation detail."""

        return asdict(self)


@dataclass(frozen=True)
class AgentServerHandle:
    """Keeps the immutable container identity and frozen project mount for one owner."""

    container_id: str
    name: str
    run_id: str | None
    project_path: Path | None
    mode: str


class OpenHandsRuntime:
    """Checks the fixed loopback OpenHands topology declared by the model registry."""

    def __init__(
        self,
        registry: LoadedModelRegistry,
        *,
        docker_probe: DockerProbe | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Freeze the registry and optional test adapters before any mutable operation."""

        self.registry = registry
        self._docker_probe = docker_probe or self._probe_docker_engine
        self._transport = transport

    @property
    def _agent_config(self):
        """Return the pinned Agent Server settings without exposing them through an API."""

        return self.registry.document.openhands.agent_server

    @property
    def _agent_runtime_config(self):
        """Return the constrained state-volume settings used by the minimal containers."""

        return self.registry.document.openhands.agent_runtime

    @property
    def agent_server_url(self) -> str:
        """Return the sole loopback Agent Server endpoint from the central registry."""

        server = self.registry.document.openhands.agent_server
        return f"http://{server.host}:{server.port}"

    @property
    def model_url(self) -> str:
        """Return the Qwen `/v1/models` endpoint that OpenHands must consume locally."""

        endpoint = self.registry.document.openhands.model_endpoint
        return f"http://{endpoint.host}:{endpoint.port}{endpoint.models_path}"

    async def _probe_docker_engine(self) -> bool:
        """Run one fixed, read-only Docker query and never attempt to launch Docker Desktop."""

        try:
            process = await asyncio.create_subprocess_exec(
                "docker.exe",
                "version",
                "--format",
                "{{.Server.Os}}/{{.Server.Arch}}",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError:
            return False
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return False
        return process.returncode == 0 and stdout.decode("utf-8", errors="replace").strip() == "linux/amd64"

    async def _http_client(self) -> httpx.AsyncClient:
        """Create a short-lived loopback client, optionally backed by a test transport."""

        return httpx.AsyncClient(timeout=2.0, transport=self._transport)

    async def _qwen_available(self) -> bool:
        """Confirm that the endpoint serves the exact Qwen alias declared for Programming."""

        expected_alias = self.registry.profile("development").runtime.alias
        try:
            async with await self._http_client() as client:
                response = await client.get(self.model_url)
                response.raise_for_status()
            entries = response.json().get("data", [])
        except (httpx.HTTPError, TypeError, ValueError):
            return False
        return any(isinstance(item, dict) and item.get("id") == expected_alias for item in entries)

    async def _agent_server_available(self) -> bool:
        """Check health and the three official tool names without deserializing SDK history."""

        required_tools = set(self.registry.document.openhands.agent_server.tool_names)
        try:
            async with await self._http_client() as client:
                health = await client.get(f"{self.agent_server_url}/health")
                health.raise_for_status()
                tools_response = await client.get(f"{self.agent_server_url}/api/tools/")
                tools_response.raise_for_status()
            payload = tools_response.json()
        except (httpx.HTTPError, TypeError, ValueError):
            return False
        raw_tools = payload if isinstance(payload, list) else payload.get("tools", []) if isinstance(payload, dict) else []
        names = {
            item
            if isinstance(item, str)
            else item.get("name")
            if isinstance(item, dict)
            else None
            for item in raw_tools
        }
        return required_tools.issubset({name for name in names if isinstance(name, str)})

    async def status(self) -> DevelopmentReadiness:
        """Assess Docker, Qwen and Agent Server independently for a truthful user message."""

        docker_available = await self._docker_probe()
        if not docker_available:
            return DevelopmentReadiness(False, False, False, False, DOCKER_REQUIRED_MESSAGE)
        qwen_available, agent_server_available = await asyncio.gather(
            self._qwen_available(), self._agent_server_available()
        )
        if not qwen_available:
            return DevelopmentReadiness(True, agent_server_available, False, False, QWEN_UNAVAILABLE_MESSAGE)
        if not agent_server_available:
            return DevelopmentReadiness(True, False, True, False, AGENT_SERVER_UNAVAILABLE_MESSAGE)
        return DevelopmentReadiness(True, True, True, True, "Le profil Programmation est prêt.")

    async def wait_until_ready(self, *, timeout_seconds: float = 30) -> DevelopmentReadiness:
        """Wait through Agent Server startup races and return the last readiness result."""

        deadline = asyncio.get_running_loop().time() + timeout_seconds
        latest = await self.status()
        while not latest.profile_ready and asyncio.get_running_loop().time() < deadline:
            # Health can answer just before the native tools registry settles.
            await asyncio.sleep(0.5)
            latest = await self.status()
        return latest

    async def require_docker(self) -> None:
        """Raise the prescribed message before any attempt to create an Agent Server container."""

        if not await self._docker_probe():
            raise OpenHandsRuntimeError(DOCKER_REQUIRED_MESSAGE)

    async def _docker(self, *arguments: str, timeout_seconds: float = 30) -> str:
        """Run one fixed Docker CLI command without a shell and return its bounded textual output."""

        try:
            process = await asyncio.create_subprocess_exec(
                "docker.exe",
                *arguments,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise OpenHandsRuntimeError(DOCKER_REQUIRED_MESSAGE) from error
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError as error:
            process.kill()
            await process.communicate()
            raise OpenHandsRuntimeError("Docker ne répond pas dans le délai autorisé.") from error
        if process.returncode != 0:
            # La sortie Docker peut contenir chemins, identifiants ou détails
            # système : elle reste dans le journal local et ne va pas au navigateur.
            raise OpenHandsRuntimeError("Docker ne peut pas préparer l’Agent Server local.")
        return stdout.decode("utf-8", errors="replace").strip()

    @staticmethod
    def _container_name(run_id: str | None) -> str:
        """Derive a Docker-safe deterministic name from an immutable run UUID or idle mode."""

        if run_id is None:
            return "lea-openhands-development-idle"
        try:
            canonical = str(UUID(run_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise OpenHandsRuntimeError("Identifiant de run OpenHands invalide.") from error
        return f"lea-openhands-run-{canonical.replace('-', '')}"

    async def _image_available(self) -> None:
        """Require the bootstrap-pinned image locally; stage 10 never pulls an image implicitly."""

        await self._docker("image", "inspect", self._agent_config.image)

    def _terminal_policy_source(self) -> Path:
        """Return only the reviewed native-tool hook when its checked-in digest still matches.

        The Agent Server SDK falls open when a configured command hook is
        missing or crashes.  Refusing to start a run unless this host source
        matches its declared digest, then mounting it read-only, prevents a
        stale or model-modifiable policy from becoming an unobserved allow.
        """

        source = self.registry.project_root / AGENT_TERMINAL_POLICY_SOURCE
        try:
            resolved = source.resolve(strict=True)
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as error:
            raise OpenHandsRuntimeError("La politique OpenHands est introuvable.") from error
        if not resolved.is_file() or digest != AGENT_TERMINAL_POLICY_SHA256:
            raise OpenHandsRuntimeError("La politique OpenHands n'est pas vérifiée.")
        try:
            resolved.relative_to(self.registry.project_root.resolve(strict=True))
        except ValueError as error:
            raise OpenHandsRuntimeError("La politique OpenHands sort du dépôt Léa.") from error
        return resolved

    async def _volume_exists_or_create(self) -> bool:
        """Create only Léa's labelled state volume and report whether tokenizer seeding is needed."""

        volume = self._agent_runtime_config.state_volume
        try:
            raw = await self._docker("volume", "inspect", volume)
        except OpenHandsRuntimeError:
            await self._docker(
                "volume",
                "create",
                "--label",
                f"{AGENT_LABEL}=true",
                "--label",
                f"{AGENT_MODE_LABEL}=state",
                volume,
            )
            return True
        try:
            inspected = json.loads(raw)[0]
            labels = inspected.get("Labels") or {}
        except (IndexError, TypeError, ValueError) as error:
            raise OpenHandsRuntimeError("Le volume OpenHands existant est illisible.") from error
        if labels.get(AGENT_LABEL) != "true" or labels.get(AGENT_MODE_LABEL) != "state":
            raise OpenHandsRuntimeError("Le volume OpenHands existant n’appartient pas à Léa.")
        return False

    async def _seed_tiktoken_cache(self) -> None:
        """Copy the verified local tokenizer into the labelled volume without mounting the repo in Agent Server."""

        runtime = self._agent_runtime_config
        source = self.registry.project_root / runtime.tiktoken_cache_path
        try:
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as error:
            raise OpenHandsRuntimeError("Le cache tiktoken OpenHands est introuvable.") from error
        if digest != runtime.expected_tiktoken_cache_sha256:
            raise OpenHandsRuntimeError("Le cache tiktoken OpenHands ne correspond pas au registre.")
        seed_name = f"lea-openhands-seed-{os.getpid()}"
        seed_id: str | None = None
        try:
            seed_id = await self._docker(
                "container",
                "create",
                "--name",
                seed_name,
                "--label",
                f"{AGENT_LABEL}=true",
                "--label",
                f"{AGENT_MODE_LABEL}=tokenizer-seed",
                "--user",
                "0:0",
                "--mount",
                f"type=volume,src={runtime.state_volume},dst={runtime.state_volume_path}",
                "--entrypoint",
                "/bin/sh",
                self._agent_config.image,
                "-lc",
                f"mkdir -p {runtime.state_volume_path}/tiktoken && sleep 120",
            )
            if re.fullmatch(r"[0-9a-f]{64}", seed_id or "") is None:
                raise OpenHandsRuntimeError("Docker n’a pas retourné une identité de seed vérifiable.")
            await self._docker("container", "start", seed_id)
            destination = f"{seed_id}:{runtime.state_volume_path}/tiktoken/{source.name}"
            await self._docker("container", "cp", str(source), destination)
            verification = await self._docker(
                "container",
                "exec",
                seed_id,
                "sh",
                "-lc",
                f"chown -R openhands:openhands {runtime.state_volume_path} && sha256sum {runtime.state_volume_path}/tiktoken/{source.name}",
            )
            if runtime.expected_tiktoken_cache_sha256 not in verification:
                raise OpenHandsRuntimeError("Le cache tiktoken copié dans le volume est invalide.")
        finally:
            if seed_id is not None and re.fullmatch(r"[0-9a-f]{64}", seed_id):
                # Ce conteneur a été créé avec un label et un ID connus dans
                # cette invocation : sa suppression ne peut viser un tiers.
                try:
                    await self._docker("container", "rm", "-f", seed_id)
                except OpenHandsRuntimeError:
                    pass

    async def _inspect_container(self, name: str) -> dict[str, object] | None:
        """Inspect a named container read-only and treat a missing name as the normal empty state."""

        try:
            raw = await self._docker("container", "inspect", name)
        except OpenHandsRuntimeError:
            return None
        try:
            value = json.loads(raw)[0]
        except (IndexError, TypeError, ValueError) as error:
            raise OpenHandsRuntimeError("Le conteneur OpenHands existant est illisible.") from error
        return value if isinstance(value, dict) else None

    def _verify_container(
        self,
        inspected: dict[str, object],
        handle: AgentServerHandle,
    ) -> bool:
        """Verify labels, image, loopback port, state volume, and the exact frozen project mount."""

        configuration = inspected.get("Config") if isinstance(inspected.get("Config"), dict) else {}
        host = inspected.get("HostConfig") if isinstance(inspected.get("HostConfig"), dict) else {}
        labels = configuration.get("Labels") if isinstance(configuration.get("Labels"), dict) else {}
        server = self._agent_config
        runtime = self._agent_runtime_config
        expected_command = [
            "--host",
            "0.0.0.0",
            "--port",
            str(server.container_port),
            "--import-modules",
            AGENT_SERVER_TOOL_MODULES,
        ]
        port_key = f"{server.container_port}/tcp"
        expected_port_bindings = {
            port_key: [{"HostIp": server.host, "HostPort": str(server.port)}]
        }
        environment = configuration.get("Env") if isinstance(configuration.get("Env"), list) else []
        for expected_environment in self._agent_environment():
            variable_prefix = expected_environment.split("=", 1)[0] + "="
            matching_values = [
                value
                for value in environment
                if isinstance(value, str) and value.startswith(variable_prefix)
            ]
            if matching_values != [expected_environment]:
                return False
        restart_policy = host.get("RestartPolicy")
        if (
            configuration.get("Image") != self._agent_config.image
            or configuration.get("User") != AGENT_SERVER_USER
            or configuration.get("Entrypoint") != AGENT_SERVER_ENTRYPOINT
            or configuration.get("Cmd") != expected_command
            or labels.get(AGENT_LABEL) != "true"
            or labels.get(AGENT_MODE_LABEL) != handle.mode
            or labels.get(AGENT_RUN_LABEL) != (handle.run_id or "")
            # The process directory is the Agent Server's state root.  An old
            # container using /workspace would persist conversations inside a
            # user project, so never reuse it.
            or configuration.get("WorkingDir") != self._agent_runtime_config.state_volume_path
            or bool(host.get("Privileged"))
            or host.get("NetworkMode") != AGENT_SERVER_NETWORK_MODE
            or host.get("PortBindings") != expected_port_bindings
            or not isinstance(restart_policy, dict)
            or restart_policy.get("Name") not in {"", "no"}
            or restart_policy.get("MaximumRetryCount") != 0
            or host.get("Memory") != runtime.memory_mib * 1024 * 1024
            or host.get("MemorySwap") != runtime.memory_mib * 1024 * 1024
            or host.get("NanoCpus") != runtime.cpus * 1_000_000_000
            or host.get("PidsLimit") != runtime.pids_limit
            or host.get("SecurityOpt") != ["no-new-privileges:true"]
            or host.get("PidMode") not in {None, ""}
            or host.get("IpcMode") not in {None, "private"}
            or host.get("CapAdd") not in (None, [])
            or host.get("Devices") not in (None, [])
        ):
            return False
        mounts = inspected.get("Mounts") if isinstance(inspected.get("Mounts"), list) else []
        state_mounts = [mount for mount in mounts if isinstance(mount, dict) and mount.get("Destination") == self._agent_runtime_config.state_volume_path]
        project_mounts = [mount for mount in mounts if isinstance(mount, dict) and mount.get("Destination") == AGENT_CONTAINER_WORKSPACE]
        git_overlays = [mount for mount in mounts if isinstance(mount, dict) and mount.get("Destination") == AGENT_GIT_OVERLAY_PATH]
        if len(state_mounts) != 1 or state_mounts[0].get("Name") != self._agent_runtime_config.state_volume:
            return False
        if handle.project_path is None:
            run_environment_prefixes = (
                "LEA_OPENHANDS_TERMINAL_POLICY_SHA256=",
                f"{AGENT_POLICY_WORKSPACE_ENV}=",
            )
            has_run_environment = any(
                isinstance(value, str) and value.startswith(run_environment_prefixes)
                for value in environment
            )
            return (
                len(project_mounts) == 0
                and len(git_overlays) == 0
                and len(mounts) == 1
                and not has_run_environment
            )
        try:
            policy_source = self._terminal_policy_source()
        except OpenHandsRuntimeError:
            return False
        policy_mounts = [
            mount
            for mount in mounts
            if isinstance(mount, dict)
            and mount.get("Destination") == AGENT_TERMINAL_POLICY_CONTAINER_PATH
        ]
        expected_policy_environment = (
            f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}"
        )
        expected_workspace_environment = (
            f"{AGENT_POLICY_WORKSPACE_ENV}={AGENT_POLICY_WORKSPACE_PATH}"
        )
        policy_environment_values = [
            value
            for value in environment
            if isinstance(value, str)
            and value.startswith("LEA_OPENHANDS_TERMINAL_POLICY_SHA256=")
        ]
        workspace_environment_values = [
            value
            for value in environment
            if isinstance(value, str) and value.startswith(f"{AGENT_POLICY_WORKSPACE_ENV}=")
        ]
        # Agent Server may initialize Git before it emits any agent action.
        # Keep that transient metadata on tmpfs, never in the selected project bind.
        tmpfs = host.get("Tmpfs") if isinstance(host.get("Tmpfs"), dict) else {}
        if tmpfs.get(AGENT_GIT_OVERLAY_PATH) != AGENT_GIT_OVERLAY_OPTIONS:
            return False
        if (
            len(project_mounts) != 1
            or len(policy_mounts) != 1
            or len(mounts) not in {3, 4}
            or project_mounts[0].get("Type") != "bind"
            or policy_mounts[0].get("Type") != "bind"
            or policy_mounts[0].get("RW") is not False
            or not self._bind_mount_matches(policy_mounts[0].get("Source"), policy_source)
            or policy_environment_values != [expected_policy_environment]
            or workspace_environment_values != [expected_workspace_environment]
        ):
            return False
        if any(
            mount.get("Destination")
            not in {
                self._agent_runtime_config.state_volume_path,
                AGENT_CONTAINER_WORKSPACE,
                AGENT_GIT_OVERLAY_PATH,
                AGENT_TERMINAL_POLICY_CONTAINER_PATH,
            }
            for mount in mounts
            if isinstance(mount, dict)
        ):
            return False
        if git_overlays and (
            len(git_overlays) != 1 or git_overlays[0].get("Type") != "tmpfs"
        ):
            return False
        source = project_mounts[0].get("Source")
        return self._project_mount_matches(source, handle.project_path)

    @staticmethod
    def _bind_mount_matches(source: object, expected_path: Path) -> bool:
        """Compare a Docker Desktop bind source to one exact Windows source path.

        Docker Desktop can serialize an L: source either as the native path or
        as its `/run/desktop/mnt/host/l/...` Linux projection.  Accepting only
        these two spellings keeps auxiliary read-only mounts as narrow as the
        user project mount.
        """

        if not isinstance(source, str) or not source:
            return False
        expected = PureWindowsPath(str(expected_path))
        if expected.drive.casefold() == "l:" and expected.is_absolute():
            native = str(expected).rstrip("\\").casefold()
            supplied_native = source.replace("/", "\\").rstrip("\\").casefold()
            if supplied_native == native:
                return True
            parts = [part for part in expected.parts if part not in {expected.drive + "\\", "\\"}]
            translated = "/run/desktop/mnt/host/l/" + "/".join(parts)
            return source.replace("\\", "/").rstrip("/").casefold() == translated.rstrip("/").casefold()
        try:
            return Path(source).resolve() == expected_path.resolve()
        except OSError:
            return False

    @staticmethod
    def _project_mount_matches(source: object, project_path: Path) -> bool:
        """Accept only the exact Windows bind source or Docker Desktop's exact L: translation.

        Docker Desktop can report a Windows bind source as either `L:\\...` or
        `/run/desktop/mnt/host/l/...` in an inspection response.  Both forms
        identify the same frozen directory; accepting arbitrary `/run/...`
        sources would weaken the project boundary.
        """

        # Recovery intentionally preserves this lexical path: resolving it
        # after a directory replacement would hide the identity that the
        # checkpoint captured before the run began.
        return OpenHandsRuntime._bind_mount_matches(source, project_path)

    def _agent_environment(self) -> list[str]:
        """Return the fixed local-only environment shared by idle and run containers."""

        state_path = self._agent_runtime_config.state_volume_path
        return [
            "OH_ENABLE_VNC=0",
            "OH_ENABLE_VSCODE=0",
            "OH_PRELOAD_TOOLS=0",
            "OH_WEBHOOKS=[]",
            "LITELLM_LOCAL_MODEL_COST_MAP=True",
            f"CUSTOM_TIKTOKEN_CACHE_DIR={state_path}/tiktoken",
            "OPENHANDS_SUPPRESS_BANNER=1",
        ]

    async def start_agent_server(
        self,
        *,
        run_id: str | None = None,
        project_path: Path | None = None,
    ) -> AgentServerHandle:
        """Start a no-project idle server or a run server mounted only to its frozen project."""

        await self.require_docker()
        await self._image_available()
        if (run_id is None) != (project_path is None):
            raise OpenHandsRuntimeError("Un projet figé est requis uniquement pour un run OpenHands.")
        mode = AGENT_SERVER_MODE_IDLE if run_id is None else AGENT_SERVER_MODE_RUN
        frozen_project = project_path.resolve() if project_path is not None else None
        terminal_policy_source = (
            self._terminal_policy_source() if frozen_project is not None else None
        )
        handle = AgentServerHandle(
            container_id="",
            name=self._container_name(run_id),
            run_id=run_id,
            project_path=frozen_project,
            mode=mode,
        )
        existing = await self._inspect_container(handle.name)
        if existing is not None:
            existing_id = existing.get("Id")
            if not isinstance(existing_id, str) or not self._verify_container(existing, handle):
                raise OpenHandsRuntimeError("Le conteneur OpenHands existant n’appartient pas à ce run.")
            state = existing.get("State") if isinstance(existing.get("State"), dict) else {}
            if not state.get("Running"):
                await self._docker("container", "start", existing_id)
            return AgentServerHandle(existing_id, handle.name, run_id, frozen_project, mode)
        if await self._volume_exists_or_create():
            await self._seed_tiktoken_cache()
        server = self._agent_config
        runtime = self._agent_runtime_config
        arguments = [
            "container",
            "run",
            "--detach",
            "--name",
            handle.name,
            "--user",
            AGENT_SERVER_USER,
            "--restart",
            "no",
            "--network",
            AGENT_SERVER_NETWORK_MODE,
            "--label",
            f"{AGENT_LABEL}=true",
            "--label",
            f"{AGENT_MODE_LABEL}={mode}",
            "--label",
            f"{AGENT_RUN_LABEL}={run_id or ''}",
            "--publish",
            f"{server.host}:{server.port}:{server.container_port}",
            "--mount",
            f"type=volume,src={runtime.state_volume},dst={runtime.state_volume_path}",
            "--workdir",
            # Agent Server writes its conversation/event state relative to its
            # process directory.  Keep that directory inside its dedicated
            # volume; the project remains a separate bind at /workspace.
            runtime.state_volume_path,
            "--memory",
            f"{runtime.memory_mib}m",
            "--memory-swap",
            f"{runtime.memory_mib}m",
            "--cpus",
            str(runtime.cpus),
            "--pids-limit",
            str(runtime.pids_limit),
            "--security-opt",
            "no-new-privileges:true",
        ]
        for environment_value in self._agent_environment():
            arguments.extend(("--env", environment_value))
        if frozen_project is not None:
            # OpenHands 1.43.1 can create a Git metadata directory while it
            # initializes a workspace.  The nested tmpfs hides that directory
            # from the user bind and is discarded when the run container stops.
            arguments.extend(
                (
                    "--tmpfs",
                    f"{AGENT_GIT_OVERLAY_PATH}:{AGENT_GIT_OVERLAY_OPTIONS}",
                    "--mount",
                    f"type=bind,src={frozen_project},dst={AGENT_CONTAINER_WORKSPACE}",
                    "--mount",
                    f"type=bind,src={terminal_policy_source},dst={AGENT_TERMINAL_POLICY_CONTAINER_PATH},readonly",
                    "--env",
                    f"LEA_OPENHANDS_TERMINAL_POLICY_SHA256={AGENT_TERMINAL_POLICY_SHA256}",
                    "--env",
                    f"{AGENT_POLICY_WORKSPACE_ENV}={AGENT_POLICY_WORKSPACE_PATH}",
                )
            )
        arguments.extend(
            (
                server.image,
                "--host",
                "0.0.0.0",
                "--port",
                str(server.container_port),
                "--import-modules",
                AGENT_SERVER_TOOL_MODULES,
            )
        )
        container_id = await self._docker(*arguments, timeout_seconds=60)
        if re.fullmatch(r"[0-9a-f]{64}", container_id) is None:
            raise OpenHandsRuntimeError("Docker n’a pas retourné une identité Agent Server vérifiable.")
        started = AgentServerHandle(container_id, handle.name, run_id, frozen_project, mode)
        deadline = asyncio.get_running_loop().time() + 120
        while asyncio.get_running_loop().time() < deadline:
            if await self._agent_server_available():
                inspected = await self._inspect_container(started.name)
                if inspected is not None and self._verify_container(inspected, started):
                    return started
            await asyncio.sleep(0.5)
        await self.stop_agent_server(started)
        raise OpenHandsRuntimeError(AGENT_SERVER_UNAVAILABLE_MESSAGE)

    async def stop_agent_server(self, handle: AgentServerHandle) -> None:
        """Stop only the inspected container whose labels and mount still match this immutable handle."""

        inspected = await self._inspect_container(handle.name)
        if inspected is None:
            return
        if inspected.get("Id") != handle.container_id or not self._verify_container(inspected, handle):
            raise OpenHandsRuntimeError("Le conteneur OpenHands à arrêter n’est plus vérifiable.")
        state = inspected.get("State") if isinstance(inspected.get("State"), dict) else {}
        if state.get("Running"):
            await self._docker("container", "stop", "--time", "30", handle.container_id, timeout_seconds=45)

    async def find_run_agent_server(self, run_id: str, project_path: Path) -> AgentServerHandle | None:
        """Recover only the exact labelled run container matching its persisted lexical mount."""

        # Do not resolve here: recovery may run after a project deletion or a
        # same-name replacement.  The handle is used only to verify and stop a
        # labelled container; filesystem access is revalidated separately.
        frozen_project = project_path
        handle = AgentServerHandle(
            container_id="",
            name=self._container_name(run_id),
            run_id=run_id,
            project_path=frozen_project,
            mode=AGENT_SERVER_MODE_RUN,
        )
        inspected = await self._inspect_container(handle.name)
        if inspected is None:
            return None
        container_id = inspected.get("Id")
        if not isinstance(container_id, str) or not self._verify_container(inspected, handle):
            raise OpenHandsRuntimeError("Le conteneur OpenHands existant n'appartient pas à ce run.")
        return AgentServerHandle(container_id, handle.name, run_id, frozen_project, handle.mode)

    async def stop_idle_agent_server(self) -> None:
        """Find and stop only Léa's labelled no-project readiness container, if it still verifies."""

        name = self._container_name(None)
        inspected = await self._inspect_container(name)
        if inspected is None:
            return
        container_id = inspected.get("Id")
        if not isinstance(container_id, str):
            raise OpenHandsRuntimeError("Le conteneur OpenHands idle est illisible.")
        handle = AgentServerHandle(
            container_id=container_id,
            name=name,
            run_id=None,
            project_path=None,
            mode=AGENT_SERVER_MODE_IDLE,
        )
        await self.stop_agent_server(handle)

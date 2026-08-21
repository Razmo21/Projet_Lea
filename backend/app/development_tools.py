"""Commandes de développement locales à liste blanche, sans shell brut."""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .database import Database, ProjectNotFoundError
from .workspace import ValidatedWorkspacePath, WorkspaceGuard, WorkspacePathError


MAX_PROCESS_OUTPUT_BYTES = 65_536
MAX_COMMAND_TIMEOUT_SECONDS = 300
WINDOWS_CREATION_FLAGS = 0x00000200 | 0x00004000 | 0x08000000


class DevelopmentToolError(RuntimeError):
    """Signale un outil absent, interdit, expiré ou impossible à exécuter sûrement."""


if os.name == "nt":
    from ctypes import wintypes

    class _JobBasicLimitInformation(ctypes.Structure):
        """Reproduit la structure Win32 requise pour configurer un Job Object."""

        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]


    class _IoCounters(ctypes.Structure):
        """Reproduit les compteurs Win32 inclus dans la configuration d'un job."""

        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]


    class _JobExtendedLimitInformation(ctypes.Structure):
        """Contient la politique kill-on-close appliquée à tout l'arbre enfant."""

        _fields_ = [
            ("BasicLimitInformation", _JobBasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


class _WindowsJob:
    """Possède un Job Object Win32 qui termine tous ses descendants à la fermeture."""

    _KILL_ON_JOB_CLOSE = 0x00002000
    _EXTENDED_LIMIT_INFORMATION = 9
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self) -> None:
        """Crée un job non héritable; toute impossibilité fait échouer l'exécution sûre."""

        if os.name != "nt":
            raise DevelopmentToolError("Les Job Objects ne sont disponibles que sous Windows.")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise DevelopmentToolError(f"Impossible de créer le Job Object ({ctypes.get_last_error()}).")
        limits = _JobExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = self._KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            self._handle,
            self._EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not configured:
            error_code = ctypes.get_last_error()
            self.close()
            raise DevelopmentToolError(f"Impossible de sécuriser le Job Object ({error_code}).")

    def assign(self, pid: int) -> None:
        """Rattache le PID créé par Léa au job sans adopter de processus découvert ailleurs."""

        rights = self._PROCESS_TERMINATE | self._PROCESS_SET_QUOTA | self._PROCESS_QUERY_LIMITED_INFORMATION
        process_handle = self._kernel32.OpenProcess(rights, False, pid)
        if not process_handle:
            raise DevelopmentToolError(f"Impossible d'ouvrir le processus enfant ({ctypes.get_last_error()}).")
        try:
            if not self._kernel32.AssignProcessToJobObject(self._handle, process_handle):
                raise DevelopmentToolError(
                    f"Impossible de contrôler l'arbre du processus enfant ({ctypes.get_last_error()})."
                )
        finally:
            self._kernel32.CloseHandle(process_handle)

    def terminate(self) -> None:
        """Termine atomiquement les processus encore membres de ce job."""

        if self._handle and not self._kernel32.TerminateJobObject(self._handle, 1):
            raise DevelopmentToolError(f"Impossible d'arrêter l'arbre contrôlé ({ctypes.get_last_error()}).")

    def close(self) -> None:
        """Ferme l'autorité sur le job; kill-on-close élimine tout descendant résiduel."""

        if getattr(self, "_handle", None):
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


class StrictDevelopmentArguments(BaseModel):
    """Refuse les champs inconnus et conversions implicites des appels modèle."""

    model_config = ConfigDict(extra="forbid", strict=True)


class NoArguments(StrictDevelopmentArguments):
    """Arguments vides d'une inspection dont la cible est toujours le projet actif."""


class CommandSelectionArguments(StrictDevelopmentArguments):
    """Sélectionne un identifiant abstrait déjà retourné par la détection."""

    command_id: str | None = Field(default=None, max_length=100)
    timeout_seconds: int = Field(default=120, ge=1, le=MAX_COMMAND_TIMEOUT_SECONDS)


class NamedScriptArguments(StrictDevelopmentArguments):
    """Sélectionne exactement un script réellement déclaré dans package.json."""

    script_name: str = Field(min_length=1, max_length=100)
    timeout_seconds: int = Field(default=120, ge=1, le=MAX_COMMAND_TIMEOUT_SECONDS)


class GitDiffArguments(StrictDevelopmentArguments):
    """Borne git diff à une variante staged et un chemin relatif facultatif."""

    staged: bool = False
    path: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=120)


class GitLogArguments(StrictDevelopmentArguments):
    """Limite explicitement le nombre de commits Git en lecture seule."""

    limit: int = Field(default=10, ge=1, le=20)


class StartDevServerArguments(StrictDevelopmentArguments):
    """Démarre uniquement un script npm déclaré, sans arguments supplémentaires."""

    script_name: str | None = Field(default=None, max_length=100)


class StopDevServerArguments(StrictDevelopmentArguments):
    """Arrête uniquement un serveur identifié et créé par cet exécuteur."""

    server_id: str


DEVELOPMENT_ARGUMENT_MODELS: dict[str, type[StrictDevelopmentArguments]] = {
    "detect_project": NoArguments,
    "list_project_commands": NoArguments,
    "build_project": CommandSelectionArguments,
    "run_tests": CommandSelectionArguments,
    "run_linter": CommandSelectionArguments,
    "run_typecheck": CommandSelectionArguments,
    "run_named_script": NamedScriptArguments,
    "git_status": NoArguments,
    "git_diff": GitDiffArguments,
    "git_diff_check": GitDiffArguments,
    "git_log": GitLogArguments,
    "start_dev_server": StartDevServerArguments,
    "stop_dev_server": StopDevServerArguments,
}


@dataclass(frozen=True)
class CommandSpec:
    """Associe un identifiant public sûr à un argv immuable et une catégorie."""

    command_id: str
    category: str
    label: str
    argv: tuple[str, ...]


@dataclass
class RunningProcess:
    """Conserve l'objet enfant créé afin de ne jamais adopter un PID externe."""

    execution_id: str
    run_id: str
    process: asyncio.subprocess.Process
    process_tree: _WindowsJob | None
    command_id: str
    started_at: float


@dataclass
class RunningServer:
    """Conserve les handles et journaux d'un serveur créé par start_dev_server."""

    server_id: str
    run_id: str
    process: asyncio.subprocess.Process
    process_tree: _WindowsJob | None
    command_id: str
    stdout_handle: Any
    stderr_handle: Any
    started_at: float


def _safe_which(name: str) -> str | None:
    """Résout un exécutable installé sans accepter de valeur fournie par le modèle."""

    resolved = shutil.which(name)
    if resolved is None:
        return None
    path = Path(resolved).resolve(strict=True)
    return str(path) if path.is_file() else None


def _find_msbuild() -> str | None:
    """Demande à vswhere un MSBuild installé sans recherche réseau ni chemin libre."""

    candidates = (
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio/Installer/vswhere.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Visual Studio/Installer/vswhere.exe",
    )
    vswhere = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
    if vswhere is None:
        return None
    try:
        result = subprocess.run(
            (
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.Component.MSBuild",
                "-find",
                r"MSBuild\**\Bin\MSBuild.exe",
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=5,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for raw_line in result.stdout.decode("utf-8", errors="replace").splitlines()[:20]:
        candidate = Path(raw_line.strip())
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_file() and resolved.name.casefold() == "msbuild.exe":
            return str(resolved)
    return None


class DevelopmentToolExecutor:
    """Détecte puis exécute seulement des commandes de haut niveau prédéfinies."""

    def __init__(
        self,
        database: Database,
        guard: WorkspaceGuard,
        runtime_root: Path,
    ) -> None:
        """Lie les commandes à l'unique projet actif et à un runtime Git-ignoré."""

        self.database = database
        self.guard = guard
        self.runtime_root = runtime_root
        self._running: dict[str, RunningProcess] = {}
        self._servers: dict[str, RunningServer] = {}
        self._lock = asyncio.Lock()

    def schemas(self) -> list[dict[str, Any]]:
        """Expose les schémas JSON des seules commandes autorisées au modèle."""

        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": model.__doc__.strip() if model.__doc__ else name,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, model in DEVELOPMENT_ARGUMENT_MODELS.items()
        ]

    def _active_project(self) -> ValidatedWorkspacePath:
        """Revalide le projet SQLite avant toute détection ou exécution."""

        project = self.database.get_active_project()
        if project is None:
            raise ProjectNotFoundError("Sélectionne un projet actif avant d'utiliser un outil.")
        return self.guard.resolve_project(project["relative_path"])

    def _read_package_scripts(self, project: ValidatedWorkspacePath) -> dict[str, str]:
        """Lit les scripts npm comme données et refuse un manifeste énorme ou invalide."""

        package_path = project.path / "package.json"
        if not package_path.is_file() or package_path.stat().st_size > 262_144:
            return {}
        try:
            document = json.loads(package_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        scripts = document.get("scripts") if isinstance(document, dict) else None
        if not isinstance(scripts, dict):
            return {}
        return {
            name: command
            for name, command in scripts.items()
            if isinstance(name, str)
            and isinstance(command, str)
            and name
            and len(name) <= 100
            and command
        }

    def _command_catalog(self, project: ValidatedWorkspacePath) -> dict[str, CommandSpec]:
        """Construit une liste déterministe depuis manifests présents et outils installés."""

        catalog: dict[str, CommandSpec] = {}
        npm = _safe_which("npm.cmd")
        scripts = self._read_package_scripts(project)
        if npm and scripts:
            for script_name in sorted(scripts, key=lambda value: (value.casefold(), value)):
                command_id = f"npm:{script_name}"
                category = "named_script"
                if script_name == "build":
                    category = "build"
                elif script_name in {"test", "tests"}:
                    category = "test"
                elif script_name in {"lint", "linter"}:
                    category = "lint"
                elif script_name in {"typecheck", "type-check", "check-types"}:
                    category = "typecheck"
                catalog[command_id] = CommandSpec(
                    command_id,
                    category,
                    f"npm run {script_name}",
                    (npm, "run", script_name),
                )

        has_python_project = any(
            (project.path / name).is_file()
            for name in ("pyproject.toml", "setup.py", "requirements.txt")
        )
        if has_python_project:
            pytest = _safe_which("pytest.exe") or _safe_which("pytest")
            if pytest:
                catalog["python:pytest"] = CommandSpec(
                    "python:pytest", "test", "Python pytest", (pytest,)
                )
            ruff = _safe_which("ruff.exe") or _safe_which("ruff")
            if ruff:
                catalog["python:ruff"] = CommandSpec(
                    "python:ruff", "lint", "Python ruff", (ruff, "check", ".")
                )
            mypy = _safe_which("mypy.exe") or _safe_which("mypy")
            if mypy:
                catalog["python:mypy"] = CommandSpec(
                    "python:mypy", "typecheck", "Python mypy", (mypy, ".")
                )
            try:
                import build as _python_build  # type: ignore[import-not-found]  # noqa: F401
            except ImportError:
                pass
            else:
                catalog["python:build"] = CommandSpec(
                    "python:build", "build", "Python build", (str(Path(sys.executable).resolve()), "-m", "build")
                )

        dotnet = _safe_which("dotnet")
        if dotnet and (any(project.path.glob("*.sln")) or any(project.path.glob("*.csproj"))):
            catalog["dotnet:build"] = CommandSpec(
                "dotnet:build", "build", ".NET build", (dotnet, "build", "--no-restore")
            )
            catalog["dotnet:test"] = CommandSpec(
                "dotnet:test", "test", ".NET test", (dotnet, "test", "--no-restore")
            )

        msbuild = _find_msbuild()
        msbuild_targets = sorted(
            (*project.path.glob("*.sln"), *project.path.glob("*.vcxproj"), *project.path.glob("*.csproj")),
            key=lambda value: (value.name.casefold(), value.name),
        )
        if msbuild and msbuild_targets:
            target = msbuild_targets[0].name
            catalog["msbuild:build"] = CommandSpec(
                "msbuild:build",
                "build",
                f"MSBuild {target}",
                (msbuild, target, "/m:1", "/restore:false"),
            )

        cmake = _safe_which("cmake")
        if cmake and (project.path / "CMakeLists.txt").is_file() and (project.path / "build").is_dir():
            catalog["cmake:build"] = CommandSpec(
                "cmake:build", "build", "CMake build existant", (cmake, "--build", "build")
            )

        gradle_wrapper = project.path / "gradlew.bat"
        if gradle_wrapper.is_file():
            catalog["gradle:build"] = CommandSpec(
                "gradle:build", "build", "Gradle wrapper offline", (str(gradle_wrapper), "--offline", "build")
            )
            catalog["gradle:test"] = CommandSpec(
                "gradle:test", "test", "Gradle wrapper tests offline", (str(gradle_wrapper), "--offline", "test")
            )

        maven_wrapper = project.path / "mvnw.cmd"
        if maven_wrapper.is_file():
            catalog["maven:build"] = CommandSpec(
                "maven:build", "build", "Maven wrapper offline", (str(maven_wrapper), "-o", "package", "-DskipTests")
            )
            catalog["maven:test"] = CommandSpec(
                "maven:test", "test", "Maven wrapper tests offline", (str(maven_wrapper), "-o", "test")
            )

        git = _safe_which("git.exe") or _safe_which("git")
        if git and (project.path / ".git").exists():
            catalog["git:status"] = CommandSpec(
                "git:status", "git_status", "Git status", (git, "status", "--short", "--branch")
            )
            catalog["git:diff"] = CommandSpec(
                "git:diff", "git_diff", "Git diff", (git, "diff", "--no-ext-diff")
            )
            catalog["git:diff-check"] = CommandSpec(
                "git:diff-check", "git_diff_check", "Git diff --check", (git, "diff", "--check", "--no-ext-diff")
            )
            catalog["git:log"] = CommandSpec(
                "git:log", "git_log", "Git log borné", (git, "log", "--oneline", "--decorate=no")
            )
        return catalog

    def _detection(self, project: ValidatedWorkspacePath) -> dict[str, Any]:
        """Rapporte les écosystèmes présents et outils manquants sans téléchargement."""

        scripts = self._read_package_scripts(project)
        ecosystems = {
            "node": {
                "detected": (project.path / "package.json").is_file(),
                "tool_available": _safe_which("npm.cmd") is not None,
                "scripts": sorted(scripts),
            },
            "python": {
                "detected": any((project.path / name).is_file() for name in ("pyproject.toml", "setup.py", "requirements.txt")),
                "tool_available": Path(sys.executable).is_file(),
                "pytest_available": (_safe_which("pytest.exe") or _safe_which("pytest")) is not None,
            },
            "dotnet": {
                "detected": bool(list(project.path.glob("*.sln")) or list(project.path.glob("*.csproj"))),
                "tool_available": _safe_which("dotnet") is not None,
            },
            "msbuild": {
                "detected": bool(list(project.path.glob("*.sln")) or list(project.path.glob("*.vcxproj"))),
                "vswhere_available": any(
                    path.is_file()
                    for path in (
                        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio/Installer/vswhere.exe",
                        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Visual Studio/Installer/vswhere.exe",
                    )
                ),
                "tool_available": _find_msbuild() is not None,
            },
            "cmake": {
                "detected": (project.path / "CMakeLists.txt").is_file(),
                "tool_available": _safe_which("cmake") is not None,
            },
            "gradle_wrapper": {
                "detected": (project.path / "gradlew.bat").is_file(),
                "offline_only": True,
            },
            "maven_wrapper": {
                "detected": (project.path / "mvnw.cmd").is_file(),
                "offline_only": True,
            },
        }
        return {"ecosystems": ecosystems}

    def _environment(self, run_id: str) -> dict[str, str]:
        """Construit un environnement minimal et redirige caches/TEMP vers data ignoré."""

        runtime = self.runtime_root / run_id
        runtime.mkdir(parents=True, exist_ok=True)
        cache = runtime / "cache"
        temporary = runtime / "tmp"
        home = runtime / "home"
        appdata = runtime / "appdata"
        local_appdata = runtime / "local-appdata"
        cache.mkdir(exist_ok=True)
        temporary.mkdir(exist_ok=True)
        home.mkdir(exist_ok=True)
        appdata.mkdir(exist_ok=True)
        local_appdata.mkdir(exist_ok=True)
        source = os.environ
        environment = {
            key: source[key]
            for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC")
            if key in source
        }
        environment.update(
            {
                "CI": "true",
                "NO_UPDATE_NOTIFIER": "1",
                "TEMP": str(temporary),
                "TMP": str(temporary),
                # Node/npm interroge le dossier personnel même en mode hors ligne.
                # Ces valeurs isolées évitent à la fois l'échec uv_os_homedir et
                # toute lecture de la configuration npm personnelle.
                "HOME": str(home),
                "USERPROFILE": str(home),
                "APPDATA": str(appdata),
                "LOCALAPPDATA": str(local_appdata),
                "NPM_CONFIG_CACHE": str(cache / "npm"),
                "NPM_CONFIG_AUDIT": "false",
                "NPM_CONFIG_FUND": "false",
                "NPM_CONFIG_OFFLINE": "true",
                "PIP_CACHE_DIR": str(cache / "pip"),
                "PIP_NO_INDEX": "1",
                # Les gestionnaires de paquets utilisent leurs modes hors ligne;
                # les proxys invalides ferment en plus les accès réseau coopératifs.
                "HTTP_PROXY": "http://127.0.0.1:9",
                "HTTPS_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9",
                "NO_PROXY": "",
                "DOTNET_CLI_HOME": str(cache / "dotnet"),
                "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                "GRADLE_USER_HOME": str(cache / "gradle"),
            }
        )
        return environment

    async def _drain(self, stream: asyncio.StreamReader | None) -> tuple[str, bool]:
        """Draine toujours le pipe tout en ne conservant qu'une sortie UTF-8 bornée."""

        if stream is None:
            return "", False
        kept = bytearray()
        truncated = False
        while True:
            chunk = await stream.read(8192)
            if not chunk:
                break
            remaining = MAX_PROCESS_OUTPUT_BYTES - len(kept)
            if remaining > 0:
                kept.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        return kept.decode("utf-8", errors="replace"), truncated

    async def _terminate_tree(
        self,
        process: asyncio.subprocess.Process,
        process_tree: _WindowsJob | None,
    ) -> None:
        """Termine l'arbre du seul PID enfant conservé, jamais un propriétaire de port."""

        if os.name == "nt":
            if process_tree is None:
                raise DevelopmentToolError("L'arbre Windows n'a pas d'autorité Job Object.")
            try:
                if process.returncode is None:
                    process_tree.terminate()
            finally:
                # La fermeture est une seconde barrière kill-on-close, notamment
                # si le lanceur npm est déjà sorti mais qu'un descendant subsiste.
                process_tree.close()
            await process.wait()
            return
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()

    async def _run(
        self,
        project: ValidatedWorkspacePath,
        spec: CommandSpec,
        timeout_seconds: int,
        run_id: str,
    ) -> dict[str, Any]:
        """Exécute un argv fixe avec cwd forcé, délai, sortie bornée et annulation."""

        self.guard.revalidate_project(project)
        execution_id = str(uuid.uuid4())
        started = time.monotonic()
        process_tree = _WindowsJob() if os.name == "nt" else None
        try:
            process = await asyncio.create_subprocess_exec(
                *spec.argv,
                cwd=str(project.path),
                env=self._environment(run_id),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                creationflags=WINDOWS_CREATION_FLAGS if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
            if process_tree is not None:
                process_tree.assign(process.pid)
        except BaseException:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            if process_tree is not None:
                process_tree.close()
            raise
        record = RunningProcess(execution_id, run_id, process, process_tree, spec.command_id, started)
        async with self._lock:
            self._running[execution_id] = record
        stdout_task = asyncio.create_task(self._drain(process.stdout))
        stderr_task = asyncio.create_task(self._drain(process.stderr))
        timed_out = False
        cancelled = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            await self._terminate_tree(process, process_tree)
        except asyncio.CancelledError:
            cancelled = True
            await self._terminate_tree(process, process_tree)
            raise
        finally:
            if process_tree is not None:
                # Un enfant détaché ne doit pas prolonger la lecture des pipes
                # après la fin normale du lanceur.
                process_tree.close()
            stdout, stdout_truncated = await stdout_task
            stderr, stderr_truncated = await stderr_task
            async with self._lock:
                self._running.pop(execution_id, None)
        return {
            "execution_id": execution_id,
            "command_id": spec.command_id,
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timed_out": timed_out,
            "cancelled": cancelled,
            "duration_seconds": round(time.monotonic() - started, 3),
        }

    @staticmethod
    def _select_command(
        catalog: dict[str, CommandSpec],
        category: str,
        command_id: str | None,
    ) -> CommandSpec:
        """Choisit un identifiant connu de la bonne catégorie ou refuse l'ambiguïté."""

        available = [spec for spec in catalog.values() if spec.category == category]
        if command_id is not None:
            selected = catalog.get(command_id)
            if selected is None or selected.category != category:
                raise DevelopmentToolError("La commande sélectionnée n'est pas autorisée pour cet outil.")
            return selected
        if not available:
            raise DevelopmentToolError("Aucune commande installée n'est disponible pour cet outil.")
        return sorted(available, key=lambda item: item.command_id)[0]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Valide un appel puis distribue vers une branche fixe, sans eval ni shell."""

        model = DEVELOPMENT_ARGUMENT_MODELS.get(name)
        if model is None:
            raise DevelopmentToolError("Outil de développement inconnu.")
        parsed = model.model_validate(arguments)
        effective_run_id = str(uuid.UUID(run_id)) if run_id is not None else str(uuid.uuid4())
        project = self._active_project()
        catalog = self._command_catalog(project)
        if name == "detect_project":
            return self._detection(project)
        if name == "list_project_commands":
            return {
                "commands": [
                    {"id": spec.command_id, "category": spec.category, "label": spec.label}
                    for spec in sorted(catalog.values(), key=lambda item: item.command_id)
                ]
            }
        if name in {"build_project", "run_tests", "run_linter", "run_typecheck"}:
            category = {
                "build_project": "build",
                "run_tests": "test",
                "run_linter": "lint",
                "run_typecheck": "typecheck",
            }[name]
            selected = self._select_command(catalog, category, parsed.command_id)
            return await self._run(project, selected, parsed.timeout_seconds, effective_run_id)
        if name == "run_named_script":
            scripts = self._read_package_scripts(project)
            if parsed.script_name not in scripts:
                raise DevelopmentToolError("Le script npm demandé n'est pas déclaré.")
            selected = catalog.get(f"npm:{parsed.script_name}")
            if selected is None:
                raise DevelopmentToolError("npm n'est pas disponible localement.")
            return await self._run(project, selected, parsed.timeout_seconds, effective_run_id)
        if name == "git_status":
            return await self._run(
                project,
                self._select_command(catalog, "git_status", "git:status"),
                60,
                effective_run_id,
            )
        if name in {"git_diff", "git_diff_check"}:
            category = "git_diff" if name == "git_diff" else "git_diff_check"
            selected = self._select_command(catalog, category, f"git:{'diff' if name == 'git_diff' else 'diff-check'}")
            argv = list(selected.argv)
            if parsed.staged:
                argv.append("--cached")
            if parsed.path is not None:
                member = self.guard.resolve_member(project, parsed.path)
                argv.extend(("--", member.relative_path))
            selected = CommandSpec(selected.command_id, selected.category, selected.label, tuple(argv))
            return await self._run(project, selected, parsed.timeout_seconds, effective_run_id)
        if name == "git_log":
            selected = self._select_command(catalog, "git_log", "git:log")
            selected = CommandSpec(
                selected.command_id,
                selected.category,
                selected.label,
                (*selected.argv, f"-{parsed.limit}"),
            )
            return await self._run(project, selected, 60, effective_run_id)
        if name == "start_dev_server":
            return await self._start_server(project, catalog, parsed, effective_run_id)
        if name == "stop_dev_server":
            return await self._stop_server(parsed.server_id)
        raise DevelopmentToolError("Outil de développement non distribué.")

    async def _start_server(
        self,
        project: ValidatedWorkspacePath,
        catalog: dict[str, CommandSpec],
        arguments: StartDevServerArguments,
        run_id: str,
    ) -> dict[str, Any]:
        """Lance un script dev déclaré avec fichiers de logs et identité conservée."""

        self.guard.revalidate_project(project)
        scripts = self._read_package_scripts(project)
        script_name = arguments.script_name
        if script_name is None:
            script_name = next((name for name in ("dev", "start", "serve") if name in scripts), None)
        if script_name is None or script_name not in scripts:
            raise DevelopmentToolError("Aucun script de serveur déclaré n'est disponible.")
        spec = catalog.get(f"npm:{script_name}")
        if spec is None:
            raise DevelopmentToolError("npm n'est pas disponible localement.")
        server_id = str(uuid.uuid4())
        directory = self.runtime_root / run_id / "servers"
        directory.mkdir(parents=True, exist_ok=True)
        stdout_handle = (directory / f"{server_id}.stdout.log").open("wb")
        stderr_handle = (directory / f"{server_id}.stderr.log").open("wb")
        try:
            process_tree = _WindowsJob() if os.name == "nt" else None
            process = await asyncio.create_subprocess_exec(
                *spec.argv,
                cwd=str(project.path),
                env=self._environment(run_id),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                creationflags=WINDOWS_CREATION_FLAGS if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
            if process_tree is not None:
                process_tree.assign(process.pid)
        except BaseException:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            if "process_tree" in locals() and process_tree is not None:
                process_tree.close()
            stdout_handle.close()
            stderr_handle.close()
            raise
        record = RunningServer(
            server_id,
            run_id,
            process,
            process_tree,
            spec.command_id,
            stdout_handle,
            stderr_handle,
            time.monotonic(),
        )
        async with self._lock:
            self._servers[server_id] = record
        await asyncio.sleep(0.25)
        if process.returncode is not None:
            await self._finish_server(record)
            raise DevelopmentToolError("Le serveur de développement s'est arrêté au démarrage.")
        return {"server_id": server_id, "command_id": spec.command_id, "state": "running"}

    async def _finish_server(self, record: RunningServer) -> None:
        """Ferme les journaux et retire une seule identité serveur enregistrée."""

        record.stdout_handle.close()
        record.stderr_handle.close()
        if record.process_tree is not None:
            record.process_tree.close()
        async with self._lock:
            self._servers.pop(record.server_id, None)

    async def _stop_server(self, server_id: str) -> dict[str, Any]:
        """Arrête l'arbre d'un serveur connu après validation de son UUID interne."""

        try:
            canonical_id = str(uuid.UUID(server_id))
        except (ValueError, TypeError, AttributeError) as error:
            raise DevelopmentToolError("Identifiant de serveur invalide.") from error
        async with self._lock:
            record = self._servers.get(canonical_id)
        if record is None:
            raise DevelopmentToolError("Ce serveur n'a pas été lancé par Léa.")
        await self._terminate_tree(record.process, record.process_tree)
        exit_code = record.process.returncode
        await self._finish_server(record)
        return {"server_id": canonical_id, "state": "stopped", "exit_code": exit_code}

    async def cancel_run(self, run_id: str) -> int:
        """Annule tous les processus encore vivants appartenant au run indiqué."""

        canonical_run_id = str(uuid.UUID(run_id))
        async with self._lock:
            processes = [record for record in self._running.values() if record.run_id == canonical_run_id]
            servers = [record for record in self._servers.values() if record.run_id == canonical_run_id]
        for record in processes:
            await self._terminate_tree(record.process, record.process_tree)
        for server in servers:
            await self._terminate_tree(server.process, server.process_tree)
            await self._finish_server(server)
        return len(processes) + len(servers)

    async def close(self) -> None:
        """Nettoie les seuls serveurs encore possédés lors de l'arrêt FastAPI."""

        async with self._lock:
            servers = list(self._servers.values())
        for server in servers:
            await self._terminate_tree(server.process, server.process_tree)
            await self._finish_server(server)

#!/usr/bin/env python3
"""Own the local model process used by Léa's Programming profile.

The controller handles only the model process on its configured local port. It
does not start Docker Desktop, does not mount a project, and never adopts an
unknown listener.  The FastAPI/OpenHands layer owns Agent Server containers.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = PROJECT_ROOT / ".lea" / "development-runtime.json"
LOG_DIRECTORY = PROJECT_ROOT / ".lea"
SYSTEM32_DIRECTORY = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
NETSTAT_EXECUTABLE = SYSTEM32_DIRECTORY / "netstat.exe"
TASKKILL_EXECUTABLE = SYSTEM32_DIRECTORY / "taskkill.exe"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.model_registry import RegistryError, load_model_registry  # noqa: E402
from app.inference import inference_adapter, llama_cpp_arguments  # noqa: E402


class RuntimeErrorPublic(RuntimeError):
    """Signals a safe runtime failure whose detailed log remains local."""


class FileTime(ctypes.Structure):
    """Matches the Windows FILETIME layout used by GetProcessTimes."""

    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


def parse_arguments() -> argparse.Namespace:
    """Accept only the three fixed lifecycle actions and an optional registry path."""

    parser = argparse.ArgumentParser(description="Manage Léa's local OpenHands model runtime.")
    parser.add_argument("action", choices=("start", "stop", "status"))
    parser.add_argument("--registry", type=Path, default=PROJECT_ROOT / "config" / "models.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_runtime_configuration(
    registry_path: Path,
    *,
    verify_model: bool,
) -> dict[str, Any]:
    """Load the exact profile and hash its large artifacts only before a new launch."""

    try:
        registry = load_model_registry(registry_path, project_root=PROJECT_ROOT)
        return inference_adapter(registry, "development").launch_configuration(
            verify_model=verify_model
        )
    except RegistryError as error:
        raise RuntimeErrorPublic(str(error)) from error


def process_identity(pid: int) -> dict[str, str | int] | None:
    """Read executable and creation time through Windows APIs for safe later ownership checks."""

    if os.name != "nt" or pid <= 0:
        return None
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.c_ulong(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
            return None
        creation = FileTime()
        ignored = FileTime()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(ignored),
            ctypes.byref(ignored),
            ctypes.byref(ignored),
        ):
            return None
        created = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return {"pid": pid, "executable": str(Path(buffer.value).resolve()), "created_filetime": created}
    finally:
        kernel32.CloseHandle(handle)


def listener_pids(port: int) -> set[int]:
    """Return TCP listeners for one local port without assigning them ownership."""

    completed = subprocess.run(
        [str(NETSTAT_EXECUTABLE), "-ano", "-p", "tcp"],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.IGNORECASE)
    return {int(match.group(1)) for line in completed.stdout.splitlines() if (match := pattern.match(line))}


def state_is_owned(state: object, configuration: dict[str, Any]) -> bool:
    """Confirm the exact saved process identity and dedicated loopback listener before stopping it."""

    if not isinstance(state, dict):
        return False
    try:
        recorded = state["process"]
        identity = process_identity(int(recorded["pid"]))
        return bool(
            identity
            and identity["executable"].casefold() == str(configuration["executable"]).casefold()
            and identity["created_filetime"] == int(recorded["created_filetime"])
            and int(recorded["pid"]) in listener_pids(int(configuration["port"]))
        )
    except (KeyError, TypeError, ValueError):
        return False


def state_is_conclusively_stale(state: object, configuration: dict[str, Any]) -> bool:
    """Prove a recorded runtime has gone before its state can be cleared safely.

    A changed template or a reboot can leave a ready record behind after its
    owned process has already exited.  The record is stale only when its PID
    no longer exists *and* no process listens on the dedicated model port.
    Any surviving process remains ambiguous and is never adopted or stopped.
    """

    if not isinstance(state, dict):
        return False
    try:
        recorded = state["process"]
        if not isinstance(recorded, dict):
            return False
        pid = int(recorded["pid"])
        if pid <= 0:
            return False
        return process_identity(pid) is None and not listener_pids(int(configuration["port"]))
    except (KeyError, TypeError, ValueError):
        return False


def mark_state_stopped(state: dict[str, Any]) -> None:
    """Atomically preserve a conclusively stopped record for the next safe launch."""

    state["phase"] = "stopped"
    write_state(state)


def read_state() -> dict[str, Any] | None:
    """Read only the dedicated ignored state file and reject malformed ownership metadata."""

    if not STATE_PATH.is_file():
        return None
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeErrorPublic("L’état du runtime Programmation est illisible ; aucun processus ne sera adopté.") from error
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RuntimeErrorPublic("L’état du runtime Programmation est inconnu ; aucun processus ne sera adopté.")
    return value


def write_state(state: dict[str, Any]) -> None:
    """Publish state atomically so an interruption cannot leave an adopted partial JSON file."""

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_name(f"{STATE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, STATE_PATH)


def model_ready(configuration: dict[str, Any]) -> bool:
    """Check the local models endpoint for the single configured model alias."""

    url = f"http://{configuration['host']}:{configuration['port']}{configuration['models_path']}"
    try:
        with urlopen(url, timeout=3) as response:  # nosec B310: fixed loopback endpoint from validated registry.
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError):
        return False
    return any(
        isinstance(item, dict) and item.get("id") == configuration["alias"]
        for item in payload.get("data", [])
    )


def runtime_arguments(configuration: dict[str, Any]) -> list[str]:
    """Translate only registry runtime fields into the fixed llama.cpp invocation."""

    return llama_cpp_arguments(configuration)


def start(configuration: dict[str, Any]) -> dict[str, Any]:
    """Start one owned model process only after the port and any prior state are safe."""

    existing = read_state()
    if existing is not None:
        if state_is_owned(existing, configuration) and model_ready(configuration):
            return {"state": "ready", "profile_id": "development", "reused": True}
        if state_is_conclusively_stale(existing, configuration):
            mark_state_stopped(existing)
        elif existing.get("phase") not in {"stopped", "failed"}:
            raise RuntimeErrorPublic("Le runtime Programmation existant est ambigu ; aucun processus ne sera remplacé.")
    owners = listener_pids(int(configuration["port"]))
    if owners:
        raise RuntimeErrorPublic("Le port du modèle Programmation est occupé par un processus non géré.")
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    stdout = (LOG_DIRECTORY / f"development-llama-{stamp}.stdout.log").open("wb")
    stderr = (LOG_DIRECTORY / f"development-llama-{stamp}.stderr.log").open("wb")
    try:
        process = subprocess.Popen(
            [str(configuration["executable"]), *runtime_arguments(configuration)],
            cwd=str(configuration["root"]),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        stdout.close()
        stderr.close()
    identity = process_identity(process.pid)
    if identity is None:
        process.terminate()
        process.wait(timeout=10)
        raise RuntimeErrorPublic("Le runtime Programmation lancé ne possède pas d’identité vérifiable.")
    state = {"schema_version": 1, "phase": "starting", "process": identity, "profile_id": "development"}
    write_state(state)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if model_ready(configuration):
            state["phase"] = "ready"
            write_state(state)
            return {"state": "ready", "profile_id": "development", "reused": False}
        if process.poll() is not None:
            state["phase"] = "failed"
            write_state(state)
            raise RuntimeErrorPublic("Le modèle Programmation s’est arrêté avant sa readiness.")
        time.sleep(0.5)
    if state_is_owned(state, configuration):
        subprocess.run(
            [str(TASKKILL_EXECUTABLE), "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    state["phase"] = "failed"
    write_state(state)
    raise RuntimeErrorPublic("Le modèle Programmation n’est pas prêt avant le délai autorisé.")


def stop(configuration: dict[str, Any]) -> dict[str, Any]:
    """Stop only the exact process recorded by this helper and wait for port release."""

    state = read_state()
    if state is None or state.get("phase") == "stopped":
        return {"state": "stopped", "profile_id": None}
    if state_is_conclusively_stale(state, configuration):
        mark_state_stopped(state)
        return {"state": "stopped", "profile_id": None}
    if not state_is_owned(state, configuration):
        raise RuntimeErrorPublic("Le runtime Programmation n’est pas vérifiable ; aucun processus ne sera arrêté.")
    pid = int(state["process"]["pid"])
    subprocess.run(
        [str(TASKKILL_EXECUTABLE), "/PID", str(pid), "/T", "/F"],
        check=False,
        capture_output=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not listener_pids(int(configuration["port"])):
            state["phase"] = "stopped"
            write_state(state)
            return {"state": "stopped", "profile_id": None}
        time.sleep(0.25)
    raise RuntimeErrorPublic("Le port du modèle Programmation reste occupé ; aucun autre processus ne sera arrêté.")


def status(configuration: dict[str, Any]) -> dict[str, Any]:
    """Report readiness only when the persisted identity and model endpoint both agree."""

    state = read_state()
    if state is not None and state_is_owned(state, configuration) and model_ready(configuration):
        return {"state": "ready", "profile_id": "development"}
    return {"state": "stopped", "profile_id": None}


def main() -> int:
    """Dispatch one lifecycle action and keep all public failures short and non-sensitive."""

    arguments = parse_arguments()
    try:
        configuration = load_runtime_configuration(
            arguments.registry,
            verify_model=arguments.action == "start",
        )
        result = {"start": start, "stop": stop, "status": status}[arguments.action](configuration)
    except RuntimeErrorPublic as error:
        result = {"state": "error", "message": str(error)}
        if arguments.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Erreur : {result['message']}", file=sys.stderr)
        return 1
    if arguments.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["state"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

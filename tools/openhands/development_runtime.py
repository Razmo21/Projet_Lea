#!/usr/bin/env python3
"""Own the local Qwen process used by Léa's Programming profile.

The controller deliberately handles only the model process on port 8081.  It
does not start Docker Desktop, does not mount a project, and never adopts an
unknown listener.  The FastAPI/OpenHands layer owns Agent Server containers.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
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
# The registry chooses the active value; the helper accepts only the four
# user-approved Stage 10 candidates and never silently launches another size.
SUPPORTED_DEVELOPMENT_CONTEXT_TOKENS = {16_000, 18_000, 20_000, 22_000}


class RuntimeErrorPublic(RuntimeError):
    """Signals a safe runtime failure whose detailed log remains local."""


class FileTime(ctypes.Structure):
    """Matches the Windows FILETIME layout used by GetProcessTimes."""

    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


def parse_arguments() -> argparse.Namespace:
    """Accept only the three fixed lifecycle actions and an optional registry path."""

    parser = argparse.ArgumentParser(description="Manage Léa's local OpenHands Qwen runtime.")
    parser.add_argument("action", choices=("start", "stop", "status"))
    parser.add_argument("--registry", type=Path, default=PROJECT_ROOT / "config" / "models.json")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def canonical_path(path: Path) -> Path:
    """Resolve an existing local path and reject a value outside the project root."""

    return path.resolve(strict=True)


def relative_file(root: Path, value: object, allowed_root: Path, label: str) -> Path:
    """Resolve a registry-relative file without accepting a drive, UNC path, or traversal."""

    if not isinstance(value, str) or not value or "\x00" in value:
        raise RuntimeErrorPublic(f"{label} est invalide.")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise RuntimeErrorPublic(f"{label} doit rester relatif au projet.")
    resolved = canonical_path(root / candidate)
    try:
        resolved.relative_to(allowed_root)
    except ValueError as error:
        raise RuntimeErrorPublic(f"{label} sort de sa racine autorisée.") from error
    if not resolved.is_file():
        raise RuntimeErrorPublic(f"{label} est introuvable.")
    return resolved


def sha256_file(path: Path) -> str:
    """Hash a large local file by chunks so activation does not duplicate the GGUF in RAM."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_runtime_configuration(
    registry_path: Path,
    *,
    verify_model: bool,
) -> dict[str, Any]:
    """Load the exact profile and hash its large artifacts only before a new launch."""

    root = canonical_path(PROJECT_ROOT)
    registry = canonical_path(registry_path)
    try:
        registry.relative_to(root)
        document = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise RuntimeErrorPublic("Le registre du profil Programmation est invalide.") from error
    profiles = [profile for profile in document.get("profiles", []) if profile.get("id") == "development"]
    if len(profiles) != 1:
        raise RuntimeErrorPublic("Le profil Programmation est absent ou ambigu.")
    profile = profiles[0]
    openhands = document.get("openhands")
    context_tokens = profile.get("context_tokens")
    if (
        profile.get("agent_engine") != "OpenHands"
        or profile.get("model_name") != "Qwen2.5-Coder-7B-Instruct Q6_K"
        or not isinstance(context_tokens, int)
        or isinstance(context_tokens, bool)
        or context_tokens not in SUPPORTED_DEVELOPMENT_CONTEXT_TOKENS
        or not isinstance(openhands, dict)
        or not isinstance(openhands.get("model_endpoint"), dict)
    ):
        raise RuntimeErrorPublic("Le registre ne décrit pas une fenêtre OpenHands Qwen2.5 Stage 10 autorisée.")
    runtime = profile.get("runtime")
    endpoint = openhands["model_endpoint"]
    if not isinstance(runtime, dict) or endpoint.get("host") != "127.0.0.1":
        raise RuntimeErrorPublic("Le runtime Programmation doit rester local.")
    model_path = relative_file(root, profile.get("model_path"), root / "models", "Le modèle")
    executable = relative_file(
        root,
        document.get("runtime", {}).get("executable"),
        root / "runtime" / "llama.cpp",
        "llama-server",
    )
    # The pinned template is the runtime contract for llama.cpp's native
    # OpenAI parser.  Load and hash it before a Programming server can start.
    template = relative_file(
        root,
        openhands.get("chat_template_path"),
        root / "tools" / "openhands" / "templates",
        "Le template OpenHands",
    )
    if model_path.stat().st_size != profile.get("expected_size_bytes"):
        raise RuntimeErrorPublic("Le modèle Programmation ne correspond pas au registre.")
    if verify_model and (
        sha256_file(model_path) != profile.get("expected_sha256")
        or sha256_file(template) != openhands.get("expected_chat_template_sha256")
    ):
        raise RuntimeErrorPublic("Le modèle ou le template Programmation ne correspond pas au registre.")
    if runtime.get("parallel_slots") != 1 or runtime.get("fit_context_min_tokens") != context_tokens:
        raise RuntimeErrorPublic("Le runtime Programmation ne respecte pas le contexte ou le slot validé.")
    return {
        "root": root,
        "executable": executable,
        "model_path": model_path,
        "template": template,
        "host": endpoint["host"],
        "port": int(endpoint["port"]),
        "models_path": endpoint["models_path"],
        "alias": runtime["alias"],
        "context": int(profile["context_tokens"]),
        "runtime": runtime,
    }


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
    """Check the local models endpoint for the single configured Qwen alias."""

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

    runtime = configuration["runtime"]
    arguments = [
        "-m",
        str(configuration["model_path"]),
        "--host",
        str(configuration["host"]),
        "--port",
        str(configuration["port"]),
        "--alias",
        str(configuration["alias"]),
        "--ctx-size",
        str(configuration["context"]),
        "--parallel",
        str(runtime["parallel_slots"]),
        "--cache-type-k",
        str(runtime["cache_type_k"]),
        "--cache-type-v",
        str(runtime["cache_type_v"]),
        "--cache-ram",
        "1" if runtime["cache_ram"] else "0",
        "--gpu-layers",
        str(runtime["gpu_layers"]),
        "--fit",
        "on" if runtime["fit"] else "off",
        "--fit-target",
        str(runtime["fit_target_mib"]),
        "--fit-ctx",
        str(runtime["fit_context_min_tokens"]),
        "--prio",
        str(runtime["priority"]),
        "--threads",
        str(runtime["threads"]),
        "--batch-size",
        str(runtime["batch_size"]),
        "--ubatch-size",
        str(runtime["ubatch_size"]),
    ]
    if runtime["mmap"]:
        arguments.append("--mmap")
    if runtime["jinja"]:
        # llama.cpp accepts an arbitrary custom Jinja file only after Jinja has
        # been enabled; preserving this order keeps native tool parsing active.
        arguments.append("--jinja")
    arguments.extend(("--chat-template-file", str(configuration["template"])))
    if not runtime["skip_chat_parsing"]:
        arguments.append("--no-skip-chat-parsing")
    return arguments


def start(configuration: dict[str, Any]) -> dict[str, Any]:
    """Start one owned Qwen process only after the port and any prior state are safe."""

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
    """Report readiness only when the persisted identity and Qwen endpoint both agree."""

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

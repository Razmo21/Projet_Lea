#!/usr/local/bin/python3
"""Guard native OpenHands terminal and file-editor actions.

OpenHands SDK 1.43.1 executes this synchronous ``PreToolUse`` hook inside the
Agent Server container. The verified, read-only hook confines editor targets
to ``/workspace`` and rejects direct shell escapes, network clients, package
installation, mutable Git, test-file writes, and ineffective replacements. It
never edits project files or supplies a model-specific recovery command.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath
from typing import Any


_EXPECTED_DIGEST_ENV = "LEA_OPENHANDS_TERMINAL_POLICY_SHA256"
_WORKSPACE_ENV = "LEA_OPENHANDS_POLICY_WORKSPACE"
_MAX_EVENT_BYTES = 65_536
_SHELL_OPERATOR_TOKENS = frozenset({";", "&", "&&", "|", "||", "<", ">", "(", ")"})
_SHELL_EXPANSION_RE = re.compile(r"[$`]")
_SHELL_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
_URL_RE = re.compile(r"(?:https?|ssh|git)://|git@", re.IGNORECASE)
_NETWORK_EXECUTABLES = frozenset(
    {
        "aria2c",
        "curl",
        "ftp",
        "getent",
        "lftp",
        "nc",
        "ncat",
        "nslookup",
        "ping",
        "rsync",
        "scp",
        "sftp",
        "ssh",
        "telnet",
        "wget",
    }
)
_PACKAGE_EXECUTABLES = frozenset({"conda", "pip", "pip3", "poetry", "uv"})
_PACKAGE_MANAGERS = frozenset({"bun", "npm", "pnpm", "yarn"})
_PACKAGE_MUTATING_SUBCOMMANDS = frozenset(
    {"add", "ci", "create", "dlx", "exec", "install", "publish", "update", "upgrade"}
)
_SHELL_WRAPPERS = frozenset(
    {
        ".",
        "bash",
        "busybox",
        "chroot",
        "command",
        "dash",
        "env",
        "eval",
        "exec",
        "nice",
        "nohup",
        "setsid",
        "sh",
        "source",
        "stdbuf",
        "sudo",
        "time",
        "timeout",
        "xargs",
        "zsh",
    }
)
_INLINE_RUNTIME_FLAGS = frozenset({"-c", "--command", "--eval", "-e"})
_NATIVE_TOOL_NAMES = frozenset({"file_editor", "terminal"})
_IMMUTABLE_TEST_DIRECTORIES = frozenset({"test", "tests", "__tests__"})
_IMMUTABLE_TEST_FILE_RE = re.compile(
    r"^(?:test_.+|.+_test)\.[A-Za-z0-9]+$|\.(?:test|spec)\.[A-Za-z0-9]+$",
    re.IGNORECASE,
)
_SOURCE_SUFFIXES = frozenset({".py", ".js", ".jsx", ".ts", ".tsx"})
_IMMUTABLE_TEST_POLICY_REASON = (
    "Les tests sont immuables pendant un run Léa. Lis le test, puis crée "
    "ou corrige uniquement le module source attendu ; ne modifie jamais "
    "l'import ni l'attente du test."
)


def _reply(decision: str, reason: str | None = None) -> int:
    """Write one documented hook verdict and return its matching process status."""

    payload: dict[str, str] = {"decision": decision}
    if reason is not None:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
    return 0 if decision == "allow" else 2


def _policy_file_matches_declared_digest() -> bool:
    """Fail closed when the runtime mount differs from the verified source file."""

    expected = os.environ.get(_EXPECTED_DIGEST_ENV, "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        return False
    try:
        actual = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return False
    return hmac.compare_digest(actual, expected)


def _terminal_command_from_event(payload: object) -> str | None:
    """Extract one bounded native TerminalAction command."""

    if not isinstance(payload, dict):
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    normalized = command.strip()
    if not normalized or "\x00" in normalized or len(normalized.encode("utf-8")) > 16_384:
        return None
    return normalized


def _file_editor_workspace_reason(payload: object) -> str | None:
    """Reject every editor target that does not resolve below the mounted project."""

    if not isinstance(payload, dict):
        return "L'action file_editor native est invalide."
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "L'action file_editor native est invalide."
    path = tool_input.get("path")
    if (
        not isinstance(path, str)
        or not path.strip()
        or "\x00" in path
        or len(path.encode("utf-8")) > 4_096
    ):
        return "Le chemin file_editor est invalide."
    workspace_text = os.environ.get(_WORKSPACE_ENV, "/workspace")
    try:
        workspace = Path(workspace_text).resolve(strict=True)
        declared = Path(path)
        candidate = workspace / declared if not declared.is_absolute() else declared
        candidate.resolve(strict=False).relative_to(workspace)
    except (OSError, UnicodeError, ValueError):
        return "file_editor doit rester strictement dans /workspace."
    return None


def _file_editor_immutable_test_reason(payload: object) -> str | None:
    """Allow test inspection while denying native mutations of test files."""

    if not isinstance(payload, dict):
        return "L'action file_editor native est invalide."
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "L'action file_editor native est invalide."
    if tool_input.get("command") in {"view", "read"}:
        return None
    path = tool_input.get("path")
    if not isinstance(path, str):
        return None
    workspace_text = os.environ.get(_WORKSPACE_ENV, "/workspace")
    try:
        workspace = Path(workspace_text).resolve(strict=True)
        declared = Path(path)
        candidate = workspace / declared if not declared.is_absolute() else declared
        relative = candidate.resolve(strict=False).relative_to(workspace)
    except (OSError, UnicodeError, ValueError):
        # The workspace guard above owns malformed and escaping targets.
        return None
    parts = tuple(part.casefold() for part in relative.parts)
    is_test_target = any(
        part in _IMMUTABLE_TEST_DIRECTORIES for part in parts[:-1]
    ) or bool(parts and _IMMUTABLE_TEST_FILE_RE.search(parts[-1]))
    if is_test_target:
        return _IMMUTABLE_TEST_POLICY_REASON
    return None


def _file_editor_replacement_reason(payload: object) -> str | None:
    """Reject malformed or byte-identical native text replacements."""

    if not isinstance(payload, dict):
        return "L'action file_editor native est invalide."
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return "L'action file_editor native est invalide."
    if tool_input.get("command") != "str_replace":
        return None
    old_str = tool_input.get("old_str")
    new_str = tool_input.get("new_str")
    if not isinstance(old_str, str) or not isinstance(new_str, str):
        return "Le remplacement file_editor est incomplet."
    if "\x00" in old_str or "\x00" in new_str:
        return "Le remplacement file_editor est invalide."
    if old_str == new_str:
        return "old_str et new_str doivent être différents."
    return None


def _simple_sed_substitution(script: str) -> tuple[str, str] | None:
    """Return before/after text for one compact sed substitution."""

    if len(script) < 4 or script[0] != "s":
        return None
    delimiter = script[1]
    chunks: list[str] = []
    current: list[str] = []
    escaped = False
    for character in script[2:]:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            current.append(character)
            escaped = True
        elif character == delimiter:
            chunks.append("".join(current))
            current = []
            if len(chunks) == 2:
                return chunks[0], chunks[1]
        else:
            current.append(character)
    return None


def _terminal_edit_reason(command: str) -> str | None:
    """Keep source edits in file_editor and reject objectively null sed edits."""

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return "La commande terminal est invalide."
    if tokens[:3] == ["cd", "/workspace", "&&"]:
        tokens = tokens[3:]
    if len(tokens) < 4 or PurePosixPath(tokens[0]).name.casefold() != "sed" or "-i" not in tokens:
        return None
    script = next((token for token in tokens[1:] if token.startswith("s")), None)
    substitution = _simple_sed_substitution(script) if script is not None else None
    if substitution is not None and substitution[0] == substitution[1]:
        return "Une commande terminal d'édition doit modifier réellement le source."
    if any(PurePosixPath(token).suffix.casefold() == ".py" for token in tokens):
        return (
            "Les éditions terminal du source Python sont interdites ; utilise "
            "file_editor view puis str_replace."
        )
    return None


def _path_escape_reason(tokens: list[str]) -> str | None:
    """Reject lexical paths outside /workspace, including option values."""

    for token in tokens:
        candidates = [token]
        if "=" in token:
            candidates.append(token.split("=", 1)[1])
        for candidate in candidates:
            if not candidate or candidate.startswith("-"):
                continue
            if candidate == "~" or candidate.startswith("~/"):
                return "La commande terminal doit rester strictement dans /workspace."
            if _WINDOWS_ABSOLUTE_RE.match(candidate):
                return "La commande terminal doit rester strictement dans /workspace."
            if ".." in PurePosixPath(candidate).parts:
                return "La commande terminal doit rester strictement dans /workspace."
            if candidate.startswith("/") and candidate != "/dev/null" and not (
                candidate == "/workspace" or candidate.startswith("/workspace/")
            ):
                return "La commande terminal doit rester strictement dans /workspace."
    return None


def _prohibited_reason(command: str) -> str | None:
    """Classify direct shell escapes, transport, package, Git, and path violations."""

    if "\r" in command or "\n" in command:
        return "Une seule commande terminal locale est autorisée par appel."
    if _SHELL_EXPANSION_RE.search(command):
        return "Les expansions shell sont interdites pendant ce run isolé."
    if _URL_RE.search(command):
        return "Les accès réseau directs sont interdits pendant ce run isolé."
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "La commande terminal est invalide."
    if not tokens:
        return "La commande terminal est invalide."

    command_tokens = tokens
    if len(tokens) >= 4 and tokens[0] == "cd" and tokens[2] == "&&":
        if tokens[1] != "/workspace" and not tokens[1].startswith("/workspace/"):
            return "La commande terminal doit rester strictement dans /workspace."
        command_tokens = tokens[3:]
    if not command_tokens or any(token in _SHELL_OPERATOR_TOKENS for token in command_tokens):
        return "Une seule commande terminal locale est autorisée par appel."
    if any(_SHELL_ASSIGNMENT_RE.match(token) for token in command_tokens):
        return "Les affectations shell sont interdites pendant ce run isolé."
    if reason := _path_escape_reason(tokens):
        return reason

    executable = PurePosixPath(command_tokens[0]).name.casefold()
    if executable in _NATIVE_TOOL_NAMES:
        return (
            "Les outils OpenHands ne sont pas des commandes shell ; appelle "
            "directement l'outil natif."
        )
    if executable in _SHELL_WRAPPERS:
        return "Les interpréteurs et enveloppes shell sont interdits pendant ce run isolé."
    if executable in _NETWORK_EXECUTABLES:
        return "Les accès réseau directs sont interdits pendant ce run isolé."
    if executable == "git":
        allowed = command_tokens[1:] and command_tokens[1] == "status" and all(
            token in {"--short", "--porcelain", "--porcelain=v1", "--untracked-files=no"}
            for token in command_tokens[2:]
        )
        if not allowed:
            return "Les commandes Git mutantes sont interdites pendant ce run isolé."
    if executable in _PACKAGE_EXECUTABLES:
        return "Les installations ou gestionnaires de paquets sont interdits pendant ce run isolé."
    if executable in _PACKAGE_MANAGERS:
        subcommand = command_tokens[1].casefold() if len(command_tokens) > 1 else ""
        if subcommand in _PACKAGE_MUTATING_SUBCOMMANDS:
            return "Les installations ou gestionnaires de paquets sont interdits pendant ce run isolé."
    if executable == "npx" and not (
        len(command_tokens) >= 3
        and command_tokens[1] == "--no-install"
        and command_tokens[2].casefold() in {"eslint", "jest", "tsc", "vitest"}
    ):
        return "npx doit utiliser un outil local validé avec --no-install."
    if executable in {"python", "python3", "node"}:
        if any(token in _INLINE_RUNTIME_FLAGS for token in command_tokens[1:]):
            return "Les évaluations runtime en ligne sont interdites pendant ce run isolé."
        if "-m" in command_tokens:
            module_index = command_tokens.index("-m") + 1
            if module_index < len(command_tokens) and command_tokens[module_index].casefold() in {
                "ensurepip",
                "http.server",
                "pip",
                "venv",
            }:
                return "Ce module runtime est interdit pendant ce run isolé."
    if executable == "find" and any(
        token in {"-delete", "-exec", "-execdir"} for token in command_tokens[1:]
    ):
        return "Cette forme mutante de find est interdite pendant ce run isolé."
    if executable == "ln":
        return "La création de liens est interdite pendant ce run isolé."
    if executable == "touch" and any(
        PurePosixPath(token).suffix.casefold() in _SOURCE_SUFFIXES
        for token in command_tokens[1:]
    ):
        return (
            "La création d'un fichier source vide par terminal est interdite ; "
            "utilise file_editor create avec son contenu réel."
        )
    return None


def main() -> int:
    """Return a fail-closed decision for one pending terminal or editor action."""

    try:
        if not _policy_file_matches_declared_digest():
            return _reply("deny", "La politique terminal vérifiée est indisponible.")
        raw_event = sys.stdin.buffer.read(_MAX_EVENT_BYTES + 1)
        if len(raw_event) > _MAX_EVENT_BYTES:
            return _reply("deny", "L'action OpenHands est trop volumineuse.")
        payload: Any = json.loads(raw_event.decode("utf-8"))
        if not isinstance(payload, dict):
            return _reply("deny", "L'action OpenHands native est invalide.")
        tool_name = payload.get("tool_name")
        if tool_name == "terminal":
            command = _terminal_command_from_event(payload)
            if command is None:
                return _reply("deny", "L'action terminal native est invalide.")
            reason = _prohibited_reason(command) or _terminal_edit_reason(command)
            return _reply("deny", reason) if reason is not None else _reply("allow")
        if tool_name == "file_editor":
            reason = (
                _file_editor_workspace_reason(payload)
                or _file_editor_immutable_test_reason(payload)
                or _file_editor_replacement_reason(payload)
            )
            return _reply("deny", reason) if reason is not None else _reply("allow")
        return _reply("deny", "L'outil OpenHands natif est invalide pour cette politique.")
    except (UnicodeDecodeError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return _reply("deny", "La politique terminal ne peut pas vérifier cette action.")


if __name__ == "__main__":
    raise SystemExit(main())

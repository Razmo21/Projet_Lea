"""Fail-closed evidence gates for native OpenHands SDK conversations.

The Agent Server owns execution. This module never parses model prose into
actions, recreates tools, or repairs model decisions. It verifies structured,
paginated REST history and exposes generic loop signals to the local runner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable


PROJECT_ACTION_TOOL_NAMES = frozenset({"terminal", "file_editor"})
_VALIDATION_TASK_RE = re.compile(
    r"\b(?:test\w*|unittest|pytest|build|compil\w*|lint\w*|"
    r"valid\w*|v[ée]rif\w*|verify\w*)\b",
    re.IGNORECASE,
)
_VALIDATION_COMMAND_RE = re.compile(
    r"^\s*(?:cd\s+/workspace(?:/[A-Za-z0-9_.-]+)*\s+&&\s*)?(?:"
    r"(?:(?:[A-Za-z0-9_./-]+/)?python(?:3(?:\.\d+)?)?\s+-m\s+(?:unittest|pytest)\b[^\r\n;&|<>]*)|"
    r"(?:pytest\b[^\r\n;&|<>]*)|"
    r"(?:npm\s+(?:run\s+)?(?:test|build|lint)\b[^\r\n;&|<>]*)|"
    r"(?:npx\s+--no-install\s+(?:vitest|jest|tsc|eslint)\b[^\r\n;&|<>]*)|"
    r"(?:tsc\b[^\r\n;&|<>]*)|"
    r"(?:cargo\s+(?:test|build|check)\b[^\r\n;&|<>]*)|"
    r"(?:go\s+test\b[^\r\n;&|<>]*)|"
    r"(?:dotnet\s+(?:test|build)\b[^\r\n;&|<>]*)|"
    r"(?:(?:mvn|gradle|\./gradlew)\s+(?:test|build|check)\b[^\r\n;&|<>]*)|"
    r"(?:make\s+(?:test|build|check|lint)\b[^\r\n;&|<>]*)|"
    r"(?:(?:ruff\s+check|eslint)\b[^\r\n;&|<>]*)"
    r")\s*$",
    re.IGNORECASE,
)
_FUTURE_ACTION_RE = re.compile(
    r"\b(?:je\s+vais|j['’]irai|je\s+dois\s+encore|"
    r"i(?:\s+am|'m)\s+going\s+to|i\s+will|i\s+need\s+to)\b"
    r".{0,220}\b(?:corrig\w*|fix\w*|relanc\w*|rerun\w*|"
    r"test\w*|build\w*|valid\w*|v[ée]rif\w*|retry\w*|read\w*|lire\w*)\b",
    re.IGNORECASE | re.DOTALL,
)
_RAW_TOOL_TAG_RE = re.compile(
    r"<\s*(?:tool_call|function_call)\b|<\s*function\s*=", re.IGNORECASE
)
_RAW_TOOL_METADATA_RE = re.compile(
    r'"(?:function_name|tool_name|tool_calls)"\s*:', re.IGNORECASE
)
_RAW_NAMED_ARGUMENTS_RE = re.compile(
    r'"name"\s*:\s*"[^"\\]+"(?:(?![{}]).){0,512}"arguments"\s*:',
    re.IGNORECASE | re.DOTALL,
)
_FILE_EDITOR_READ_COMMANDS = frozenset({"view", "read"})
_TERMINAL_EXPLICIT_NON_MUTATING_RE = re.compile(
    r"^\s*(?:cd\s+/workspace(?:/[A-Za-z0-9_.-]+)*\s+&&\s*)?(?:"
    r"(?:python(?:3(?:\.\d+)?)?\s+-m\s+(?:unittest|pytest)\b[^\r\n;&|<>]*)|"
    r"(?:pytest\b[^\r\n;&|<>]*)|"
    r"(?:npm\s+(?:run\s+)?test\b[^\r\n;&|<>]*)|"
    r"(?:npx\s+--no-install\s+(?:vitest|jest)\b[^\r\n;&|<>]*)|"
    r"(?:ls|dir|pwd|where|which|type|cat|rg|grep|find|stat)\b[^\r\n;&|<>]*|"
    r"(?:git\s+(?:status|diff|log|rev-parse)\b[^\r\n;&|<>]*)|"
    r"(?:echo)\b[^\r\n;&|<>]*"
    r")\s*$",
    re.IGNORECASE,
)
_IMMUTABLE_TEST_POLICY_REASON = (
    "Les tests sont immuables pendant un run Léa. Lis le test, puis crée "
    "ou corrige uniquement le module source attendu ; ne modifie jamais "
    "l'import ni l'attente du test."
)
_STRICT_EVENT_KINDS = frozenset(
    {"ActionEvent", "ObservationEvent", "AgentErrorEvent", "HookExecutionEvent"}
)
_PUBLIC_FAILURES = {
    "history_unavailable": (
        "OpenHands a terminé techniquement, mais ses preuves de session sont "
        "incomplètes. La tâche n'est pas présentée comme réussie."
    ),
    "missing_project_action": (
        "OpenHands a terminé techniquement, mais aucune action terminal ou "
        "file_editor réussie n'a été observée. La tâche n'est pas présentée comme réussie."
    ),
    "missing_terminal_finish": (
        "OpenHands a terminé techniquement sans FinishTool final vérifiable. "
        "La tâche n'est pas présentée comme réussie."
    ),
    "unsafe_final_summary": (
        "OpenHands a terminé techniquement avec une réponse finale interne ou "
        "non exploitable. La tâche n'est pas présentée comme réussie."
    ),
    "future_action_in_final_summary": (
        "OpenHands a terminé techniquement alors que sa réponse finale annonçait "
        "encore une action à faire. La tâche n'est pas validée."
    ),
    "unretried_file_editor_error": (
        "OpenHands a terminé techniquement après une erreur file_editor sans "
        "relecture et nouvelle tentative vérifiables. La tâche n'est pas validée."
    ),
    "missing_post_mutation_validation": (
        "OpenHands a terminé techniquement, mais aucune validation demandée avec "
        "code de sortie 0 n'a été observée après la dernière modification. "
        "La tâche n'est pas validée."
    ),
    "repetitive_file_editor_cycle": (
        "OpenHands a été arrêté après une boucle de remplacements file_editor "
        "répétés sans nouvelle validation. La tâche n'est pas validée."
    ),
    "noop_file_editor_replacement": (
        "OpenHands a tenté un remplacement source sans changement réel. "
        "La tâche n'est pas validée."
    ),
    "prohibited_terminal_action": (
        "OpenHands a tenté une commande terminal interdite, qui a été bloquée "
        "avant exécution. La tâche n'est pas validée."
    ),
}


@dataclass(frozen=True)
class _OrderedEvent:
    """Preserve one unique server event in authoritative chronological order."""

    sequence: int
    event_id: str
    timestamp: datetime
    payload: dict[str, Any]


@dataclass(frozen=True)
class _ActionRecord:
    """Store exact identifiers needed to pair one native tool observation."""

    sequence: int
    event_id: str
    tool_call_id: str
    tool_name: str
    action: dict[str, Any]

    @property
    def path(self) -> str | None:
        """Return the path carried by a file-editor action, if any."""

        return _text(self.action.get("path"))

    @property
    def file_editor_command(self) -> str | None:
        """Return the normalized structured editor command."""

        command = _text(self.action.get("command"))
        return command.casefold() if command is not None else None

    @property
    def file_editor_mutates(self) -> bool:
        """Classify every successful non-read editor action as a mutation."""

        return (
            self.tool_name == "file_editor"
            and self.file_editor_command not in _FILE_EDITOR_READ_COMMANDS
        )

    @property
    def terminal_validation(self) -> bool:
        """Recognize a bounded validation command from structured action data."""

        command = _text(self.action.get("command")) or _text(self.action.get("cmd"))
        return self.tool_name == "terminal" and bool(
            command and _VALIDATION_COMMAND_RE.fullmatch(command)
        )

    @property
    def terminal_may_mutate(self) -> bool:
        """Fail closed for terminal commands outside known read-only forms."""

        command = _text(self.action.get("command")) or _text(self.action.get("cmd"))
        return self.tool_name == "terminal" and bool(
            command
            and not _VALIDATION_COMMAND_RE.fullmatch(command)
            and not _TERMINAL_EXPLICIT_NON_MUTATING_RE.fullmatch(command)
        )


@dataclass(frozen=True)
class _EditorRetry:
    """Track the required re-read and retry after a failed editor mutation."""

    path: str | None
    failed_at: int
    reread_at: int | None = None


@dataclass(frozen=True)
class AgentRunEvidence:
    """Describe whether a finished SDK conversation proved its public outcome."""

    tool_names: tuple[str, ...]
    final_summary: str | None
    failure_code: str | None
    validation_required: bool
    validation_observed: bool

    @property
    def validated(self) -> bool:
        """Return success only for a verified final conclusion."""

        return self.failure_code is None and self.final_summary is not None


def task_requires_validation(task: str) -> bool:
    """Recognize an explicit test, build, compile, lint, or validation request."""

    return bool(_VALIDATION_TASK_RE.search(task))


def public_failure_summary(code: object) -> str:
    """Convert an internal evidence code into a compact browser-safe message."""

    if isinstance(code, str):
        return _PUBLIC_FAILURES.get(code, "Le run OpenHands n'a pas abouti.")
    return "Le run OpenHands n'a pas abouti."


def _text(value: object) -> str | None:
    """Normalize a bounded non-empty protocol string."""

    if not isinstance(value, str):
        return None
    normalized = value.replace("\x00", "").strip()
    return normalized if normalized else None


def _mapping(value: object) -> dict[str, Any] | None:
    """Accept only JSON-object protocol fields."""

    return value if isinstance(value, dict) else None


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO server timestamp in UTC."""

    text = _text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _ordered_history(events: Iterable[dict[str, Any]]) -> list[_OrderedEvent] | None:
    """Deduplicate history and reject malformed security-relevant events."""

    by_id: dict[str, _OrderedEvent] = {}
    for sequence, payload in enumerate(events):
        if not isinstance(payload, dict):
            continue
        event_id = _text(payload.get("id"))
        timestamp = _parse_timestamp(payload.get("timestamp"))
        kind = _text(payload.get("kind"))
        if kind in _STRICT_EVENT_KINDS and (event_id is None or timestamp is None):
            return None
        if event_id is None or timestamp is None:
            continue
        record = _OrderedEvent(sequence, event_id, timestamp, payload)
        existing = by_id.get(event_id)
        if existing is not None and existing.payload != payload:
            return None
        by_id.setdefault(event_id, record)
    chronological = sorted(
        by_id.values(), key=lambda item: (item.timestamp, item.sequence, item.event_id)
    )
    return [
        _OrderedEvent(index, item.event_id, item.timestamp, item.payload)
        for index, item in enumerate(chronological)
    ]


def _current_turn(events: list[_OrderedEvent]) -> list[_OrderedEvent]:
    """Return events following the latest structured user message."""

    latest_user = max(
        (
            event.sequence
            for event in events
            if _text(event.payload.get("kind")) == "MessageEvent"
            and _text(event.payload.get("source")) == "user"
        ),
        default=-1,
    )
    return [event for event in events if event.sequence > latest_user]


def _action_record(event: _OrderedEvent) -> _ActionRecord | None:
    """Require every action identifier before accepting an observation."""

    payload = event.payload
    tool_name = _text(payload.get("tool_name"))
    tool_call_id = _text(payload.get("tool_call_id"))
    action = _mapping(payload.get("action"))
    if tool_name is None or tool_call_id is None or action is None:
        return None
    return _ActionRecord(
        event.sequence,
        event.event_id,
        tool_call_id,
        tool_name.casefold(),
        action,
    )


def _matched_action(
    payload: dict[str, Any], actions: dict[tuple[str, str, str], _ActionRecord]
) -> _ActionRecord | None:
    """Pair only exact tool name, tool-call id, and action id."""

    tool_name = _text(payload.get("tool_name"))
    tool_call_id = _text(payload.get("tool_call_id"))
    action_id = _text(payload.get("action_id"))
    if tool_name is None or tool_call_id is None or action_id is None:
        return None
    return actions.get((tool_name.casefold(), tool_call_id, action_id))


def _raw_replacement_key(action: _ActionRecord) -> tuple[str, str, str] | None:
    """Return the byte-significant identity of one editor replacement."""

    if action.tool_name != "file_editor" or action.file_editor_command != "str_replace":
        return None
    values = (
        action.action.get("path"),
        action.action.get("old_str"),
        action.action.get("new_str"),
    )
    if not all(isinstance(value, str) and value for value in values):
        return None
    path, old_str, new_str = values
    return path, old_str, new_str


def _is_exact_noop_replacement(action: _ActionRecord) -> bool:
    """Recognize only a byte-for-byte identical replacement payload."""

    old_str = action.action.get("old_str")
    new_str = action.action.get("new_str")
    return (
        action.tool_name == "file_editor"
        and action.file_editor_command == "str_replace"
        and isinstance(old_str, str)
        and isinstance(new_str, str)
        and old_str == new_str
    )


def _observation_is_error(observation: dict[str, Any]) -> bool:
    """Fail closed unless the protocol explicitly marks an observation successful."""

    return observation.get("is_error") is not False


def _terminal_exit_zero(observation: dict[str, Any]) -> bool:
    """Accept only a non-timeout terminal observation with integer exit code zero."""

    return (
        observation.get("kind") == "TerminalObservation"
        and observation.get("is_error") is False
        and observation.get("timeout") is False
        and isinstance(observation.get("exit_code"), int)
        and not isinstance(observation.get("exit_code"), bool)
        and observation.get("exit_code") == 0
    )


def _finish_summary(action: _ActionRecord, observation: dict[str, Any]) -> str | None:
    """Return text only from a successful native FinishTool round trip."""

    if (
        action.tool_name != "finish"
        or action.action.get("kind") != "FinishAction"
        or observation.get("kind") != "FinishObservation"
        or observation.get("is_error") is not False
    ):
        return None
    return _text(action.action.get("message"))


def _unsafe_final_summary(summary: str) -> bool:
    """Reject raw tool payloads embedded in the final message."""

    return bool(
        _RAW_TOOL_TAG_RE.search(summary)
        or _RAW_TOOL_METADATA_RE.search(summary)
        or _RAW_NAMED_ARGUMENTS_RE.search(summary)
    )


def _failure(
    tool_names: set[str], code: str, *, validation_required: bool, validation_observed: bool
) -> AgentRunEvidence:
    """Produce a bounded non-success result without exposing model messages."""

    return AgentRunEvidence(
        tool_names=tuple(sorted(tool_names)),
        final_summary=None,
        failure_code=code,
        validation_required=validation_required,
        validation_observed=validation_observed,
    )


def _is_blocked_terminal_policy_event(payload: dict[str, Any]) -> bool:
    """Recognize the documented synchronous terminal denial tuple."""

    return (
        _text(payload.get("kind")) == "HookExecutionEvent"
        and _text(payload.get("hook_event_type")) == "PreToolUse"
        and (_text(payload.get("tool_name")) or "").casefold() == "terminal"
        and payload.get("blocked") is True
    )


def has_blocked_terminal_policy_action(events: Iterable[dict[str, Any]]) -> bool:
    """Detect an authoritative terminal denial without reading model prose."""

    ordered = _ordered_history(events)
    return bool(
        ordered
        and any(_is_blocked_terminal_policy_event(event.payload) for event in ordered)
    )


def _paired_actions(
    ordered: list[_OrderedEvent],
) -> tuple[
    dict[tuple[str, str, str], _ActionRecord], dict[str, _ActionRecord]
] | None:
    """Index valid native actions for observation and hook correlation."""

    paired: dict[tuple[str, str, str], _ActionRecord] = {}
    by_id: dict[str, _ActionRecord] = {}
    for event in ordered:
        if _text(event.payload.get("kind")) != "ActionEvent":
            continue
        action = _action_record(event)
        if action is None:
            return None
        paired[(action.tool_name, action.tool_call_id, action.event_id)] = action
        by_id[action.event_id] = action
    return paired, by_id


def has_successful_noop_file_editor_replacement(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect a successful editor replacement that cannot change source."""

    ordered = _ordered_history(events)
    indexed = _paired_actions(ordered) if ordered is not None else None
    if ordered is None or indexed is None:
        return False
    actions, _ = indexed
    for event in ordered:
        if _text(event.payload.get("kind")) != "ObservationEvent":
            continue
        action = _matched_action(event.payload, actions)
        observation = _mapping(event.payload.get("observation"))
        if action is None or observation is None:
            return False
        if not _observation_is_error(observation) and _is_exact_noop_replacement(action):
            return True
    return False


def has_repeated_hook_blocked_file_editor_replacement(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect two identical replacements denied before execution on unchanged source."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, actions_by_id = indexed
    counts: dict[tuple[str, str, str], int] = {}
    seen_action_ids: set[str] = set()
    for event in ordered:
        payload = event.payload
        kind = _text(payload.get("kind"))
        if kind == "HookExecutionEvent":
            action_id = _text(payload.get("action_id"))
            action = actions_by_id.get(action_id or "")
            key = _raw_replacement_key(action) if action is not None else None
            if (
                _text(payload.get("hook_event_type")) == "PreToolUse"
                and (_text(payload.get("tool_name")) or "").casefold() == "file_editor"
                and payload.get("blocked") is True
                and action_id is not None
                and action_id not in seen_action_ids
                and key is not None
            ):
                seen_action_ids.add(action_id)
                counts[key] = counts.get(key, 0) + 1
                if counts[key] >= 2:
                    return True
            continue
        if kind != "ObservationEvent":
            continue
        action = _matched_action(payload, actions)
        observation = _mapping(payload.get("observation"))
        if action is None or observation is None:
            return False
        if _observation_is_error(observation):
            continue
        if action.terminal_may_mutate:
            counts.clear()
        elif action.file_editor_mutates and action.path is not None:
            counts = {
                key: value for key, value in counts.items() if key[0] != action.path
            }
    return False


def has_repeated_hook_blocked_immutable_test_edit(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect two authenticated immutable-test denials without project progress."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, actions_by_id = indexed
    denied = 0
    seen_action_ids: set[str] = set()
    for event in ordered:
        payload = event.payload
        kind = _text(payload.get("kind"))
        if kind == "HookExecutionEvent":
            action_id = _text(payload.get("action_id"))
            action = actions_by_id.get(action_id or "")
            if (
                _text(payload.get("hook_event_type")) == "PreToolUse"
                and (_text(payload.get("tool_name")) or "").casefold() == "file_editor"
                and payload.get("blocked") is True
                and _text(payload.get("reason")) == _IMMUTABLE_TEST_POLICY_REASON
                and action_id is not None
                and action_id not in seen_action_ids
                and action is not None
                and action.file_editor_mutates
            ):
                seen_action_ids.add(action_id)
                denied += 1
                if denied >= 2:
                    return True
            continue
        if kind != "ObservationEvent":
            continue
        action = _matched_action(payload, actions)
        observation = _mapping(payload.get("observation"))
        if action is None or observation is None:
            return False
        if not _observation_is_error(observation) and (
            action.file_editor_mutates or action.terminal_may_mutate
        ):
            denied = 0
    return False


def has_repeated_failed_file_editor_view(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect two failed reads of the same path during the current user turn."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, _ = indexed
    failures: dict[str, int] = {}
    for event in ordered:
        if _text(event.payload.get("kind")) != "ObservationEvent":
            continue
        action = _matched_action(event.payload, actions)
        observation = _mapping(event.payload.get("observation"))
        if action is None or observation is None:
            return False
        if not _observation_is_error(observation) and (
            action.terminal_validation
            or action.terminal_may_mutate
            or action.file_editor_mutates
        ):
            failures.clear()
        if (
            action.tool_name == "file_editor"
            and action.file_editor_command in _FILE_EDITOR_READ_COMMANDS
            and action.path is not None
        ):
            if _observation_is_error(observation):
                failures[action.path] = failures.get(action.path, 0) + 1
                if failures[action.path] >= 2:
                    return True
            else:
                failures.pop(action.path, None)
    return False


def _successful_reads_since_progress(
    events: Iterable[dict[str, Any]],
) -> list[_ActionRecord] | None:
    """Collect consecutive successful editor reads from the current turn."""

    ordered = _ordered_history(events)
    if ordered is None:
        return None
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return None
    actions, _ = indexed
    reads: list[_ActionRecord] = []
    for event in ordered:
        if _text(event.payload.get("kind")) != "ObservationEvent":
            continue
        action = _matched_action(event.payload, actions)
        observation = _mapping(event.payload.get("observation"))
        if action is None or observation is None:
            return None
        if (
            action.tool_name == "file_editor"
            and action.file_editor_command in _FILE_EDITOR_READ_COMMANDS
            and action.path is not None
            and not _observation_is_error(observation)
        ):
            reads.append(action)
        elif not _observation_is_error(observation):
            reads.clear()
    return reads


def has_repeated_successful_file_editor_view_cycle(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect three consecutive alternating reads of two unchanged paths."""

    reads = _successful_reads_since_progress(events)
    if reads is None or len(reads) < 6:
        return False
    paths = [action.path for action in reads[-6:]]
    first, second = paths[0], paths[1]
    return first != second and paths == [first, second, first, second, first, second]


def has_repeated_successful_file_editor_read_sweep(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect ten read-only actions revisiting at least two paths three times."""

    reads = _successful_reads_since_progress(events)
    if reads is None or len(reads) < 10:
        return False
    counts: dict[str, int] = {}
    for action in reads:
        if action.path is not None:
            counts[action.path] = counts.get(action.path, 0) + 1
    return sum(count >= 3 for count in counts.values()) >= 2


def has_repeated_successful_file_editor_expansion_cycle(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect one successful self-embedding replacement repeated three times."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, _ = indexed
    counts: dict[tuple[str, str, str], int] = {}
    for event in ordered:
        if _text(event.payload.get("kind")) != "ObservationEvent":
            continue
        action = _matched_action(event.payload, actions)
        observation = _mapping(event.payload.get("observation"))
        if action is None or observation is None:
            return False
        if action.terminal_validation:
            counts.clear()
            continue
        if _observation_is_error(observation):
            continue
        key = _raw_replacement_key(action)
        if key is None:
            continue
        _, old_str, new_str = key
        if old_str == new_str or old_str not in new_str or len(new_str) <= len(old_str):
            continue
        counts[key] = counts.get(key, 0) + 1
        if counts[key] >= 3:
            return True
    return False


def _failed_replacement_counts(
    events: Iterable[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str], int], bool]:
    """Count correlated failed replacements and report malformed history."""

    ordered = _ordered_history(events)
    if ordered is None:
        return {}, False
    indexed = _paired_actions(ordered)
    if indexed is None:
        return {}, False
    actions, _ = indexed
    counts: dict[tuple[str, str, str], int] = {}
    seen_actions: set[str] = set()

    def record(action: _ActionRecord) -> None:
        """Count one failed native action once."""

        key = _raw_replacement_key(action)
        if key is not None and action.event_id not in seen_actions:
            seen_actions.add(action.event_id)
            counts[key] = counts.get(key, 0) + 1

    for event in ordered:
        payload = event.payload
        kind = _text(payload.get("kind"))
        if kind == "AgentErrorEvent":
            action = _matched_action(payload, actions)
            if (_text(payload.get("tool_name")) or "").casefold() == "file_editor":
                if action is None:
                    return {}, False
                record(action)
            continue
        if kind != "ObservationEvent":
            continue
        action = _matched_action(payload, actions)
        observation = _mapping(payload.get("observation"))
        if action is None or observation is None:
            return {}, False
        if action.tool_name != "file_editor":
            continue
        if _observation_is_error(observation):
            record(action)
        elif action.file_editor_mutates and action.path is not None:
            counts = {
                key: value for key, value in counts.items() if key[0] != action.path
            }
    return counts, True


def has_repeated_failed_file_editor_replacement(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect two correlated failures of the exact same replacement."""

    counts, valid = _failed_replacement_counts(events)
    return valid and any(count >= 2 for count in counts.values())


def has_repeated_failed_file_editor_retry_cycle(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect three failed edit/re-read rounds on one unchanged path."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, _ = indexed
    seen_actions: set[str] = set()
    failures: dict[str, int] = {}
    completed_rounds: dict[str, int] = {}

    def failed(action: _ActionRecord) -> bool:
        """Record one failed replacement and flag the third futile round."""

        if action.event_id in seen_actions or _raw_replacement_key(action) is None:
            return False
        seen_actions.add(action.event_id)
        path = action.path
        if path is None:
            return False
        failures[path] = failures.get(path, 0) + 1
        return completed_rounds.get(path, 0) >= 2 and failures[path] >= 2

    for event in ordered:
        payload = event.payload
        kind = _text(payload.get("kind"))
        if kind == "AgentErrorEvent":
            action = _matched_action(payload, actions)
            if (_text(payload.get("tool_name")) or "").casefold() == "file_editor":
                if action is None:
                    return False
                if failed(action):
                    return True
            continue
        if kind != "ObservationEvent":
            continue
        action = _matched_action(payload, actions)
        observation = _mapping(payload.get("observation"))
        if action is None or observation is None:
            return False
        if action.tool_name == "terminal":
            if not _observation_is_error(observation) and (
                action.terminal_validation or action.terminal_may_mutate
            ):
                failures.clear()
                completed_rounds.clear()
            continue
        if action.tool_name != "file_editor":
            continue
        if _observation_is_error(observation):
            if failed(action):
                return True
        elif action.file_editor_mutates and action.path is not None:
            failures.pop(action.path, None)
            completed_rounds.pop(action.path, None)
        elif (
            action.file_editor_command in _FILE_EDITOR_READ_COMMANDS
            and action.path is not None
        ):
            path = action.path
            if failures.get(path, 0) >= 2:
                completed_rounds[path] = completed_rounds.get(path, 0) + 1
                failures.pop(path, None)
    return False


def has_repeated_successful_file_editor_replacement_cycle(
    events: Iterable[dict[str, Any]],
) -> bool:
    """Detect a successful forward, reverse, forward replacement cycle."""

    ordered = _ordered_history(events)
    if ordered is None:
        return False
    ordered = _current_turn(ordered)
    indexed = _paired_actions(ordered)
    if indexed is None:
        return False
    actions, _ = indexed
    forwards: set[tuple[str, str, str]] = set()
    reversed_forwards: set[tuple[str, str, str]] = set()
    for event in ordered:
        if _text(event.payload.get("kind")) != "ObservationEvent":
            continue
        action = _matched_action(event.payload, actions)
        observation = _mapping(event.payload.get("observation"))
        if action is None or observation is None:
            return False
        if action.terminal_validation:
            forwards.clear()
            reversed_forwards.clear()
            continue
        if _observation_is_error(observation):
            continue
        key = _raw_replacement_key(action)
        if key is None or key[1] == key[2]:
            continue
        reverse = (key[0], key[2], key[1])
        if key in reversed_forwards:
            return True
        if reverse in forwards:
            reversed_forwards.add(reverse)
        forwards.add(key)
    return False


def evaluate_agent_history(task: str, events: Iterable[dict[str, Any]]) -> AgentRunEvidence:
    """Validate a completed SDK history from structured, correlated evidence."""

    validation_required = task_requires_validation(task)
    ordered = _ordered_history(events)
    if not ordered:
        return _failure(
            set(),
            "history_unavailable",
            validation_required=validation_required,
            validation_observed=False,
        )

    actions: dict[tuple[str, str, str], _ActionRecord] = {}
    tool_names: set[str] = set()
    successful_project_action = False
    last_successful_mutation = -1
    last_validation = -1
    finish_action: _ActionRecord | None = None
    finish_observation: dict[str, Any] | None = None
    last_action_sequence = -1
    pending_retries: list[_EditorRetry] = []
    unresolved_unknown_editor_error = False
    blocked_terminal = False
    no_op_replacement = False

    for event in ordered:
        payload = event.payload
        kind = _text(payload.get("kind"))
        if kind == "HookExecutionEvent":
            blocked_terminal = blocked_terminal or _is_blocked_terminal_policy_event(payload)
            continue
        if kind == "ActionEvent":
            action = _action_record(event)
            if action is None:
                return _failure(
                    tool_names,
                    "history_unavailable",
                    validation_required=validation_required,
                    validation_observed=False,
                )
            tool_names.add(action.tool_name)
            actions[(action.tool_name, action.tool_call_id, action.event_id)] = action
            last_action_sequence = action.sequence
            if action.tool_name == "finish":
                finish_action = action
            continue
        if kind == "AgentErrorEvent":
            matched = _matched_action(payload, actions)
            if matched is not None:
                if matched.tool_name == "file_editor" and matched.file_editor_mutates:
                    pending_retries.append(_EditorRetry(matched.path, event.sequence))
            elif (_text(payload.get("tool_name")) or "").casefold() == "file_editor":
                unresolved_unknown_editor_error = True
            continue
        if kind != "ObservationEvent":
            continue
        action = _matched_action(payload, actions)
        observation = _mapping(payload.get("observation"))
        if action is None or observation is None:
            return _failure(
                tool_names,
                "history_unavailable",
                validation_required=validation_required,
                validation_observed=False,
            )
        is_error = _observation_is_error(observation)
        if action.tool_name in PROJECT_ACTION_TOOL_NAMES and not is_error:
            successful_project_action = True
        if action.tool_name == "file_editor":
            if observation.get("kind") != "FileEditorObservation":
                return _failure(
                    tool_names,
                    "history_unavailable",
                    validation_required=validation_required,
                    validation_observed=False,
                )
            if is_error:
                if action.file_editor_mutates:
                    pending_retries.append(_EditorRetry(action.path, event.sequence))
                continue
            for index, retry in enumerate(pending_retries):
                if (
                    retry.path is not None
                    and retry.path == action.path
                    and retry.reread_at is None
                    and action.file_editor_command in _FILE_EDITOR_READ_COMMANDS
                    and action.sequence > retry.failed_at
                ):
                    pending_retries[index] = _EditorRetry(
                        retry.path, retry.failed_at, action.sequence
                    )
            resolved = [
                index
                for index, retry in enumerate(pending_retries)
                if retry.path is not None
                and retry.path == action.path
                and retry.reread_at is not None
                and action.file_editor_mutates
                and action.sequence > retry.reread_at
            ]
            for index in reversed(resolved):
                pending_retries.pop(index)
            if action.file_editor_mutates:
                no_op_replacement = no_op_replacement or _is_exact_noop_replacement(action)
                last_successful_mutation = max(last_successful_mutation, action.sequence)
        elif action.tool_name == "terminal":
            if action.terminal_may_mutate and _terminal_exit_zero(observation):
                last_successful_mutation = max(last_successful_mutation, action.sequence)
            if action.terminal_validation and _terminal_exit_zero(observation):
                last_validation = max(last_validation, action.sequence)
        elif action.tool_name == "finish":
            finish_observation = observation

    validation_observed = last_validation > last_successful_mutation
    if blocked_terminal:
        return _failure(
            tool_names,
            "prohibited_terminal_action",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if no_op_replacement:
        return _failure(
            tool_names,
            "noop_file_editor_replacement",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if not successful_project_action:
        return _failure(
            tool_names,
            "missing_project_action",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if (
        finish_action is None
        or finish_observation is None
        or finish_action.sequence != last_action_sequence
    ):
        return _failure(
            tool_names,
            "missing_terminal_finish",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    summary = _finish_summary(finish_action, finish_observation)
    if summary is None:
        return _failure(
            tool_names,
            "missing_terminal_finish",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if _unsafe_final_summary(summary):
        return _failure(
            tool_names,
            "unsafe_final_summary",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if _FUTURE_ACTION_RE.search(summary):
        return _failure(
            tool_names,
            "future_action_in_final_summary",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if unresolved_unknown_editor_error or pending_retries:
        return _failure(
            tool_names,
            "unretried_file_editor_error",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    if validation_required and not validation_observed:
        return _failure(
            tool_names,
            "missing_post_mutation_validation",
            validation_required=validation_required,
            validation_observed=validation_observed,
        )
    return AgentRunEvidence(
        tool_names=tuple(sorted(tool_names)),
        final_summary=summary,
        failure_code=None,
        validation_required=validation_required,
        validation_observed=validation_observed,
    )

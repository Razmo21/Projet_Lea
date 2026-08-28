#!/usr/bin/env python3
"""Run one isolated OpenHands SDK smoke-test conversation against local Qwen."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

from pydantic import SecretStr

from openhands.sdk import Agent, Conversation, LLM, Workspace
from openhands.sdk.tool.defaults import DEFAULT_EXEC_TOOL_NAMES, default_tool_specs


class MemoryStatusEx(ctypes.Structure):
    """Mirror the Windows MEMORYSTATUSEX structure used for physical RAM samples."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


@dataclass(frozen=True)
class EventRecord:
    """Keep one sanitized, ordered Agent Server event without retaining SDK objects."""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    source: str


@dataclass
class RunEvidence:
    """Accumulate callback and authoritative Agent Server evidence for one run."""

    event_types: dict[str, int] = field(default_factory=dict)
    action_payloads: list[dict[str, Any]] = field(default_factory=list)
    agent_messages: list[str] = field(default_factory=list)
    tool_action_counts: dict[str, int] = field(default_factory=dict)
    major_errors: list[str] = field(default_factory=list)
    event_records: list[EventRecord] = field(default_factory=list)
    server_history_records: list[EventRecord] = field(default_factory=list)
    event_ids: set[str] = field(default_factory=set)
    event_source_counts: dict[str, int] = field(default_factory=dict)
    history_sync_error: str | None = None
    event_count: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


def parse_args() -> argparse.Namespace:
    """Parse explicit runner inputs rather than reading implicit project settings."""

    parser = argparse.ArgumentParser(
        description="Execute one SDK/Agent Server smoke test without Agent Canvas."
    )
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--model-alias", required=True)
    parser.add_argument("--context-size", type=int, required=True)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--events-path", type=Path, required=True)
    parser.add_argument("--resources-path", type=Path, required=True)
    parser.add_argument("--result-path", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--normal-free-bytes", type=int, required=True)
    parser.add_argument("--acceptable-free-bytes", type=int, required=True)
    parser.add_argument("--critical-free-bytes", type=int, required=True)
    return parser.parse_args()


def write_json_line(path: Path, payload: dict[str, Any]) -> None:
    """Append one durable UTF-8 JSON record to an ignored audit log."""

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    """Publish the final result with replace semantics so interruptions leave no partial JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def get_available_physical_memory() -> tuple[int, int, int, int]:
    """Return physical RAM plus committed-memory counters without a third-party dependency."""

    if os.name != "nt":
        raise RuntimeError("Le runner SDK de ce bootstrap doit etre execute sous Windows.")

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    committed = int(status.ullTotalPageFile - status.ullAvailPageFile)
    return (
        int(status.ullAvailPhys),
        int(status.ullTotalPhys),
        committed,
        int(status.ullTotalPageFile),
    )


def run_command(arguments: list[str], timeout_seconds: int = 5) -> dict[str, Any]:
    """Run an informative local probe and preserve failures as data instead of raising."""

    try:
        completed = subprocess.run(
            arguments,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "arguments": arguments,
            "return_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as error:
        return {"arguments": arguments, "error": str(error)}


def capture_gpu_memory() -> dict[str, Any] | None:
    """Collect NVIDIA memory telemetry when the utility is locally available."""

    result = run_command(
        [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    if result.get("return_code") != 0:
        return result
    return {"csv": [line for line in result.get("stdout", "").splitlines() if line]}


def capture_wsl_memory() -> dict[str, Any]:
    """Read Docker Desktop WSL memory counters independently from Windows RAM."""

    probe = run_command(
        [
            "wsl.exe",
            "-d",
            "docker-desktop",
            "-e",
            "sh",
            "-lc",
            "grep -E '^(MemTotal|MemAvailable|Cached|SwapTotal|SwapFree):' /proc/meminfo",
        ]
    )
    if probe.get("return_code") != 0:
        return probe

    counters: dict[str, int] = {}
    for line in probe.get("stdout", "").splitlines():
        name, _, remainder = line.partition(":")
        pieces = remainder.split()
        if pieces and pieces[0].isdigit():
            counters[name] = int(pieces[0]) * 1024
    return {"bytes": counters}


def capture_docker_memory(container_name: str) -> dict[str, Any]:
    """Collect the Agent Server container memory reported by Docker without inspecting other containers."""

    probe = run_command(
        ["docker.exe", "container", "stats", "--no-stream", "--format", "{{json .}}", container_name]
    )
    if probe.get("return_code") != 0:
        return probe
    try:
        return {"stats": json.loads(probe.get("stdout", ""))}
    except json.JSONDecodeError:
        return probe


def capture_pagefile_usage() -> dict[str, Any]:
    """Collect live Windows pagefile counters without making telemetry a run dependency."""

    command = (
        "$ErrorActionPreference='Stop'; "
        "$items=@(Get-CimInstance Win32_PageFileUsage | "
        "Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage); "
        "$items | ConvertTo-Json -Compress"
    )
    probe = run_command(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        timeout_seconds=5,
    )
    if probe.get("return_code") != 0:
        return probe
    try:
        raw_items = json.loads(probe.get("stdout", ""))
    except json.JSONDecodeError:
        return probe
    items = raw_items if isinstance(raw_items, list) else [raw_items]
    return {
        "items": [
            {
                "name": item.get("Name"),
                "allocated_mb": item.get("AllocatedBaseSize"),
                "current_usage_mb": item.get("CurrentUsage"),
                "peak_usage_mb": item.get("PeakUsage"),
            }
            for item in items
            if isinstance(item, dict)
        ]
    }


def capture_resource_sample(container_name: str, stage: str) -> dict[str, Any]:
    """Capture one cross-boundary resource sample during the live agent run."""

    available, total, committed, commit_limit = get_available_physical_memory()
    # Secondary probes run concurrently so physical-RAM enforcement is never delayed by one slow utility.
    with ThreadPoolExecutor(max_workers=4) as executor:
        gpu_future = executor.submit(capture_gpu_memory)
        wsl_future = executor.submit(capture_wsl_memory)
        docker_future = executor.submit(capture_docker_memory, container_name)
        pagefile_future = executor.submit(capture_pagefile_usage)
        gpu = gpu_future.result()
        wsl = wsl_future.result()
        docker = docker_future.result()
        pagefile = pagefile_future.result()
    return {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage": stage,
        "system_available_ram_bytes": available,
        "system_total_ram_bytes": total,
        "system_committed_bytes": committed,
        "system_commit_limit_bytes": commit_limit,
        "pagefile": pagefile,
        "gpu": gpu,
        "wsl": wsl,
        "docker": docker,
    }


def event_texts(value: Any) -> Iterable[str]:
    """Yield scalar text recursively so evidence checks remain schema-tolerant across SDK releases."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from event_texts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from event_texts(nested)


def classify_available_memory(available_bytes: int, arguments: argparse.Namespace) -> str:
    """Apply the agreed nightly RAM policy to a single physical-memory sample."""

    if available_bytes >= arguments.normal_free_bytes:
        return "normal"
    if available_bytes >= arguments.acceptable_free_bytes:
        return "acceptable"
    if available_bytes >= arguments.critical_free_bytes:
        return "warning"
    return "critical"


def extract_finish_summary(payload: dict[str, Any]) -> str | None:
    """Read the native FinishTool message from an ActionEvent when the agent terminates normally."""

    if payload.get("tool_name") != "finish":
        return None
    action = payload.get("action")
    if not isinstance(action, dict):
        return None
    message = action.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return None


def sanitize_payload_data(value: Any) -> Any:
    """Recursively retain executable evidence while removing model-reasoning fields from logs."""

    private_fields = {
        "thought",
        "reasoning_content",
        "thinking_blocks",
        "responses_reasoning_item",
    }
    if isinstance(value, dict):
        return {
            key: sanitize_payload_data(nested)
            for key, nested in value.items()
            if key not in private_fields
        }
    if isinstance(value, list):
        return [sanitize_payload_data(nested) for nested in value]
    return value


def sanitize_event_payload(event: Any) -> dict[str, Any]:
    """Serialize one SDK callback event using the same recursive privacy filter as REST history."""

    payload = sanitize_payload_data(event.model_dump(mode="json"))
    if not isinstance(payload, dict):
        raise RuntimeError("Un evenement SDK ne s'est pas serialise en objet JSON.")
    return payload


def build_event_record(event: Any, source: str) -> EventRecord:
    """Convert one SDK event into the stable record used by evidence and JSONL logs."""

    payload = sanitize_event_payload(event)
    return EventRecord(
        event_id=str(payload.get("id", "")),
        event_type=type(event).__name__,
        payload=payload,
        source=source,
    )


def build_raw_event_record(payload: Any, source: str) -> EventRecord:
    """Convert one official Agent Server REST event without deserializing server-only tool classes."""

    clean_payload = sanitize_payload_data(payload)
    if not isinstance(clean_payload, dict):
        raise RuntimeError("L'historique Agent Server contient un evenement JSON non objet.")
    event_type = clean_payload.get("kind")
    if not isinstance(event_type, str) or not event_type:
        raise RuntimeError("L'historique Agent Server contient un evenement sans champ kind.")
    return EventRecord(
        event_id=str(clean_payload.get("id", "")),
        event_type=event_type,
        payload=clean_payload,
        source=source,
    )


def record_event_record(
    record: EventRecord,
    evidence: RunEvidence,
    events_path: Path,
) -> bool:
    """Persist one unique normalized event without double-counting callback/history overlap."""

    event_key = record.event_id or f"{record.source}:{record.event_type}:{len(record.payload)}"
    with evidence.lock:
        if event_key in evidence.event_ids:
            return False
        evidence.event_ids.add(event_key)
        evidence.event_count += 1
        evidence.event_records.append(record)
        evidence.event_types[record.event_type] = (
            evidence.event_types.get(record.event_type, 0) + 1
        )
        evidence.event_source_counts[record.source] = (
            evidence.event_source_counts.get(record.source, 0) + 1
        )
        if record.event_type == "ActionEvent":
            evidence.action_payloads.append(record.payload)
            tool_name = str(record.payload.get("tool_name", ""))
            if tool_name:
                evidence.tool_action_counts[tool_name] = (
                    evidence.tool_action_counts.get(tool_name, 0) + 1
                )
            finish_summary = extract_finish_summary(record.payload)
            if finish_summary:
                evidence.agent_messages.append(finish_summary)
        if record.event_type == "MessageEvent" and record.payload.get("source") == "agent":
            message_text = "\n".join(event_texts(record.payload.get("llm_message", record.payload)))
            if message_text:
                evidence.agent_messages.append(message_text)
        # A red unittest exit is an expected observation; structured SDK errors are not.
        if record.event_type.endswith("ErrorEvent"):
            evidence.major_errors.append(record.event_type)
    write_json_line(
        events_path,
        {
            "event_id": record.event_id,
            "event_source": record.source,
            "event_type": record.event_type,
            "payload": record.payload,
        },
    )
    return True


def record_event(
    event: Any,
    evidence: RunEvidence,
    events_path: Path,
    source: str,
) -> bool:
    """Normalize an SDK callback event before sending it through the shared evidence recorder."""

    return record_event_record(build_event_record(event, source), evidence, events_path)


def fetch_agent_server_history(server_url: str, conversation_id: str) -> list[dict[str, Any]]:
    """Read every paginated event from the exact local REST route used by SDK 1.43.1 synchronization."""

    parsed_server_url = urlparse(server_url)
    if (
        parsed_server_url.scheme != "http"
        or parsed_server_url.hostname not in {"127.0.0.1", "localhost"}
    ):
        raise RuntimeError("La lecture d'historique doit rester limitee a l'Agent Server local loopback.")
    if not conversation_id:
        raise RuntimeError("La conversation Agent Server n'a pas d'identifiant exploitable.")

    endpoint = (
        f"{server_url.rstrip('/')}/api/conversations/"
        f"{quote(conversation_id, safe='')}/events/search"
    )
    page_id: str | None = None
    seen_page_ids: set[str] = set()
    events: list[dict[str, Any]] = []
    while True:
        parameters: dict[str, str | int] = {"limit": 100}
        if page_id:
            parameters["page_id"] = page_id
        request = Request(
            f"{endpoint}?{urlencode(parameters)}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:  # nosec B310: loopback URL is asserted above.
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "La lecture REST officielle de l'historique Agent Server a echoue: "
                f"{type(error).__name__}: {error}"
            ) from error
        if not isinstance(response_payload, dict):
            raise RuntimeError("La reponse d'historique Agent Server n'est pas un objet JSON.")
        page_items = response_payload.get("items")
        if not isinstance(page_items, list) or not all(
            isinstance(item, dict) for item in page_items
        ):
            raise RuntimeError("La reponse d'historique Agent Server ne contient pas une liste d'evenements JSON.")
        events.extend(page_items)
        next_page_id = response_payload.get("next_page_id")
        if not next_page_id:
            return events
        page_id = str(next_page_id)
        if page_id in seen_page_ids:
            raise RuntimeError("La pagination d'historique Agent Server boucle sur le meme page_id.")
        seen_page_ids.add(page_id)


def collect_server_history(
    conversation: Any,
    server_url: str,
    evidence: RunEvidence,
    events_path: Path,
) -> None:
    """Fetch authoritative server history through the SDK's own REST route, avoiding its stale tool union."""

    history = [
        build_raw_event_record(event, "agent_server_history")
        for event in fetch_agent_server_history(server_url, str(conversation.id))
    ]
    if not history:
        raise RuntimeError("L'historique officiel Agent Server est vide apres le run.")
    with evidence.lock:
        evidence.server_history_records = history
    for record in history:
        record_event_record(record, evidence, events_path)


def action_text(payload: dict[str, Any]) -> str:
    """Extract only tool-call arguments, never model reasoning, for command-level evidence."""

    return "\n".join(
        event_texts({"action": payload.get("action"), "tool_call": payload.get("tool_call")})
    ).lower()


def observation_text(payload: dict[str, Any]) -> str:
    """Extract a tool observation's structured result for red/green test classification."""

    return "\n".join(event_texts(payload.get("observation", payload))).lower()


def is_unittest_action(text: str) -> bool:
    """Recognize the explicitly requested standard-library test command in a tool action."""

    compact = " ".join(text.split())
    return "unittest" in compact and "python" in compact


def is_red_test_observation(text: str) -> bool:
    """Classify a real unittest observation as red without treating a normal tool result as an error."""

    required_markers = (
        "failed (failures=2)",
        "test_discount_reduces_the_subtotal",
        "test_receipt_has_the_expected_label",
    )
    return all(marker in text for marker in required_markers)


def is_green_test_observation(text: str) -> bool:
    """Classify a real unittest observation as green only when failure markers are absent."""

    required_markers = (
        "test_discount_reduces_the_subtotal",
        "test_receipt_has_the_expected_label",
        "ran 2 tests",
    )
    return (
        all(marker in text for marker in required_markers)
        and ("\nok" in text or text.rstrip().endswith("ok"))
        and "failed" not in text
        and "error" not in text
    )


def is_successful_tool_observation(text: str) -> bool:
    """Accept a completed write observation only when it has no command-level failure marker."""

    failure_markers = ("traceback", "permission denied", "command not found", "error:")
    return not any(marker in text for marker in failure_markers)


def is_pricing_write_action(action: dict[str, Any]) -> bool:
    """Recognize a real file-editor or terminal write aimed specifically at pricing.py."""

    text = action["text"]
    if "pricing.py" not in text:
        return False
    if action["tool_name"] == "file_editor":
        return any(marker in text for marker in ("old", "new", "replace", "str_replace", "edit"))
    write_markers = (
        "apply_patch",
        "sed -i",
        "perl -pi",
        "tee ",
        "> pricing.py",
        ">pricing.py",
        "write_text",
        "open(",
    )
    return action["tool_name"] == "terminal" and any(marker in text for marker in write_markers)


def build_agent(model_alias: str, context_size: int) -> Agent:
    """Construct a no-browser SDK agent bound exclusively to the local OpenAI-compatible Qwen endpoint."""

    tool_specs = list(default_tool_specs(enable_browser=False))
    tool_names = tuple(tool.name for tool in tool_specs)
    if tool_names != DEFAULT_EXEC_TOOL_NAMES:
        raise RuntimeError(
            "Les specifications d'outils SDK 1.43.1 ne correspondent pas au contrat "
            f"officiel attendu: {tool_names!r}."
        )
    llm = LLM(
        usage_id="agent",
        model=f"openai/{model_alias}",
        base_url="http://host.docker.internal:8081/v1",
        api_key=SecretStr("local-llm"),
        max_input_tokens=context_size,
        max_output_tokens=2048,
        native_tool_calling=True,
        api_mode="chat",
        caching_prompt=False,
        num_retries=0,
        timeout=180,
    )
    return Agent(
        llm=llm,
        tools=tool_specs,
        system_prompt_kwargs={"cli_mode": True},
    )


def summarize_evidence(evidence: RunEvidence) -> dict[str, Any]:
    """Prove the required read/red/edit/green sequence from authoritative server events."""

    with evidence.lock:
        timeline = list(evidence.server_history_records or evidence.event_records)
        event_types: dict[str, int] = {}
        actions: list[dict[str, Any]] = []
        observations_by_call: dict[str, list[dict[str, Any]]] = {}
        summaries: list[str] = []
        major_errors = list(evidence.major_errors)
        for index, record in enumerate(timeline):
            event_types[record.event_type] = event_types.get(record.event_type, 0) + 1
            if record.event_type == "ActionEvent":
                tool_name = str(record.payload.get("tool_name", ""))
                action = {
                    "index": index,
                    "event_id": record.event_id,
                    "tool_name": tool_name,
                    "tool_call_id": str(record.payload.get("tool_call_id", "")),
                    "text": action_text(record.payload),
                }
                actions.append(action)
                finish_summary = extract_finish_summary(record.payload)
                if finish_summary:
                    summaries.append(finish_summary)
            elif record.event_type == "ObservationEvent":
                call_id = str(record.payload.get("tool_call_id", ""))
                observations_by_call.setdefault(call_id, []).append(
                    {
                        "index": index,
                        "action_id": str(record.payload.get("action_id", "")),
                        "text": observation_text(record.payload),
                    }
                )
            elif record.event_type.endswith("ErrorEvent") and record.event_type not in major_errors:
                major_errors.append(record.event_type)

        def matched_observations(action: dict[str, Any]) -> list[dict[str, Any]]:
            """Return only server observations that explicitly match one tool action."""

            return [
                observation
                for observation in observations_by_call.get(action["tool_call_id"], [])
                if not observation["action_id"] or observation["action_id"] == action["event_id"]
            ]

        test_runs: list[dict[str, Any]] = []
        for action in actions:
            if not is_unittest_action(action["text"]):
                continue
            observations = matched_observations(action)
            result_text = "\n".join(item["text"] for item in observations)
            test_runs.append(
                {
                    "action_index": action["index"],
                    "observation_index": max((item["index"] for item in observations), default=-1),
                    "red": is_red_test_observation(result_text),
                    "green": is_green_test_observation(result_text),
                }
            )

        first_red = next((item for item in test_runs if item["red"]), None)
        first_green_after_red = next(
            (
                item
                for item in test_runs
                if first_red is not None
                and item["green"]
                and item["action_index"] > first_red["action_index"]
            ),
            None,
        )
        read_requirements = {
            "readme.md": ("openhands smoke test",),
            "pricing.py": ("1 + discount_percent / 100", "receipt for"),
            "test_pricing.py": (
                "test_discount_reduces_the_subtotal",
                "total for mina: $45.00",
            ),
        }
        read_before_red: dict[str, bool] = {}
        read_positions: dict[str, int] = {}
        for file_name, sentinels in read_requirements.items():
            candidates = [
                action
                for action in actions
                if action["tool_name"] != "finish"
                and file_name in action["text"]
                and (first_red is None or action["index"] < first_red["action_index"])
                and all(
                    sentinel in "\n".join(item["text"] for item in matched_observations(action))
                    for sentinel in sentinels
                )
            ]
            read_before_red[file_name] = bool(candidates)
            if candidates:
                read_positions[file_name] = candidates[0]["index"]

        edit_candidates = [
            action
            for action in actions
            if first_red is not None
            and first_green_after_red is not None
            and first_red["action_index"] < action["index"] < first_green_after_red["action_index"]
            and is_pricing_write_action(action)
            and matched_observations(action)
            and all(
                is_successful_tool_observation(observation["text"])
                for observation in matched_observations(action)
            )
        ]
        pricing_action_between_tests = bool(edit_candidates)
        project_tool_action_count = sum(
            1 for action in actions if action["tool_name"] and action["tool_name"] != "finish"
        )
        all_files_read = all(read_before_red.values())
        files_read_in_required_order = (
            all_files_read
            and read_positions["readme.md"] < read_positions["pricing.py"] < read_positions["test_pricing.py"]
        )
        ordered_sequence = bool(
            files_read_in_required_order
            and first_red is not None
            and pricing_action_between_tests
            and first_green_after_red is not None
        )
        action_ids = {action["event_id"] for action in actions}
        matched_action_ids = {
            observation["action_id"]
            for observations in observations_by_call.values()
            for observation in observations
            if observation["action_id"]
        }
        return {
            "event_count": evidence.event_count,
            "event_types": dict(sorted(event_types.items())),
            "event_source_counts": dict(sorted(evidence.event_source_counts.items())),
            "authoritative_history_event_count": len(evidence.server_history_records),
            "history_sync_error": evidence.history_sync_error,
            "action_count": len(actions),
            "tool_action_counts": dict(
                sorted(
                    {
                        tool_name: sum(1 for action in actions if action["tool_name"] == tool_name)
                        for tool_name in {action["tool_name"] for action in actions if action["tool_name"]}
                    }.items()
                )
            ),
            "project_tool_action_count": project_tool_action_count,
            "read_before_red": read_before_red,
            "files_read_in_required_order": files_read_in_required_order,
            "all_required_files_read_before_red_test": all_files_read,
            "red_unittest_observed": first_red is not None,
            "green_unittest_observed_after_red": first_green_after_red is not None,
            "pricing_action_between_red_and_green": pricing_action_between_tests,
            "ordered_smoke_sequence_observed": ordered_sequence,
            "orphan_action_count": len(action_ids - matched_action_ids),
            "orphan_observation_count": len(matched_action_ids - action_ids),
            "major_error_events": major_errors,
            "agent_summary": (summaries or evidence.agent_messages)[-1]
            if (summaries or evidence.agent_messages)
            else None,
        }


def wait_for_conversation(
    conversation: Any,
    arguments: argparse.Namespace,
    evidence: RunEvidence,
) -> tuple[str, list[dict[str, Any]], bool, str | None, str | None]:
    """Poll one remote run, interrupt it on RAM breach or timeout, and never leave it mutating unattended."""

    samples: list[dict[str, Any]] = []
    memory_breach = False
    interruption_sent = False
    interruption_reason: str | None = None
    interruption_error: str | None = None
    interruption_deadline: float | None = None
    consecutive_critical_samples = 0
    started_at = time.monotonic()
    last_sample_at = 0.0
    terminal_status = "unknown"

    conversation.run(blocking=False)
    while True:
        now = time.monotonic()
        if now - last_sample_at >= 2.0:
            sample = capture_resource_sample(arguments.container_name, "during_agent_run")
            sample["memory_policy"] = classify_available_memory(
                sample["system_available_ram_bytes"], arguments
            )
            samples.append(sample)
            write_json_line(arguments.resources_path, sample)
            last_sample_at = now
            if sample["memory_policy"] == "critical":
                consecutive_critical_samples += 1
            else:
                consecutive_critical_samples = 0
            # Two successive samples make the <4 GiB condition durable rather than reacting to a transient dip.
            if consecutive_critical_samples >= 2:
                memory_breach = True

        try:
            status = conversation.state.execution_status.value
        except Exception as error:  # SDK networking errors are evidence, not a reason to strand the server.
            status = f"status_error:{type(error).__name__}"

        elapsed = now - started_at
        must_interrupt = memory_breach or elapsed >= arguments.timeout_seconds
        if must_interrupt and not interruption_sent:
            interruption_sent = True
            interruption_reason = "critical_memory" if memory_breach else "timeout"
            # The orchestrator stops the verified Agent Server immediately after this short grace period.
            interruption_deadline = now + 10.0
            try:
                conversation.interrupt()
            except Exception as error:
                interruption_error = f"{type(error).__name__}: {error}"
                with evidence.lock:
                    evidence.major_errors.append("InterruptError")

        if status in {"finished", "error", "stuck"}:
            terminal_status = status
            break
        if interruption_deadline is not None and now >= interruption_deadline:
            terminal_status = "interrupted_without_terminal_status"
            break

        time.sleep(1.0)

    return (
        terminal_status,
        samples,
        memory_breach,
        interruption_reason,
        interruption_error,
    )


def main() -> int:
    """Execute the bounded true-agent smoke task and leave JSON evidence for the PowerShell gate."""

    arguments = parse_args()
    arguments.events_path.parent.mkdir(parents=True, exist_ok=True)
    arguments.events_path.write_text("", encoding="utf-8")
    arguments.resources_path.write_text("", encoding="utf-8")
    evidence = RunEvidence()
    conversation: Any | None = None
    terminal_status = "not_started"
    samples: list[dict[str, Any]] = []
    memory_breach = False
    interruption_reason: str | None = None
    interruption_error: str | None = None
    failure: str | None = None

    prompt = (
        "Tu travailles uniquement dans le projet courant /projects/OpenHands_SmokeTest. "
        "N'utilise ni reseau, ni telechargement, ni service externe, ni git, ni fichier hors du projet. "
        "Avec tes outils OpenHands, lis separement et dans cet ordre README.md, pricing.py puis test_pricing.py. "
        "Emets exactement un seul appel outil par tour et attends son observation avant le suivant. "
        "Lance ensuite exactement `python -m unittest -v` et observe les deux echecs. "
        "Apres ce test rouge, modifie uniquement pricing.py : utilise file_editor avec deux remplacements explicites si disponible, "
        "et utilise pour old_str/new_str des extraits observes verbatim, en preservant exactement les guillemets et caracteres, "
        "jamais des exemples ou des placeholders. "
        "sinon une commande terminal d'ecriture qui cible explicitement pricing.py. Ne modifie ni README.md ni les tests. "
        "Relance exactement `python -m unittest -v` et attends le resultat vert. Si un test reste rouge, ne termine pas : "
        "relis pricing.py, applique la correction restante, puis reteste jusqu'a ce que les deux tests soient verts. "
        "N'appelle jamais finish avant d'avoir observe les deux tests verts. Ne reponds pas seulement avec une explication : "
        "execute reellement les outils. Termine par un bref resume factuel des deux changements et du resultat des tests."
    )

    try:
        agent = build_agent(arguments.model_alias, arguments.context_size)
        workspace = Workspace(host=arguments.server_url, working_dir=".")

        def persist_agent_event(event: Any) -> None:
            """Forward each SDK callback to the evidence recorder bound to this run."""

            record_event(event, evidence, arguments.events_path, "websocket_callback")

        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            callbacks=[persist_agent_event],
            max_iteration_per_run=40,
            delete_on_close=False,
        )
        conversation.send_message(prompt)
        (
            terminal_status,
            samples,
            memory_breach,
            interruption_reason,
            interruption_error,
        ) = wait_for_conversation(conversation, arguments, evidence)
        if interruption_reason is not None:
            failure = f"run_interrupted:{interruption_reason}"
        try:
            # The callback can omit server-side tool events; collect the local official REST history before close().
            collect_server_history(
                conversation,
                arguments.server_url,
                evidence,
                arguments.events_path,
            )
        except Exception as history_error:
            with evidence.lock:
                evidence.history_sync_error = f"{type(history_error).__name__}: {history_error}"
                evidence.major_errors.append("RemoteHistoryError")
            failure = failure or f"remote_history_error:{type(history_error).__name__}: {history_error}"
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    finally:
        if conversation is not None:
            try:
                conversation.close()
            except Exception as close_error:
                failure = failure or f"close_error:{type(close_error).__name__}: {close_error}"

    summary = summarize_evidence(evidence)
    minimum_available = min(
        (sample["system_available_ram_bytes"] for sample in samples),
        default=None,
    )
    maximum_committed = max(
        (sample["system_committed_bytes"] for sample in samples),
        default=None,
    )
    result = {
        "context_size": arguments.context_size,
        "server_url": arguments.server_url,
        "model": f"openai/{arguments.model_alias}",
        "terminal_status": terminal_status,
        "memory_breach": memory_breach,
        "minimum_available_ram_bytes": minimum_available,
        "minimum_memory_classification": (
            classify_available_memory(minimum_available, arguments)
            if minimum_available is not None
            else None
        ),
        "maximum_system_committed_bytes": maximum_committed,
        "samples": len(samples),
        "interruption_reason": interruption_reason,
        "interruption_error": interruption_error,
        "failure": failure,
        "evidence": summary,
    }
    write_json_atomically(arguments.result_path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))

    if memory_breach:
        return 3
    if (
        failure is not None
        or interruption_reason is not None
        or terminal_status != "finished"
        or summary["major_error_events"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""One bounded offline operation over stdio. No HTTP listener or audio files."""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.model_registry import load_model_registry
from app.voice import VoiceEngineError, VoiceError, synthesize, transcribe, voice_status


def own_windows_job() -> int:
    """Terminate this worker and inherited children together when the owner disappears."""
    if os.name != "nt":
        raise VoiceError("Le cycle de vie vocal est disponible uniquement sous Windows.")

    class BasicLimits(ctypes.Structure):
        """Native JOBOBJECT_BASIC_LIMIT_INFORMATION, pointer-sized fields included."""
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class ExtendedLimits(ctypes.Structure):
        """Native extended limits, with counters and memory bounds in ABI order."""
        _fields_ = [("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise VoiceError("La protection du processus vocal n’a pas pu être établie.")
    # The handle deliberately stays open until process exit, including forced cancellation.
    return handle


def watch_owner() -> None:
    """Vite keeps stdin open; EOF means cancellation or owner death, never another request."""
    try:
        # A blocking read on Windows can deadlock a native library's stdin probe.
        # Peek only while this short-lived worker exists; EOF cancels the whole job.
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.PeekNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        handle = msvcrt.get_osfhandle(0)
        available = wintypes.DWORD()
        pause = threading.Event()
        while kernel.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
            if available.value:
                break
            pause.wait(0.1)
    finally:
        os._exit(64)


def main() -> None:
    """Read exactly one JSON line and expose only controlled public diagnostics."""
    try:
        job = own_windows_job()
        if len(sys.argv) != 2 or sys.argv[1] not in ("status", "transcribe", "speak"):
            raise VoiceError("Opération vocale inconnue.")
        action = sys.argv[1]
        raw = sys.stdin.buffer.readline(5_200_001)
        if len(raw) > 5_200_000 or not raw.endswith(b"\n"):
            raise VoiceError("Requête vocale trop grande ou incomplète.")
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise VoiceError("Requête vocale invalide.")
        threading.Thread(target=watch_owner, daemon=True).start()
        registry = load_model_registry(os.environ.get("LEA_MODEL_REGISTRY") or None)
        if action == "status" and not body:
            value = voice_status(registry)
        elif action == "transcribe" and set(body) == {"audio", "language"}:
            value = transcribe(registry, base64.b64decode(body["audio"], validate=True), body["language"])
        elif action == "speak" and set(body) == {"text", "voice_id", "rate"}:
            value = synthesize(registry, body["text"], body["voice_id"], body["rate"])
            value["audio"] = base64.b64encode(value["audio"]).decode("ascii")
        else:
            raise VoiceError("Requête vocale invalide.")
        reply = {"status": 200, "body": value}
    except VoiceEngineError as error:
        reply = {"status": 503, "body": {"detail": str(error)}}
    except VoiceError as error:
        reply = {"status": 422, "body": {"detail": str(error)}}
    except Exception:
        reply = {"status": 503, "body": {"detail": "Le moteur vocal local est indisponible ou son traitement a échoué."}}
    print(json.dumps(reply, ensure_ascii=True), flush=True)
    # Exit closes the job handle and all native children, without interpreter teardown.
    os._exit(0)


if __name__ == "__main__":
    main()

"""Read-only, in-memory resource supervision. Never owns or stops a workload."""

from __future__ import annotations

import asyncio
import ctypes
import math
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Awaitable, Callable

from .model_registry import ResourcePolicy


class MemoryStatusEx(ctypes.Structure):
    """Windows available RAM includes reclaimable cache, not merely free pages."""

    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong) for name in (
            "total", "available", "page_total", "page_available",
            "virtual_total", "virtual_available", "extended_available",
        )
    ]


def memory_values(total: float, available: float) -> dict | None:
    """Reject partial, impossible or non-finite readings instead of inventing zero."""

    if not all(math.isfinite(value) for value in (total, available)) or not 0 <= available <= total or total <= 0:
        return None
    return {"total_bytes": total, "available_bytes": available, "used_bytes": total - available}


class WindowsCounters:
    """Read RAM and interval-averaged CPU directly, without WMI or a shell process."""

    def __init__(self) -> None:
        """Keep only the previous system CPU counters; the first CPU reading is unknown."""

        self.previous: tuple[int, int] | None = None

    def sample(self) -> tuple[dict | None, float | None]:
        """Return available physical RAM and CPU since the previous sample."""

        if os.name != "nt":
            return None, None
        kernel = ctypes.windll.kernel32
        memory = MemoryStatusEx()
        memory.length = ctypes.sizeof(memory)
        ram = memory_values(memory.total, memory.available) if kernel.GlobalMemoryStatusEx(ctypes.byref(memory)) else None
        idle, kernel_time, user = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if not kernel.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel_time), ctypes.byref(user)):
            self.previous = None
            return ram, None
        current = (idle.value, kernel_time.value + user.value)
        cpu = None
        if self.previous is not None:
            idle_delta, total_delta = (current[index] - self.previous[index] for index in (0, 1))
            if total_delta > 0 and 0 <= idle_delta <= total_delta:
                cpu = round(100 * (1 - idle_delta / total_delta), 1)
        self.previous = current
        return ram, cpu


async def gpu_memory() -> dict | None:
    """Query the installed NVIDIA tool at most every 30 seconds, with a bounded child."""

    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/nvidia-smi.exe"
    if not executable.is_file():
        return None
    try:
        child = await asyncio.create_subprocess_exec(
            str(executable), "--query-gpu=memory.total,memory.free", "--format=csv,noheader,nounits",
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return None
    try:
        output, _ = await asyncio.wait_for(child.communicate(), timeout=5)
    except (TimeoutError, asyncio.CancelledError) as error:
        if child.returncode is None:
            child.kill()
        await child.communicate()
        if isinstance(error, asyncio.CancelledError):
            raise
        return None
    try:
        # This PC has one GPU. Multiple devices are not silently summed into
        # one fictitious allocation pool usable by the model.
        lines = output.decode("ascii").strip().splitlines()
        if child.returncode != 0 or len(lines) != 1:
            return None
        total, available = (float(value.strip()) * 1024**2 for value in lines[0].split(","))
        return memory_values(total, available)
    except (UnicodeError, ValueError):
        return None


class ResourceAlerts:
    """Apply persistence and recovery margins to a small, bounded set of alert codes."""

    def __init__(self, policy: ResourcePolicy) -> None:
        """Reuse profile RAM/VRAM thresholds instead of guessing percentages."""

        self.policy = policy
        self.ram_level = 0
        self.ram_candidate = (0, 0)
        self.cpu_high = 0
        self.cpu_low = 0
        self.cpu_warning = False
        self.gpu_low = 0
        self.gpu_warning = False

    def evaluate(self, ram: dict | None, cpu: float | None, gpu: dict | None, services: dict, *, fresh_gpu: bool) -> tuple[str, list[str]]:
        """Change stable alerts only; no notifications, retries or lifecycle calls occur here."""

        alerts: list[str] = []
        critical = False
        if ram is None:
            alerts.append("Mesure de RAM indisponible.")
        else:
            available = ram["available_bytes"]
            warning = self.policy.system_available_warning_bytes
            danger = self.policy.system_available_critical_bytes
            # One GiB of recovery margin avoids oscillation around the thresholds.
            candidate = 2 if available < danger else 1 if available < warning else 0
            if self.ram_level == 2 and available < danger + 1024**3:
                candidate = 2
            elif self.ram_level == 1 and candidate == 0 and available < warning + 1024**3:
                candidate = 1
            count = self.ram_candidate[1] + 1 if candidate == self.ram_candidate[0] else 1
            self.ram_candidate = (candidate, min(count, 2))
            if count >= 2:
                self.ram_level = candidate
        if self.ram_level:
            critical = self.ram_level == 2
            alerts.append("RAM disponible critique." if critical else "RAM disponible faible.")
        self.cpu_high = min(self.cpu_high + 1, 3) if cpu is not None and cpu >= 90 else 0
        self.cpu_low = min(self.cpu_low + 1, 2) if cpu is not None and cpu < 80 else 0
        if self.cpu_high >= 3:
            self.cpu_warning = True
        if self.cpu_low >= 2:
            self.cpu_warning = False
        if cpu is None:
            alerts.append("Mesure CPU en attente ou indisponible.")
        if self.cpu_warning:
            alerts.append("Charge CPU élevée persistante.")
        if fresh_gpu:
            low = gpu is not None and gpu["available_bytes"] < self.policy.vram_target_free_mib * 1024**2
            self.gpu_low = min(self.gpu_low + 1, 2) if low else 0
            if self.gpu_low >= 2:
                self.gpu_warning = True
            if gpu is not None and gpu["available_bytes"] >= (self.policy.vram_target_free_mib + 256) * 1024**2:
                self.gpu_warning = False
        if self.gpu_warning:
            alerts.append("Marge VRAM faible persistante.")
        if services.get("openhands_required") and not services.get("docker_available"):
            alerts.append("Docker est indisponible ; ouvre Docker Desktop manuellement.")
        if not services.get("model_available") and not services.get("loading"):
            alerts.append("Le modèle actif ne répond pas ; son état est incertain.")
        if services.get("run_active") and (
            not services.get("model_available")
            or (services.get("openhands_required") and (
                not services.get("docker_available") or not services.get("agent_server_available")
            ))
        ):
            critical = True
            alerts.append("Un service indispensable au run ne répond plus. Vérifie le run avant toute nouvelle action.")
        return "CRITICAL" if critical else "WARNING" if alerts else "NORMAL", alerts


class ResourceMonitor:
    """One app-owned task for all active profiles, with no persistent samples."""

    interval = 10.0
    gpu_interval = 30.0

    def __init__(self, policy: ResourcePolicy, services: Callable[[], Awaitable[dict]]) -> None:
        """Inject the existing readiness owner, not another process lifecycle manager."""

        self.services = services
        self.policy = policy
        self.counters = WindowsCounters()
        self.alerts = ResourceAlerts(policy)
        self.active = False
        self.profile_id: str | None = None
        self.closed = False
        self.task: asyncio.Task | None = None
        self.wake = asyncio.Event()
        self.latest: dict = {}
        self.gpu: dict | None = None
        self.gpu_at = 0.0

    def start(self) -> None:
        """Start once; repeated calls cannot create parallel sampling loops."""

        if self.task is None and not self.closed:
            self.task = asyncio.create_task(self._loop())

    def set_active(
        self, active: bool, *, profile_id: str | None = None, policy: ResourcePolicy | None = None
    ) -> None:
        """Reuse the same loop across profiles, discarding their obsolete service alerts."""

        next_policy = policy if policy is not None else self.policy
        if active != self.active or profile_id != self.profile_id or next_policy != self.policy:
            # System counters and the GPU cache remain valid across a profile
            # switch; only a real start/stop resets their sampling interval.
            if active != self.active:
                self.counters.previous = None
                self.gpu_at = 0.0
            self.active = active
            self.profile_id = profile_id
            self.policy = next_policy
            self.alerts = ResourceAlerts(self.policy)
            self.latest = {}
            self.wake.set()

    def snapshot(self) -> dict:
        """Serve cached values only; HTTP clients cannot trigger OS probes."""

        return {
            "active": self.active,
            "stale": not self.latest or time.time() - self.latest["sampled_at"] > 35,
            **deepcopy(self.latest),
        }

    async def sample(self) -> dict:
        """Collect bounded readings and record their age and collection cost in RAM."""

        started = time.monotonic()
        profile_id, alerts = self.profile_id, self.alerts
        ram, cpu = self.counters.sample()
        fresh_gpu = started - self.gpu_at >= self.gpu_interval
        if fresh_gpu:
            self.gpu = await gpu_memory()
            self.gpu_at = started
        services = await self.services()
        level, messages = alerts.evaluate(ram, cpu, self.gpu, services, fresh_gpu=fresh_gpu)
        return {
            "profile_id": profile_id,
            "sampled_at": time.time(), "ram": ram, "cpu_percent": cpu, "vram": self.gpu,
            "gpu_age_seconds": round(time.monotonic() - self.gpu_at, 2),
            "services": services, "level": level, "messages": messages,
            "collection_ms": round((time.monotonic() - started) * 1000, 2),
        }

    async def _loop(self) -> None:
        """Wait while idle and finish every in-flight bounded probe before shutdown."""

        while not self.closed:
            self.wake.clear()
            if self.active:
                alerts = self.alerts
                try:
                    value = await self.sample()
                    # A probe started for the previous profile cannot republish
                    # its Docker/model warnings after a switch or shutdown.
                    if self.active and self.alerts is alerts:
                        self.latest = value
                except Exception:
                    # Invalidate the snapshot; a failed probe is never healthy.
                    if self.alerts is alerts:
                        self.latest = {}
            if self.closed:
                break
            try:
                await asyncio.wait_for(self.wake.wait(), self.interval if self.active else None)
            except TimeoutError:
                pass

    async def close(self) -> None:
        """Release the single task without abandoning an NVIDIA child process."""

        self.closed = True
        self.active = False
        self.wake.set()
        if self.task is not None:
            await self.task
            self.task = None

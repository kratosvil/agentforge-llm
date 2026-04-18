"""
Monitor de recursos del sistema durante la ejecucion de tareas AgentForge.

Captura CPU y RAM muestreando cada segundo en background usando asyncio.
Al detener el monitor escribe perf_report.json en el directorio de la tarea.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psutil


@dataclass
class PerfSample:
    ts: str
    cpu_percent: float
    ram_used_mb: float
    ram_percent: float
    swap_used_mb: float


@dataclass
class PerfReport:
    task_id: str
    started_at: str
    finished_at: str
    duration_seconds: float
    samples: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class PerfMonitor:
    """Muestrea CPU/RAM cada segundo mientras corre una tarea."""

    def __init__(self, task_id: str, task_dir: Path, interval: float = 1.0):
        self._task_id = task_id
        self._task_dir = task_dir
        self._interval = interval
        self._samples: list[PerfSample] = []
        self._started_at: datetime | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._started_at = datetime.now(timezone.utc)
        # primer sample de cpu_percent necesita un intervalo previo — inicializar
        psutil.cpu_percent(interval=None)
        self._task = asyncio.create_task(self._sample_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._write_report()

    async def _sample_loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            self._capture()

    def _capture(self) -> None:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        self._samples.append(PerfSample(
            ts=datetime.now(timezone.utc).isoformat(),
            cpu_percent=cpu,
            ram_used_mb=round(mem.used / 1024 / 1024, 1),
            ram_percent=mem.percent,
            swap_used_mb=round(swap.used / 1024 / 1024, 1),
        ))

    def _write_report(self) -> None:
        finished_at = datetime.now(timezone.utc)
        duration = (finished_at - self._started_at).total_seconds() if self._started_at else 0.0

        samples_dict = [s.__dict__ for s in self._samples]

        summary: dict = {}
        if self._samples:
            cpus = [s.cpu_percent for s in self._samples]
            rams = [s.ram_used_mb for s in self._samples]
            summary = {
                "avg_cpu_percent": round(sum(cpus) / len(cpus), 1),
                "peak_cpu_percent": round(max(cpus), 1),
                "avg_ram_mb": round(sum(rams) / len(rams), 1),
                "peak_ram_mb": round(max(rams), 1),
                "peak_ram_percent": round(max(s.ram_percent for s in self._samples), 1),
                "peak_swap_mb": round(max(s.swap_used_mb for s in self._samples), 1),
                "sample_count": len(self._samples),
            }

        report = PerfReport(
            task_id=self._task_id,
            started_at=self._started_at.isoformat() if self._started_at else "",
            finished_at=finished_at.isoformat(),
            duration_seconds=round(duration, 3),
            samples=samples_dict,
            summary=summary,
        )

        out = self._task_dir / "perf_report.json"
        out.write_text(json.dumps(report.__dict__, indent=2), encoding="utf-8")

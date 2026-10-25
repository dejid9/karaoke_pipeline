from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import itertools
import threading
import time
from typing import Optional


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    id: str
    source: str
    title: str
    stage: str
    progress: Optional[float]
    status: str
    started_at: float
    updated_at: float
    finished_at: Optional[float] = None
    detail: str = ""

    @property
    def running(self) -> bool:
        return self.status == "running"

    @property
    def percent_text(self) -> str:
        if self.progress is None:
            return "—"
        return f"{max(0.0, min(100.0, self.progress)):.0f}%"


@dataclass(frozen=True, slots=True)
class LogEntry:
    seq: int
    timestamp: float
    source: str
    level: str
    message: str
    task_id: Optional[str] = None

    @property
    def time_text(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")


class TaskHandle:
    def __init__(self, center: "TaskCenter", task_id: str):
        self.center = center
        self.id = task_id

    def update(self, progress: Optional[float] = None, stage: Optional[str] = None, detail: Optional[str] = None) -> None:
        self.center.update(self.id, progress=progress, stage=stage, detail=detail)

    def log(self, message: str, level: str = "INFO") -> None:
        self.center.log(message, source=self.center.task(self.id).source if self.center.task(self.id) else "Task", level=level, task_id=self.id)

    def done(self, message: str = "Готово") -> None:
        self.center.finish(self.id, message)

    def fail(self, message: str) -> None:
        self.center.fail(self.id, message)

    def cancel(self, message: str = "Отменено") -> None:
        self.center.cancel(self.id, message)


class TaskCenter:
    """Thread-safe task/progress and log store.

    Worker threads never touch Tk. The GUI polls snapshots periodically, which
    avoids Tkinter cross-thread callbacks and also makes high-frequency FFmpeg
    progress updates cheap.
    """

    def __init__(self, *, max_logs: int = 10000, max_tasks: int = 300):
        self.max_logs = max_logs
        self.max_tasks = max_tasks
        self._lock = threading.RLock()
        self._task_counter = itertools.count(1)
        self._log_counter = itertools.count(1)
        self._tasks: dict[str, TaskSnapshot] = {}
        self._order: list[str] = []
        self._logs: list[LogEntry] = []
        self._revision = 0

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def start(self, source: str, title: str, *, stage: str = "Подготовка", progress: Optional[float] = 0.0, detail: str = "") -> TaskHandle:
        now = time.time()
        task_id = f"task-{next(self._task_counter)}"
        snap = TaskSnapshot(task_id, source, title, stage, self._norm(progress), "running", now, now, None, detail)
        with self._lock:
            self._tasks[task_id] = snap
            self._order.append(task_id)
            self._trim_tasks_locked()
            self._revision += 1
        self.log(f"{title}: {stage}", source=source, level="START", task_id=task_id)
        return TaskHandle(self, task_id)

    def task(self, task_id: str) -> Optional[TaskSnapshot]:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: str, *, progress: Optional[float] = None, stage: Optional[str] = None, detail: Optional[str] = None) -> None:
        with self._lock:
            old = self._tasks.get(task_id)
            if old is None or old.status != "running":
                return
            new_progress = old.progress if progress is None and stage is None else self._norm(progress) if progress is not None else old.progress
            new = replace(
                old,
                progress=new_progress,
                stage=stage if stage is not None else old.stage,
                detail=detail if detail is not None else old.detail,
                updated_at=time.time(),
            )
            self._tasks[task_id] = new
            self._revision += 1

    def set_indeterminate(self, task_id: str, stage: Optional[str] = None) -> None:
        with self._lock:
            old = self._tasks.get(task_id)
            if old is None or old.status != "running":
                return
            self._tasks[task_id] = replace(old, progress=None, stage=stage or old.stage, updated_at=time.time())
            self._revision += 1

    def finish(self, task_id: str, message: str = "Готово") -> None:
        self._terminal(task_id, "done", message, 100.0, "DONE")

    def fail(self, task_id: str, message: str) -> None:
        self._terminal(task_id, "error", message, None, "ERROR")

    def cancel(self, task_id: str, message: str = "Отменено") -> None:
        self._terminal(task_id, "cancelled", message, None, "CANCEL")

    def _terminal(self, task_id: str, status: str, message: str, progress: Optional[float], level: str) -> None:
        source = "Task"
        with self._lock:
            old = self._tasks.get(task_id)
            if old is None or old.status != "running":
                return
            source = old.source
            now = time.time()
            self._tasks[task_id] = replace(old, status=status, stage=message or old.stage, progress=self._norm(progress), updated_at=now, finished_at=now)
            self._revision += 1
        self.log(message, source=source, level=level, task_id=task_id)

    def log(self, message: str, *, source: str = "App", level: str = "INFO", task_id: Optional[str] = None) -> None:
        if message is None:
            return
        lines = str(message).replace("\r\n", "\n").replace("\r", "\n").split("\n")
        now = time.time()
        with self._lock:
            for line in lines:
                if not line and len(lines) > 1:
                    continue
                self._logs.append(LogEntry(next(self._log_counter), now, source, level.upper(), line, task_id))
            if len(self._logs) > self.max_logs:
                del self._logs[: len(self._logs) - self.max_logs]
            self._revision += 1

    def tasks(self) -> tuple[TaskSnapshot, ...]:
        with self._lock:
            return tuple(self._tasks[tid] for tid in self._order if tid in self._tasks)

    def active_tasks(self) -> tuple[TaskSnapshot, ...]:
        return tuple(task for task in self.tasks() if task.running)

    def latest_active(self) -> Optional[TaskSnapshot]:
        with self._lock:
            for tid in reversed(self._order):
                task = self._tasks.get(tid)
                if task and task.running:
                    return task
        return None

    def logs_since(self, seq: int = 0) -> tuple[LogEntry, ...]:
        with self._lock:
            return tuple(entry for entry in self._logs if entry.seq > seq)

    def all_logs(self) -> tuple[LogEntry, ...]:
        with self._lock:
            return tuple(self._logs)

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()
            self._revision += 1

    def _trim_tasks_locked(self) -> None:
        while len(self._order) > self.max_tasks:
            victim = self._order[0]
            task = self._tasks.get(victim)
            if task is not None and task.running:
                break
            self._order.pop(0)
            self._tasks.pop(victim, None)

    @staticmethod
    def _norm(progress: Optional[float]) -> Optional[float]:
        if progress is None:
            return None
        try:
            return max(0.0, min(100.0, float(progress)))
        except (TypeError, ValueError):
            return None

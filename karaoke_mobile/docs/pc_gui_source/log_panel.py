from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Optional

from karaoke_gui.task_center import TaskCenter
from karaoke_gui.theme import ThemePalette, apply_text_theme


class LogPanel(ttk.Frame):
    def __init__(self, master, *, task_center: TaskCenter):
        super().__init__(master, padding=8)
        self.task_center = task_center
        self._last_log_seq = 0
        self._last_revision = -1
        self._task_rows: set[str] = set()
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.source_var = tk.StringVar(value="Все")
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="Фоновые задачи и логи", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="Источник:").pack(side="left", padx=(18, 4))
        self.source_combo = ttk.Combobox(header, textvariable=self.source_var, state="readonly", width=16, values=("Все",))
        self.source_combo.pack(side="left")
        self.source_combo.bind("<<ComboboxSelected>>", lambda _e: self.rebuild_logs())
        ttk.Checkbutton(header, text="Автопрокрутка", variable=self.autoscroll_var).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Сохранить лог…", command=self.save_log).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Очистить", command=self.clear_logs).pack(side="right")

        paned = ttk.Panedwindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        task_frame = ttk.Frame(paned)
        log_frame = ttk.Frame(paned)
        paned.add(task_frame, weight=1)
        paned.add(log_frame, weight=3)

        columns = ("state", "source", "title", "stage", "progress", "elapsed")
        self.tasks = ttk.Treeview(task_frame, columns=columns, show="headings", height=8)
        for col, title, width in (
            ("state", "Состояние", 95), ("source", "Источник", 100), ("title", "Задача", 230),
            ("stage", "Этап", 300), ("progress", "%", 70), ("elapsed", "Время", 85),
        ):
            self.tasks.heading(col, text=title)
            self.tasks.column(col, width=width, stretch=col in {"title", "stage"})
        y = ttk.Scrollbar(task_frame, orient="vertical", command=self.tasks.yview)
        self.tasks.configure(yscrollcommand=y.set)
        self.tasks.pack(side="left", fill="both", expand=True)
        y.pack(side="right", fill="y")

        self.log_text = tk.Text(log_frame, wrap="none", undo=False, height=18)
        y2 = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        x2 = ttk.Scrollbar(log_frame, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=y2.set, xscrollcommand=x2.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        y2.grid(row=0, column=1, sticky="ns")
        x2.grid(row=1, column=0, sticky="ew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text.configure(state="disabled")

    def apply_theme(self, palette: ThemePalette) -> None:
        apply_text_theme(self.log_text, palette)
        self.log_text.tag_configure("ERROR", foreground=palette.danger)
        self.log_text.tag_configure("CANCEL", foreground=palette.warning)
        self.log_text.tag_configure("START", foreground=palette.accent)
        self.log_text.tag_configure("DONE", foreground=palette.success)
        self.log_text.tag_configure("WARN", foreground=palette.warning)

    def project_state(self) -> dict:
        return {
            "autoscroll": bool(self.autoscroll_var.get()),
            "source": self.source_var.get(),
        }

    def apply_project_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        if "autoscroll" in state:
            self.autoscroll_var.set(bool(state["autoscroll"]))
        if "source" in state:
            self.source_var.set(str(state["source"]))

    def refresh(self) -> None:
        revision = self.task_center.revision
        if revision == self._last_revision:
            return
        self._last_revision = revision
        self._refresh_tasks()
        self._refresh_sources()
        # Incremental append is valid only when showing all sources.
        if self.source_var.get() == "Все":
            entries = self.task_center.logs_since(self._last_log_seq)
            if entries:
                self._append_entries(entries)
                self._last_log_seq = max(e.seq for e in entries)
        else:
            self.rebuild_logs()

    def _refresh_tasks(self) -> None:
        now = __import__("time").time()
        current = set()
        for task in self.task_center.tasks():
            current.add(task.id)
            elapsed_end = task.finished_at or now
            elapsed = max(0.0, elapsed_end - task.started_at)
            mm, ss = divmod(int(elapsed), 60)
            state = {"running": "Выполняется", "done": "Готово", "error": "Ошибка", "cancelled": "Отменено"}.get(task.status, task.status)
            values = (state, task.source, task.title, task.stage, task.percent_text, f"{mm:02d}:{ss:02d}")
            if task.id in self._task_rows:
                self.tasks.item(task.id, values=values)
            else:
                self.tasks.insert("", "end", iid=task.id, values=values)
                self._task_rows.add(task.id)
        for stale in tuple(self._task_rows - current):
            self.tasks.delete(stale)
            self._task_rows.discard(stale)
        children = self.tasks.get_children()
        if children:
            self.tasks.see(children[-1])

    def _refresh_sources(self) -> None:
        names = sorted({e.source for e in self.task_center.all_logs()})
        values = ("Все", *names)
        if tuple(self.source_combo.cget("values")) != values:
            self.source_combo.configure(values=values)

    def _append_entries(self, entries) -> None:
        self.log_text.configure(state="normal")
        for entry in entries:
            prefix = f"[{entry.time_text}] [{entry.source}] [{entry.level}] "
            self.log_text.insert("end", prefix)
            self.log_text.insert("end", entry.message + "\n", entry.level)
        self.log_text.configure(state="disabled")
        if self.autoscroll_var.get():
            self.log_text.see("end")

    def rebuild_logs(self) -> None:
        selected = self.source_var.get()
        entries = self.task_center.all_logs()
        if selected != "Все":
            entries = tuple(e for e in entries if e.source == selected)
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._append_entries(entries)
        self._last_log_seq = max((e.seq for e in self.task_center.all_logs()), default=0)

    def clear_logs(self) -> None:
        self.task_center.clear_logs()
        self._last_log_seq = 0
        self.rebuild_logs()

    def save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Сохранить лог", defaultextension=".log", filetypes=(("Log", "*.log"), ("Text", "*.txt"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        lines = [f"[{e.time_text}] [{e.source}] [{e.level}] {e.message}" for e in self.task_center.all_logs()]
        Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from karaoke_gui.timeline import format_clock


def slice_audio(
    media_path: str | Path,
    target_path: str | Path,
    start_s: float,
    end_s: float,
    *,
    ffmpeg: str | Path = "ffmpeg",
    format_choice: str = "mp3",
    bitrate: str = "192k",
) -> None:
    """Slice an audio excerpt from media_path between start_s and end_s using FFmpeg."""
    start_s = max(0.0, float(start_s))
    end_s = max(start_s + 0.05, float(end_s))
    duration = end_s - start_s

    media_path = Path(media_path).resolve()
    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{start_s:.6f}",
        "-t", f"{duration:.6f}",
        "-i", str(media_path),
        "-vn",
    ]

    ext = target_path.suffix.lower()
    if ext == ".mp3" or format_choice.lower() == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif ext == ".wav" or format_choice.lower() == "wav":
        cmd += ["-c:a", "pcm_s16le"]
    elif ext in {".m4a", ".aac"}:
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif ext in {".flac"}:
        cmd += ["-c:a", "flac"]
    else:
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]

    cmd.append(str(target_path))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip() or f"FFmpeg exited with code {proc.returncode}"
        raise RuntimeError(f"Не удалось экспортировать аудио: {err}")


class AudioExportDialog(tk.Toplevel):
    """Dialog to choose range, padding, format and destination for audio excerpt export."""

    def __init__(
        self,
        master,
        *,
        media_path: Path,
        ffmpeg: str | Path,
        selection_range: Optional[tuple[float, float, str]] = None,
        burst_range: Optional[tuple[float, float, str]] = None,
        project_root: Optional[Path] = None,
        on_play: Optional[Callable[[float, float], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self.owner = master.winfo_toplevel()
        self.title("Экспорт аудио-отрывка")
        self.transient(self.owner)
        self.resizable(False, False)

        self.media_path = Path(media_path).resolve()
        self.ffmpeg = ffmpeg
        self.selection_range = selection_range
        self.burst_range = burst_range
        self.project_root = project_root
        self.on_play = on_play
        self.on_stop = on_stop

        palette = getattr(master, "palette", None)
        if palette is not None:
            self.configure(background=palette.bg)

        # Range choice
        if selection_range is not None and burst_range is not None:
            # Check if ranges are substantially different (> 0.05s)
            diff = abs(selection_range[0] - burst_range[0]) + abs(selection_range[1] - burst_range[1])
            has_both = diff > 0.05
        else:
            has_both = False

        self.range_choice_var = tk.StringVar(value="selection" if selection_range is not None else "burst")
        self.padding_var = tk.StringVar(value="0.1")
        self.format_var = tk.StringVar(value="MP3")

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Экспорт аудио-отрывка для подтверждения", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text=f"Медиа-источник: {self.media_path.name}",
            style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        range_frame = ttk.LabelFrame(body, text="Диапазон отрывка", padding=8)
        range_frame.pack(fill="x", pady=(0, 10))

        if has_both and selection_range is not None and burst_range is not None:
            s_dur = selection_range[1] - selection_range[0]
            b_dur = burst_range[1] - burst_range[0]
            s_label = f"Выделенные слоги: {format_clock(selection_range[0])} — {format_clock(selection_range[1])} ({s_dur:.2f} с)"
            if selection_range[2]:
                s_label += f" · «{selection_range[2][:30]}»"
            b_label = f"Весь бёрст: {format_clock(burst_range[0])} — {format_clock(burst_range[1])} ({b_dur:.2f} с)"
            if burst_range[2]:
                b_label += f" · «{burst_range[2][:30]}»"

            ttk.Radiobutton(
                range_frame, text=s_label, variable=self.range_choice_var, value="selection",
                command=self._update_default_path,
            ).pack(anchor="w", pady=2)
            ttk.Radiobutton(
                range_frame, text=b_label, variable=self.range_choice_var, value="burst",
                command=self._update_default_path,
            ).pack(anchor="w", pady=2)
        else:
            active_range = selection_range or burst_range or (0.0, 1.0, "")
            label_prefix = "Выделенные слоги" if selection_range is not None else "Бёрст"
            dur = active_range[1] - active_range[0]
            text_str = f" · «{active_range[2][:40]}»" if active_range[2] else ""
            ttk.Label(
                range_frame,
                text=f"{label_prefix}: {format_clock(active_range[0])} — {format_clock(active_range[1])} ({dur:.2f} с){text_str}",
            ).pack(anchor="w", pady=4)

        opt_frame = ttk.Frame(body)
        opt_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(opt_frame, text="Отступ по краям:").pack(side="left", padx=(0, 4))
        self.padding_combo = ttk.Combobox(
            opt_frame,
            textvariable=self.padding_var,
            values=("0.0", "0.05", "0.1", "0.2", "0.3", "0.5", "1.0"),
            width=6,
            state="readonly",
        )
        self.padding_combo.pack(side="left")
        ttk.Label(opt_frame, text="с  (добавит контекст звука)", style="CardMuted.TLabel").pack(side="left", padx=(4, 16))

        ttk.Label(opt_frame, text="Формат:").pack(side="left", padx=(0, 4))
        self.format_combo = ttk.Combobox(
            opt_frame,
            textvariable=self.format_var,
            values=("MP3 (192 kbps)", "WAV (PCM 16-bit)", "M4A / AAC"),
            width=14,
            state="readonly",
        )
        self.format_combo.pack(side="left")
        self.format_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_format_changed())

        path_frame = ttk.LabelFrame(body, text="Файл для сохранения", padding=8)
        path_frame.pack(fill="x", pady=(0, 12))

        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, width=54)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(path_frame, text="Обзор…", command=self._browse_path, style="Secondary.TButton").pack(side="right")

        bot_frame = ttk.Frame(body)
        bot_frame.pack(fill="x")

        # Preview buttons
        if self.on_play is not None:
            ttk.Button(bot_frame, text="▶ Прослушать", command=self._preview_play, style="Secondary.TButton").pack(side="left")
            if self.on_stop is not None:
                ttk.Button(bot_frame, text="■ Стоп", width=4, command=self.on_stop, style="Secondary.TButton").pack(side="left", padx=(3, 0))

        ttk.Button(bot_frame, text="Отмена", command=self._close).pack(side="right")
        self.export_btn = ttk.Button(bot_frame, text="Экспортировать", command=self._export, style="Accent.TButton")
        self.export_btn.pack(side="right", padx=(0, 6))

        self._update_default_path()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        try:
            x = self.owner.winfo_rootx() + max(12, (self.owner.winfo_width() - self.winfo_reqwidth()) // 2)
            y = self.owner.winfo_rooty() + max(12, (self.owner.winfo_height() - self.winfo_reqheight()) // 3)
            self.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        self.lift(self.owner)
        self.focus_force()
        self.grab_set()

    def _active_range(self) -> tuple[float, float, str]:
        if self.range_choice_var.get() == "burst" and self.burst_range is not None:
            return self.burst_range
        if self.selection_range is not None:
            return self.selection_range
        return self.burst_range or (0.0, 1.0, "")

    def _effective_times(self) -> tuple[float, float]:
        start, end, _ = self._active_range()
        try:
            pad = max(0.0, float(self.padding_var.get().replace(",", ".")))
        except ValueError:
            pad = 0.0
        return max(0.0, start - pad), end + pad

    def _extension_for_format(self) -> str:
        fmt = self.format_var.get().casefold()
        if "wav" in fmt:
            return ".wav"
        if "m4a" in fmt or "aac" in fmt:
            return ".m4a"
        return ".mp3"

    def _default_filename(self) -> str:
        start, end, _ = self._active_range()
        stem = self.media_path.stem
        tag = "burst" if self.range_choice_var.get() == "burst" else "clip"
        c_start = format_clock(start).replace(":", "-").replace(".", "_")
        c_end = format_clock(end).replace(":", "-").replace(".", "_")
        ext = self._extension_for_format()
        return f"{stem}_{tag}_{c_start}-{c_end}{ext}"

    def _update_default_path(self) -> None:
        if self.project_root is not None:
            out_dir = self.project_root / "exports"
        else:
            out_dir = self.media_path.parent
        self.path_var.set(str(out_dir / self._default_filename()))

    def _on_format_changed(self) -> None:
        current = self.path_var.get().strip()
        if current:
            new_ext = self._extension_for_format()
            p = Path(current)
            self.path_var.set(str(p.with_suffix(new_ext)))

    def _browse_path(self) -> None:
        current = self.path_var.get().strip()
        init_dir = str(Path(current).parent) if current else str(self.media_path.parent)
        init_file = Path(current).name if current else self._default_filename()
        ext = self._extension_for_format()
        filetypes = [
            ("MP3 Audio", "*.mp3"),
            ("WAV Audio", "*.wav"),
            ("M4A Audio", "*.m4a"),
            ("All files", "*.*"),
        ]
        chosen = filedialog.asksaveasfilename(
            parent=self,
            title="Сохранить аудио-отрывок",
            initialdir=init_dir,
            initialfile=init_file,
            defaultextension=ext,
            filetypes=filetypes,
        )
        if chosen:
            self.path_var.set(chosen)

    def _preview_play(self) -> None:
        if self.on_play is None:
            return
        t_start, t_end = self._effective_times()
        self.on_play(t_start, t_end)

    def _export(self) -> None:
        target_path_str = self.path_var.get().strip()
        if not target_path_str:
            messagebox.showwarning("Укажите путь", "Укажите файл для сохранения.", parent=self)
            return

        target_path = Path(target_path_str).resolve()
        if target_path.exists():
            if not messagebox.askyesno("Перезапись", f"Файл {target_path.name} уже существует. Перезаписать?", parent=self):
                return

        t_start, t_end = self._effective_times()
        fmt_choice = "wav" if ".wav" in target_path.suffix.lower() else "mp3"

        self.export_btn.configure(state="disabled", text="Экспорт…")

        def work() -> None:
            try:
                slice_audio(
                    self.media_path,
                    target_path,
                    t_start,
                    t_end,
                    ffmpeg=self.ffmpeg,
                    format_choice=fmt_choice,
                )
                self.after(0, lambda: self._on_success(target_path))
            except Exception as exc:
                self.after(0, lambda: self._on_failure(str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _on_success(self, target: Path) -> None:
        self.export_btn.configure(state="normal", text="Экспортировать")
        msg = f"Аудио-отрывок успешно сохранён:\n{target.name}\n\nОткрыть папку с файлом?"
        if messagebox.askyesno("Экспорт завершён", msg, parent=self):
            try:
                if os.name == "nt":
                    subprocess.Popen(["explorer.exe", "/select,", str(target)])
                else:
                    subprocess.Popen(["xdg-open", str(target.parent)])
            except Exception:
                pass
        self._close()

    def _on_failure(self, err_msg: str) -> None:
        self.export_btn.configure(state="normal", text="Экспортировать")
        messagebox.showerror("Ошибка экспорта", err_msg, parent=self)

    def _close(self) -> None:
        if self.on_stop is not None:
            try:
                self.on_stop()
            except Exception:
                pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

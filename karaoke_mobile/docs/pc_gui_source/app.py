from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
import unicodedata
from tkinter import filedialog, messagebox, simpledialog, ttk

from karaoke_core.ass import KaraokeTagType, format_ass_time
from karaoke_core.editor import KaraokeEditError
from karaoke_core.measurements import read_measurements, replace_measurements, save_measurements, update_measurements
from karaoke_core.media import (
    MediaPlayer, load_or_extract_waveform, load_or_extract_playback_pcm_cache,
    media_tool_subprocess_env, normalize_playback_speed, probe_media_duration, resolve_ffplay,
)
from karaoke_core.spectrogram import (
    SPEED_PRESETS, VOICE_PRESETS, SpectrogramAnalysisSettings, SpectrogramViewSettings,
    fft_size_for_expected_sps, load_or_extract_spectrogram, spectrogram_cache_path,
)
from karaoke_core.sps import fastest_legacy_window, manual_bursts, selection_audition_bounds, sps_graph_points
from karaoke_core.project import save_project as save_project_config
from karaoke_gui.session import KaraokeSession, TransferResult, build_sps_transfer
from karaoke_gui.timeline import DualTimeline, Viewport, format_clock
from karaoke_gui.sps_graph import (
    GraphExportSettings, GraphSeries, SPSGraph, ask_sps_graph_export_settings,
    render_sps_graph_png,
)
from karaoke_gui.render_panel import RenderPanel
from karaoke_gui.alignment_panel import AlignmentPanel
from karaoke_gui.task_center import TaskCenter
from karaoke_gui.log_panel import LogPanel
from karaoke_gui.scrollable import ScrollableFrame
from karaoke_gui.audio_export import AudioExportDialog
from karaoke_gui.keybindings import DEFAULT_HOTKEYS, HOTKEY_LABELS, merged_hotkeys, shortcut_to_tk, validate_hotkeys
from karaoke_gui.theme import (
    DEFAULT_THEME, apply_menu_theme, apply_text_theme, apply_ttk_theme,
    get_theme, load_ui_preferences, save_ui_preferences, theme_names,
)


PLAY_SYMBOL = "\u25b6"


class KaraokeApp(tk.Tk):
    _PROJECT_STATE_VARS = (
        "theme_var", "advanced_mode_var", "playback_warmup_var", "playback_tail_var",
        "playback_speed_var", "playback_preserve_pitch_var", "playback_return_to_start_var",
        "playback_follow_default_device_var", "playback_cursor_offset_var",
        "spectrogram_mode_var", "voice_preset_var", "speed_preset_var", "expected_sps_var",
        "sps_graph_source_var", "sps_graph_smoothing_var", "karaoke_tag_var",
        "min_sps_var", "scope_var", "autosave_mode_var",
    )

    def __init__(self):
        super().__init__()
        self.ui_preferences = load_ui_preferences()
        self.theme_var = tk.StringVar(value=str(self.ui_preferences.get("theme", DEFAULT_THEME)))
        self.advanced_mode_var = tk.BooleanVar(value=bool(self.ui_preferences.get("advanced", False)))
        self.ffmpeg_mode_var = tk.StringVar(value=str(self.ui_preferences.get("ffmpeg_mode", "portable")))
        self.ffmpeg_path_var = tk.StringVar(value=str(self.ui_preferences.get("ffmpeg_path", "")))
        self.playback_warmup_var = tk.StringVar(value=str(self.ui_preferences.get("playback_warmup_ms", 700)))
        self.playback_tail_var = tk.StringVar(value=str(self.ui_preferences.get("playback_tail_ms", 250)))
        self.playback_speed_var = tk.DoubleVar(value=float(self.ui_preferences.get("playback_speed", 1.0)))
        self.playback_speed_text_var = tk.StringVar(value=f"{self.playback_speed_var.get():.2f}×")
        self.playback_preserve_pitch_var = tk.BooleanVar(value=bool(self.ui_preferences.get("playback_preserve_pitch", True)))
        self.playback_return_to_start_var = tk.BooleanVar(value=bool(self.ui_preferences.get("playback_return_to_start", True)))
        self.playback_follow_default_device_var = tk.BooleanVar(value=bool(self.ui_preferences.get("playback_follow_default_device", True)))
        self.playback_cursor_offset_var = tk.StringVar(value=str(self.ui_preferences.get("playback_cursor_offset_ms", 0)))
        self.hotkeys = merged_hotkeys(self.ui_preferences.get("hotkeys"))
        self.playhead_time = 0.0
        self._playback_origin: float | None = None
        self._playback_return_target: float | None = None
        self._playback_was_active = False
        self._transport_mode = "idle"  # idle | normal | selection | from-start | to-stop | bounded
        self._transport_serial = 0
        self.playback_range_ids = {
            "karaoke": {"in": None, "out": None},
            "sps": {"in": None, "out": None},
        }
        self.playback_range_vars = {
            "karaoke": tk.StringVar(value="In–Out: —"),
            "sps": tk.StringVar(value="In–Out: —"),
        }
        # Independent persistent bounds for ordinary Play/Space.  They are
        # deliberately separate from the audition-only In/Out range.
        self.playback_limit_ids = {
            "karaoke": {"start": None, "stop": None},
            "sps": {"start": None, "stop": None},
        }
        self.playback_limit_vars = {
            "karaoke": tk.StringVar(value="Play: текущая позиция → конец"),
            "sps": tk.StringVar(value="Play: текущая позиция → конец"),
        }
        self._selected_fastest_window = None
        # Keep exactly one Tk polling loop for task UI and playback cursor.
        # Update 027 accidentally spawned a new infinite playback poller from
        # every task-center tick, causing callback count to grow without bound.
        self._task_poll_job = None
        self._playback_poll_job = None
        self._prime_audio_job = None
        self.palette = get_theme(self.theme_var.get())
        self.title("Karaoke SPS Workbench")
        self.geometry("1520x820")
        self.minsize(1180, 560)
        self.session = KaraokeSession()
        self.session.configure_ffmpeg(self.ffmpeg_mode_var.get(), self.ffmpeg_path_var.get())
        self.task_center = TaskCenter()
        self._task_ui_revision = -1
        self._task_progress_indeterminate = False
        self.player = MediaPlayer(
            lead_silence_seconds=self._playback_ms_value(self.playback_warmup_var.get(), 700) / 1000.0,
            tail_silence_seconds=self._playback_ms_value(self.playback_tail_var.get(), 250) / 1000.0,
            cursor_offset_seconds=self._playback_offset_ms_value(self.playback_cursor_offset_var.get(), 0) / 1000.0,
            follow_default_device=self.playback_follow_default_device_var.get(),
        )
        self.player.set_preserve_pitch(self.playback_preserve_pitch_var.get())
        self.playback_cache = None
        self._playback_cache_generation = 0
        self._playback_cache_building = False
        self.waveform = None
        self.spectrogram = None
        self.spectrogram_analysis = SpectrogramAnalysisSettings()
        try:
            saved_analysis = self.ui_preferences.get("spectrogram_analysis")
            if isinstance(saved_analysis, dict):
                candidate = SpectrogramAnalysisSettings(**saved_analysis)
                candidate.validate()
                self.spectrogram_analysis = candidate
        except (TypeError, ValueError):
            pass
        self.spectrogram_view = SpectrogramViewSettings()
        try:
            saved_view = self.ui_preferences.get("spectrogram_view")
            if isinstance(saved_view, dict):
                candidate = SpectrogramViewSettings(**saved_view)
                candidate.validate(self.spectrogram_analysis.sample_rate / 2.0)
                self.spectrogram_view = candidate
        except (TypeError, ValueError):
            pass
        self.spectrogram_mode_var = tk.StringVar(
            value=str(self.ui_preferences.get("spectrogram_mode", "Waveform"))
        )
        self.voice_preset_var = tk.StringVar(
            value=str(self.ui_preferences.get("spectrogram_voice_preset", "Средний голос"))
        )
        self.speed_preset_var = tk.StringVar(
            value=str(self.ui_preferences.get("spectrogram_speed_preset", "Средне (6–12 SPS)"))
        )
        self.expected_sps_var = tk.StringVar(
            value=str(self.ui_preferences.get("spectrogram_expected_sps", "10"))
        )
        self.sps_graph_source_var = tk.StringVar(value=str(self.ui_preferences.get("sps_graph_source", "Оба")))
        # Precise/user-facing SPS is intentionally fixed to the archived 1–2 s method.
        # Strict windows remain internal to automatic burst candidate discovery only.
        self.sps_graph_metric_var = tk.StringVar(value="Legacy 1–2 s")
        self.sps_graph_window_var = tk.StringVar(value="1.0")  # internal compatibility only
        self.sps_graph_smoothing_var = tk.StringVar(value=str(self.ui_preferences.get("sps_graph_smoothing", 1)))
        self._sps_graph_export_settings: GraphExportSettings | None = None
        self._analysis_generation = 0
        self._waveform_generation = 0
        self._spectrogram_generation = 0
        self._spectrogram_building_for = None
        self._updating_measurement_fields = False
        self.karaoke_tag_var = tk.StringVar(value="\\kf (плавный)")
        self.karaoke_selected_info_var = tk.StringVar(value="Слог: —")
        self.karaoke_text_state_var = tk.StringVar(value="")
        self.karaoke_burst_state_var = tk.StringVar(value="Burst-окраска: —")
        self.karaoke_romanize_var = tk.BooleanVar(value=False)
        self.karaoke_romanization_var = tk.StringVar(value="")
        self.autosave_mode_var = tk.StringVar(
            value=str(self.ui_preferences.get("autosave_mode", "disabled"))
        )
        self._karaoke_text_bound_id = None
        self._karaoke_text_bound_raw = None
        self._karaoke_text_drafts: dict[str, str] = {}
        self._karaoke_romanization_drafts: dict[str, str] = {}
        self._loading_karaoke_text = False
        self._loading_karaoke_romanization = False
        self._text_apply_debounce_job = None
        self._last_autosave_time = time.monotonic()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_style()
        self._build_menu()
        self._build_ui()
        self._audio_view_changed()
        self._apply_theme(save=False)
        self._apply_ui_mode(save=False)
        self._setup_text_class_bindings()
        self.bind_all("<Control-s>", lambda _e: self._save_ass_with_commit())
        self.bind_all("<Control-Shift-S>", lambda _e: self._save_ass_as_with_commit())
        self.bind_all("<Control-Cyrillic_yeru>", lambda _e: self._save_ass_with_commit())
        self.bind_all("<Control-Cyrillic_YERU>", lambda _e: self._save_ass_with_commit())
        self.bind_all("<Control-Shift-Cyrillic_yeru>", lambda _e: self._save_ass_as_with_commit())
        self.bind_all("<Control-Shift-Cyrillic_YERU>", lambda _e: self._save_ass_as_with_commit())
        self.bind_all("<F2>", lambda _e: self.focus_karaoke_text_editor())
        self.bind_all("<Control-comma>", lambda _e: self.open_settings())
        self._install_hotkeys()
        self._set_status("Готово")
        self._task_poll_job = self.after(120, self._poll_task_ui)
        self._prime_audio_job = self.after(250, self._prime_audio_output)
        self._playback_poll_job = self.after(33, self._poll_playback_cursor)
        self._autosave_poll_job = self.after(5000, self._poll_autosave_timer)

    @staticmethod
    def _playback_ms_value(value, default: int) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            parsed = int(default)
        return max(0, min(2000, parsed))


    @staticmethod
    def _playback_offset_ms_value(value, default: int = 0) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            parsed = int(default)
        return max(-250, min(250, parsed))

    def _sps_smoothing_value(self) -> int:
        try:
            return max(1, min(31, int(self.sps_graph_smoothing_var.get())))
        except (TypeError, ValueError, tk.TclError):
            return 1

    def _apply_playback_padding(self, *, save: bool = False) -> None:
        lead_ms = self._playback_ms_value(self.playback_warmup_var.get(), 700)
        tail_ms = self._playback_ms_value(self.playback_tail_var.get(), 250)
        self.playback_warmup_var.set(str(lead_ms))
        self.playback_tail_var.set(str(tail_ms))
        self.player.set_padding(lead_seconds=lead_ms / 1000.0, tail_seconds=tail_ms / 1000.0)
        offset_ms = self._playback_offset_ms_value(self.playback_cursor_offset_var.get(), 0)
        self.playback_cursor_offset_var.set(str(offset_ms))
        self.player.set_cursor_offset(offset_ms / 1000.0)
        if save:
            self._save_preferences()

    def _build_style(self) -> None:
        apply_ttk_theme(self, self.palette)

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        self.main_menu = menu
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Новый проект…", command=self.new_project)
        file_menu.add_command(label="Открыть проект…", command=self.open_project)
        file_menu.add_command(label="Сохранить проект", command=self.save_project)
        file_menu.add_command(label="Сохранить проект как…", command=lambda: self.save_project(save_as=True))
        file_menu.add_separator()
        file_menu.add_command(label="Открыть ASS…", command=self.open_ass)
        file_menu.add_command(label="Новый пустой ASS…", command=self.new_blank_ass)
        file_menu.add_command(label="Сохранить ASS", accelerator="Ctrl+S", command=self.save_ass)
        file_menu.add_command(label="Сохранить ASS как…", accelerator="Ctrl+Shift+S", command=self.save_ass_as)
        file_menu.add_command(label="Указать медиа…", command=self.set_media)
        file_menu.add_command(label="FFmpeg…", command=self.open_ffmpeg_settings)
        file_menu.add_command(label="Экспорт аудио отрывка…", command=self.export_burst_or_selection_audio)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self._close)
        menu.add_cascade(label="Файл", menu=file_menu)
        edit_menu = tk.Menu(menu, tearoff=False)
        edit_menu.add_command(label="Отменить", accelerator="Ctrl+Z", command=self.undo_active_history)
        edit_menu.add_command(label="Повторить", accelerator="Ctrl+Y", command=self.redo_active_history)
        edit_menu.add_separator()
        edit_menu.add_command(label="Вставить слог", command=self.insert_karaoke)
        edit_menu.add_command(label="Разделить слог", command=self.split_karaoke)
        edit_menu.add_command(label="Совместить слоги", command=self.merge_karaoke)
        edit_menu.add_command(label="Удалить слог", accelerator="Delete", command=self.delete_karaoke)
        menu.add_cascade(label="Правка", menu=edit_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_checkbutton(label="Advanced", variable=self.advanced_mode_var, command=self._advanced_changed)
        theme_menu = tk.Menu(view_menu, tearoff=False)
        for theme_name in theme_names():
            theme_menu.add_radiobutton(label=theme_name, variable=self.theme_var, value=theme_name, command=self._theme_changed)
        view_menu.add_cascade(label="Тема", menu=theme_menu)
        view_menu.add_separator()
        view_menu.add_command(label="Показать весь таймлайн", command=self.reset_active_view)
        menu.add_cascade(label="Вид", menu=view_menu)
        settings_menu = tk.Menu(menu, tearoff=False)
        settings_menu.add_command(label="Общие…", accelerator="Ctrl+,", command=lambda: self.open_settings("general"))
        settings_menu.add_command(label="Воспроизведение…", command=lambda: self.open_settings("playback"))
        settings_menu.add_command(label="Точный SPS…", command=lambda: self.open_settings("sps"))
        settings_menu.add_command(label="Горячие клавиши…", command=lambda: self.open_settings("hotkeys"))
        settings_menu.add_separator()
        settings_menu.add_command(label="FFmpeg…", command=self.open_ffmpeg_settings)
        menu.add_cascade(label="Настройки", menu=settings_menu)
        sps_menu = tk.Menu(menu, tearoff=False)
        sps_menu.add_radiobutton(label="Waveform", variable=self.spectrogram_mode_var, value="Waveform", command=lambda: self._audio_view_changed(save=True))
        sps_menu.add_radiobutton(label="Спектрограмма", variable=self.spectrogram_mode_var, value="Spectrogram", command=lambda: self._audio_view_changed(save=True))
        sps_menu.add_radiobutton(label="Waveform + спектрограмма", variable=self.spectrogram_mode_var, value="Both", command=lambda: self._audio_view_changed(save=True))
        sps_menu.add_separator()
        sps_menu.add_command(label="Построить / обновить спектрограмму", command=lambda: self._ensure_spectrogram_async(force=True))
        sps_menu.add_command(label="Настройки спектрограммы…", command=self.open_spectrogram_settings)
        sps_menu.add_separator()
        sps_menu.add_command(label="Настройки прослушивания…", command=lambda: self.open_settings("playback"))
        sps_menu.add_separator()
        sps_menu.add_command(label="Загрузить measurements…", command=self.import_measurements)
        sps_menu.add_command(label="Экспортировать measurements…", command=self.export_measurements)
        sps_menu.add_separator()
        sps_menu.add_command(label="Экспортировать SPS-график в PNG…", command=self.export_sps_graph_png)
        sps_menu.add_command(label="Экспортировать SPS-график в CSV…", command=self.export_sps_graph_csv)
        menu.add_cascade(label="Точный SPS", menu=sps_menu)
        self.config(menu=menu)

    def _build_ui(self) -> None:
        top = ttk.Frame(self, style="Header.TFrame")
        top.pack(fill="x", padx=0, pady=0)
        ttk.Label(top, text="KARAOKE // SPS", style="Header.TLabel").pack(side="left", padx=(6, 12))
        ttk.Button(top, text="Проект…", command=self.open_project, style="Secondary.TButton").pack(side="left")
        ttk.Button(top, text="ASS…", command=self.open_ass, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(top, text="ASS+", command=self.new_blank_ass, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(top, text="Медиа…", command=self.set_media, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(top, text="FFmpeg…", command=self.open_ffmpeg_settings, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        self.project_label = ttk.Label(top, text="Проект: —", style="Chip.TLabel")
        self.project_label.pack(side="left", padx=(12, 6))

        self.advanced_toggle = ttk.Checkbutton(
            top, text="Advanced", variable=self.advanced_mode_var, command=self._advanced_changed, style="Switch.TCheckbutton"
        )
        self.advanced_toggle.pack(side="right", padx=(8, 6))
        self.theme_combo = ttk.Combobox(top, state="readonly", width=22, textvariable=self.theme_var, values=theme_names())
        self.theme_combo.pack(side="right", padx=(6, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", lambda _e: self._theme_changed())
        ttk.Label(top, text="Тема:", style="PanelMuted.TLabel").pack(side="right")
        self.waveform_label = ttk.Label(top, text="Waveform: —", style="Chip.TLabel")
        self.waveform_label.pack(side="right", padx=(10, 0))
        self.media_label = ttk.Label(top, text="Медиа: —", style="Chip.TLabel")
        self.media_label.pack(side="right", padx=(6, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.karaoke_tab = ttk.Frame(self.notebook, padding=8)
        self.sps_tab = ttk.Frame(self.notebook, padding=8)
        self.alignment_tab = ttk.Frame(self.notebook)
        self.render_tab = ttk.Frame(self.notebook)
        self.logs_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.alignment_tab, text="Подготовка")
        self.notebook.add(self.karaoke_tab, text="Караоке")
        self.notebook.add(self.sps_tab, text="Точный SPS")
        self.notebook.add(self.render_tab, text="Рендер")
        self.notebook.add(self.logs_tab, text="Логи")
        self.notebook.bind("<<NotebookTabChanged>>", self._notebook_tab_changed, add="+")
        self._build_karaoke_tab()
        self._build_sps_tab()
        self.alignment_scroll = ScrollableFrame(self.alignment_tab)
        self.alignment_scroll.pack(fill="both", expand=True)
        self.alignment_panel = AlignmentPanel(
            self.alignment_scroll.content,
            session=self.session,
            open_generated=self.open_ass_path,
            set_status=self._set_status,
            task_center=self.task_center,
        )
        self.alignment_panel.pack(fill="both", expand=True)
        self.render_scroll = ScrollableFrame(self.render_tab)
        self.render_scroll.pack(fill="both", expand=True)
        self.render_panel = RenderPanel(
            self.render_scroll.content,
            session=self.session,
            prepare_source=lambda: self._commit_text_drafts(
                preserve_selection=set(self._selected_karaoke_ids())
            ),
            set_status=self._set_status,
            task_center=self.task_center,
            selected_syllables=lambda: set(self.karaoke_timeline.selected_ids),
            document_changed=self._refresh_labels,
        )
        self.render_panel.pack(fill="both", expand=True)
        self.logs_scroll = ScrollableFrame(self.logs_tab)
        self.logs_scroll.pack(fill="both", expand=True)
        self.log_panel = LogPanel(self.logs_scroll.content, task_center=self.task_center)
        self.log_panel.pack(fill="both", expand=True)

        taskbar = ttk.Frame(self, style="Toolbar.TFrame")
        taskbar.pack(fill="x")
        self.task_stage_label = ttk.Label(taskbar, text="Фоновые задачи: —", style="PanelMuted.TLabel", anchor="w")
        self.task_stage_label.pack(side="left", fill="x", expand=True)
        self.task_progress = ttk.Progressbar(taskbar, orient="horizontal", mode="determinate", maximum=100, length=260)
        self.task_progress.pack(side="right", padx=(8, 4))
        self.task_percent_label = ttk.Label(taskbar, text="", width=6, style="PanelMuted.TLabel", anchor="e")
        self.task_percent_label.pack(side="right")

        self.status = ttk.Label(self, text="", style="Status.TLabel", anchor="w")
        self.status.pack(fill="x")

    def _set_speed_preset_value(self, speed: float) -> None:
        self.playback_speed_var.set(speed)
        self.playback_speed_text_var.set(f"{speed:.2f}×")
        try:
            self.player.set_speed(speed)
        except Exception as exc:
            self._set_status(f"Не удалось изменить скорость: {exc}")
        self._save_preferences()

    def _build_transport_bar(self, parent, *, context: str) -> ttk.Frame:
        bar = ttk.Frame(parent, style="Card.TFrame", padding=(10, 7))
        bar.pack(fill="x", pady=(2, 4))

        primary = ttk.Frame(bar, style="Card.TFrame")
        primary.pack(fill="x")
        # U+25B6 is deliberately used as a text symbol, without an emoji
        # variation selector, so these controls stay compact on Windows.
        play = "\u25b6"
        ttk.Button(primary, text=f"{play}/■", width=6, command=lambda c=context: self.toggle_continuous_playback(c), style="Primary.TButton").pack(side="left")
        ttk.Button(primary, text="■", width=3, command=self.stop_playback, style="Secondary.TButton").pack(side="left", padx=(4, 10))

        ttk.Label(primary, text="Метки:", style="CardTitle.TLabel").pack(side="left", padx=(4, 4))
        ttk.Button(primary, text="|←", width=4, command=lambda c=context: self.set_playback_limit_marker(c, "start"), style="Secondary.TButton").pack(side="left")
        ttk.Button(primary, text=f"|{play}", width=4, command=lambda c=context: self.play_from_start_marker(c), style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(primary, text="→|", width=4, command=lambda c=context: self.set_playback_limit_marker(c, "stop"), style="Secondary.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(primary, text=f"{play}|", width=4, command=lambda c=context: self.play_to_stop_marker(c), style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(primary, text=f"|{play}|", width=5, command=lambda c=context: self.play_between_markers(c), style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(primary, text="↔", width=3, command=lambda c=context: self.set_playback_range_from_selection(c), style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(primary, text="×", width=3, command=lambda c=context: self.clear_playback_limits(c), style="Secondary.TButton").pack(side="left", padx=(3, 10))
        ttk.Label(primary, textvariable=self.playback_limit_vars[context], style="CardMuted.TLabel").pack(side="left", fill="x", expand=True)

        row2 = ttk.Frame(bar, style="Card.TFrame")
        row2.pack(fill="x", pady=(6, 0))

        ttk.Label(row2, text="Скорость:", style="CardTitle.TLabel").pack(side="left", padx=(0, 4))
        scale = ttk.Scale(row2, from_=0.25, to=2.0, variable=self.playback_speed_var, command=self._playback_speed_preview)
        scale.pack(side="left", fill="x", expand=False, padx=(4, 4), ipadx=35)
        scale.bind("<ButtonRelease-1>", lambda _e: self._commit_playback_speed())
        scale.bind("<KeyRelease>", lambda _e: self._commit_playback_speed())
        ttk.Label(row2, textvariable=self.playback_speed_text_var, width=6, style="CardHeader.TLabel").pack(side="left")

        for preset_val, preset_label in ((0.5, "0.5×"), (0.75, "0.75×"), (1.0, "1×"), (1.25, "1.25×"), (1.5, "1.5×")):
            ttk.Button(row2, text=preset_label, width=5, style="Pill.TButton",
                       command=lambda v=preset_val: self._set_speed_preset_value(v)).pack(side="left", padx=(2, 0))

        ttk.Checkbutton(
            row2, text="Сохранять тон", variable=self.playback_preserve_pitch_var,
            command=self._pitch_mode_changed, style="Switch.TCheckbutton",
        ).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(
            row2, text="Возврат к старту", variable=self.playback_return_to_start_var,
            command=self._save_preferences, style="Switch.TCheckbutton",
        ).pack(side="left", padx=(8, 0))
        return bar

    def _prime_audio_output(self) -> None:
        self._prime_audio_job = None
        # Device discovery/opening can block in Windows audio drivers.  Doing
        # it 250 ms after startup on Tk's thread made the freshly shown window
        # pause while it was being moved or restored.
        def work() -> None:
            try:
                available = self.player.prepare_output()
            except Exception:
                available = False
            if available:
                return
            try:
                self.after(
                    0,
                    lambda: self._set_status(
                        "Низколатентный PortAudio-плеер недоступен: "
                        "установите sounddevice в Conda-env"
                    ),
                )
            except (RuntimeError, tk.TclError):
                pass

        threading.Thread(target=work, name="karaoke-audio-prime", daemon=True).start()

    def _pitch_mode_changed(self) -> None:
        self.player.set_preserve_pitch(self.playback_preserve_pitch_var.get())
        try:
            self.player.set_speed(normalize_playback_speed(float(self.playback_speed_var.get())))
        except Exception as exc:
            self._set_status(f"Не удалось изменить режим высоты тона: {exc}")
        self._save_preferences()

    def _add_hotkey_bindtag(self, widget) -> None:
        tag = "KaraokeHotkeys"
        try:
            tags = list(widget.bindtags())
            if tag not in tags:
                tags.insert(1, tag)
                widget.bindtags(tuple(tags))
        except tk.TclError:
            return
        for child in widget.winfo_children():
            self._add_hotkey_bindtag(child)

    @staticmethod
    def _hotkey_text_focus(widget) -> bool:
        if widget is None:
            return False
        try:
            cls = str(widget.winfo_class())
        except Exception:
            return False
        return cls in {"Entry", "TEntry", "Text", "Spinbox", "TSpinbox"}

    def _install_hotkeys(self) -> None:
        """Install configurable shortcuts before ttk class bindings.

        A dedicated bindtag is required so Space never activates the previously
        focused button/combobox before the transport handler sees it.
        """
        tag = "KaraokeHotkeys"
        for sequence in getattr(self, "_hotkey_bound_sequences", set()):
            try:
                self.unbind_class(tag, sequence)
            except tk.TclError:
                pass
        bound: set[str] = set()
        # Handle history by physical Z/Y key as well as keysym. On Windows a
        # Russian keyboard layout reports Ctrl+Я/Ctrl+Н instead of Ctrl+Z/Y,
        # even though the user pressed the conventional physical shortcut.
        history_sequence = "<KeyPress>"
        self.bind_class(tag, history_sequence, self._fallback_keypress)
        bound.add(history_sequence)
        for action, display in self.hotkeys.items():
            if not display:
                continue
            try:
                sequence = shortcut_to_tk(display)
            except ValueError:
                continue
            if not sequence:
                continue
            self.bind_class(tag, sequence, lambda e, a=action: self._hotkey_action(a, e))
            bound.add(sequence)
        self._hotkey_bound_sequences = bound
        self._add_hotkey_bindtag(self)

    def _history_hotkey(self, event, *, redo: bool):
        if self._hotkey_text_focus(getattr(event, "widget", None)):
            return None
        if redo:
            self.redo_active_history()
        else:
            self.undo_active_history()
        return "break"

    def undo_active_history(self) -> None:
        if self._active_timeline_context() == "sps":
            if self.undo_sps_measurement():
                return
        self.undo_karaoke()

    def redo_active_history(self) -> None:
        if self._active_timeline_context() == "sps":
            if self.redo_sps_measurement():
                return
        self.redo_karaoke()

    def _history_keypress(self, event):
        keysym = str(getattr(event, "keysym", "")).lower()
        try:
            windows = self.tk.call("tk", "windowingsystem") == "win32"
        except tk.TclError:
            windows = False
        keycode = int(getattr(event, "keycode", -1))
        is_z = keysym in {"z", "я"} or (windows and keycode == 90)
        is_y = keysym in {"y", "н"} or (windows and keycode == 89)
        if not is_z and not is_y:
            return None
        shift = bool(int(getattr(event, "state", 0)) & 0x0001)
        return self._history_hotkey(event, redo=is_y or (is_z and shift))

    def _save_ass_with_commit(self) -> str:
        self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids()))
        self.save_ass()
        self._last_autosave_time = time.monotonic()
        return "break"

    def _save_ass_as_with_commit(self) -> str:
        self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids()))
        self.save_ass_as()
        self._last_autosave_time = time.monotonic()
        return "break"

    def _handle_text_widget_shortcuts(self, event):
        widget = getattr(event, "widget", None)
        if not self._hotkey_text_focus(widget):
            return None
        state = int(getattr(event, "state", 0))
        is_ctrl = bool(state & 0x0004)
        is_shift = bool(state & 0x0001)
        is_alt = bool(state & 0x0008)
        if is_alt:
            return None
        keycode = int(getattr(event, "keycode", -1))
        keysym = str(getattr(event, "keysym", "")).lower()
        char = str(getattr(event, "char", ""))
        is_text = isinstance(widget, tk.Text)

        # Match helpers for Latin and Russian layouts (keysym, keycode, char)
        is_s = keycode == ord("S") or keysym in {"s", "cyrillic_yeru"} or char in {"\x13", "ы", "Ы"}
        is_a = keycode == ord("A") or keysym in {"a", "cyrillic_ef"} or char in {"\x01", "ф", "Ф"}
        is_c = keycode == ord("C") or keysym in {"c", "cyrillic_es"} or char in {"\x03", "с", "С"}
        is_x = keycode == ord("X") or keysym in {"x", "cyrillic_che"} or char in {"\x18", "ч", "Ч"}
        is_v = keycode == ord("V") or keysym in {"v", "cyrillic_em"} or char in {"\x16", "м", "М"}
        is_z = keycode == ord("Z") or keysym in {"z", "cyrillic_ya"} or char in {"\x1a", "я", "Я"}
        is_y = keycode == ord("Y") or keysym in {"y", "cyrillic_en"} or char in {"\x19", "н", "Н"}

        # 1. Ctrl+S: Save ASS with commit
        if is_ctrl and not is_shift and is_s:
            return self._save_ass_with_commit()

        # 2. Ctrl+Shift+S: Save ASS As
        if is_ctrl and is_shift and is_s:
            return self._save_ass_as_with_commit()

        # 3. Ctrl+A: Select All
        if is_ctrl and not is_shift and is_a:
            try:
                if is_text:
                    widget.tag_add("sel", "1.0", "end-1c")
                    widget.mark_set("insert", "end-1c")
                else:
                    widget.selection_range(0, "end")
                    widget.icursor("end")
            except Exception:
                pass
            return "break"

        # 4. Ctrl+C: Copy
        if is_ctrl and not is_shift and is_c:
            try:
                if is_text:
                    try:
                        text = widget.get("sel.first", "sel.last")
                    except Exception:
                        return "break"
                else:
                    if hasattr(widget, "selection_present") and not widget.selection_present():
                        return "break"
                    try:
                        text = widget.selection_get()
                    except Exception:
                        return "break"
                widget.clipboard_clear()
                widget.clipboard_append(text)
            except Exception:
                pass
            return "break"

        # 5. Ctrl+X: Cut
        if is_ctrl and not is_shift and is_x:
            try:
                if is_text:
                    try:
                        text = widget.get("sel.first", "sel.last")
                        widget.delete("sel.first", "sel.last")
                    except Exception:
                        return "break"
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                else:
                    if hasattr(widget, "selection_present") and not widget.selection_present():
                        return "break"
                    try:
                        start = widget.index("sel.first")
                        end = widget.index("sel.last")
                        text = widget.get()[start:end]
                        widget.delete(start, end)
                    except Exception:
                        return "break"
                    if widget is getattr(self, "karaoke_romanization_entry", None):
                        self._remember_current_romanization_draft()
                widget.clipboard_clear()
                widget.clipboard_append(text)
            except Exception:
                pass
            return "break"

        # 6. Ctrl+V: Paste
        if is_ctrl and not is_shift and is_v:
            try:
                clip = widget.clipboard_get()
                if clip:
                    if is_text:
                        try:
                            widget.delete("sel.first", "sel.last")
                        except Exception:
                            pass
                        widget.insert("insert", clip)
                        if widget is getattr(self, "karaoke_text_editor", None):
                            self._remember_current_karaoke_draft()
                    else:
                        try:
                            if hasattr(widget, "selection_present") and widget.selection_present():
                                start = widget.index("sel.first")
                                end = widget.index("sel.last")
                                widget.delete(start, end)
                        except Exception:
                            pass
                        widget.insert("insert", clip)
                        if widget is getattr(self, "karaoke_romanization_entry", None):
                            self._remember_current_romanization_draft()
            except Exception:
                pass
            return "break"

        # 7. Ctrl+Z: Undo
        if is_ctrl and not is_shift and is_z:
            try:
                if is_text:
                    widget.edit_undo()
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                else:
                    widget.event_generate("<<Undo>>")
            except Exception:
                pass
            return "break"

        # 8. Ctrl+Y or Ctrl+Shift+Z: Redo
        if (is_ctrl and not is_shift and is_y) or (is_ctrl and is_shift and is_z):
            try:
                if is_text:
                    widget.edit_redo()
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                else:
                    widget.event_generate("<<Redo>>")
            except Exception:
                pass
            return "break"

        # 9. Ctrl+BackSpace: Delete word left
        if is_ctrl and not is_shift and (keycode == 8 or keysym in {"backspace"}):
            try:
                if is_text:
                    try:
                        widget.delete("sel.first", "sel.last")
                    except Exception:
                        ins = widget.index("insert")
                        prev = widget.search(r"\y", ins, backwards=True, regexp=True, stopindex="1.0")
                        if not prev or prev == ins:
                            prev = widget.search(r"\s+", ins, backwards=True, regexp=True, stopindex="1.0")
                        if not prev:
                            prev = "1.0"
                        widget.delete(prev, ins)
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                else:
                    try:
                        start = widget.index("sel.first")
                        end = widget.index("sel.last")
                        widget.delete(start, end)
                    except Exception:
                        ins = widget.index("insert")
                        val = widget.get()
                        before = val[:ins]
                        m = re.search(r"(\s*\w+|\s+|[^\w\s]+)$", before)
                        if m:
                            widget.delete(ins - len(m.group(0)), ins)
                    if widget is getattr(self, "karaoke_romanization_entry", None):
                        self._remember_current_romanization_draft()
            except Exception:
                pass
            return "break"

        # 10. Ctrl+Delete: Delete word right
        if is_ctrl and not is_shift and (keycode == 46 or keysym in {"delete"}):
            try:
                if is_text:
                    try:
                        widget.delete("sel.first", "sel.last")
                    except Exception:
                        ins = widget.index("insert")
                        nxt = widget.search(r"\y", "insert + 1 c", regexp=True, stopindex="end")
                        if not nxt:
                            nxt = "end-1c"
                        widget.delete(ins, nxt)
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                else:
                    try:
                        start = widget.index("sel.first")
                        end = widget.index("sel.last")
                        widget.delete(start, end)
                    except Exception:
                        ins = widget.index("insert")
                        val = widget.get()
                        after = val[ins:]
                        m = re.match(r"^(\w+\s*|\s+|[^\w\s]+)", after)
                        if m:
                            widget.delete(ins, ins + len(m.group(0)))
                    if widget is getattr(self, "karaoke_romanization_entry", None):
                        self._remember_current_romanization_draft()
            except Exception:
                pass
            return "break"

        # 11. Plain Backspace or Delete with selection in Text: delete selection
        if not is_ctrl and not is_alt and not is_shift and (keycode in (8, 46) or keysym in {"backspace", "delete"}):
            if is_text:
                try:
                    widget.delete("sel.first", "sel.last")
                    if widget is getattr(self, "karaoke_text_editor", None):
                        self._remember_current_karaoke_draft()
                    return "break"
                except Exception:
                    pass

        # 12. Typing a printable character with selection in Text: replace selection
        char = getattr(event, "char", "")
        if is_text and not is_ctrl and not is_alt and char and char.isprintable():
            try:
                widget.delete("sel.first", "sel.last")
                if widget is getattr(self, "karaoke_text_editor", None):
                    self._remember_current_karaoke_draft()
            except Exception:
                pass

        return None

    def _setup_text_class_bindings(self) -> None:
        # Register Cyrillic keysyms to standard virtual events so all widgets
        # (Entry, TEntry, Text, Spinbox) respond natively to Ctrl shortcuts on Russian layout.
        for ev, keys in [
            ("<<SelectAll>>", ["<Control-Key-Cyrillic_ef>", "<Control-Key-Cyrillic_EF>"]),
            ("<<Copy>>", ["<Control-Key-Cyrillic_es>", "<Control-Key-Cyrillic_ES>"]),
            ("<<Paste>>", ["<Control-Key-Cyrillic_em>", "<Control-Key-Cyrillic_EM>"]),
            ("<<Cut>>", ["<Control-Key-Cyrillic_che>", "<Control-Key-Cyrillic_CHE>"]),
            ("<<Undo>>", ["<Control-Key-Cyrillic_ya>", "<Control-Key-Cyrillic_YA>"]),
            ("<<Redo>>", ["<Control-Key-Cyrillic_en>", "<Control-Key-Cyrillic_EN>"]),
        ]:
            for k in keys:
                try:
                    self.event_add(ev, k)
                except Exception:
                    pass

        for cls in ("Entry", "TEntry", "Text", "Spinbox", "TSpinbox"):
            self.bind_class(cls, "<Control-Key>", lambda e: self._handle_text_widget_shortcuts(e))
            self.bind_class(cls, "<KeyPress>", lambda e: self._handle_text_widget_shortcuts(e), add="+")

    def _fallback_keypress(self, event):
        text_result = self._handle_text_widget_shortcuts(event)
        if text_result is not None:
            return text_result
        if self._hotkey_text_focus(getattr(event, "widget", None)):
            return None
        history_result = self._history_keypress(event)
        if history_result is not None:
            return history_result
        try:
            if self.tk.call("tk", "windowingsystem") != "win32":
                return None
        except tk.TclError:
            return None
        keycode = int(getattr(event, "keycode", -1))
        keysym = str(getattr(event, "keysym", "")).lower()
        state = int(getattr(event, "state", 0))
        actual_modifiers = {
            name for name, active in (
                ("ctrl", state & 0x0004),
                ("shift", state & 0x0001),
                ("alt", state & 0x0008),
            ) if active
        }

        # Reserved application shortcuts also keep working on a non-Latin
        # layout. Punctuation/function keys already have stable keysyms.
        char = str(getattr(event, "char", ""))
        is_s = keycode == ord("S") or keysym in {"s", "cyrillic_yeru"} or char in {"\x13", "ы", "Ы"}
        if is_s and actual_modifiers == {"ctrl"}:
            return self._save_ass_with_commit()
        if is_s and actual_modifiers == {"ctrl", "shift"}:
            return self._save_ass_as_with_commit()

        for action, display in self.hotkeys.items():
            parts = [part.strip().lower() for part in str(display).split("+") if part.strip()]
            if not parts or len(parts[-1]) != 1 or not parts[-1].isalpha():
                continue
            wanted_modifiers = {
                "ctrl" if part in {"ctrl", "control"} else part
                for part in parts[:-1]
            }
            if keycode == ord(parts[-1].upper()) and actual_modifiers == wanted_modifiers:
                return self._hotkey_action(action, event)
        return None

    def _active_timeline_context(self) -> str | None:
        try:
            selected = self.notebook.select()
        except Exception:
            return None
        if selected == str(self.sps_tab):
            return "sps"
        if selected == str(self.karaoke_tab):
            return "karaoke"
        return None

    def _hotkey_action(self, action: str, event):
        if self._hotkey_text_focus(getattr(event, "widget", None)):
            return None
        context = self._active_timeline_context()
        if action == "transport_toggle":
            self.toggle_continuous_playback(context or "karaoke")
        elif action == "play_selection":
            if context == "sps": self.play_sps_selection()
            elif context == "karaoke": self.play_karaoke_selection()
            else: return None
        elif action == "play_range":
            if context is None: return None
            self.play_marked_range(context)
        elif action == "stop":
            self.stop_playback()
        elif action == "set_play_start":
            if context is None: return None
            self.set_playback_limit_marker(context, "start")
        elif action == "play_from_start":
            if context is None: return None
            self.play_from_start_marker(context)
        elif action == "set_play_stop":
            if context is None: return None
            self.set_playback_limit_marker(context, "stop")
        elif action == "play_to_stop":
            if context is None: return None
            self.play_to_stop_marker(context)
        elif action == "clear_play_limits":
            if context is None: return None
            self.clear_playback_limits(context)
        elif action == "range_from_selection":
            if context is None: return None
            self.set_playback_range_from_selection(context)
        elif action == "previous_syllable":
            if context is None: return None
            self.navigate_active_syllable(-1, context)
        elif action == "next_syllable":
            if context is None: return None
            self.navigate_active_syllable(1, context)
        elif action == "insert_syllable":
            if context != "karaoke": return None
            self.insert_karaoke()
        elif action == "split_syllable":
            if context != "karaoke": return None
            self.split_karaoke()
        elif action == "merge_syllables":
            if context != "karaoke": return None
            self.merge_karaoke()
        elif action == "delete_syllable":
            if context != "karaoke": return None
            self.delete_karaoke()
        elif action == "reset_measurement":
            if context != "sps": return None
            self.reset_selected_measurement()
        else:
            return None
        return "break"

    def _playback_speed_preview(self, value=None) -> None:
        try:
            raw_speed = max(0.25, min(2.0, float(self.playback_speed_var.get() if value is None else value)))
        except Exception:
            raw_speed = 1.0
        speed = normalize_playback_speed(raw_speed)
        self.playback_speed_text_var.set(f"{speed:.2f}×")

    def _commit_playback_speed(self) -> None:
        speed = normalize_playback_speed(max(0.25, min(2.0, float(self.playback_speed_var.get()))))
        self.playback_speed_var.set(speed)
        self.playback_speed_text_var.set(f"{speed:.2f}×")
        try:
            self.player.set_speed(speed)
        except Exception as exc:
            self._set_status(f"Не удалось изменить скорость: {exc}")
        self._save_preferences()

    def _context_items(self, context: str):
        if context == "sps":
            timeline = self.session.sps_timeline
            return list(timeline.syllables) if timeline is not None else []
        return list(self.session.syllables)

    def _context_selected_items(self, context: str):
        items = self._context_items(context)
        if context == "sps":
            ids = set(getattr(self.sps_timeline, "selected_ids", set()))
        else:
            ids = set(getattr(self.karaoke_timeline, "selected_ids", set()))
        return [item for item in items if item.id in ids]

    @staticmethod
    def _item_bounds(item, context: str) -> tuple[float, float]:
        if context == "sps":
            return float(item.effective_start), float(item.effective_end)
        return float(item.start), float(item.end)

    def _playback_limit_item(self, context: str, marker: str):
        marker_id = self.playback_limit_ids[context].get(marker)
        if not marker_id:
            return None
        return next((item for item in self._context_items(context) if item.id == marker_id), None)

    def _marker_bounds(self, context: str) -> tuple[float | None, float | None]:
        start_item = self._playback_limit_item(context, "start")
        stop_item = self._playback_limit_item(context, "stop")
        start = self._item_bounds(start_item, context)[0] if start_item is not None else None
        stop = self._item_bounds(stop_item, context)[1] if stop_item is not None else None
        return start, stop

    def _marker_items(self, context: str):
        items = self._context_items(context)
        marks = self.playback_limit_ids[context]
        if not marks.get("start") or not marks.get("stop"):
            return []
        ids = [item.id for item in items]
        if marks["start"] not in ids or marks["stop"] not in ids:
            return []
        a = ids.index(marks["start"]); b = ids.index(marks["stop"])
        if a > b:
            return []
        return items[a:b + 1]

    def _update_playback_limit_label(self, context: str) -> None:
        timeline_widget = self.sps_timeline if context == "sps" else self.karaoke_timeline
        items = self._context_items(context)
        valid_ids = {item.id for item in items}
        marks = self.playback_limit_ids[context]
        for key in ("start", "stop"):
            if marks.get(key) and marks[key] not in valid_ids:
                marks[key] = None
        start, stop = self._marker_bounds(context)
        timeline_widget.set_playback_limits(start, stop)
        # The old In/Out range is now the same marker pair. When both markers
        # exist, draw the bracketed range too; with only one marker, keep only
        # the independent start/stop line.
        if start is not None and stop is not None:
            timeline_widget.set_playback_range(start, stop)
        else:
            timeline_widget.set_playback_range(None, None)

        left = format_clock(start) if start is not None else "—"
        right = format_clock(stop) if stop is not None else "—"
        suffix = ""
        segment = self._marker_items(context)
        if segment:
            peak = fastest_legacy_window(segment, measured=(context == "sps"))
            if peak is not None:
                suffix = f" · max {peak.speed:.4f} SPS ({peak.count}//{peak.duration:.4f})"
        if start is not None and stop is not None and stop <= start:
            if context == "sps" and segment:
                suffix += " · End раньше Start"
            else:
                suffix += " · ⚠ финиш не позже старта"
        label = f"|← {left}   →| {right}{suffix}"
        self.playback_limit_vars[context].set(label)
        # Compatibility variables from Update 030 now mirror the same marker
        # pair rather than maintaining a second, competing range.
        self.playback_range_ids[context]["in"] = marks.get("start")
        self.playback_range_ids[context]["out"] = marks.get("stop")
        self.playback_range_vars[context].set(label)

    def set_playback_limit_marker(self, context: str, marker: str) -> None:
        if marker not in {"start", "stop"}:
            raise ValueError(marker)
        chosen = self._context_selected_items(context)
        if not chosen:
            self._set_status("Сначала выберите слог")
            return
        items = self._context_items(context)
        order = {item.id: i for i, item in enumerate(items)}
        chosen.sort(key=lambda item: order.get(item.id, 10**9))
        item = chosen[0] if marker == "start" else chosen[-1]
        self.playback_limit_ids[context][marker] = item.id
        self._update_playback_limit_label(context)
        self._set_status(
            f"{'Метка старта |←' if marker == 'start' else 'Метка окончания →|'}: "
            f"{item.text.strip() or item.id}"
        )

    def clear_playback_limit(self, context: str, marker: str) -> None:
        if marker not in {"start", "stop"}:
            raise ValueError(marker)
        self.playback_limit_ids[context][marker] = None
        self._update_playback_limit_label(context)
        self._set_status("Метка старта очищена" if marker == "start" else "Метка окончания очищена")

    def clear_playback_limits(self, context: str) -> None:
        self.playback_limit_ids[context] = {"start": None, "stop": None}
        self._update_playback_limit_label(context)
        self._set_status("Метки воспроизведения очищены")

    # Backward-compatible In/Out API: Update 033 intentionally merges In/Out
    # with the independent start/end markers instead of keeping two pairs.
    def _range_items(self, context: str):
        return self._marker_items(context)

    def _update_playback_range_label(self, context: str) -> None:
        self._update_playback_limit_label(context)

    def set_playback_range_marker(self, context: str, marker: str) -> None:
        self.set_playback_limit_marker(context, "start" if marker == "in" else "stop")

    def set_playback_range_from_selection(self, context: str) -> None:
        chosen = self._context_selected_items(context)
        if not chosen:
            self._set_status("Сначала выделите один или несколько слогов")
            return
        items = self._context_items(context)
        order = {item.id: i for i, item in enumerate(items)}
        chosen.sort(key=lambda item: order.get(item.id, 10**9))
        self.playback_limit_ids[context]["start"] = chosen[0].id
        self.playback_limit_ids[context]["stop"] = chosen[-1].id
        self._update_playback_limit_label(context)
        self._set_status(f"Обе метки поставлены по выделению: {len(chosen)} слогов")

    def clear_playback_range(self, context: str) -> None:
        self.clear_playback_limits(context)

    def _begin_transport(self, start: float, end: float | None, *, label: str, mode: str) -> bool:
        if self.session.media_path is None:
            messagebox.showinfo("Нет медиа", "Сначала укажите аудио или видео.", parent=self)
            return False
        start = max(0.0, float(start))
        if end is not None:
            end = float(end)
            if end <= start + 1e-9:
                self._set_status("Некорректный диапазон воспроизведения")
                return False
        if not self._playback_ready():
            return False
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            messagebox.showerror("FFmpeg не найден", "Выберите FFmpeg в настройках.", parent=self)
            return False
        ffplay = resolve_ffplay(ffmpeg)
        speed = normalize_playback_speed(float(self.playback_speed_var.get()))
        self._transport_serial += 1
        serial = self._transport_serial
        self._set_playhead(start)
        try:
            if end is None:
                self.player.play_continuous(
                    self.session.media_path, start, ffmpeg=ffmpeg, ffplay=ffplay, speed=speed,
                )
            else:
                self.player.play(
                    self.session.media_path, start, end, ffplay=ffplay, ffmpeg=ffmpeg, speed=speed,
                )
        except Exception as exc:
            self._playback_origin = None
            self._playback_return_target = None
            self._playback_was_active = False
            self._transport_mode = "idle"
            messagebox.showerror("Не удалось воспроизвести", str(exc), parent=self)
            return False
        # Capture the start of this *user transport command*. Internal PortAudio
        # restarts may change engine state, but must never mutate this target.
        self._playback_origin = float(start)
        self._playback_return_target = float(start)
        self._playback_was_active = True
        self._transport_mode = mode
        end_text = format_clock(end) if end is not None else "конца"
        self._set_status(f"{label}: {format_clock(start)} → {end_text} · {speed:.2f}×")
        return serial == self._transport_serial

    def _play_interval(self, start: float, end: float, *, label: str) -> None:
        self._begin_transport(start, end, label=label, mode="selection")

    def play_from_start_marker(self, context: str) -> None:
        start, _ = self._marker_bounds(context)
        if start is None:
            self._set_status("Сначала поставьте метку старта кнопкой |←")
            return
        self._begin_transport(start, None, label="|▶", mode="from-start")

    def play_to_stop_marker(self, context: str) -> None:
        formal_start, stop = self._marker_bounds(context)
        if stop is None:
            self._set_status("Сначала поставьте метку окончания кнопкой →|")
            return
        start = max(0.0, float(self.playhead_time))
        if stop <= start + 1e-9:
            segment = self._marker_items(context)
            if (
                context != "sps"
                or formal_start is None
                or stop > formal_start + 1e-9
                or not segment
            ):
                self._set_status("Полоса воспроизведения уже находится на/после метки окончания")
                return
            start, stop, _ = selection_audition_bounds(segment, measured=True)
            if stop <= start + 1e-9:
                self._set_status("Невозможно прослушать End в самом начале медиа")
                return
        self._begin_transport(start, stop, label="▶|", mode="to-stop")

    def play_between_markers(self, context: str) -> None:
        start, stop = self._marker_bounds(context)
        if start is None or stop is None:
            self._set_status("Для |▶| нужны обе метки: |← и →|")
            return
        if stop <= start + 1e-9:
            segment = self._marker_items(context)
            if context != "sps" or not segment:
                self._set_status("Метка окончания должна быть позже метки старта")
                return
            start, stop, _ = selection_audition_bounds(segment, measured=True)
            if stop <= start + 1e-9:
                self._set_status("Невозможно прослушать End в самом начале медиа")
                return
        self._begin_transport(start, stop, label="|▶|", mode="bounded")

    def play_marked_range(self, context: str) -> None:
        # Retained for existing Shift+Space and older extensions.
        self.play_between_markers(context)

    def navigate_active_syllable(self, direction: int, context: str | None = None) -> None:
        context = context or self._active_timeline_context()
        if context == "karaoke":
            self.navigate_karaoke(direction)
            return
        if context != "sps":
            return
        items = self._context_items("sps")
        if not items:
            return
        ids = [item.id for item in items]
        selected = [sid for sid in self.sps_timeline.selected_ids if sid in ids]
        index = ids.index(selected[0]) if len(selected) == 1 else (0 if direction >= 0 else len(ids) - 1)
        index = max(0, min(len(ids) - 1, index + (1 if direction > 0 else -1)))
        target = items[index]
        self.sps_timeline.select_ids((target.id,))
        start, end = self._item_bounds(target, "sps")
        self.sps_timeline.focus_time((start + end) / 2)

    def _set_playhead(self, value: float, *, ensure_visible: bool = False) -> None:
        self.playhead_time = max(0.0, float(value))
        if hasattr(self, "karaoke_timeline"):
            self.karaoke_timeline.set_playhead(self.playhead_time, ensure_visible=ensure_visible)
        if hasattr(self, "sps_timeline"):
            self.sps_timeline.set_playhead(self.playhead_time, ensure_visible=ensure_visible)

    def _playback_seek_requested(self, value: float) -> None:
        if self.player.playing or self.player.paused:
            self.player.stop()
        self._transport_serial += 1
        self._playback_origin = None
        self._playback_return_target = None
        self._playback_was_active = False
        self._transport_mode = "idle"
        self._set_playhead(value)
        self._set_status(f"Курсор: {format_clock(value)}")

    def _playback_ready(self) -> bool:
        if self.playback_cache is not None:
            if self.player.prepare_output():
                return True
            self._set_status(
                "Нужен PortAudio backend: установите в активной Conda-среде `python -m pip install sounddevice` "
                "или `conda install -c conda-forge python-sounddevice`."
            )
            return False
        self._ensure_playback_cache_async()
        self._set_status("Подготавливается PCM-аудиокэш. После этого Play/Space будет читать звук напрямую из кэша.")
        return False

    def _continuous_bounds(self, context: str) -> tuple[float, float | None]:
        # Ordinary Space is intentionally independent from |← / →| markers.
        return max(0.0, float(self.playhead_time)), None

    def _continuous_start_point(self, context: str) -> float:
        return self._continuous_bounds(context)[0]

    def _interrupt_special_transport_with_space(self) -> None:
        try:
            current = self.player.position()
        except Exception:
            current = self.playhead_time
        self.player.stop()
        # Space explicitly cancels a bounded/special transport. Do not snap back
        # to its origin: the user interrupted it and expects to remain where it
        # was interrupted. A subsequent Space starts normal playback from here.
        self._finish_playback_ui(current, respect_return=False)
        self._set_status(f"Спецвоспроизведение прервано Space · курсор {format_clock(current)}")

    def toggle_continuous_playback(self, context: str = "karaoke") -> None:
        active = self.player.playing or self.player.paused
        if active and self._transport_mode not in {"idle", "normal"}:
            self._interrupt_special_transport_with_space()
            return
        if active:
            # Repeated Play/Space is an audition stop, not Pause: when return
            # is enabled, the next press starts from the exact same origin.
            self.stop_playback()
            return
        start = max(0.0, float(self.playhead_time))
        self._begin_transport(start, None, label="Play", mode="normal")

    def _restore_finished_playhead(self, target: float, serial: int) -> None:
        # Tk may still have one queued playhead paint from the frame immediately
        # before Stop. Re-apply the final target on idle, but only if no newer
        # transport has started in the meantime.
        if serial != self._transport_serial:
            return
        if self.player.playing or self.player.paused:
            return
        self._set_playhead(target)

    def _finish_playback_ui(
        self, final_position: float | None = None, *, respect_return: bool = True,
        return_target: float | None = None,
    ) -> None:
        """Finalize one user-visible transport session exactly once.

        The return target is captured by the user command that started playback
        and survives PortAudio restarts. Manual Stop and natural completion use
        this same path.
        """
        target = self._playback_return_target if return_target is None else return_target
        if target is None:
            target = self._playback_origin
        if final_position is None:
            try:
                final_position = self.player.position()
            except Exception:
                final_position = self.playhead_time
        should_return = bool(respect_return and self.playback_return_to_start_var.get() and target is not None)
        final_ui = float(target) if should_return else float(final_position)
        serial = self._transport_serial
        self._playback_origin = None
        self._playback_return_target = None
        self._playback_was_active = False
        self._transport_mode = "idle"
        self._set_playhead(final_ui)
        try:
            self.after_idle(lambda t=final_ui, s=serial: self._restore_finished_playhead(t, s))
        except tk.TclError:
            pass

    def _poll_playback_cursor(self) -> None:
        active = False
        try:
            active = self.player.playing or self.player.paused
            if active:
                pos = self.player.position()
                self._set_playhead(pos, ensure_visible=self.player.playing)
                self._playback_was_active = True
            elif self._playback_was_active:
                self._finish_playback_ui(self.player.position())
        except Exception:
            pass
        try:
            # Keep one self-rescheduling poller only.  Do not create another
            # loop from unrelated UI timers.  A fast cadence is useful only
            # while audio is active; polling 25 times a second in the idle app
            # needlessly competes with Windows paint/move messages.
            delay_ms = 40 if active or self._playback_was_active else 200
            self._playback_poll_job = self.after(delay_ms, self._poll_playback_cursor)
        except tk.TclError:
            self._playback_poll_job = None

    def _build_karaoke_tab(self) -> None:
        tab = self.karaoke_tab

        # Top subheader: Title, ASS status, syllable count, and SPS transfer cluster
        header = ttk.Frame(tab, style="Subheader.TFrame")
        header.pack(fill="x", pady=(0, 3))
        left = ttk.Frame(header, style="Subheader.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="Редактор karaoke timing", style="Header.TLabel").pack(side="left")
        self.ass_label = ttk.Label(left, text="ASS не открыт", style="PanelMuted.TLabel")
        self.ass_label.pack(side="left", padx=(10, 8))
        self.karaoke_info = ttk.Label(left, text="0 слогов", style="Badge.TLabel")
        self.karaoke_info.pack(side="left")

        transfer = ttk.Frame(header, style="Subheader.TFrame")
        transfer.pack(side="right")
        ttk.Label(transfer, text="Мин. peak SPS:", style="PanelMuted.TLabel").grid(row=0, column=0, padx=(0, 4))
        self.min_sps_var = tk.StringVar(value="6.0")
        ttk.Spinbox(transfer, from_=1.0, to=50.0, increment=0.5, width=5, textvariable=self.min_sps_var).grid(row=0, column=1)
        self.scope_var = tk.StringVar(value="Весь ASS")
        ttk.Combobox(transfer, state="readonly", width=14, textvariable=self.scope_var, values=("Весь ASS", "Выделенные слоги")).grid(row=0, column=2, padx=6)
        self.transfer_button = ttk.Button(transfer, text="→ В точный SPS", command=self.transfer_to_sps, style="Accent.TButton")
        self.transfer_button.grid(row=0, column=3)
        self._karaoke_transfer_advanced = [w for w in transfer.grid_slaves(row=0) if int(w.grid_info().get("column", 0)) < 3]

        # Modern Transport Bar
        self._build_transport_bar(tab, context="karaoke")

        # Audio layer strip
        karaoke_viewbar = ttk.Frame(tab, style="Toolbar.TFrame", padding=(8, 4))
        karaoke_viewbar.pack(fill="x", pady=(0, 4))
        ttk.Label(karaoke_viewbar, text="Аудио-слой:", style="PanelMuted.TLabel").pack(side="left")
        self.karaoke_audio_view_combo = ttk.Combobox(
            karaoke_viewbar, state="readonly", width=18,
            textvariable=self.spectrogram_mode_var,
            values=("Waveform", "Spectrogram", "Both"),
        )
        self.karaoke_audio_view_combo.pack(side="left", padx=(5, 8))
        self.karaoke_audio_view_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._audio_view_changed(save=True)
        )
        ttk.Button(
            karaoke_viewbar, text="Настройки спектрограммы…",
            command=self.open_spectrogram_settings, style="Flat.TButton",
        ).pack(side="left")
        ttk.Button(
            karaoke_viewbar, text="Перестроить",
            command=lambda: self._ensure_spectrogram_async(force=True), style="Flat.TButton",
        ).pack(side="left", padx=(4, 0))
        self.karaoke_spectrogram_label = ttk.Label(
            karaoke_viewbar, text="Спектрограмма: —", style="PanelMuted.TLabel"
        )
        self.karaoke_spectrogram_label.pack(side="left", padx=10)

        # Center timeline canvas (expands to fill vertical room!)
        self.karaoke_timeline = DualTimeline(
            tab,
            on_selection=self._karaoke_selection_changed,
            on_karaoke_boundary=self._karaoke_boundary_dragged,
            editable_karaoke=True,
            on_activate=self._karaoke_timeline_activated,
            on_seek=self._playback_seek_requested,
        )
        self.karaoke_timeline.on_add_track = self._handle_add_track
        self.karaoke_timeline.on_move_track = self._handle_move_track
        self.karaoke_timeline.on_delete_track = self._handle_delete_track

        # Bottom Dock: 2 Cards (Left: Text & Syllable, Right: Actions & Burst)
        dock = ttk.Frame(tab)

        # Left Card: Syllable text & Romanization
        left_card = ttk.Frame(dock, style="Card.TFrame", padding=(10, 6))
        left_card.pack(side="left", fill="both", expand=True, padx=(0, 4))

        text_top = ttk.Frame(left_card, style="Card.TFrame")
        text_top.pack(fill="x")
        ttk.Label(text_top, textvariable=self.karaoke_selected_info_var, style="CardHeader.TLabel").pack(side="left")
        ttk.Button(text_top, text="▶ Слог", command=self.play_karaoke_selection, style="Accent.TButton").pack(side="right", padx=(4, 0))
        ttk.Button(text_top, text="→", width=3, command=lambda: self.navigate_karaoke(1), style="Secondary.TButton").pack(side="right", padx=(2, 0))
        ttk.Button(text_top, text="←", width=3, command=lambda: self.navigate_karaoke(-1), style="Secondary.TButton").pack(side="right")

        text_mid = ttk.Frame(left_card, style="Card.TFrame")
        text_mid.pack(fill="x", pady=(4, 2))
        ttk.Label(text_mid, text="Текст слога:", style="CardTitle.TLabel").pack(side="left", anchor="n", padx=(0, 5))
        textbox = ttk.Frame(text_mid, style="Card.TFrame")
        textbox.pack(side="left", fill="x", expand=True)
        self.karaoke_text_editor = tk.Text(
            textbox, height=2, wrap="none", undo=True, maxundo=100,
            font=("TkFixedFont", 10),
        )
        self.karaoke_text_editor.pack(side="top", fill="x", expand=True)
        text_scroll = ttk.Scrollbar(textbox, orient="horizontal", command=self.karaoke_text_editor.xview)
        text_scroll.pack(side="top", fill="x")
        self.karaoke_text_editor.configure(xscrollcommand=text_scroll.set, state="disabled")
        self.karaoke_text_editor.bind("<<Modified>>", self._karaoke_text_modified)
        self.karaoke_text_editor.bind("<Control-Return>", self._karaoke_text_apply_shortcut)
        self.karaoke_text_editor.bind("<Return>", self._karaoke_text_linebreak)
        self.karaoke_text_editor.bind("<FocusOut>", self._on_text_editor_focus_out)

        romanbox = ttk.Frame(text_mid, style="Card.TFrame")
        romanbox.pack(side="left", padx=(8, 0), anchor="n")
        self.karaoke_romanize_check = ttk.Checkbutton(
            romanbox,
            text="Romanize (manual)",
            variable=self.karaoke_romanize_var,
            command=self._romanization_changed,
            state="disabled",
            style="Switch.TCheckbutton",
        )
        self.karaoke_romanize_check.pack(anchor="w")
        self.karaoke_romanization_field = ttk.Frame(romanbox, style="Card.TFrame")
        ttk.Label(self.karaoke_romanization_field, text="Над слогом:", style="CardMuted.TLabel").pack(anchor="w")
        self.karaoke_romanization_entry = ttk.Entry(
            self.karaoke_romanization_field,
            textvariable=self.karaoke_romanization_var,
            width=20,
        )
        self.karaoke_romanization_entry.pack(fill="x")
        self.karaoke_romanization_entry.bind(
            "<Control-Return>", self._karaoke_text_apply_shortcut
        )
        self.karaoke_romanization_entry.bind("<FocusOut>", self._on_text_editor_focus_out)
        self.karaoke_romanization_var.trace_add("write", self._romanization_changed)

        text_bot = ttk.Frame(left_card, style="Card.TFrame")
        text_bot.pack(fill="x", pady=(3, 0))
        btn_box = ttk.Frame(text_bot, style="Card.TFrame")
        btn_box.pack(side="left")
        ttk.Button(btn_box, text="Разделить по курсору", command=self.split_karaoke_at_cursor, style="Secondary.TButton").pack(side="left")
        ttk.Button(btn_box, text="[Непроизнесённое]", command=self.mark_unspoken_selection, style="Secondary.TButton").pack(side="left", padx=(4, 0))
        self.karaoke_link_track0_btn = ttk.Button(btn_box, text="Связать с Track 0", command=self.link_karaoke_to_track0, style="Secondary.TButton")
        ttk.Label(text_bot, textvariable=self.karaoke_text_state_var, style="CardMuted.TLabel").pack(side="left", padx=(8, 0), fill="x", expand=True)

        # Right Card: Timing & Burst Actions
        right_card = ttk.Frame(dock, style="Card.TFrame", padding=(10, 6))
        right_card.pack(side="right", fill="both", padx=(4, 0))

        # Row 1: Operations
        edit_ops = ttk.Frame(right_card, style="Card.TFrame")
        edit_ops.pack(fill="x")
        ttk.Label(edit_ops, text="Тайминг:", style="CardTitle.TLabel").pack(side="left", padx=(0, 4))
        ttk.Button(edit_ops, text="Вставить", command=self.insert_karaoke, style="Secondary.TButton").pack(side="left")
        ttk.Button(edit_ops, text="Разделить", command=self.split_karaoke, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(edit_ops, text="Совместить", command=self.merge_karaoke, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(edit_ops, text="Удалить", command=self.delete_karaoke, style="Danger.TButton").pack(side="left", padx=(3, 0))

        # Row 2: Tag type
        tag_row = ttk.Frame(right_card, style="Card.TFrame")
        tag_row.pack(fill="x", pady=(3, 0))
        ttk.Label(tag_row, text="Тип:", style="CardTitle.TLabel").pack(side="left", padx=(0, 4))
        self.karaoke_tag_combo = ttk.Combobox(
            tag_row, state="readonly", width=17, textvariable=self.karaoke_tag_var,
            values=("\\k (резкий)", "\\kf (плавный)", "\\ko (outline)", "\\K (плавный alias)"),
        )
        self.karaoke_tag_combo.pack(side="left")
        ttk.Button(tag_row, text="Применить тип", command=self.apply_karaoke_type, style="Secondary.TButton").pack(side="left", padx=(4, 0))

        # Row 3: History & Save
        hist_row = ttk.Frame(right_card, style="Card.TFrame")
        hist_row.pack(fill="x", pady=(3, 0))
        ttk.Button(hist_row, text="↶", width=3, command=self.undo_karaoke, style="Secondary.TButton").pack(side="left")
        ttk.Button(hist_row, text="↷", width=3, command=self.redo_karaoke, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        ttk.Button(hist_row, text="Сохранить", command=self.save_ass, style="Success.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(hist_row, text="Весь текст…", command=self.open_full_text_editor, style="Secondary.TButton").pack(side="left", padx=(4, 0))

        # Row 4: Burst coloring
        burst_row = ttk.Frame(right_card, style="Card.TFrame")
        burst_row.pack(fill="x", pady=(3, 0))
        ttk.Label(burst_row, textvariable=self.karaoke_burst_state_var, style="CardMuted.TLabel").pack(side="left")
        ttk.Button(burst_row, text="Окрасить выделение", command=self.colour_selected_karaoke_burst, style="Danger.TButton").pack(side="right")
        ttk.Button(burst_row, text="Снять окраску", command=self.uncolour_selected_karaoke_burst, style="Secondary.TButton").pack(side="right", padx=(0, 4))
        ttk.Button(burst_row, text="Экспорт аудио…", command=self.export_burst_or_selection_audio, style="Secondary.TButton").pack(side="right", padx=(0, 4))

        self.karaoke_help = ttk.Label(
            tab,
            text=(
                "Колесо — масштаб; средняя кнопка — панорамирование; Shift+клик — диапазон; "
                "двойной клик — текст. [текст] внутри объединённого слога не окрашивается и "
                "не становится отдельной SPS-единицей. Красная заливка означает burst. "
                "F2 — фокус текста, Ctrl+Enter — применить текст и romanization."
            ),
            style="Muted.TLabel",
            wraplength=1450,
            justify="left",
        )
        self.karaoke_help.pack(side="bottom", fill="x", pady=(3, 0))
        dock.pack(side="bottom", fill="x", pady=(2, 2))
        self.karaoke_timeline.pack(side="top", fill="both", expand=True, pady=(2, 4))

    def _build_sps_tab(self) -> None:
        tab = self.sps_tab
        header = ttk.Frame(tab, style="Subheader.TFrame")
        header.pack(fill="x", pady=(0, 3))
        left = ttk.Frame(header, style="Subheader.TFrame")
        left.pack(side="left")
        ttk.Label(left, text="Точное SPS-измерение", style="Header.TLabel").pack(side="left")
        self.sps_summary = ttk.Label(left, text="Материал ещё не передан", style="Badge.TLabel")
        self.sps_summary.pack(side="left", padx=12)
        ttk.Button(header, text="Вернуться к выделению в Karaoke", command=self.return_to_karaoke, style="Accent.TButton").pack(side="right")

        self._build_transport_bar(tab, context="sps")

        tool_card = ttk.Frame(tab, style="Toolbar.TFrame", padding=(8, 4))
        tool_card.pack(fill="x", pady=(0, 4))
        ttk.Label(tool_card, text="Аудио-слой:", style="PanelMuted.TLabel").pack(side="left")
        self.audio_view_combo = ttk.Combobox(
            tool_card, state="readonly", width=16, textvariable=self.spectrogram_mode_var,
            values=("Waveform", "Spectrogram", "Both"),
        )
        self.audio_view_combo.pack(side="left", padx=(4, 6))
        self.audio_view_combo.bind("<<ComboboxSelected>>", lambda _e: self._audio_view_changed(save=True))
        ttk.Button(tool_card, text="Настройки спектрограммы…", command=self.open_spectrogram_settings, style="Flat.TButton").pack(side="left")
        ttk.Button(tool_card, text="Перестроить", command=lambda: self._ensure_spectrogram_async(force=True), style="Flat.TButton").pack(side="left", padx=(3, 8))
        self.spectrogram_label = ttk.Label(tool_card, text="Спектрограмма: —", style="PanelMuted.TLabel")
        self.spectrogram_label.pack(side="left", padx=(0, 12))

        self.sps_graphbar = tool_card
        ttk.Label(tool_card, text="SPS-график:", style="PanelMuted.TLabel").pack(side="left")
        source_combo = ttk.Combobox(
            tool_card, state="readonly", width=16, textvariable=self.sps_graph_source_var,
            values=("ASS timing", "Точное measurement", "Оба"),
        )
        source_combo.pack(side="left", padx=(4, 6))
        ttk.Label(tool_card, text="Сглаживание:", style="PanelMuted.TLabel").pack(side="left")
        smooth_spin = ttk.Spinbox(tool_card, from_=1, to=31, increment=2, width=4, textvariable=self.sps_graph_smoothing_var)
        smooth_spin.pack(side="left", padx=(3, 6))
        ttk.Button(tool_card, text="Обновить", command=self._refresh_sps_graph, style="Flat.TButton").pack(side="left")
        ttk.Button(tool_card, text="Экспорт CSV…", command=self.export_sps_graph_csv, style="Flat.TButton").pack(side="left", padx=(4, 0))
        ttk.Button(tool_card, text="Экспорт PNG 16:9…", command=self.export_sps_graph_png, style="Flat.TButton").pack(side="left", padx=(4, 0))
        source_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_sps_graph())
        smooth_spin.bind("<Return>", lambda _e: self._refresh_sps_graph())

        split = ttk.Panedwindow(tab, orient="vertical")
        self.sps_split = split
        upper = ttk.Frame(split)
        lower = ttk.Frame(split)
        split.add(upper, weight=3)
        split.add(lower, weight=2)
        visual_split = ttk.Panedwindow(upper, orient="vertical")
        visual_split.pack(fill="both", expand=True)
        graph_frame = ttk.Frame(visual_split)
        timeline_frame = ttk.Frame(visual_split)
        visual_split.add(graph_frame, weight=1)
        visual_split.add(timeline_frame, weight=3)

        self.sps_timeline = DualTimeline(
            timeline_frame,
            on_selection=self._sps_selection_changed,
            on_view_change=self._sps_viewport_changed,
            on_measurement=self._measurement_dragged,
            editable_measurements=True,
            on_seek=self._playback_seek_requested,
        )
        self.sps_timeline.pack(fill="both", expand=True)
        self.sps_graph = SPSGraph(
            graph_frame,
            viewport=self.sps_timeline.viewport,
            on_view_changed=self._sps_graph_view_changed,
            on_point_selected=self._sps_graph_point_selected,
        )
        self.sps_graph.pack(fill="both", expand=True)

        columns = ("start", "end", "peak", "mean", "text")
        self.burst_tree = ttk.Treeview(lower, columns=columns, show="headings", height=6)
        headings = {"start": "Начало", "end": "Конец", "peak": "Peak SPS", "mean": "Mean SPS", "text": "Текст"}
        widths = {"start": 95, "end": 95, "peak": 85, "mean": 85, "text": 600}
        for col in columns:
            self.burst_tree.heading(col, text=headings[col])
            self.burst_tree.column(col, width=widths[col], anchor="w" if col == "text" else "center")
        tree_scroll = ttk.Scrollbar(lower, orient="vertical", command=self.burst_tree.yview)
        self.burst_tree.configure(yscrollcommand=tree_scroll.set)
        self.burst_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.burst_tree.bind("<<TreeviewSelect>>", self._burst_selected)
        self.burst_tree.bind("<Double-1>", self._burst_double_click)

        # Dock below: Measurements & Burst Card
        dock = ttk.Frame(tab)

        meas_card = ttk.Frame(dock, style="Card.TFrame", padding=(10, 6))
        meas_card.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.measure_text = ttk.Label(meas_card, text="Слог: —", style="CardHeader.TLabel")
        self.measure_text.pack(anchor="w")

        m_inputs = ttk.Frame(meas_card, style="Card.TFrame")
        m_inputs.pack(fill="x", pady=(3, 0))
        ttk.Label(m_inputs, text="Start:", style="CardTitle.TLabel").pack(side="left", padx=(0, 3))
        self.measure_start_var = tk.StringVar()
        self.measure_start_entry = ttk.Entry(m_inputs, textvariable=self.measure_start_var, width=10)
        self.measure_start_entry.pack(side="left")
        ttk.Label(m_inputs, text="End:", style="CardTitle.TLabel").pack(side="left", padx=(6, 3))
        self.measure_end_var = tk.StringVar()
        self.measure_end_entry = ttk.Entry(m_inputs, textvariable=self.measure_end_var, width=10)
        self.measure_end_entry.pack(side="left")
        ttk.Button(m_inputs, text="Применить", command=self.apply_measurement_fields, style="Primary.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(m_inputs, text="Сбросить", command=self.reset_selected_measurement, style="Secondary.TButton").pack(side="left", padx=(4, 0))
        ttk.Button(m_inputs, text="↶", width=3, command=self.undo_sps_measurement, style="Secondary.TButton").pack(side="left", padx=(4, 0))
        ttk.Button(m_inputs, text="↷", width=3, command=self.redo_sps_measurement, style="Secondary.TButton").pack(side="left", padx=(2, 0))
        ttk.Button(m_inputs, text="▶ Выделение", command=self.play_sps_selection, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(m_inputs, text="■", width=3, command=self.stop_playback, style="Secondary.TButton").pack(side="left", padx=(3, 0))
        self.measure_stats = ttk.Label(m_inputs, text="", style="CardMuted.TLabel")
        self.measure_stats.pack(side="left", padx=(8, 0))

        burst_card = ttk.Frame(dock, style="Card.TFrame", padding=(10, 6))
        burst_card.pack(side="right", fill="both", padx=(4, 0))
        self.measure_peak_var = tk.StringVar(value="Быстрейший бёрст: —")
        self.measure_peak_row = burst_card
        ttk.Label(burst_card, textvariable=self.measure_peak_var, style="CardHeader.TLabel").pack(anchor="w")

        b_actions1 = ttk.Frame(burst_card, style="Card.TFrame")
        b_actions1.pack(fill="x", pady=(3, 0))
        ttk.Button(b_actions1, text="Выделить бёрст", command=self.select_fastest_legacy_burst, style="Accent.TButton").pack(side="left")
        ttk.Button(b_actions1, text="Окрасить бёрст", command=self.colour_selected_burst, style="Danger.TButton").pack(side="left", padx=(4, 0))
        ttk.Button(b_actions1, text="Снять окраску", command=self.uncolour_selected_burst, style="Secondary.TButton").pack(side="left", padx=(4, 0))

        b_actions2 = ttk.Frame(burst_card, style="Card.TFrame")
        b_actions2.pack(fill="x", pady=(3, 0))
        ttk.Button(b_actions2, text="Экспорт аудио…", command=self.export_burst_or_selection_audio, style="Secondary.TButton").pack(side="left")
        ttk.Button(b_actions2, text="Экспорт measurements…", command=self.export_measurements, style="Secondary.TButton").pack(side="left", padx=(4, 0))
        ttk.Button(b_actions2, text="Загрузить measurements…", command=self.import_measurements, style="Secondary.TButton").pack(side="left", padx=(4, 0))

        self.measure_start_entry.bind("<Return>", lambda _e: self.apply_measurement_fields())
        self.measure_end_entry.bind("<Return>", lambda _e: self.apply_measurement_fields())

        sps_hint = ttk.Label(
            tab,
            text="Start и End независимы: End можно поставить раньше Start, как у слога с префиксом «-» в старых labels.",
            style="Muted.TLabel",
        )
        sps_hint.pack(side="bottom", fill="x", pady=(2, 1))
        dock.pack(side="bottom", fill="x", pady=(2, 2))
        split.pack(side="top", fill="both", expand=True, pady=(2, 2))

    def _save_preferences(self) -> None:
        save_ui_preferences(
            self.theme_var.get(),
            self.advanced_mode_var.get(),
            ffmpeg_mode=self.ffmpeg_mode_var.get(),
            ffmpeg_path=self.ffmpeg_path_var.get(),
            playback_warmup_ms=self._playback_ms_value(self.playback_warmup_var.get(), 700),
            playback_tail_ms=self._playback_ms_value(self.playback_tail_var.get(), 250),
            playback_speed=normalize_playback_speed(float(self.playback_speed_var.get())),
            playback_cursor_offset_ms=self._playback_offset_ms_value(self.playback_cursor_offset_var.get(), 0),
            playback_preserve_pitch=bool(self.playback_preserve_pitch_var.get()),
            playback_return_to_start=bool(self.playback_return_to_start_var.get()),
            playback_follow_default_device=bool(self.playback_follow_default_device_var.get()),
            spectrogram_mode=self.spectrogram_mode_var.get(),
            spectrogram_analysis=asdict(self.spectrogram_analysis),
            spectrogram_view=asdict(self.spectrogram_view),
            spectrogram_voice_preset=self.voice_preset_var.get(),
            spectrogram_speed_preset=self.speed_preset_var.get(),
            spectrogram_expected_sps=self.expected_sps_var.get(),
            sps_graph_source=self.sps_graph_source_var.get(),
            sps_graph_smoothing=self._sps_smoothing_value(),
            hotkeys=self.hotkeys,
            autosave_mode=self.autosave_mode_var.get(),
        )

    def _sync_ffmpeg_from_project(self) -> None:
        mode, path = self.session.ffmpeg_preference_from_project()
        self.ffmpeg_mode_var.set(mode)
        self.ffmpeg_path_var.set(path)
        self.session.configure_ffmpeg(mode, path)
        self._save_preferences()

    def _sync_ffmpeg_to_project(self) -> None:
        self.session.configure_ffmpeg(self.ffmpeg_mode_var.get(), self.ffmpeg_path_var.get())
        self.session.persist_ffmpeg_preference()
        self._save_preferences()

    def open_ffmpeg_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("FFmpeg")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(background=self.palette.bg)
        dialog.grab_set()

        outer = ttk.Frame(dialog, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Источник FFmpeg", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="PATH и Conda больше не используются автоматически. Выберите portable FFmpeg проекта или конкретный ffmpeg.exe.",
            style="Muted.TLabel",
            wraplength=560,
            justify="left",
        ).pack(anchor="w", pady=(3, 12))

        mode = tk.StringVar(value=self.ffmpeg_mode_var.get())
        path = tk.StringVar(value=self.ffmpeg_path_var.get())
        ttk.Radiobutton(outer, text=r"Portable: work\hz\ffmpeg\bin\ffmpeg.exe", variable=mode, value="portable").pack(anchor="w", pady=2)
        ttk.Radiobutton(outer, text="Пользовательский ffmpeg.exe", variable=mode, value="custom").pack(anchor="w", pady=(7, 3))

        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 8))
        entry = ttk.Entry(row, textvariable=path, width=62)
        entry.pack(side="left", fill="x", expand=True)

        def browse() -> None:
            chosen = filedialog.askopenfilename(
                title="Выберите ffmpeg.exe",
                filetypes=(("FFmpeg", "ffmpeg.exe"), ("Исполняемые файлы", "*.exe"), ("Все файлы", "*.*")),
                parent=dialog,
            )
            if chosen:
                path.set(chosen)
                mode.set("custom")

        ttk.Button(row, text="Обзор…", command=browse).pack(side="left", padx=(6, 0))
        result_var = tk.StringVar(value="")
        result_label = ttk.Label(outer, textvariable=result_var, style="Muted.TLabel", wraplength=560, justify="left")
        result_label.pack(anchor="w", fill="x", pady=(2, 10))

        def candidate_path() -> Path | None:
            previous_mode = self.session.ffmpeg_mode
            previous_path = self.session.ffmpeg_override
            try:
                self.session.configure_ffmpeg(mode.get(), path.get())
                return self.session.resolved_ffmpeg()
            finally:
                self.session.ffmpeg_mode = previous_mode
                self.session.ffmpeg_override = previous_path

        def check() -> None:
            exe = candidate_path()
            if exe is None:
                if mode.get() == "portable":
                    result_var.set(r"Не найден work\hz\ffmpeg\bin\ffmpeg.exe. Проверьте структуру рабочей папки.")
                else:
                    result_var.set("Указанный ffmpeg.exe не найден.")
                return
            try:
                proc = subprocess.run(
                    [str(exe), "-version"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8", errors="replace", timeout=10,
                    env=media_tool_subprocess_env(exe),
                )
                first = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
                if proc.returncode == 0:
                    result_var.set(f"OK: {exe}\n{first}")
                else:
                    result_var.set(f"Ошибка запуска ({proc.returncode}): {exe}\n{first}")
            except Exception as exc:
                result_var.set(f"Ошибка запуска: {exc}")

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Проверить", command=check).pack(side="left")

        def save_and_close() -> None:
            if mode.get() == "custom":
                raw = path.get().strip().strip('"')
                if not raw or not Path(raw).expanduser().is_file():
                    messagebox.showerror("FFmpeg", "Выберите существующий ffmpeg.exe.", parent=dialog)
                    return
            self.ffmpeg_mode_var.set(mode.get())
            self.ffmpeg_path_var.set(path.get().strip())
            self._sync_ffmpeg_to_project()
            self._invalidate_waveform()
            self._invalidate_playback_cache()
            self._invalidate_spectrogram()
            self._refresh_labels()
            self._set_status(f"FFmpeg: {self.session.resolved_ffmpeg() or 'не найден'}")
            dialog.destroy()

        ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Сохранить", command=save_and_close, style="Accent.TButton").pack(side="right", padx=(0, 6))
        check()
        dialog.update_idletasks()
        try:
            x = self.winfo_rootx() + max(20, (self.winfo_width() - dialog.winfo_reqwidth()) // 2)
            y = self.winfo_rooty() + max(20, (self.winfo_height() - dialog.winfo_reqheight()) // 3)
            dialog.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def open_settings(self, initial_tab: str = "general") -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Настройки — Karaoke SPS Workbench")
        dialog.transient(self)
        dialog.geometry("720x650")
        dialog.minsize(620, 520)
        dialog.configure(background=self.palette.bg)
        self._add_hotkey_bindtag(dialog)

        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)
        tabs = {name: ttk.Frame(notebook, padding=14) for name in ("general", "playback", "sps", "hotkeys")}
        notebook.add(tabs["general"], text="Общие")
        notebook.add(tabs["playback"], text="Воспроизведение")
        notebook.add(tabs["sps"], text="Точный SPS")
        notebook.add(tabs["hotkeys"], text="Горячие клавиши")

        # General
        theme = tk.StringVar(value=self.theme_var.get())
        advanced = tk.BooleanVar(value=self.advanced_mode_var.get())
        autosave_labels = {
            "disabled": "Выключено",
            "after_edit": "После каждого изменения",
            "1": "Раз в 1 мин",
            "5": "Раз в 5 мин",
            "10": "Раз в 10 мин",
        }
        autosave_reverse = {v: k for k, v in autosave_labels.items()}
        autosave_display = tk.StringVar(
            value=autosave_labels.get(self.autosave_mode_var.get(), "Выключено")
        )
        ttk.Label(tabs["general"], text="Интерфейс", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(tabs["general"], text="Тема:").grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Combobox(tabs["general"], state="readonly", width=32, textvariable=theme, values=theme_names()).grid(row=1, column=1, sticky="ew", pady=(12, 4))
        ttk.Checkbutton(tabs["general"], text="Advanced-интерфейс", variable=advanced).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(tabs["general"], text="Автосохранение ASS:").grid(row=3, column=0, sticky="w", pady=(8, 4))
        ttk.Combobox(tabs["general"], state="readonly", width=32, textvariable=autosave_display, values=tuple(autosave_labels.values())).grid(row=3, column=1, sticky="ew", pady=(8, 4))
        ttk.Separator(tabs["general"]).grid(row=4, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(tabs["general"], text="Медиа", style="Header.TLabel").grid(row=5, column=0, columnspan=2, sticky="w")
        ffmpeg_text = tk.StringVar(value=f"FFmpeg: {self.session.resolved_ffmpeg() or 'не найден'}")
        ttk.Label(tabs["general"], textvariable=ffmpeg_text, style="Muted.TLabel", wraplength=520).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 5))
        ttk.Button(tabs["general"], text="Настроить FFmpeg…", command=self.open_ffmpeg_settings).grid(row=7, column=0, sticky="w")
        tabs["general"].columnconfigure(1, weight=1)

        # Playback
        speed = tk.DoubleVar(value=float(self.playback_speed_var.get()))
        preserve = tk.BooleanVar(value=bool(self.playback_preserve_pitch_var.get()))
        return_start = tk.BooleanVar(value=bool(self.playback_return_to_start_var.get()))
        follow_default = tk.BooleanVar(value=bool(self.playback_follow_default_device_var.get()))
        cursor_offset = tk.StringVar(value=self.playback_cursor_offset_var.get())
        warmup = tk.StringVar(value=self.playback_warmup_var.get())
        tail = tk.StringVar(value=self.playback_tail_var.get())
        pt = tabs["playback"]
        ttk.Label(pt, text="Транспорт", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(pt, text="Скорость:").grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Spinbox(pt, from_=0.25, to=2.0, increment=0.05, width=8, textvariable=speed).grid(row=1, column=1, sticky="w", pady=(12, 4))
        ttk.Label(pt, text="0.97×–1.03× автоматически = 1.00×", style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=(82, 0), pady=(12, 4))
        ttk.Checkbutton(pt, text="Сохранять высоту тона при изменении скорости", variable=preserve).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(pt, text="После Stop/окончания вернуть полосу к точке старта", variable=return_start).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(pt, text="Коррекция полосы, мс (− назад / + вперёд):").grid(row=4, column=0, sticky="w", pady=(10, 4))
        ttk.Spinbox(pt, from_=-250, to=250, increment=5, width=8, textvariable=cursor_offset).grid(row=4, column=1, sticky="w", pady=(10, 4))
        ttk.Separator(pt).grid(row=5, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(pt, text="Аудиоустройство", style="Header.TLabel").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            pt, text="Следовать системному устройству вывода по умолчанию", variable=follow_default
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 4))
        device_text = tk.StringVar(value=f"Сейчас: {self.player.backend_description}")
        ttk.Label(pt, textvariable=device_text, style="Muted.TLabel", wraplength=560).grid(row=8, column=0, columnspan=2, sticky="w", pady=(2, 5))

        def reconnect_audio_device() -> None:
            try:
                self.player.set_follow_default_device(bool(follow_default.get()))
                self.player.refresh_output_device(force=True)
                device_text.set(f"Сейчас: {self.player.backend_description}")
                self._set_status(f"Аудиовыход переподключён · {self.player.backend_description}")
            except Exception as exc:
                device_text.set(f"Ошибка переподключения: {exc}")

        ttk.Button(pt, text="Переподключить сейчас", command=reconnect_audio_device).grid(row=9, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            pt,
            text="При включённой опции PortAudio следит за Windows Core Audio и переоткрывает stream только при реальной смене default endpoint.",
            style="Muted.TLabel", wraplength=560, justify="left"
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Separator(pt).grid(row=11, column=0, columnspan=2, sticky="ew", pady=12)
        ttk.Label(pt, text="Fallback-плеер", style="Header.TLabel").grid(row=12, column=0, columnspan=2, sticky="w")
        ttk.Label(pt, text="Warm-up, мс:").grid(row=13, column=0, sticky="w", pady=(8, 4))
        ttk.Spinbox(pt, from_=0, to=2000, increment=50, width=8, textvariable=warmup).grid(row=13, column=1, sticky="w")
        ttk.Label(pt, text="Tail, мс:").grid(row=14, column=0, sticky="w", pady=4)
        ttk.Spinbox(pt, from_=0, to=2000, increment=50, width=8, textvariable=tail).grid(row=14, column=1, sticky="w")
        ttk.Label(pt, text="Warm-up/tail используются только резервным backend; PortAudio читает готовый PCM-кэш напрямую.", style="Muted.TLabel", wraplength=560).grid(row=15, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # SPS
        source = tk.StringVar(value=self.sps_graph_source_var.get())
        smoothing = tk.StringVar(value=self.sps_graph_smoothing_var.get())
        st = tabs["sps"]
        ttk.Label(st, text="Точный SPS", style="Header.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(st, text="Метод расчёта:").grid(row=1, column=0, sticky="w", pady=(12, 4))
        ttk.Label(st, text="Legacy 1–2 s (count / фактическая длительность)", style="Panel.TLabel").grid(row=1, column=1, sticky="w", pady=(12, 4))
        ttk.Label(st, text="Источник графика:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(st, state="readonly", width=24, textvariable=source, values=("ASS timing", "Точное measurement", "Оба")).grid(row=2, column=1, sticky="w")
        ttk.Label(st, text="Сглаживание графика:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(st, from_=1, to=31, increment=2, width=8, textvariable=smoothing).grid(row=3, column=1, sticky="w")
        ttk.Label(st, text="Strict-window алгоритмы больше не доступны как способ точного измерения. Они остаются внутренней эвристикой только для автоматической подсказки кандидатов на бёрсты.", style="Muted.TLabel", wraplength=560, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))

        # Hotkeys
        hotkey_vars = {action: tk.StringVar(value=self.hotkeys.get(action, "")) for action in DEFAULT_HOTKEYS}
        ht = tabs["hotkeys"]
        ttk.Label(ht, text="Горячие клавиши", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            ht,
            text="Формат: Ctrl+Space, Shift+Space, Ctrl+Left, Delete, I. "
                 "Пустое поле отключает сочетание. Alt в стандартных сочетаниях не используется.",
            style="Muted.TLabel",
            wraplength=590,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 10))
        row = 2
        for action, label in HOTKEY_LABELS.items():
            ttk.Label(ht, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(ht, textvariable=hotkey_vars[action], width=22).grid(row=row, column=1, sticky="ew", padx=(12, 4), pady=2)
            row += 1
        def reset_hotkeys() -> None:
            for action, value in DEFAULT_HOTKEYS.items():
                hotkey_vars[action].set(value)
        ttk.Button(ht, text="Сбросить по умолчанию", command=reset_hotkeys).grid(row=row, column=0, sticky="w", pady=(10, 0))
        ht.columnconfigure(1, weight=1)

        def apply_values(*, close: bool = False) -> bool:
            try:
                parsed_hotkeys = validate_hotkeys({action: var.get() for action, var in hotkey_vars.items()})
                smooth = max(1, min(31, int(smoothing.get())))
                spd = normalize_playback_speed(max(0.25, min(2.0, float(speed.get()))))
            except (ValueError, TypeError) as exc:
                messagebox.showerror("Настройки", str(exc), parent=dialog)
                return False
            self.theme_var.set(theme.get())
            self.advanced_mode_var.set(bool(advanced.get()))
            self.autosave_mode_var.set(autosave_reverse.get(autosave_display.get(), "disabled"))
            self.playback_speed_var.set(spd)
            self.playback_preserve_pitch_var.set(bool(preserve.get()))
            self.playback_return_to_start_var.set(bool(return_start.get()))
            self.playback_follow_default_device_var.set(bool(follow_default.get()))
            self.playback_cursor_offset_var.set(cursor_offset.get())
            self.playback_warmup_var.set(warmup.get())
            self.playback_tail_var.set(tail.get())
            self.sps_graph_source_var.set(source.get())
            self.sps_graph_smoothing_var.set(str(smooth))
            self.hotkeys = parsed_hotkeys
            self._install_hotkeys()
            self._apply_theme(save=False)
            self._apply_ui_mode(save=False)
            self._apply_playback_padding(save=False)
            self.player.set_preserve_pitch(self.playback_preserve_pitch_var.get())
            self.player.set_follow_default_device(self.playback_follow_default_device_var.get())
            try:
                self.player.set_speed(spd)
            except Exception:
                pass
            self.playback_speed_text_var.set(f"{spd:.2f}×")
            self._refresh_sps_graph()
            self._save_preferences()
            if close:
                dialog.destroy()
            return True

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", command=lambda: apply_values(close=True), style="Accent.TButton").pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text="Применить", command=apply_values).pack(side="right", padx=(0, 6))
        if initial_tab in tabs:
            notebook.select(tabs[initial_tab])
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        try:
            dialog.grab_set()
        except tk.TclError:
            pass

    def open_playback_settings(self) -> None:
        self.open_settings("playback")

    def _theme_changed(self) -> None:
        self._apply_theme(save=True)

    def _advanced_changed(self) -> None:
        self._apply_ui_mode(save=True)

    def _apply_theme(self, *, save: bool = True) -> None:
        self.palette = get_theme(self.theme_var.get())
        apply_ttk_theme(self, self.palette)
        if hasattr(self, "main_menu"):
            apply_menu_theme(self.main_menu, self.palette)
        if hasattr(self, "karaoke_text_editor"):
            apply_text_theme(self.karaoke_text_editor, self.palette)
        if hasattr(self, "karaoke_timeline"):
            self.karaoke_timeline.apply_theme(self.palette)
        if hasattr(self, "sps_timeline"):
            self.sps_timeline.apply_theme(self.palette)
        if hasattr(self, "sps_graph"):
            # Theme switching must not recalculate SPS data.  SPSGraph.apply_theme
            # recolours the existing series and schedules one lightweight redraw.
            self.sps_graph.apply_theme(self.palette)
        if hasattr(self, "alignment_panel"):
            self.alignment_panel.apply_theme(self.palette)
        if hasattr(self, "render_panel"):
            self.render_panel.apply_theme(self.palette)
        if hasattr(self, "log_panel"):
            self.log_panel.apply_theme(self.palette)
        for scroll_frame in ("alignment_scroll", "render_scroll", "logs_scroll"):
            if hasattr(self, scroll_frame):
                getattr(self, scroll_frame).set_palette(self.palette)
        if save:
            self._save_preferences()

    def _apply_ui_mode(self, *, save: bool = True) -> None:
        advanced = bool(self.advanced_mode_var.get())
        if hasattr(self, "_karaoke_transfer_advanced"):
            for widget in self._karaoke_transfer_advanced:
                if advanced:
                    widget.grid()
                else:
                    widget.grid_remove()
        if hasattr(self, "karaoke_timeline"):
            self.karaoke_timeline.set_advanced_mode(advanced)
        if hasattr(self, "karaoke_link_track0_btn"):
            if advanced:
                self.karaoke_link_track0_btn.pack(side="left", padx=(4, 0))
            else:
                self.karaoke_link_track0_btn.pack_forget()
        self._update_karaoke_help_text()
        if hasattr(self, "sps_graphbar"):
            if advanced:
                self.sps_graphbar.pack(fill="x", before=self.sps_split)
            else:
                self.sps_graphbar.pack_forget()
        if hasattr(self, "alignment_panel"):
            self.alignment_panel.set_advanced_mode(advanced)
        if hasattr(self, "render_panel"):
            self.render_panel.set_advanced_mode(advanced)
        self._set_status("Advanced-интерфейс" if advanced else "Simple-интерфейс")
        if save:
            self._save_preferences()

    def _update_karaoke_help_text(self) -> None:
        if not hasattr(self, "karaoke_help"):
            return
        advanced = bool(self.advanced_mode_var.get())
        if advanced:
            text = (
                "Колесо — прокрутка дорожек; Ctrl+Колесо — масштаб; Shift+Колесо — панорамирование; "
                "средняя кнопка — панорамирование; Shift+клик — диапазон; двойной клик — текст. "
                "Дорожка 0: номер слога снизу, {\\remap} отключает закраску. "
                "Доп. дорожки: {\\id0:N} ссылается на слог N. "
                "F2 — фокус текста, Ctrl+Enter — применить текст и romanization."
            )
        else:
            text = (
                "Колесо — масштаб; средняя кнопка — панорамирование; Shift+клик — диапазон; "
                "двойной клик — текст. [текст] внутри объединённого слога не окрашивается и "
                "не становится отдельной SPS-единицей. Красная заливка означает burst. "
                "F2 — фокус текста, Ctrl+Enter — применить текст и romanization."
            )
        self.karaoke_help.configure(text=text)
        self.karaoke_help.pack(fill="x", pady=(3, 0))

    @staticmethod
    def _portable_project_value(root: Path, value: str | Path | None) -> str | None:
        if value is None or not str(value).strip():
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            return str(path)
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return str(path)

    @staticmethod
    def _timeline_project_state(widget) -> dict:
        return {
            "selected_ids": sorted(widget.selected_ids),
            "view_start": float(widget.viewport.view_start),
            "view_end": float(widget.viewport.view_end),
        }

    @staticmethod
    def _apply_timeline_project_state(widget, state: object) -> None:
        if not isinstance(state, dict):
            return
        widget.select_ids(state.get("selected_ids", ()))
        try:
            start = float(state["view_start"])
            end = float(state["view_end"])
        except (KeyError, TypeError, ValueError):
            return
        if end <= start:
            return
        widget.viewport.view_start = start
        widget.viewport.view_end = end
        widget.viewport._clamp()
        widget._sync_scrollbar()
        widget.request_redraw(delay_ms=1, force=True)

    def _collect_project_state(self) -> dict:
        root = self.session.project_root
        if root is None:
            raise RuntimeError("Проект не создан")
        values: dict[str, object] = {}
        for name in self._PROJECT_STATE_VARS:
            variable = getattr(self, name, None)
            if variable is not None:
                values[name.removesuffix("_var")] = variable.get()
        sps_ids = []
        if self.session.sps_timeline is not None:
            sps_ids = [item.id for item in self.session.sps_timeline.syllables]
            if sps_ids == [item.id for item in self.session.syllables]:
                sps_ids = []  # Empty scope means the whole ASS.
        try:
            active_tab = int(self.notebook.index(self.notebook.select()))
        except (tk.TclError, ValueError):
            active_tab = 0
        return {
            "version": 1,
            "active_tab": active_tab,
            "values": values,
            "spectrogram_analysis": asdict(self.spectrogram_analysis),
            "spectrogram_view": asdict(self.spectrogram_view),
            "playhead_time": float(self.playhead_time),
            "playback_limits": self.playback_limit_ids,
            "karaoke_timeline": self._timeline_project_state(self.karaoke_timeline),
            "sps": {
                "loaded": self.session.sps_timeline is not None,
                "scope_ids": sps_ids,
                "timeline": self._timeline_project_state(self.sps_timeline),
            },
            "alignment": self.alignment_panel.project_state(root),
            "render": self.render_panel.project_state(root),
            "logs": self.log_panel.project_state(),
        }

    def _restore_project_state(self) -> None:
        project = self.session.project
        root = self.session.project_root
        if project is None or root is None or not isinstance(project.metadata, dict):
            return
        state = project.metadata.get("ui_state")
        if not isinstance(state, dict):
            return

        values = state.get("values", {})
        if isinstance(values, dict):
            for name in self._PROJECT_STATE_VARS:
                key = name.removesuffix("_var")
                if key not in values or not hasattr(self, name):
                    continue
                try:
                    getattr(self, name).set(values[key])
                except (tk.TclError, TypeError, ValueError):
                    continue

        analysis_state = state.get("spectrogram_analysis")
        if isinstance(analysis_state, dict):
            try:
                analysis = SpectrogramAnalysisSettings(**analysis_state)
                analysis.validate()
                self.spectrogram_analysis = analysis
            except (TypeError, ValueError):
                pass
        view_state = state.get("spectrogram_view")
        if isinstance(view_state, dict):
            try:
                view = SpectrogramViewSettings(**view_state)
                view.validate(self.spectrogram_analysis.sample_rate / 2.0)
                self.spectrogram_view = view
            except (TypeError, ValueError):
                pass

        self.alignment_panel.apply_project_state(state.get("alignment"), root)
        self.render_panel.apply_project_state(state.get("render"), root)
        self.log_panel.apply_project_state(state.get("logs"))
        self._apply_theme(save=False)
        self._apply_ui_mode(save=False)
        self._apply_playback_padding(save=False)
        try:
            speed = normalize_playback_speed(float(self.playback_speed_var.get()))
            self.playback_speed_var.set(speed)
            self.playback_speed_text_var.set(f"{speed:.2f}×")
            self.player.set_preserve_pitch(bool(self.playback_preserve_pitch_var.get()))
            self.player.set_follow_default_device(bool(self.playback_follow_default_device_var.get()))
            self.player.set_speed(speed)
        except Exception:
            pass

        sps_state = state.get("sps", {})
        if (
            isinstance(sps_state, dict)
            and sps_state.get("loaded")
            and self.session.karaoke_timeline is not None
        ):
            try:
                saved_ids = [str(value) for value in sps_state.get("scope_ids", ())]
                all_ids = [item.id for item in self.session.syllables]
                scope_ids = None if not saved_ids or saved_ids == all_ids else saved_ids
                threshold = float(str(self.min_sps_var.get()).replace(",", "."))
                result = self.session.transfer_to_sps(syllable_ids=scope_ids, min_peak_sps=threshold)
                self._populate_sps(result)
            except Exception as exc:
                self._set_status(f"Проект открыт, но состояние Точного SPS не восстановлено: {exc}")

        limits = state.get("playback_limits")
        if isinstance(limits, dict):
            for context in ("karaoke", "sps"):
                raw = limits.get(context)
                if isinstance(raw, dict):
                    self.playback_limit_ids[context] = {
                        "start": raw.get("start"),
                        "stop": raw.get("stop"),
                    }
        self._update_playback_limit_label("karaoke")
        self._update_playback_limit_label("sps")
        self._apply_timeline_project_state(self.karaoke_timeline, state.get("karaoke_timeline"))
        if isinstance(sps_state, dict):
            self._apply_timeline_project_state(self.sps_timeline, sps_state.get("timeline"))
        try:
            self._set_playhead(float(state.get("playhead_time", 0.0)))
        except (TypeError, ValueError):
            self._set_playhead(0.0)
        display = self.spectrogram_mode_var.get()
        audio_mode = {"Waveform": "waveform", "Spectrogram": "spectrogram", "Both": "both"}.get(
            display, "waveform"
        )
        self.karaoke_timeline.set_spectrogram_view(self.spectrogram_view)
        self.sps_timeline.set_spectrogram_view(self.spectrogram_view)
        self.karaoke_timeline.set_audio_mode(audio_mode)
        self.sps_timeline.set_audio_mode(audio_mode)
        try:
            tabs = self.notebook.tabs()
            index = int(state.get("active_tab", 0))
            if 0 <= index < len(tabs):
                self.notebook.select(index)
        except (tk.TclError, TypeError, ValueError):
            pass

    def save_project(self, *, save_as: bool = False) -> bool:
        if self.session.document is not None:
            if not self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids())):
                return False

        root = self.session.project_root
        if root is None or save_as:
            folder = filedialog.askdirectory(title="Папка сохранения проекта")
            if not folder:
                return False
            target = Path(folder).resolve()
            config_path = target / "project.json"
            same_project = root is not None and target == root.resolve()
            if config_path.exists() and not same_project:
                if not messagebox.askyesno(
                    "Проект уже существует",
                    "В выбранной папке уже есть project.json. Перезаписать его текущим проектом?",
                    parent=self,
                ):
                    return False
            if not same_project:
                try:
                    self.session.attach_project(target, name=target.name)
                except Exception as exc:
                    messagebox.showerror("Не удалось создать проект", str(exc), parent=self)
                    return False
            root = target

        assert root is not None
        try:
            if self.session.document is not None:
                if self.session.subtitle_path is None:
                    self.session.save_subtitles(root / "subtitles" / f"{root.name}.ass", backup=False)
                else:
                    self.session.save_subtitles()
            project = self.session.project
            if project is None:
                raise RuntimeError("Конфигурация проекта не создана")
            media_value = self.session.media_path or self.alignment_panel.media_var.get().strip() or None
            if media_value is not None:
                project.media = self._portable_project_value(root, media_value)
            if self.session.subtitle_path is not None:
                project.subtitles = self._portable_project_value(root, self.session.subtitle_path)
            transcript = self.alignment_panel.transcript_var.get().strip()
            project.transcript = self._portable_project_value(root, transcript)
            project.mfa = self.alignment_panel.mfa_command_var.get().strip() or "mfa"
            project.conda_executable = self.alignment_panel.conda_executable_var.get().strip() or "conda"
            project.mfa_conda_env = self.alignment_panel.conda_env_var.get().strip() or "mfa"
            project.mfa_use_conda = bool(self.alignment_panel.mfa_use_conda_var.get())
            self.session.configure_ffmpeg(self.ffmpeg_mode_var.get(), self.ffmpeg_path_var.get())
            project.ffmpeg_mode = self.session.ffmpeg_mode
            project.ffmpeg = (
                self._portable_project_value(root, self.session.ffmpeg_override)
                if self.session.ffmpeg_mode == "custom" and self.session.ffmpeg_override is not None
                else None
            )
            if self.session.sps_timeline is not None:
                sidecar = self.session.measurement_sidecar_path()
                if sidecar is not None:
                    update_measurements(
                        sidecar,
                        self.session.sps_timeline,
                        (item.id for item in self.session.sps_timeline.syllables),
                    )
            if not isinstance(project.metadata, dict):
                project.metadata = {}
            project.metadata["ui_state"] = self._collect_project_state()
            save_project_config(root, project)
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить проект", str(exc), parent=self)
            return False
        self._refresh_labels()
        self._set_status(f"Проект сохранён: {root / 'project.json'}")
        return True

    def new_project(self) -> None:
        if not self._confirm_dirty():
            return
        folder = filedialog.askdirectory(title="Папка нового проекта")
        if not folder:
            return
        try:
            self.session.new_project(folder)
            self._sync_ffmpeg_to_project()
        except Exception as exc:
            messagebox.showerror("Не удалось создать проект", str(exc), parent=self)
            return
        self._invalidate_analysis()
        self._invalidate_waveform()
        self._invalidate_playback_cache()
        self._invalidate_spectrogram()
        self._refresh_from_session(reset_view=True)
        self._set_status(f"Создан проект: {folder}")

    def open_project(self) -> None:
        if not self._confirm_dirty():
            return
        folder = filedialog.askdirectory(title="Открыть папку проекта")
        if not folder:
            return
        try:
            self.session.open_project(folder)
            self._sync_ffmpeg_from_project()
        except Exception as exc:
            messagebox.showerror("Не удалось открыть проект", str(exc), parent=self)
            return
        self._invalidate_analysis()
        self._invalidate_waveform()
        self._invalidate_playback_cache()
        self._invalidate_spectrogram()
        self._refresh_from_session(reset_view=True)
        self._ensure_waveform_async()
        self._restore_project_state()
        if self.spectrogram_mode_var.get() != "Waveform":
            self._ensure_spectrogram_async()
        self._set_status(f"Открыт проект: {folder}")

    def open_ass(self) -> None:
        path = filedialog.askopenfilename(title="Открыть ASS", filetypes=(("Advanced SubStation Alpha", "*.ass"), ("Все файлы", "*.*")))
        if not path:
            return
        self.open_ass_path(path)

    def _blank_ass_duration(self) -> float | None:
        # Prefer already prepared data so creating a subtitle file never forces
        # another expensive decode. Fall back to ffprobe only when necessary.
        if self.playback_cache is not None:
            try:
                if self.playback_cache.duration > 0:
                    return float(self.playback_cache.duration)
            except Exception:
                pass
        if self.waveform is not None:
            try:
                if self.waveform.duration > 0:
                    return float(self.waveform.duration)
            except Exception:
                pass
        if self.session.media_path is not None:
            try:
                duration = probe_media_duration(self.session.media_path, self.session.resolved_ffmpeg())
                if duration is not None and duration > 0:
                    return float(duration)
            except Exception:
                pass
        value = simpledialog.askfloat(
            "Длительность пустого ASS",
            "Медиа не привязано или его длительность пока неизвестна.\n"
            "Укажите длительность таймлайна в секундах:",
            parent=self, initialvalue=300.0, minvalue=0.02,
        )
        return None if value is None else float(value)

    def new_blank_ass(self) -> None:
        if not self._confirm_dirty():
            return
        duration = self._blank_ass_duration()
        if duration is None:
            return
        try:
            self.session.new_blank_subtitles(duration)
        except Exception as exc:
            messagebox.showerror("Не удалось создать пустой ASS", str(exc), parent=self)
            return
        self._invalidate_analysis()
        self._refresh_from_session(reset_view=True)
        self.notebook.select(self.karaoke_tab)
        # The seed span has no visible text and only exists so timing can be
        # divided immediately at the playhead. Select it for the first split.
        if self.session.syllables:
            first = self.session.syllables[0]
            self.karaoke_timeline.select_ids((first.id,))
            self._set_playhead(first.start)
        self._set_status(
            f"Создан пустой ASS на {duration:.2f} с · ставьте курсор и нажимайте «Разделить»/«Вставить»"
        )

    def open_ass_path(self, path) -> bool:
        """Open a known ASS path (also used by the Alignment tab)."""
        if not self._confirm_dirty():
            return False
        try:
            self.session.open_subtitles(path)
        except Exception as exc:
            messagebox.showerror("Не удалось открыть ASS", str(exc), parent=self)
            return False
        self._invalidate_analysis()
        self._refresh_from_session(reset_view=True)
        self.notebook.select(self.karaoke_tab)
        self._set_status(f"Открыт ASS: {path}")
        return True

    def set_media(self) -> None:
        path = filedialog.askopenfilename(title="Указать аудио/видео")
        if not path:
            return
        try:
            self.session.set_media(path)
        except Exception as exc:
            messagebox.showerror("Не удалось указать медиа", str(exc), parent=self)
            return
        self._invalidate_waveform()
        self._invalidate_playback_cache()
        self._invalidate_spectrogram()
        self._refresh_labels()
        if hasattr(self, "render_panel"):
            self.render_panel.refresh_source(reset_measurement=False)
        self._ensure_waveform_async()
        if self.spectrogram_mode_var.get() != "Waveform":
            self._ensure_spectrogram_async()
        self._set_status(f"Медиа привязано: {path}")

    def _invalidate_playback_cache(self) -> None:
        self._playback_cache_generation += 1
        self._playback_cache_building = False
        self.playback_cache = None
        try:
            self.player.clear_pcm_cache()
        except Exception:
            pass

    def _ensure_playback_cache_async(self) -> None:
        media = self.session.media_path
        if media is None or self._playback_cache_building:
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            return
        self._playback_cache_generation += 1
        generation = self._playback_cache_generation
        self._playback_cache_building = True
        cache_root = self.session.playback_cache_root()
        task = self.task_center.start("Audio cache", "Подготовка аудио для мгновенного Play", stage="Проверка PCM-кэша", progress=0)
        task.log(f"Media: {media}")

        def work():
            try:
                cache, path, cached = load_or_extract_playback_pcm_cache(
                    media, ffmpeg=ffmpeg, cache_root=cache_root,
                    progress=lambda value, stage: task.update(value, stage),
                    log=lambda line: task.log(line),
                )
            except Exception as exc:
                task.fail(str(exc))
                self.after(0, lambda exc=exc: self._playback_cache_failed(generation, exc))
                return
            task.done("PCM-кэш готов" + (" (кэш)" if cached else ""))
            self.after(0, lambda: self._playback_cache_finished(generation, media, cache, path, cached))
        threading.Thread(target=work, name="playback-cache", daemon=True).start()

    def _playback_cache_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._playback_cache_generation:
            return
        self._playback_cache_building = False
        self._set_status(f"Аудиокэш плеера: ошибка: {exc}")

    def _playback_cache_finished(self, generation: int, media, cache, path, cached: bool) -> None:
        if generation != self._playback_cache_generation or self.session.media_path != Path(media):
            return
        self._playback_cache_building = False
        self.playback_cache = cache
        try:
            self.player.set_pcm_cache(media, cache)
        except Exception as exc:
            self._set_status(f"PCM-кэш готов, но PortAudio не запущен: {exc}")
            return
        self._set_status(f"Аудио готово для мгновенного Play · {self.player.backend_description} · {path.name}")

    def _invalidate_waveform(self) -> None:
        self._waveform_generation += 1
        self.waveform = None
        self.karaoke_timeline.set_waveform(None)
        self.sps_timeline.set_waveform(None)
        self.waveform_label.configure(text="Waveform: —")

    def _ensure_waveform_async(self) -> None:
        media = self.session.media_path
        if media is None:
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            self.waveform_label.configure(text="Waveform: FFmpeg не настроен")
            self._set_status("FFmpeg не найден. Нажмите «FFmpeg…» и выберите portable или пользовательский ffmpeg.exe.")
            return
        self._waveform_generation += 1
        generation = self._waveform_generation
        cache_root = self.session.waveform_cache_root()
        self.waveform_label.configure(text="Waveform: строится…")
        task = self.task_center.start("Waveform", "Построение waveform", stage="Проверка кэша", progress=0)
        task.log(f"Media: {media}")

        def work():
            try:
                waveform, cache, cached = load_or_extract_waveform(
                    media, ffmpeg=ffmpeg, cache_root=cache_root,
                    progress=lambda value, stage: task.update(value, stage),
                    log=lambda line: task.log(line),
                )
            except Exception as exc:
                task.fail(str(exc))
                self.after(0, lambda exc=exc: self._waveform_failed(generation, exc))
                return
            task.done("Waveform готов" + (" (кэш)" if cached else ""))
            self.after(0, lambda: self._waveform_finished(generation, waveform, cache, cached))

        threading.Thread(target=work, name="waveform-extract", daemon=True).start()

    def _waveform_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._waveform_generation:
            return
        self.waveform_label.configure(text="Waveform: ошибка")
        self._set_status(f"Не удалось построить waveform: {exc}")
        self._ensure_playback_cache_async()

    def _waveform_finished(self, generation, waveform, cache, cached: bool) -> None:
        if generation != self._waveform_generation:
            return
        self.waveform = waveform
        self.karaoke_timeline.set_waveform(waveform, reset_view=False)
        self.sps_timeline.set_waveform(waveform, reset_view=False)
        source = "кэш" if cached else "FFmpeg"
        self.waveform_label.configure(text=f"Waveform: {waveform.duration:.1f} с ({source})")
        self._set_status(f"Waveform готов · {waveform.duration:.2f} с · {cache}")
        self._ensure_playback_cache_async()

    def _invalidate_spectrogram(self) -> None:
        self._spectrogram_generation += 1
        self._spectrogram_building_for = None
        self.spectrogram = None
        if hasattr(self, "karaoke_timeline"):
            self.karaoke_timeline.set_spectrogram(None, view=self.spectrogram_view, reset_view=False)
        if hasattr(self, "sps_timeline"):
            self.sps_timeline.set_spectrogram(None, view=self.spectrogram_view, reset_view=False)
        self._set_spectrogram_status("Спектрограмма: —")

    def _set_spectrogram_status(self, text: str) -> None:
        for name in ("karaoke_spectrogram_label", "spectrogram_label"):
            label = getattr(self, name, None)
            if label is not None:
                label.configure(text=text)

    def _set_spectrogram_on_timelines(self, data) -> None:
        for name in ("karaoke_timeline", "sps_timeline"):
            timeline = getattr(self, name, None)
            if timeline is not None:
                timeline.set_spectrogram(
                    data, view=self.spectrogram_view, reset_view=False
                )

    def _audio_view_changed(self, *, save: bool = False) -> None:
        display = self.spectrogram_mode_var.get()
        mode = {"Waveform": "waveform", "Spectrogram": "spectrogram", "Both": "both"}.get(display, "waveform")
        for name in ("karaoke_timeline", "sps_timeline"):
            timeline = getattr(self, name, None)
            if timeline is not None:
                timeline.set_audio_mode(mode)
        if save:
            self._save_preferences()
        if mode != "waveform":
            self._ensure_spectrogram_async()

    def _ensure_spectrogram_async(self, *, force: bool = False) -> None:
        media = self.session.media_path
        if media is None:
            self._set_spectrogram_status("Спектрограмма: нет медиа")
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            self._set_spectrogram_status("Спектрограмма: FFmpeg не найден")
            return
        if self.spectrogram is not None and not force:
            self._set_spectrogram_on_timelines(self.spectrogram)
            return
        build_key = (str(media.resolve()), self.spectrogram_analysis)
        if not force and self._spectrogram_building_for == build_key:
            self._set_spectrogram_status("Спектрограмма: строится…")
            return
        self._spectrogram_generation += 1
        generation = self._spectrogram_generation
        self._spectrogram_building_for = build_key
        cache_root = self.session.spectrogram_cache_root()
        analysis = self.spectrogram_analysis
        if force:
            try:
                spectrogram_cache_path(media, cache_root, analysis).unlink(missing_ok=True)
            except Exception:
                pass
            self.spectrogram = None
            self._set_spectrogram_on_timelines(None)
        self._set_spectrogram_status("Спектрограмма: строится…")
        task = self.task_center.start("Spectrogram", "Построение спектрограммы", stage="Проверка кэша", progress=0)
        task.log(f"Media: {media}")

        def work():
            try:
                data, cache, cached = load_or_extract_spectrogram(
                    media, ffmpeg=ffmpeg, cache_root=cache_root, settings=analysis,
                    progress=lambda value, stage: task.update(value, stage),
                    log=lambda line: task.log(line),
                )
            except Exception as exc:
                task.fail(str(exc))
                self.after(0, lambda exc=exc: self._spectrogram_failed(generation, exc))
                return
            task.done("Спектрограмма готова" + (" (кэш)" if cached else ""))
            self.after(0, lambda: self._spectrogram_finished(generation, data, cache, cached, analysis))

        threading.Thread(target=work, name="spectrogram-extract", daemon=True).start()

    def _spectrogram_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._spectrogram_generation:
            return
        self._spectrogram_building_for = None
        self._set_spectrogram_status("Спектрограмма: ошибка")
        self._set_status(f"Не удалось построить спектрограмму: {exc}")

    def _spectrogram_finished(self, generation, data, cache, cached: bool, analysis) -> None:
        if generation != self._spectrogram_generation or analysis != self.spectrogram_analysis:
            return
        self._spectrogram_building_for = None
        self.spectrogram = data
        self._set_spectrogram_on_timelines(data)
        source = "кэш" if cached else "FFmpeg + FFT"
        window_ms = analysis.fft_size / analysis.sample_rate * 1000.0
        self._set_spectrogram_status(
            f"Спектрограмма: FFT {analysis.fft_size} · {window_ms:.1f} мс · {source}"
        )
        self._set_status(f"Спектрограмма готова · {data.duration:.2f} с · {cache}")

    def open_spectrogram_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.configure(background=self.palette.bg)
        dialog.title("Настройки спектрограммы")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)

        analysis = self.spectrogram_analysis
        view = self.spectrogram_view
        voice_var = tk.StringVar(value=self.voice_preset_var.get())
        speed_var = tk.StringVar(value=self.speed_preset_var.get())
        expected_var = tk.StringVar(value=self.expected_sps_var.get())
        sample_rate_var = tk.StringVar(value=str(analysis.sample_rate))
        fft_var = tk.StringVar(value=str(analysis.fft_size))
        overlap_var = tk.StringVar(value=f"{analysis.overlap * 100:.0f}")
        window_var = tk.StringVar(value=analysis.window)
        min_freq_var = tk.StringVar(value=f"{view.min_frequency:g}")
        max_freq_var = tk.StringVar(value=f"{view.max_frequency:g}")
        floor_var = tk.StringVar(value=f"{view.db_floor:g}")
        ceiling_var = tk.StringVar(value=f"{view.db_ceiling:g}")
        scale_var = tk.StringVar(value="Логарифмическая" if view.frequency_scale == "log" else "Линейная")
        window_info = ttk.Label(body, text="", style="Muted.TLabel")

        def update_info(*_args):
            try:
                sr = int(sample_rate_var.get())
                size = int(fft_var.get())
                overlap = float(overlap_var.get().replace(",", ".")) / 100.0
                ms = size / sr * 1000.0
                hop_ms = max(1, round(size * (1.0 - overlap))) / sr * 1000.0
                hz = sr / size
                window_info.configure(text=f"Окно: {ms:.2f} мс · шаг: {hop_ms:.2f} мс · Δf: {hz:.2f} Гц")
            except Exception:
                window_info.configure(text="")

        def apply_voice(_event=None):
            preset = voice_var.get()
            if preset in VOICE_PRESETS:
                lo, hi = VOICE_PRESETS[preset]
                min_freq_var.set(f"{lo:g}")
                max_freq_var.set(f"{hi:g}")

        def apply_speed(_event=None):
            preset = speed_var.get()
            if preset in SPEED_PRESETS:
                fft_var.set(str(SPEED_PRESETS[preset]))
                overlap_var.set("75")
                update_info()

        def apply_expected():
            try:
                value = float(expected_var.get().replace(",", "."))
            except ValueError:
                messagebox.showerror("Некорректный SPS", "Предполагаемый SPS должен быть числом.", parent=dialog)
                return
            fft = fft_size_for_expected_sps(value)
            fft_var.set(str(fft))
            overlap_var.set("75")
            if value <= 6:
                speed_var.set("Медленно (≤6 SPS)")
            elif value <= 12:
                speed_var.set("Средне (6–12 SPS)")
            elif value <= 20:
                speed_var.set("Быстро (12–20 SPS)")
            else:
                speed_var.set("Очень быстро (>20 SPS)")
            update_info()

        row = 0
        ttk.Label(body, text="Пресеты", style="Header.TLabel").grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 6))
        row += 1
        ttk.Label(body, text="Высота голоса:").grid(row=row, column=0, sticky="w")
        voice = ttk.Combobox(body, state="readonly", width=23, textvariable=voice_var, values=tuple(VOICE_PRESETS))
        voice.grid(row=row, column=1, sticky="ew", padx=(6, 18))
        voice.bind("<<ComboboxSelected>>", apply_voice)
        ttk.Label(body, text="Скорость:").grid(row=row, column=2, sticky="w")
        speed = ttk.Combobox(body, state="readonly", width=24, textvariable=speed_var, values=tuple(SPEED_PRESETS))
        speed.grid(row=row, column=3, sticky="ew", padx=(6, 0))
        speed.bind("<<ComboboxSelected>>", apply_speed)
        row += 1
        ttk.Label(body, text="Предполагаемый SPS:").grid(row=row, column=0, sticky="w", pady=(5, 8))
        ttk.Entry(body, width=10, textvariable=expected_var).grid(row=row, column=1, sticky="w", padx=(6, 0), pady=(5, 8))
        ttk.Button(body, text="Подобрать окно", command=apply_expected).grid(row=row, column=1, sticky="e", pady=(5, 8))
        ttk.Label(
            body,
            text="Чем выше SPS, тем короче FFT-окно: лучше временная, но хуже частотная точность.",
            style="Muted.TLabel",
        ).grid(row=row, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(5, 8))

        row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(0, 9))
        row += 1
        ttk.Label(body, text="Анализ (требует перестроения FFT)", style="Header.TLabel").grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 5))
        row += 1
        fields = [
            ("Sample rate, Hz", sample_rate_var),
            ("FFT / окно, samples", fft_var),
            ("Overlap, %", overlap_var),
        ]
        for label, var in fields:
            ttk.Label(body, text=label + ":").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, width=14, textvariable=var).grid(row=row, column=1, sticky="w", padx=(6, 18), pady=2)
            row += 1
        ttk.Label(body, text="Window function:").grid(row=row - 3, column=2, sticky="w", pady=2)
        ttk.Combobox(body, state="readonly", width=16, textvariable=window_var, values=("hann", "hamming", "blackman", "rect")).grid(row=row - 3, column=3, sticky="w", padx=(6, 0), pady=2)
        window_info.grid(row=row - 2, column=2, columnspan=2, sticky="w", padx=(0, 0), pady=2)
        for var in (sample_rate_var, fft_var, overlap_var):
            var.trace_add("write", update_info)
        update_info()

        row += 1
        ttk.Separator(body).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(7, 9))
        row += 1
        ttk.Label(body, text="Отображение (меняется без нового FFT)", style="Header.TLabel").grid(row=row, column=0, columnspan=4, sticky="w", pady=(0, 5))
        row += 1
        display_fields = [
            ("Мин. частота, Hz", min_freq_var, "Макс. частота, Hz", max_freq_var),
            ("dB floor", floor_var, "dB ceiling", ceiling_var),
        ]
        for l1, v1, l2, v2 in display_fields:
            ttk.Label(body, text=l1 + ":").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, width=14, textvariable=v1).grid(row=row, column=1, sticky="w", padx=(6, 18), pady=2)
            ttk.Label(body, text=l2 + ":").grid(row=row, column=2, sticky="w", pady=2)
            ttk.Entry(body, width=14, textvariable=v2).grid(row=row, column=3, sticky="w", padx=(6, 0), pady=2)
            row += 1
        ttk.Label(body, text="Шкала частоты:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(body, state="readonly", width=16, textvariable=scale_var, values=("Линейная", "Логарифмическая")).grid(row=row, column=1, sticky="w", padx=(6, 0), pady=2)

        def commit(*, render: bool = False):
            try:
                new_analysis = SpectrogramAnalysisSettings(
                    sample_rate=int(sample_rate_var.get()),
                    fft_size=int(fft_var.get()),
                    overlap=float(overlap_var.get().replace(",", ".")) / 100.0,
                    window=window_var.get(),
                )
                new_analysis.validate()
                new_view = SpectrogramViewSettings(
                    min_frequency=float(min_freq_var.get().replace(",", ".")),
                    max_frequency=float(max_freq_var.get().replace(",", ".")),
                    db_floor=float(floor_var.get().replace(",", ".")),
                    db_ceiling=float(ceiling_var.get().replace(",", ".")),
                    frequency_scale="log" if scale_var.get() == "Логарифмическая" else "linear",
                )
                new_view.validate(new_analysis.sample_rate / 2.0)
            except Exception as exc:
                messagebox.showerror("Некорректные настройки", str(exc), parent=dialog)
                return
            analysis_changed = new_analysis != self.spectrogram_analysis
            self.spectrogram_analysis = new_analysis
            self.spectrogram_view = new_view
            self.voice_preset_var.set(voice_var.get())
            self.speed_preset_var.set(speed_var.get())
            self.expected_sps_var.set(expected_var.get())
            self.sps_timeline.set_spectrogram_view(new_view)
            self.karaoke_timeline.set_spectrogram_view(new_view)
            if analysis_changed:
                self._invalidate_spectrogram()
            if render:
                self.spectrogram_mode_var.set("Spectrogram")
                self._audio_view_changed()
            elif self.spectrogram_mode_var.get() != "Waveform":
                self._ensure_spectrogram_async()
            self._save_preferences()
            dialog.destroy()

        row += 1
        buttons = ttk.Frame(body)
        buttons.grid(row=row, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Применить", command=commit).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text="Применить и показать", command=lambda: commit(render=True)).pack(side="right", padx=(0, 6))
        ttk.Label(
            body,
            text="Применённые значения сохраняются как настройки спектрограммы по умолчанию.",
            style="Muted.TLabel",
        ).grid(row=row + 1, column=0, columnspan=4, sticky="e", pady=(5, 0))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.grab_set()

    def transfer_to_sps(self) -> None:
        if self.session.karaoke_timeline is None:
            messagebox.showinfo("Нет субтитров", "Сначала откройте ASS.", parent=self)
            return
        try:
            threshold = float(self.min_sps_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Некорректный SPS", "Минимальный peak SPS должен быть числом.", parent=self)
            return
        ids = None
        if self.scope_var.get() == "Выделенные слоги":
            if not self.karaoke_timeline.selected_ids:
                messagebox.showinfo("Нет выделения", "Выделите слоги либо выберите «Весь ASS».", parent=self)
                return
            ids = set(self.karaoke_timeline.selected_ids)

        self._analysis_generation += 1
        generation = self._analysis_generation
        self.transfer_button.configure(state="disabled")
        self._set_status("Ищу кандидаты на бёрсты перед передачей в SPS…")
        source_snapshot = list(self.session.karaoke_timeline.syllables)
        task = self.task_center.start("SPS", "Автопоиск бёрстов", stage="Подготовка слогов", progress=5)
        task.log(f"Scope: {self.scope_var.get()} · min peak SPS: {threshold:g}")

        def work():
            try:
                task.update(20, "Расчёт SPS-окон")
                result = build_sps_transfer(source_snapshot, syllable_ids=ids, min_peak_sps=threshold)
                task.update(90, "Формирование кандидатов")
            except Exception as exc:
                task.fail(str(exc))
                self.after(0, lambda exc=exc: self._transfer_failed(generation, exc))
                return
            task.log(f"Слогов: {len(result.timeline.syllables)} · кандидатов: {len(result.candidates)}")
            task.done("Автопоиск бёрстов завершён")
            self.after(0, lambda: self._transfer_finished(generation, result))

        threading.Thread(target=work, name="burst-analysis", daemon=True).start()

    def _transfer_failed(self, generation: int, exc: Exception) -> None:
        if generation != self._analysis_generation:
            return
        self.transfer_button.configure(state="normal")
        messagebox.showerror("Ошибка SPS-анализа", str(exc), parent=self)
        self._set_status("SPS-анализ завершился ошибкой")

    def _transfer_finished(self, generation: int, result: TransferResult) -> None:
        if generation != self._analysis_generation:
            return
        self.transfer_button.configure(state="normal")
        try:
            self.session.adopt_transfer_result(result)
        except Exception as exc:
            messagebox.showerror("Ошибка measurement-sidecar", str(exc), parent=self)
            return
        # A new SPS transfer can reuse source IDs differently or contain only a
        # subset, so an old In/Out transport range is intentionally discarded.
        self.playback_range_ids["sps"] = {"in": None, "out": None}
        self.playback_limit_ids["sps"] = {"start": None, "stop": None}
        self._update_playback_range_label("sps")
        self._update_playback_limit_label("sps")
        self._populate_sps(result)
        self.notebook.select(self.sps_tab)
        self._set_status(f"Передано в SPS: {len(result.timeline.syllables)} слогов; кандидатов: {len(result.candidates)}")

    def _populate_sps(self, result: TransferResult) -> None:
        self.sps_timeline.set_data(result.timeline.syllables, bursts=result.candidates, manual_regions=result.manual_regions, reset_view=True)
        self._update_playback_range_label("sps")
        self._update_playback_limit_label("sps")
        self.sps_timeline.set_waveform(self.waveform, reset_view=False)
        self.sps_timeline.set_spectrogram(self.spectrogram, view=self.spectrogram_view, reset_view=False)
        self._audio_view_changed()
        self._refresh_sps_summary(result.scope)
        self.burst_tree.delete(*self.burst_tree.get_children())
        ordered = sorted(result.candidates, key=lambda b: (-b.peak_sps, b.start))
        for i, burst in enumerate(ordered):
            self.burst_tree.insert("", "end", iid=f"burst:{i}", values=(format_clock(burst.start), format_clock(burst.end), f"{burst.peak_sps:.2f}", f"{burst.mean_sps:.2f}", burst.text))
        self._refresh_measurement_controls()
        self._refresh_sps_graph()

    def _refresh_sps_summary(self, scope: str | None = None) -> None:
        timeline = self.session.sps_timeline
        if timeline is None:
            self.sps_summary.configure(text="Материал ещё не передан")
            return
        changed = len(timeline.changed())
        suffix = f" · scope: {scope}" if scope else ""
        self.sps_summary.configure(text=f"{len(timeline.syllables)} слогов · {len(self.session.sps_candidates)} авто-кандидатов · изменено: {changed}{suffix}")

    def _refresh_from_session(self, *, reset_view: bool) -> None:
        if reset_view:
            self._karaoke_text_drafts.clear()
            self._karaoke_romanization_drafts.clear()
            self._karaoke_text_bound_id = None
            self.playback_range_ids = {"karaoke": {"in": None, "out": None}, "sps": {"in": None, "out": None}}
            self.playback_limit_ids = {"karaoke": {"start": None, "stop": None}, "sps": {"start": None, "stop": None}}
            self._update_playback_range_label("karaoke")
            self._update_playback_range_label("sps")
            self._update_playback_limit_label("karaoke")
            self._update_playback_limit_label("sps")
            if hasattr(self, "karaoke_text_editor"):
                self._set_karaoke_text_editor(None)
        self._refresh_labels()
        timeline = self.session.karaoke_timeline
        if timeline:
            manual = manual_bursts(timeline.syllables)
            self.karaoke_timeline.set_data(timeline.syllables, manual_regions=manual, reset_view=reset_view)
            self.karaoke_timeline.set_waveform(self.waveform, reset_view=False)
            self.karaoke_timeline.set_spectrogram(
                self.spectrogram, view=self.spectrogram_view, reset_view=False
            )
            self.karaoke_info.configure(text=f"{len(timeline.syllables)} karaoke-слогов · ручных burst-областей: {len(manual)}")
        else:
            self.karaoke_timeline.set_data([], reset_view=True)
            self.karaoke_info.configure(text="0 слогов")
        self.sps_timeline.set_data([], reset_view=True)
        self.sps_timeline.set_waveform(self.waveform, reset_view=False)
        self.sps_timeline.set_spectrogram(self.spectrogram, view=self.spectrogram_view, reset_view=False)
        self._update_playback_range_label("karaoke")
        self._update_playback_limit_label("karaoke")
        self._update_playback_range_label("sps")
        self._update_playback_limit_label("sps")
        self._audio_view_changed()
        self.burst_tree.delete(*self.burst_tree.get_children())
        self.sps_summary.configure(text="Материал ещё не передан")
        if hasattr(self, "sps_graph"):
            self.sps_graph.clear()
        self._refresh_measurement_controls()
        if hasattr(self, "alignment_panel"):
            self.alignment_panel.refresh_project()
        if hasattr(self, "render_panel"):
            self.render_panel.refresh_source(reset_measurement=True)

    def _refresh_labels(self) -> None:
        self.project_label.configure(text=f"Проект: {self.session.project_root.name}" if self.session.project_root else "Проект: —")
        dirty_now = (
            self.session.dirty
            or bool(self._karaoke_text_drafts)
            or bool(self._karaoke_romanization_drafts)
        )
        if self.session.subtitle_path:
            dirty = " *" if dirty_now else ""
            self.ass_label.configure(text=f"{self.session.subtitle_path}{dirty}")
        else:
            self.ass_label.configure(text="ASS не открыт")
        self.title("Karaoke SPS Workbench" + (" *" if dirty_now else ""))
        self.media_label.configure(text=f"Медиа: {self.session.media_path.name}" if self.session.media_path else "Медиа: —")

    def _text_editor_value(self) -> str:
        if not hasattr(self, "karaoke_text_editor"):
            return ""
        return self.karaoke_text_editor.get("1.0", "end-1c")

    def _source_for_karaoke_id(self, syllable_id: str):
        item = next((s for s in self.session.syllables if s.id == syllable_id), None)
        return item.source if item is not None else None

    def _update_karaoke_draft_state(self) -> None:
        sid = self._karaoke_text_bound_id
        if sid and (
            sid in self._karaoke_text_drafts
            or sid in self._karaoke_romanization_drafts
        ):
            self.karaoke_text_state_var.set(
                "● черновик текста/romanization · ещё не записан в ASS"
            )
        elif sid:
            self.karaoke_text_state_var.set("Ctrl+Enter — применить · F2 — фокус")

    def _remember_current_karaoke_draft(self) -> None:
        sid = self._karaoke_text_bound_id
        if not sid or self._loading_karaoke_text:
            return
        try:
            if str(self.karaoke_text_editor.cget("state")) == "disabled":
                return
        except Exception:
            return
        source = self._source_for_karaoke_id(sid)
        if source is None:
            self._karaoke_text_drafts.pop(sid, None)
            return
        if self._karaoke_text_bound_raw is not None and source.raw_text != self._karaoke_text_bound_raw:
            # The ASS changed structurally while the editor was still bound to
            # the same ordinal ID. Never turn the old full syllable text into a
            # draft for the newly shortened left half.
            self._karaoke_text_drafts.pop(sid, None)
            return
        value = self._text_editor_value()
        try:
            self.karaoke_text_editor.tag_remove("rtl", "1.0", "end")
            if self._contains_rtl_text(value):
                self.karaoke_text_editor.tag_configure("rtl", justify="right")
                self.karaoke_text_editor.tag_add("rtl", "1.0", "end")
        except tk.TclError:
            pass
        if value == source.raw_text:
            self._karaoke_text_drafts.pop(sid, None)
        else:
            self._karaoke_text_drafts[sid] = value
        self._update_karaoke_draft_state()
        self._refresh_labels()

    def _remember_current_romanization_draft(self) -> None:
        sid = self._karaoke_text_bound_id
        if not sid or self._loading_karaoke_romanization:
            return
        source = self._source_for_karaoke_id(sid)
        if source is None:
            self._karaoke_romanization_drafts.pop(sid, None)
            return
        value = self.karaoke_romanization_var.get().strip() if self.karaoke_romanize_var.get() else ""
        if value == source.romanization:
            self._karaoke_romanization_drafts.pop(sid, None)
        else:
            self._karaoke_romanization_drafts[sid] = value
        self._update_karaoke_draft_state()
        self._refresh_labels()

    @staticmethod
    def _contains_rtl_text(value: str) -> bool:
        return any(unicodedata.bidirectional(ch) in {"R", "AL", "AN"} for ch in value)

    def _set_karaoke_romanization_editor(self, source) -> None:
        self._loading_karaoke_romanization = True
        try:
            if source is None:
                self.karaoke_romanize_var.set(False)
                self.karaoke_romanization_var.set("")
                self.karaoke_romanize_check.configure(state="disabled")
                self.karaoke_romanization_field.pack_forget()
                return
            self.karaoke_romanize_check.configure(state="normal")
            value = self._karaoke_romanization_drafts.get(source.id, source.romanization)
            enabled = bool(value) or source.id in self._karaoke_romanization_drafts
            self.karaoke_romanization_var.set(value)
            self.karaoke_romanize_var.set(enabled)
            if enabled:
                self.karaoke_romanization_field.pack(fill="x", pady=(3, 0))
            else:
                self.karaoke_romanization_field.pack_forget()
            self._update_karaoke_draft_state()
        finally:
            self._loading_karaoke_romanization = False

    def _romanization_changed(self, *_args) -> None:
        if self._loading_karaoke_romanization:
            return
        if self.karaoke_romanize_var.get() and self._karaoke_text_bound_id:
            if not self.karaoke_romanization_field.winfo_manager():
                self.karaoke_romanization_field.pack(fill="x", pady=(3, 0))
        else:
            self.karaoke_romanization_field.pack_forget()
        self._remember_current_romanization_draft()

    def _set_karaoke_text_editor(self, source) -> None:
        self._loading_karaoke_text = True
        try:
            self.karaoke_text_editor.configure(state="normal")
            if source is None:
                self._karaoke_text_bound_id = None
                self._karaoke_text_bound_raw = None
                self.karaoke_text_editor.delete("1.0", "end")
                self.karaoke_text_editor.configure(state="disabled")
                self.karaoke_text_state_var.set("Выберите один слог. Inline ASS-теги показываются как есть.")
            else:
                self._karaoke_text_bound_id = source.id
                self._karaoke_text_bound_raw = source.raw_text
                value = self._karaoke_text_drafts.get(source.id, source.raw_text)
                editor_had_focus = (self.focus_get() is self.karaoke_text_editor)
                current_val = self._text_editor_value()
                if current_val != value:
                    cursor_pos = None
                    if editor_had_focus:
                        try:
                            cursor_pos = self.karaoke_text_editor.index("insert")
                        except Exception:
                            pass
                    self.karaoke_text_editor.delete("1.0", "end")
                    self.karaoke_text_editor.insert("1.0", value)
                    self.karaoke_text_editor.tag_remove("rtl", "1.0", "end")
                    if self._contains_rtl_text(source.visible_text):
                        self.karaoke_text_editor.tag_configure("rtl", justify="right")
                        self.karaoke_text_editor.tag_add("rtl", "1.0", "end")
                    if editor_had_focus and cursor_pos:
                        try:
                            self.karaoke_text_editor.mark_set("insert", cursor_pos)
                        except Exception:
                            self.karaoke_text_editor.mark_set("insert", "end-1c")
                    else:
                        self.karaoke_text_editor.mark_set("insert", "end-1c")
                if source.id in self._karaoke_text_drafts:
                    self.karaoke_text_state_var.set("● не сохранено (выйдите из поля или Ctrl+Enter)")
                else:
                    self.karaoke_text_state_var.set("Сохранение при смене фокуса / Ctrl+Enter · F2 — фокус")
                try:
                    self.karaoke_text_editor.edit_reset()
                except tk.TclError:
                    pass
            self.karaoke_text_editor.edit_modified(False)
        finally:
            self._loading_karaoke_text = False
        self._set_karaoke_romanization_editor(source)

    def _karaoke_text_modified(self, _event=None):
        if self._loading_karaoke_text:
            return
        try:
            modified = self.karaoke_text_editor.edit_modified()
        except tk.TclError:
            return
        if modified:
            self.karaoke_text_editor.edit_modified(False)
            self._remember_current_karaoke_draft()

    def _schedule_auto_apply(self) -> None:
        pass

    def _auto_apply_drafts(self) -> None:
        pass

    def _on_text_editor_focus_out(self, _event=None) -> None:
        if self._text_apply_debounce_job is not None:
            try:
                self.after_cancel(self._text_apply_debounce_job)
            except tk.TclError:
                pass
            self._text_apply_debounce_job = None
        sid = self._karaoke_text_bound_id
        if sid:
            self._remember_current_karaoke_draft()
            self._remember_current_romanization_draft()
            if sid in self._karaoke_text_drafts or sid in self._karaoke_romanization_drafts:
                self._commit_text_drafts(preserve_selection={sid})

    def _karaoke_text_apply_shortcut(self, _event=None):
        self.apply_karaoke_text()
        return "break"

    def _karaoke_text_linebreak(self, _event=None):
        # ASS stores an in-event line break as the two-character escape \N.
        if str(self.karaoke_text_editor.cget("state")) != "disabled":
            self.karaoke_text_editor.insert("insert", r"\N")
            self._remember_current_karaoke_draft()
        return "break"

    def focus_karaoke_text_editor(self) -> str | None:
        if self._karaoke_text_bound_id and str(self.karaoke_text_editor.cget("state")) != "disabled":
            self.karaoke_text_editor.focus_set()
            return "break"
        return None

    def _karaoke_timeline_activated(self, _syllable_id: str) -> None:
        self.after_idle(self.focus_karaoke_text_editor)

    def _commit_text_drafts(self, *, exclude: set[str] | None = None, preserve_selection=None) -> bool:
        self._remember_current_karaoke_draft()
        self._remember_current_romanization_draft()
        exclude = exclude or set()
        valid = {s.id for s in self.session.syllables}
        for stale in list(self._karaoke_text_drafts):
            if stale not in valid:
                self._karaoke_text_drafts.pop(stale, None)
        for stale in list(self._karaoke_romanization_drafts):
            if stale not in valid:
                self._karaoke_romanization_drafts.pop(stale, None)
        values = {sid: value for sid, value in self._karaoke_text_drafts.items() if sid not in exclude}
        romanizations = dict(self._karaoke_romanization_drafts)
        if not values and not romanizations:
            self._refresh_labels()
            return True
        editor_had_focus = (self.focus_get() is getattr(self, "karaoke_text_editor", None))
        cursor_pos = None
        if editor_had_focus:
            try:
                cursor_pos = self.karaoke_text_editor.index("insert")
            except Exception:
                pass
        try:
            result = self.session.edit_contents(
                text_values=values,
                romanization_values=romanizations,
            )
        except (KaraokeEditError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Не удалось применить текст karaoke", str(exc), parent=self)
            return False
        for sid in values:
            self._karaoke_text_drafts.pop(sid, None)
        for sid in romanizations:
            self._karaoke_romanization_drafts.pop(sid, None)
        self._after_karaoke_edit(
            result,
            f"Применено: текстовых черновиков {len(values)}, romanization {len(romanizations)}",
        )
        if preserve_selection:
            self.karaoke_timeline.select_ids(preserve_selection)
        if editor_had_focus and cursor_pos and self._karaoke_text_bound_id:
            try:
                self.karaoke_text_editor.focus_set()
                self.karaoke_text_editor.mark_set("insert", cursor_pos)
            except Exception:
                pass
        return True

    def apply_karaoke_text(self) -> None:
        self._remember_current_karaoke_draft()
        self._remember_current_romanization_draft()
        sid = self._karaoke_text_bound_id
        if not sid:
            messagebox.showinfo("Нет слога", "Выберите один karaoke-слог.", parent=self)
            return
        has_text = sid in self._karaoke_text_drafts
        has_romanization = sid in self._karaoke_romanization_drafts
        if not has_text and not has_romanization:
            self._set_status("Текст и romanization слога не изменены")
            return
        try:
            result = self.session.edit_contents(
                text_values={sid: self._karaoke_text_drafts[sid]} if has_text else {},
                romanization_values={sid: self._karaoke_romanization_drafts[sid]} if has_romanization else {},
            )
        except (KaraokeEditError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Не удалось изменить текст", str(exc), parent=self)
            return
        self._karaoke_text_drafts.pop(sid, None)
        self._karaoke_romanization_drafts.pop(sid, None)
        self._after_karaoke_edit(result, "Текст/romanization karaoke-слога применены")
        self.after_idle(self.focus_karaoke_text_editor)

    @staticmethod
    def _wrap_selected_text_in_brackets(widget: tk.Text) -> bool:
        try:
            start = widget.index("sel.first")
            end = widget.index("sel.last")
        except tk.TclError:
            return False
        value = widget.get(start, end)
        widget.delete(start, end)
        widget.insert(start, "[" + value + "]")
        return True

    def mark_unspoken_selection(self) -> None:
        selected_ids = self._selected_karaoke_ids()
        if not selected_ids:
            messagebox.showinfo(
                "Нет выделения", "Выберите один или несколько karaoke-слогов.", parent=self
            )
            return

        if len(selected_ids) >= 2:
            changed = {}
            lookup = {s.id: s for s in self.session.syllables}
            for sid in selected_ids:
                s = lookup.get(sid)
                if s is None:
                    continue
                curr = self._karaoke_text_drafts.get(
                    sid,
                    s.source.raw_text if s.source is not None else s.text,
                )
                stripped = curr.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    continue
                changed[sid] = f"[{curr}]"
            if not changed:
                self._set_status("Выделенные слоги уже обособлены в [...]")
                return
            result = self._run_karaoke_edit(
                lambda: self.session.edit_texts(changed),
                f"Обособлено [непроизнесённое]: {len(changed)} слог(а)",
            )
            return

        if str(self.karaoke_text_editor.cget("state")) == "disabled":
            return
        sid = selected_ids[0]
        has_selection = False
        try:
            sel_start = self.karaoke_text_editor.index("sel.first")
            sel_end = self.karaoke_text_editor.index("sel.last")
            has_selection = bool(sel_start and sel_end and sel_start != sel_end)
        except tk.TclError:
            has_selection = False

        if has_selection:
            self._wrap_selected_text_in_brackets(self.karaoke_text_editor)
            self._remember_current_karaoke_draft()
            self._commit_text_drafts(preserve_selection={sid})
        else:
            if messagebox.askyesno(
                "Обособить целиком?",
                "Фрагмент текста не выделен.\nОбособить весь слог как [непроизнесённое]?",
                parent=self,
            ):
                curr = self._text_editor_value()
                stripped = curr.strip()
                if not (stripped.startswith("[") and stripped.endswith("]")):
                    self.karaoke_text_editor.delete("1.0", "end")
                    self.karaoke_text_editor.insert("1.0", f"[{curr}]")
                    self._remember_current_karaoke_draft()
                    self._commit_text_drafts(preserve_selection={sid})

    def open_full_text_editor(self) -> None:
        if self.session.document is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
            return
        if not self._commit_text_drafts(
            preserve_selection=set(self._selected_karaoke_ids())
        ):
            return
        syllables = self.session.document.karaoke_syllables()
        if not syllables:
            messagebox.showinfo("Нет karaoke", "В ASS нет karaoke-слогов.", parent=self)
            return
        separator = "⁞"
        if any(separator in item.visible_text for item in syllables):
            messagebox.showerror(
                "Редактор всего текста",
                f"Символ-разделитель {separator} уже встречается в тексте.",
                parent=self,
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("Весь текст — безопасное редактирование")
        dialog.geometry("920x650")
        dialog.minsize(700, 440)
        dialog.transient(self)
        dialog.configure(background=self.palette.bg)
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                f"Серый символ {separator} — граница существующих karaoke-слогов. "
                "Его нельзя удалять или добавлять: тайминги остаются привязаны к этим границам. "
                "Обычный Enter создаёт перенос строки; [текст] помечает непроговорённую часть."
            ),
            style="Muted.TLabel", wraplength=880, justify="left",
        ).pack(fill="x", pady=(0, 7))
        frame = ttk.Frame(body)
        frame.pack(fill="both", expand=True)
        editor = tk.Text(frame, wrap="word", undo=True, maxundo=300, font=("TkFixedFont", 11))
        scroll = ttk.Scrollbar(frame, orient="vertical", command=editor.yview)
        editor.configure(yscrollcommand=scroll.set)
        editor.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        apply_text_theme(editor, self.palette)
        editor.tag_configure("boundary", foreground=self.palette.muted)
        for index, item in enumerate(syllables):
            if index:
                start = editor.index("end-1c")
                editor.insert("end", separator)
                editor.tag_add("boundary", start, editor.index("end-1c"))
            editor.insert("end", item.visible_text)
        editor.edit_reset()
        editor.mark_set("insert", "1.0")
        editor.focus_set()

        status = tk.StringVar(value=f"Karaoke-слогов: {len(syllables)}")

        def mark_selected() -> None:
            if not self._wrap_selected_text_in_brackets(editor):
                messagebox.showinfo(
                    "Нет выделения", "Выделите непроговорённый фрагмент.", parent=dialog
                )

        def apply_all() -> None:
            parts = editor.get("1.0", "end-1c").split(separator)
            if len(parts) != len(syllables):
                messagebox.showerror(
                    "Нарушены границы слогов",
                    f"Ожидалось {len(syllables)} частей, получено {len(parts)}. "
                    f"Верните все разделители {separator} через Ctrl+Z.",
                    parent=dialog,
                )
                return
            changed = {
                item.id: value
                for item, value in zip(syllables, parts)
                if value != item.visible_text
            }
            if not changed:
                dialog.destroy()
                self._set_status("Весь текст не изменён")
                return
            try:
                result = self.session.edit_visible_texts(changed)
            except (KaraokeEditError, ValueError, RuntimeError) as exc:
                messagebox.showerror("Не удалось изменить весь текст", str(exc), parent=dialog)
                return
            dialog.destroy()
            self._after_karaoke_edit(
                result,
                f"Весь текст обновлён без изменения karaoke-таймингов: {len(changed)} слог(а)",
            )

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Label(actions, textvariable=status, style="Muted.TLabel").pack(side="left")
        ttk.Button(actions, text="Пометить [непроизнесённое]", command=mark_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Отмена", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Применить", command=apply_all, style="Accent.TButton").pack(side="right", padx=(0, 6))
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Control-Return>", lambda _e: (apply_all(), "break")[1])
        self._add_hotkey_bindtag(dialog)
        dialog.grab_set()

    def split_karaoke_at_cursor(self) -> None:
        ids = self._selected_karaoke_ids()
        if len(ids) != 1 or self._karaoke_text_bound_id != ids[0]:
            messagebox.showinfo("Выберите один слог", "Для разделения по курсору выберите один karaoke-слог.", parent=self)
            return
        sid = ids[0]
        raw = self._text_editor_value()
        try:
            # Measure the actual Python string before the cursor so supplementary
            # Unicode characters have the same indexing as the ASS core.
            offset = len(self.karaoke_text_editor.get("1.0", "insert"))
        except Exception:
            offset = len(raw)
        # Other saved drafts must be materialized before IDs can shift. The
        # current draft is folded into this split as one undoable edit.
        if not self._commit_text_drafts(exclude={sid}, preserve_selection={sid}):
            return
        try:
            # Text follows the editor caret; timing follows the playback cursor.
            # This keeps the text-editing precision mode consistent with the
            # main timeline split introduced in Update 033.
            result = self.session.edit_split_at_cursor(
                sid, offset, raw_text=raw, new_type=self._chosen_karaoke_tag(),
                boundary_time=self.playhead_time,
            )
        except (KaraokeEditError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Не удалось разделить по курсору", str(exc), parent=self)
            return
        self._karaoke_text_drafts.pop(sid, None)
        self._after_karaoke_edit(result, "Karaoke-слог разделён по позиции текстового курсора")
        if result.selected_ids:
            self.karaoke_timeline.select_ids((result.selected_ids[-1],))
            self.after_idle(self.focus_karaoke_text_editor)

    def navigate_karaoke(self, direction: int) -> None:
        self._remember_current_karaoke_draft()
        items = self.session.syllables
        if not items:
            return
        ids = [s.id for s in items]
        current = self._selected_karaoke_ids()
        if len(current) == 1 and current[0] in ids:
            index = ids.index(current[0])
        else:
            index = 0 if direction >= 0 else len(ids) - 1
        index = max(0, min(len(ids) - 1, index + (1 if direction > 0 else -1)))
        target = items[index]
        self.karaoke_timeline.select_ids((target.id,))
        self.karaoke_timeline.focus_time((target.start + target.end) / 2)
        self.after_idle(self.focus_karaoke_text_editor)

    def play_karaoke_selection(self) -> None:
        chosen = self.karaoke_timeline.selected_syllables()
        if not chosen:
            self._set_status("Выберите karaoke-слог для воспроизведения")
            return
        start = min(s.start for s in chosen)
        end = max(s.end for s in chosen)
        self._play_interval(start, end, label="Karaoke selection")

    def _karaoke_selection_changed(self, ids: set[str]) -> None:
        self._remember_current_karaoke_draft()
        lookup = {s.id: s for s in self.session.syllables}
        chosen = [lookup[i] for i in ids if i in lookup]
        if not chosen:
            self.karaoke_selected_info_var.set("Слог: —")
            self.karaoke_burst_state_var.set("Burst-окраска: —")
            self._set_karaoke_text_editor(None)
            return
        start = min(s.start for s in chosen)
        end = max(s.end for s in chosen)
        if len(chosen) == 1 and chosen[0].source is not None:
            source = chosen[0].source
            if hasattr(self, "karaoke_timeline") and self.advanced_mode_var.get():
                item_track = getattr(source, "track", 0)
                if self.karaoke_timeline.active_track != item_track:
                    self.karaoke_timeline.active_track = item_track
                    self.karaoke_timeline._draw_track_panel()
                    self.karaoke_timeline.redraw()
            label = chosen[0].text.strip().replace("\n", " ") or "(пустой)"
            self.karaoke_selected_info_var.set(
                f"{label[:20]} · {source.duration_cs} cs · \\{source.tag_type.value}"
                + (" · ROM" if source.romanization else "")
            )
            self.karaoke_burst_state_var.set(
                "Burst-окраска: ДА (красный)" if source.burst_marked
                else "Burst-окраска: нет"
            )
            mapping = {
                KaraokeTagType.K: "\\k (резкий)",
                KaraokeTagType.KF: "\\kf (плавный)",
                KaraokeTagType.KO: "\\ko (outline)",
                KaraokeTagType.CAPITAL_K: "\\K (плавный alias)",
            }
            self.karaoke_tag_var.set(mapping[source.tag_type])
            self._set_karaoke_text_editor(source)
        else:
            self.karaoke_selected_info_var.set(f"Слогов: {len(chosen)} · {(end-start):.2f} с")
            marked = sum(1 for item in chosen if item.burst_marked)
            self.karaoke_burst_state_var.set(
                f"Burst-окраска: {marked} из {len(chosen)}"
            )
            self._set_karaoke_text_editor(None)
        self._set_status(f"Karaoke: выделено {len(chosen)} · {format_clock(start)}–{format_clock(end)}")

    def _selected_karaoke_ids(self) -> list[str]:
        ids = {s.id for s in self.session.syllables}
        return [s.id for s in self.session.syllables if s.id in self.karaoke_timeline.selected_ids and s.id in ids]

    def _chosen_karaoke_tag(self) -> KaraokeTagType:
        value = self.karaoke_tag_var.get()
        if value.startswith("\\kf"):
            return KaraokeTagType.KF
        if value.startswith("\\ko"):
            return KaraokeTagType.KO
        if value.startswith("\\K"):
            return KaraokeTagType.CAPITAL_K
        return KaraokeTagType.K

    def _after_karaoke_edit(self, result, message: str) -> None:
        timeline = self.session.karaoke_timeline
        if timeline is None:
            return
        # A structural edit can retain the old left-hand syllable ID while its
        # text has changed (for example "gonna " -> "gon" + "na ").  Unbind
        # the editor before changing selection; otherwise the selection callback
        # remembers its stale pre-split contents as a new draft for that same ID.
        self._set_karaoke_text_editor(None)
        manual = manual_bursts(timeline.syllables)
        self.karaoke_timeline.set_data(timeline.syllables, manual_regions=manual, reset_view=False)
        self.karaoke_timeline.set_waveform(self.waveform, reset_view=False)
        self.karaoke_timeline.set_spectrogram(
            self.spectrogram, view=self.spectrogram_view, reset_view=False
        )
        self.karaoke_timeline.select_ids(result.selected_ids)
        # Any prior SPS transfer was derived from old karaoke timings/ordinals.
        self.sps_timeline.set_data([], reset_view=False)
        self.sps_summary.configure(text="Материал нужно передать заново после правки Karaoke")
        self.burst_tree.delete(*self.burst_tree.get_children())
        self.karaoke_info.configure(
            text=f"{len(timeline.syllables)} karaoke-слогов · ручных burst-областей: {len(manual)}"
        )
        self._refresh_labels()
        if hasattr(self, "alignment_panel"):
            self.alignment_panel.refresh_project()
        if hasattr(self, "render_panel"):
            self.render_panel.refresh_source(reset_measurement=True)
        self._karaoke_selection_changed(set(result.selected_ids))
        archive = self.session.last_measurement_archive
        suffix = f" · прежние SPS-измерения сохранены как {archive.name}" if archive else ""
        self._set_status(message + " · ASS ещё не сохранён" + suffix)
        if getattr(self, "autosave_mode_var", None) and self.autosave_mode_var.get() == "after_edit":
            if (
                self.session.document is not None
                and self.session.subtitle_path is not None
                and self.session.dirty
            ):
                try:
                    self.session.save_subtitles()
                    self._last_autosave_time = time.monotonic()
                    self._refresh_labels()
                    self._set_status(message + " · Автосохранено" + suffix)
                except Exception:
                    pass

    def _run_karaoke_edit(self, func, message: str):
        try:
            result = func()
        except (KaraokeEditError, ValueError, RuntimeError) as exc:
            messagebox.showerror("Не удалось изменить karaoke", str(exc), parent=self)
            return None
        self._after_karaoke_edit(result, message)
        return result

    def _prepare_karaoke_structure_edit(self, selected_ids: list[str]) -> bool:
        # Structural edits can shift syllable ordinals, so materialize any text
        # drafts first while the old IDs still point to the intended syllables.
        return self._commit_text_drafts(preserve_selection=set(selected_ids))

    def apply_karaoke_type(self) -> None:
        ids = self._selected_karaoke_ids()
        if not ids:
            messagebox.showinfo("Нет выделения", "Выберите один или несколько karaoke-слогов.", parent=self)
            return
        if not self._commit_text_drafts(preserve_selection=set(ids)):
            return
        tag_type = self._chosen_karaoke_tag()
        self._run_karaoke_edit(
            lambda: self.session.edit_tag_type(ids, tag_type),
            f"Тип {tag_type.value} применён к {len(ids)} слог(ам)",
        )

    def _karaoke_item_for_playhead_split(self):
        """Return the karaoke item whose timing contains the current playhead.

        A selected item wins when it contains the cursor; otherwise the first
        matching timeline item is used. This makes timing an empty ASS possible
        without repeatedly selecting the giant/remaining empty span by hand.
        """
        t = float(self.playhead_time)
        items = list(self.session.syllables)
        selected_ids = set(self._selected_karaoke_ids())

        def can_split(item) -> bool:
            duration_cs = getattr(getattr(item, "source", None), "duration_cs", None)
            if duration_cs is None:
                duration_cs = int(round((float(item.end) - float(item.start)) * 100.0))
            left_cs = int(round((t - float(item.start)) * 100.0))
            return int(duration_cs) >= 2 and 0 < left_cs < int(duration_cs)

        # 1. If exactly one syllable is selected and it can be split at playhead,
        # that syllable explicitly wins.
        selected = [item for item in items if item.id in selected_ids and can_split(item)]
        if len(selected) == 1:
            sel_item = selected[0]
            item_track = getattr(getattr(sel_item, "source", None), "track", 0)
            if hasattr(self, "karaoke_timeline") and getattr(self.karaoke_timeline, "active_track", 0) != item_track:
                self.karaoke_timeline.active_track = item_track
                self.karaoke_timeline._draw_track_panel()
                self.karaoke_timeline.redraw()
            return sel_item

        # 2. In advanced mode (multiple tracks), strictly split candidate on the active track.
        if self.advanced_mode_var.get() and hasattr(self, "karaoke_timeline"):
            active_t = getattr(self.karaoke_timeline, "active_track", 0)
            candidates = [
                item for item in items
                if can_split(item) and getattr(getattr(item, "source", None), "track", 0) == active_t
            ]
            if candidates:
                candidates.sort(key=lambda item: (float(item.start), float(item.end), item.id))
                return candidates[0]
            return None

        # 3. In single track mode, track 0 candidate wins.
        candidates = [
            item for item in items
            if can_split(item) and getattr(getattr(item, "source", None), "track", 0) == 0
        ]
        if not candidates:
            candidates = [item for item in items if can_split(item)]
        if not candidates:
            return None
        candidates.sort(key=lambda item: (float(item.start), float(item.end), item.id))
        return candidates[0]

    def insert_karaoke(self) -> None:
        if self.advanced_mode_var.get() and hasattr(self, "karaoke_timeline"):
            active_t = getattr(self.karaoke_timeline, "active_track", 0)
        else:
            active_t = 0

        item = self._karaoke_item_for_playhead_split()
        if item is not None:
            ids = [item.id]
            if not self._prepare_karaoke_structure_edit(ids):
                return
            result = self._run_karaoke_edit(
                lambda: self.session.edit_insert_at_time(
                    item.id, self.playhead_time, new_type=self._chosen_karaoke_tag()
                ),
                "Добавлен пустой karaoke-слог по позиции полосы воспроизведения",
            )
            if result is not None and result.focus_time is not None:
                self._set_playhead(result.focus_time)
            self.after_idle(self.focus_karaoke_text_editor)
            return

        if active_t != 0:
            if self.session.document is None:
                messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
                return
            t = float(self.playhead_time)
            all_syllables = list(self.session.document.karaoke_syllables())
            track0_syllables = [s for s in all_syllables if getattr(s, "track", 0) == 0]
            selected_ids = set(self._selected_karaoke_ids())
            selected_t0 = next((s for s in track0_syllables if s.id in selected_ids), None)
            syl_at_t = next((s for s in track0_syllables if s.start <= t <= s.end), None)
            ref_syl = selected_t0 or syl_at_t

            seq_id = None
            if ref_syl is not None:
                seq_id = next((i + 1 for i, s in enumerate(track0_syllables) if s.id == ref_syl.id), None)
                text = ref_syl.visible_text
                dur_cs = ref_syl.duration_cs if ref_syl.duration_cs > 0 else 50
            else:
                text = ""
                dur_cs = 50

            tag_type = self._chosen_karaoke_tag()
            result = self._run_karaoke_edit(
                lambda: self.session.edit_insert_track_syllable(
                    active_t, t, duration_cs=dur_cs, text=text,
                    ref_track0_seq=seq_id, tag_type=tag_type,
                ),
                f"Вставлен слог на дорожку {active_t}",
            )
            if result is not None and result.focus_time is not None:
                self._set_playhead(result.focus_time)
            self.after_idle(self.focus_karaoke_text_editor)
            return

        messagebox.showinfo(
            "Курсор вне слога",
            "Поставьте полосу воспроизведения строго внутрь karaoke-слога. "
            "Нужно оставить минимум 1 cs с каждой стороны.",
            parent=self,
        )

    def split_karaoke(self) -> None:
        item = self._karaoke_item_for_playhead_split()
        if item is None:
            active_t = (
                getattr(self.karaoke_timeline, "active_track", 0)
                if (self.advanced_mode_var.get() and hasattr(self, "karaoke_timeline"))
                else 0
            )
            if active_t != 0:
                msg = f"Поставьте полосу воспроизведения строго внутрь слога на дорожке {active_t}."
            else:
                msg = (
                    "Поставьте полосу воспроизведения строго внутрь karaoke-слога. "
                    "Разделение выполняется именно в этой временной точке."
                )
            messagebox.showinfo("Курсор вне слога", msg, parent=self)
            return
        ids = [item.id]
        if not self._prepare_karaoke_structure_edit(ids):
            return
        result = self._run_karaoke_edit(
            lambda: self.session.edit_split_at_time(
                item.id, self.playhead_time, new_type=self._chosen_karaoke_tag()
            ),
            "Karaoke-слог разделён по полосе воспроизведения; текст распределён пропорционально времени",
        )
        if result is not None and result.focus_time is not None:
            self._set_playhead(result.focus_time)

    def merge_karaoke(self) -> None:
        ids = self._selected_karaoke_ids()
        if len(ids) < 2:
            messagebox.showinfo("Недостаточно слогов", "Для совмещения выделите два или больше соседних слога одной строки.", parent=self)
            return
        if not self._prepare_karaoke_structure_edit(ids):
            return
        self._run_karaoke_edit(
            lambda: self.session.edit_merge(ids),
            f"Совмещено karaoke-слогов: {len(ids)}",
        )

    def delete_karaoke(self) -> None:
        ids = self._selected_karaoke_ids()
        if len(ids) != 1:
            messagebox.showinfo("Выберите один слог", "Удаление сейчас применяется к одному выбранному слогу.", parent=self)
            return
        if not self._prepare_karaoke_structure_edit(ids):
            return
        self._run_karaoke_edit(
            lambda: self.session.edit_delete(ids[0]),
            "Karaoke-слог удалён; его длительность передана соседнему",
        )

    def _delete_shortcut(self, _event=None):
        try:
            current_tab = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            return None
        if current_tab == self.karaoke_tab:
            focus = self.focus_get()
            if isinstance(focus, (tk.Entry, tk.Text, ttk.Entry, ttk.Spinbox, ttk.Combobox)):
                return None
            self.delete_karaoke()
            return "break"
        return None

    def _handle_add_track(self, direction: str, reference_track: int) -> None:
        if not self.advanced_mode_var.get():
            return
        if self.session.document is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте или создайте ASS-файл.", parent=self)
            return
        existing_tracks = list(self.karaoke_timeline.tracks)
        new_track_id = 1
        while new_track_id in existing_tracks:
            new_track_id += 1
        if reference_track in existing_tracks:
            idx = existing_tracks.index(reference_track)
            if direction == "above":
                existing_tracks.insert(idx, new_track_id)
            else:
                existing_tracks.insert(idx + 1, new_track_id)
        else:
            existing_tracks.append(new_track_id)
        self.karaoke_timeline.tracks = existing_tracks
        self.karaoke_timeline.active_track = new_track_id

        total_sec = 0.0
        if self.waveform is not None and self.waveform.duration > 0:
            total_sec = self.waveform.duration
        elif self.spectrogram is not None and self.spectrogram.duration > 0:
            total_sec = self.spectrogram.duration
        elif hasattr(self, "karaoke_timeline") and self.karaoke_timeline.viewport.total_end > 0:
            total_sec = self.karaoke_timeline.viewport.total_end
        elif self.session.document is not None:
            events = list(self.session.document.events())
            if events:
                total_sec = max(e.end for e in events)
        if total_sec <= 0.0:
            total_sec = 60.0

        tag_type = self._chosen_karaoke_tag()
        result = self._run_karaoke_edit(
            lambda: self.session.edit_add_track(new_track_id, total_sec, tag_type=tag_type),
            f"Создана дорожка {new_track_id} (заполнена пустым слогом от начала до конца)",
        )
        self.karaoke_timeline.active_track = new_track_id
        self.karaoke_timeline.redraw()
        self.karaoke_timeline._draw_track_panel()

    def link_karaoke_to_track0(self) -> None:
        if not self.advanced_mode_var.get():
            return
        ids = self._selected_karaoke_ids()
        if len(ids) != 1:
            messagebox.showinfo("Выберите один слог", "Выберите один слог на дополнительной дорожке для привязки к Track 0.", parent=self)
            return
        if self.session.document is None:
            return
        all_syllables = list(self.session.document.karaoke_syllables())
        item = next((s for s in all_syllables if s.id == ids[0]), None)
        if item is None:
            return
        if getattr(item, "track", 0) == 0:
            messagebox.showinfo("Основная дорожка", "Этот слог уже находится на основной дорожке (Track 0). Привязка к Track 0 выполняется для слогов на дополнительных дорожках.", parent=self)
            return

        track0_syllables = [s for s in all_syllables if getattr(s, "track", 0) == 0]
        if not track0_syllables:
            messagebox.showinfo("Нет слогов", "На основной дорожке (Track 0) нет слогов.", parent=self)
            return

        mid = (item.start + item.end) / 2.0
        overlapping = [s for s in track0_syllables if s.start <= mid <= s.end]
        if not overlapping:
            overlapping = [s for s in track0_syllables if not (s.end <= item.start or s.start >= item.end)]

        def_id = 1
        if overlapping:
            ref_syl = overlapping[0]
            def_id = next((i + 1 for i, s in enumerate(track0_syllables) if s.id == ref_syl.id), 1)

        id_num = simpledialog.askinteger(
            "Привязка к Track 0",
            f"Введите порядковый номер слога на основной дорожке (id: 1..{len(track0_syllables)}):",
            initialvalue=def_id,
            minvalue=1,
            maxvalue=len(track0_syllables),
            parent=self,
        )
        if id_num is None:
            return

        target_ref = track0_syllables[id_num - 1]
        text_val = item.visible_text.strip() or target_ref.visible_text.strip()
        new_raw = f"{{\\id0:{id_num}}}{text_val}"
        self._run_karaoke_edit(
            lambda: self.session.edit_text(item.id, new_raw),
            f"Слог привязан к Track 0 (id: {id_num})",
        )

    def _handle_move_track(self, track_id: int, direction: int) -> None:
        if not self.advanced_mode_var.get():
            return
        tracks = list(self.karaoke_timeline.tracks)
        if track_id not in tracks:
            return
        idx = tracks.index(track_id)
        new_idx = idx + direction
        if 0 <= new_idx < len(tracks):
            tracks.pop(idx)
            tracks.insert(new_idx, track_id)
            self.karaoke_timeline.tracks = tracks
            self.karaoke_timeline.active_track = track_id
            self.karaoke_timeline.redraw()
            self.karaoke_timeline._draw_track_panel()

    def _handle_delete_track(self, track_id: int) -> None:
        if not self.advanced_mode_var.get() or track_id == 0:
            return
        if not messagebox.askyesno(
            "Удаление дорожки",
            f"Удалить дорожку {track_id} и все её события?",
            parent=self,
        ):
            return
        if self.session.document is not None:
            events_to_delete = []
            for ev in self.session.document.events():
                eff = str(getattr(ev, "effect", "") or "").strip()
                if eff == f"track:{track_id}":
                    events_to_delete.append(ev.line_index)
            if events_to_delete:
                for line_idx in sorted(events_to_delete, reverse=True):
                    del self.session.document.lines[line_idx]
                self.session.dirty = True
                self.session._rebuild_karaoke_after_edit()
        if track_id in self.karaoke_timeline.tracks:
            self.karaoke_timeline.tracks.remove(track_id)
        if self.karaoke_timeline.active_track == track_id:
            self.karaoke_timeline.active_track = 0
        self._refresh_from_session(reset_view=False)
        self.karaoke_timeline._draw_track_panel()
        self._set_status(f"Дорожка {track_id} удалена")

    def _karaoke_boundary_dragged(self, left_id: str, right_id: str, boundary: float) -> None:
        if not self._commit_text_drafts(preserve_selection={left_id, right_id}):
            return
        self._run_karaoke_edit(
            lambda: self.session.edit_boundary(left_id, right_id, boundary),
            f"Граница karaoke перемещена на {format_clock(boundary)}",
        )

    def undo_karaoke(self) -> None:
        if self.focus_get() is getattr(self, "karaoke_text_editor", None):
            try:
                self.karaoke_text_editor.edit_undo()
                self._remember_current_karaoke_draft()
                return
            except tk.TclError:
                pass
        if not self.session.undo():
            self._set_status("Нечего отменять")
            return
        self._refresh_karaoke_after_history("Отменено последнее karaoke-изменение")

    def redo_karaoke(self) -> None:
        if self.focus_get() is getattr(self, "karaoke_text_editor", None):
            try:
                self.karaoke_text_editor.edit_redo()
                self._remember_current_karaoke_draft()
                return
            except tk.TclError:
                pass
        if not self.session.redo():
            self._set_status("Нечего повторять")
            return
        self._refresh_karaoke_after_history("Повторено karaoke-изменение")

    def undo_sps_measurement(self) -> bool:
        try:
            syllable_id = self.session.undo_measurement()
        except Exception as exc:
            messagebox.showerror("Не удалось отменить measurement", str(exc), parent=self)
            return True
        if syllable_id is None:
            self._set_status("Нечего отменять во вкладке «Точный SPS»")
            return False
        self._sync_sps_timeline_preserve_view(select_id=syllable_id)
        self._refresh_measurement_controls()
        self._refresh_sps_summary()
        self._refresh_sps_graph()
        self._set_status("Отменено последнее изменение точных SPS-границ")
        return True

    def redo_sps_measurement(self) -> bool:
        try:
            syllable_id = self.session.redo_measurement()
        except Exception as exc:
            messagebox.showerror("Не удалось повторить measurement", str(exc), parent=self)
            return True
        if syllable_id is None:
            self._set_status("Нечего повторять во вкладке «Точный SPS»")
            return False
        self._sync_sps_timeline_preserve_view(select_id=syllable_id)
        self._refresh_measurement_controls()
        self._refresh_sps_summary()
        self._refresh_sps_graph()
        self._set_status("Повторено изменение точных SPS-границ")
        return True

    def _refresh_karaoke_after_history(self, message: str) -> None:
        old_selection = set(self.karaoke_timeline.selected_ids)
        timeline = self.session.karaoke_timeline
        if timeline is None:
            return
        manual = manual_bursts(timeline.syllables)
        self.karaoke_timeline.set_data(timeline.syllables, manual_regions=manual, reset_view=False)
        self.karaoke_timeline.set_waveform(self.waveform, reset_view=False)
        self.karaoke_timeline.set_spectrogram(
            self.spectrogram, view=self.spectrogram_view, reset_view=False
        )
        self.karaoke_timeline.select_ids(old_selection)
        self.sps_timeline.set_data([], reset_view=False)
        self.sps_summary.configure(text="Материал нужно передать заново после правки Karaoke")
        self.burst_tree.delete(*self.burst_tree.get_children())
        self.karaoke_info.configure(text=f"{len(timeline.syllables)} karaoke-слогов · ручных burst-областей: {len(manual)}")
        self._refresh_labels()
        if hasattr(self, "alignment_panel"):
            self.alignment_panel.refresh_project()
        if hasattr(self, "render_panel"):
            self.render_panel.refresh_source(reset_measurement=True)
        self._set_status(message)

    def save_ass(self) -> None:
        if self.session.document is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
            return
        editor_widget = None
        cursor_pos = None
        focused = self.focus_get()
        if focused is getattr(self, "karaoke_text_editor", None):
            editor_widget = self.karaoke_text_editor
            try:
                cursor_pos = self.karaoke_text_editor.index("insert")
            except Exception:
                pass
        elif focused is getattr(self, "karaoke_romanization_entry", None):
            editor_widget = self.karaoke_romanization_entry
            try:
                cursor_pos = self.karaoke_romanization_entry.index("insert")
            except Exception:
                pass

        if not self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids())):
            return
        if self.session.subtitle_path is None:
            self.save_ass_as()
            return
        try:
            target = self.session.save_subtitles()
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить ASS", str(exc), parent=self)
            return
        self._refresh_labels()
        self._set_status(f"ASS сохранён атомарно · backup: {target.name}.bak")
        if editor_widget is not None and cursor_pos is not None:
            try:
                editor_widget.focus_set()
                if isinstance(editor_widget, tk.Text):
                    editor_widget.mark_set("insert", cursor_pos)
                else:
                    editor_widget.icursor(cursor_pos)
            except Exception:
                pass

    def save_ass_as(self) -> None:
        if self.session.document is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
            return
        editor_widget = None
        cursor_pos = None
        focused = self.focus_get()
        if focused is getattr(self, "karaoke_text_editor", None):
            editor_widget = self.karaoke_text_editor
            try:
                cursor_pos = self.karaoke_text_editor.index("insert")
            except Exception:
                pass
        elif focused is getattr(self, "karaoke_romanization_entry", None):
            editor_widget = self.karaoke_romanization_entry
            try:
                cursor_pos = self.karaoke_romanization_entry.index("insert")
            except Exception:
                pass

        if not self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids())):
            return
        initial = self.session.subtitle_path.name if self.session.subtitle_path else "subtitles.ass"
        path = filedialog.asksaveasfilename(
            title="Сохранить ASS как",
            defaultextension=".ass",
            initialfile=initial,
            filetypes=(("Advanced SubStation Alpha", "*.ass"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        try:
            target = self.session.save_subtitles(path)
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить ASS", str(exc), parent=self)
            return
        self._refresh_labels()
        self._set_status(f"ASS сохранён: {target}")
        if editor_widget is not None and cursor_pos is not None:
            try:
                editor_widget.focus_set()
                if isinstance(editor_widget, tk.Text):
                    editor_widget.mark_set("insert", cursor_pos)
                else:
                    editor_widget.icursor(cursor_pos)
            except Exception:
                pass

    def _confirm_dirty(self) -> bool:
        self._remember_current_karaoke_draft()
        self._remember_current_romanization_draft()
        if (
            not self.session.dirty
            and not self._karaoke_text_drafts
            and not self._karaoke_romanization_drafts
        ):
            return True
        answer = messagebox.askyesnocancel(
            "Несохранённые изменения",
            "Сохранить изменения karaoke перед продолжением?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            self.save_ass()
            return (
                not self.session.dirty
                and not self._karaoke_text_drafts
                and not self._karaoke_romanization_drafts
            )
        return True

    def _sps_selection_changed(self, ids: set[str]) -> None:
        self._refresh_measurement_controls()
        if ids:
            self._set_status(f"SPS: выделено слогов: {len(ids)}")

    def _selected_sps_items(self):
        timeline = self.session.sps_timeline
        if timeline is None:
            return []
        ids = self.sps_timeline.selected_ids
        return [s for s in timeline.syllables if s.id in ids]

    def _refresh_measurement_controls(self) -> None:
        chosen = self._selected_sps_items()
        self._updating_measurement_fields = True
        try:
            if len(chosen) == 1:
                s = chosen[0]
                text = s.text.strip().replace("\n", " ") or "(пустой)"
                self.measure_text.configure(text=f"Слог: {text[:22]}")
                self.measure_start_var.set(f"{s.effective_start:.6f}")
                self.measure_end_var.set(f"{s.effective_end:.6f}")
            else:
                self.measure_text.configure(text=f"Слогов: {len(chosen)}" if chosen else "Слог: —")
                self.measure_start_var.set("")
                self.measure_end_var.set("")
        finally:
            self._updating_measurement_fields = False

        if chosen:
            # Preserve marker roles instead of normalising reversed syllables.
            # This mirrors the archived leading-"-" convention used by the
            # actual Legacy 1–2 s calculation.
            start = chosen[0].effective_start
            end = chosen[-1].effective_end
            duration = max(0.0, end - start)
            speed = len(chosen) / duration if duration else 0.0
            changed = sum(1 for s in chosen if s.measurement_changed)
            reversed_count = sum(1 for s in chosen if s.effective_end < s.effective_start)
            reversed_note = f" · обратных {reversed_count}" if reversed_count else ""
            self.measure_stats.configure(
                text=f"{len(chosen)} / {duration:.4f} с = {speed:.4f} SPS · изменено {changed}{reversed_note}"
            )
            peak = fastest_legacy_window(chosen, measured=True)
            self._selected_fastest_window = peak
            if peak is None:
                self.measure_peak_var.set("Быстрейший бёрст (Legacy 1–2 s): для расчёта нужен сегмент ≥ 1 с")
            else:
                snippet = peak.text.replace("\n", " ")
                if len(snippet) > 70:
                    snippet = snippet[:69] + "…"
                self.measure_peak_var.set(
                    f"Быстрейший бёрст (Legacy 1–2 s): {peak.speed:.4f} SPS · "
                    f"{peak.count}//{peak.duration:.4f} · {format_clock(peak.start)}–{format_clock(peak.end)} · {snippet}"
                )
        else:
            self.measure_stats.configure(text="")
            self._selected_fastest_window = None
            self.measure_peak_var.set("Быстрейший бёрст: —")

    def select_fastest_legacy_burst(self) -> None:
        peak = self._selected_fastest_window
        if peak is None:
            self._set_status("В текущем выделении нет подходящего 1–2-секундного окна")
            return
        self.sps_timeline.select_ids(peak.syllable_ids)
        self.sps_timeline.focus_time((peak.start + peak.end) / 2)
        self._refresh_measurement_controls()
        self._set_status(f"Самый быстрый бёрст: {peak.speed:.4f} SPS · {peak.count}//{peak.duration:.4f}")

    def colour_selected_karaoke_burst(self) -> None:
        ids = self._selected_karaoke_ids()
        if not ids:
            messagebox.showinfo(
                "Нет выделения", "Выделите слоги во вкладке «Караоке».", parent=self,
            )
            return
        self._run_karaoke_edit(
            lambda: self.session.edit_burst_colour(ids),
            f"Бёрст окрашен: {len(ids)} слог(а)",
        )

    def uncolour_selected_karaoke_burst(self) -> None:
        ids = self._selected_karaoke_ids()
        if not ids:
            messagebox.showinfo(
                "Нет выделения", "Выделите окрашенные слоги во вкладке «Караоке».", parent=self,
            )
            return
        self._run_karaoke_edit(
            lambda: self.session.edit_burst_uncolour(ids),
            f"Burst-окраска снята: {len(ids)} слог(а)",
        )

    def colour_selected_burst(self) -> None:
        """Write legacy red/reset tags around the selected precise-SPS range."""

        self._edit_selected_sps_burst_colour(remove=False)

    def uncolour_selected_burst(self) -> None:
        self._edit_selected_sps_burst_colour(remove=True)

    def _edit_selected_sps_burst_colour(self, *, remove: bool) -> None:

        chosen = self._selected_sps_items()
        if not chosen:
            messagebox.showinfo(
                "Нет выделения",
                "Выделите соседние слоги бёрста во вкладке «Точный SPS».",
                parent=self,
            )
            return
        ids = tuple(item.id for item in chosen)
        transferred_ids = tuple(item.id for item in self.session.sps_timeline.syllables)
        all_ids = tuple(item.id for item in self.session.syllables)
        result = self._run_karaoke_edit(
            (
                (lambda: self.session.edit_burst_uncolour(ids))
                if remove else
                (lambda: self.session.edit_burst_colour(ids))
            ),
            (
                f"Burst-окраска снята: {len(ids)} слог(а)"
                if remove else f"Бёрст окрашен: {len(ids)} слог(а)"
            ),
        )
        if result is None:
            return

        # A colour edit does not alter IDs, timing or the measurement sidecar.
        # Rebuild the same SPS scope immediately so the user can keep working.
        try:
            threshold = float(self.min_sps_var.get().replace(",", "."))
        except ValueError:
            threshold = 6.0
        scope_ids = None if transferred_ids == all_ids else transferred_ids
        try:
            transfer = self.session.transfer_to_sps(
                syllable_ids=scope_ids,
                min_peak_sps=threshold,
            )
        except Exception as exc:
            messagebox.showerror(
                "ASS изменён, но SPS не обновлён",
                str(exc),
                parent=self,
            )
            return
        self._populate_sps(transfer)
        self.sps_timeline.select_ids(ids)
        if result.focus_time is not None:
            self.sps_timeline.focus_time(result.focus_time)
        self._refresh_measurement_controls()
        self.notebook.select(self.sps_tab)
        if remove:
            self._set_status(
                r"Burst-окраска снята тегом \c; измерения сохранены · ASS ещё не сохранён"
            )
        else:
            self._set_status(
                r"Бёрст записан в ASS тегами \c&Hff … \c; измерения сохранены · ASS ещё не сохранён"
            )

    def export_burst_or_selection_audio(self) -> None:
        media_path = self.session.media_path
        if media_path is None or not Path(media_path).is_file():
            messagebox.showinfo("Нет медиа", "Сначала укажите аудио или видео-файл.", parent=self)
            return
        ffmpeg = self.session.resolved_ffmpeg()
        if ffmpeg is None:
            messagebox.showerror("FFmpeg не найден", "Настройте FFmpeg в настройках.", parent=self)
            return

        current_tab = None
        try:
            current_tab = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            pass

        context = "sps" if current_tab == getattr(self, "sps_tab", None) else "karaoke"
        chosen = self._context_selected_items(context)
        if not chosen:
            other = "karaoke" if context == "sps" else "sps"
            other_chosen = self._context_selected_items(other)
            if other_chosen:
                context = other
                chosen = other_chosen

        selection_range: Optional[tuple[float, float, str]] = None
        if chosen:
            start = min(self._item_bounds(it, context)[0] for it in chosen)
            end = max(self._item_bounds(it, context)[1] for it in chosen)
            text = " ".join(it.text.strip() for it in chosen if it.text.strip())
            selection_range = (start, end, text)

        burst_range: Optional[tuple[float, float, str]] = None
        syllables = self._context_items(context)
        if not syllables and self.session.karaoke_timeline:
            syllables = list(self.session.karaoke_timeline.syllables)
        manuals = manual_bursts(syllables)

        if chosen:
            chosen_ids = {it.id for it in chosen}
            for mb in manuals:
                if any(sid in chosen_ids for sid in mb.syllable_ids):
                    burst_range = (mb.start, mb.end, mb.text)
                    break

        if burst_range is None and manuals:
            if chosen and selection_range:
                sel_mid = (selection_range[0] + selection_range[1]) / 2.0
                closest = min(manuals, key=lambda m: abs((m.start + m.end) / 2.0 - sel_mid))
                burst_range = (closest.start, closest.end, closest.text)
            else:
                burst_range = (manuals[0].start, manuals[0].end, manuals[0].text)

        if burst_range is None and getattr(self, "_selected_fastest_window", None) is not None:
            peak = self._selected_fastest_window
            burst_range = (peak.start, peak.end, "")

        if selection_range is None and burst_range is None:
            messagebox.showinfo(
                "Нет фрагмента",
                "Выделите слоги или отметьте бёрст для экспорта аудио-отрывка.",
                parent=self,
            )
            return

        ffplay = resolve_ffplay(ffmpeg)
        speed = normalize_playback_speed(float(self.playback_speed_var.get()))

        def play_clip(start: float, end: float) -> None:
            self.player.play(
                media_path, start, end, ffplay=ffplay, ffmpeg=ffmpeg, speed=speed,
            )

        def stop_clip() -> None:
            self.player.stop()

        AudioExportDialog(
            self,
            media_path=Path(media_path),
            ffmpeg=ffmpeg,
            selection_range=selection_range,
            burst_range=burst_range,
            project_root=self.session.project_root,
            on_play=play_clip,
            on_stop=stop_clip,
        )

    def apply_measurement_fields(self) -> None:
        chosen = self._selected_sps_items()
        if len(chosen) != 1:
            messagebox.showinfo("Выберите один слог", "Числовые границы применяются к одному выбранному слогу.", parent=self)
            return
        s = chosen[0]
        try:
            start = float(self.measure_start_var.get().replace(",", "."))
            end = float(self.measure_end_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Некорректные границы", "Start и End должны быть числами в секундах.", parent=self)
            return
        if (
            start < s.start - 1e-9 or start > s.end + 1e-9
            or end < s.start - 1e-9 or end > s.end + 1e-9
        ):
            messagebox.showerror(
                "Некорректные границы",
                f"Обе границы должны оставаться внутри исходного интервала {s.start:.6f}–{s.end:.6f}. "
                "End разрешено ставить раньше Start.",
                parent=self,
            )
            return
        self._commit_measurement(s.id, start, end)

    def _measurement_dragged(self, syllable_id: str, start: float, end: float) -> None:
        self._commit_measurement(syllable_id, start, end)

    def _commit_measurement(self, syllable_id: str, start: float, end: float) -> None:
        try:
            self.session.set_measurement(syllable_id, start, end)
        except Exception as exc:
            messagebox.showerror("Не удалось сохранить измерение", str(exc), parent=self)
            return
        self._sync_sps_timeline_preserve_view(select_id=syllable_id)
        self._refresh_measurement_controls()
        self._refresh_sps_summary()
        self._refresh_sps_graph()
        sidecar = self.session.measurement_sidecar_path()
        self._set_status(f"SPS-границы сохранены отдельно от ASS{f' · {sidecar}' if sidecar else ''}")

    def reset_selected_measurement(self) -> None:
        chosen = self._selected_sps_items()
        if len(chosen) != 1:
            messagebox.showinfo("Выберите один слог", "Сброс применяется к одному выбранному слогу.", parent=self)
            return
        sid = chosen[0].id
        try:
            self.session.clear_measurement(sid)
        except Exception as exc:
            messagebox.showerror("Не удалось сбросить измерение", str(exc), parent=self)
            return
        self._sync_sps_timeline_preserve_view(select_id=sid)
        self._refresh_measurement_controls()
        self._refresh_sps_summary()
        self._refresh_sps_graph()
        self._set_status("Измерительные границы сброшены к karaoke timing")

    def _sync_sps_timeline_preserve_view(self, *, select_id: str | None = None) -> None:
        timeline = self.session.sps_timeline
        if timeline is None:
            return
        self.sps_timeline.set_data(
            timeline.syllables,
            bursts=self.session.sps_candidates,
            manual_regions=self.session.manual_regions,
            reset_view=False,
        )
        self.sps_timeline.set_waveform(self.waveform, reset_view=False)
        self.sps_timeline.set_spectrogram(self.spectrogram, view=self.spectrogram_view, reset_view=False)
        self._update_playback_range_label("sps")
        self._update_playback_limit_label("sps")
        if select_id:
            self.sps_timeline.select_ids([select_id])

    def _graph_metric_key(self) -> str:
        # User-facing precise SPS always uses the archived 1–2 second method.
        return "legacy"

    def _build_sps_graph_series(self):
        timeline = self.session.sps_timeline
        if timeline is None:
            return []
        mode = self.sps_graph_source_var.get()
        series = []
        if mode in {"ASS timing", "Оба"}:
            points = sps_graph_points(timeline.syllables, metric="legacy", measured=False)
            series.append(GraphSeries("ASS", points, self.palette.accent))
        if mode in {"Точное measurement", "Оба"}:
            points = sps_graph_points(timeline.syllables, metric="legacy", measured=True)
            series.append(GraphSeries("Measured", points, self.palette.accent_alt))
        return series

    def _refresh_sps_graph(self) -> None:
        if not hasattr(self, "sps_graph"):
            return
        if self.session.sps_timeline is None:
            self.sps_graph.clear()
            return
        try:
            smooth = max(1, int(self.sps_graph_smoothing_var.get()))
            series = self._build_sps_graph_series()
        except Exception as exc:
            self._set_status(f"SPS-график: {exc}")
            return
        self.sps_graph.set_series(series, smoothing=smooth)

    def _sps_viewport_changed(self, _viewport) -> None:
        if hasattr(self, "sps_graph"):
            self.sps_graph.request_redraw()

    def _sps_graph_view_changed(self) -> None:
        # Graph and timeline share one Viewport instance. Throttle both heavy
        # canvases to the UI frame rate instead of redrawing twice for every
        # precision-touchpad event.
        self.sps_timeline.request_redraw()
        self.sps_timeline._sync_scrollbar()

    def _sps_graph_point_selected(self, point) -> None:
        self.sps_timeline.select_ids(point.syllable_ids)
        self._refresh_measurement_controls()
        self._set_status(
            f"{point.source_label}: {point.speed:.3f} SPS · "
            f"{format_clock(point.window_start)}–{format_clock(point.window_end)} · {point.count} слогов"
        )

    def export_sps_graph_csv(self) -> None:
        if self.session.sps_timeline is None:
            messagebox.showinfo("Нет данных", "Сначала передайте ASS в точный SPS.", parent=self)
            return
        try:
            series = self._build_sps_graph_series()
        except Exception as exc:
            messagebox.showerror("Не удалось построить график", str(exc), parent=self)
            return
        path = filedialog.asksaveasfilename(
            title="Экспорт SPS-графика", defaultextension=".csv",
            filetypes=(("CSV", "*.csv"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("source", "metric", "time", "speed", "count", "window_start", "window_end", "duration", "syllable_ids", "text"))
            for graph_series in series:
                for point in graph_series.points:
                    writer.writerow((
                        graph_series.name, point.metric, f"{point.time:.6f}", f"{point.speed:.6f}", point.count,
                        f"{point.window_start:.6f}", f"{point.window_end:.6f}", f"{point.duration:.6f}",
                        " ".join(point.syllable_ids), point.text,
                    ))
        self._set_status(f"SPS-график экспортирован: {path}")

    def export_sps_graph_png(self) -> None:
        measurement_timeline = self.session.sps_timeline
        if measurement_timeline is None:
            messagebox.showinfo("Нет данных", "Сначала передайте ASS в точный SPS.", parent=self)
            return
        try:
            smoothing = max(1, int(self.sps_graph_smoothing_var.get()))
            series = self._build_sps_graph_series()
        except Exception as exc:
            messagebox.showerror("Не удалось построить график", str(exc), parent=self)
            return
        if not any(item.points for item in series):
            messagebox.showinfo(
                "Нет данных", "Для выбранного источника SPS-график пуст.", parent=self,
            )
            return
        initial_settings = self._sps_graph_export_settings or GraphExportSettings(
            title=f"SPS · {self.sps_graph_source_var.get()}",
            subtitle=f"Legacy 1–2 s · сглаживание {smoothing}",
        )
        settings = ask_sps_graph_export_settings(self, initial_settings)
        if settings is None:
            return
        self._sps_graph_export_settings = settings
        self.sps_graph.set_series(series, smoothing=smoothing)
        stem = self.session.subtitle_path.stem if self.session.subtitle_path else "sps"
        source_slug = {
            "ASS timing": "ass",
            "Точное measurement": "measured",
            "Оба": "both",
        }.get(self.sps_graph_source_var.get(), "graph")
        kwargs = {}
        if self.session.project_root is not None:
            kwargs["initialdir"] = str(self.session.project_root / "exports")
        elif self.session.subtitle_path is not None:
            kwargs["initialdir"] = str(self.session.subtitle_path.parent)
        path = filedialog.asksaveasfilename(
            title="Экспорт SPS-графика в PNG 16:9",
            initialfile=f"{stem}-sps-{source_slug}-{settings.width}x{settings.height}.png",
            defaultextension=".png",
            filetypes=(("PNG image", "*.png"), ("Все файлы", "*.*")),
            **kwargs,
        )
        if not path:
            return
        try:
            export_viewport = self.sps_timeline.viewport
            if settings.scope == "all":
                export_viewport = Viewport()
                export_viewport.set_total(
                    self.sps_timeline.viewport.total_start,
                    self.sps_timeline.viewport.total_end,
                    reset=True,
                )
            target = render_sps_graph_png(
                path,
                series,
                # MeasurementTimeline stores SPS data only. The shared visible
                # range belongs to the GUI DualTimeline next to the graph.
                viewport=export_viewport,
                palette=self.palette,
                smoothing=smoothing,
                settings=settings,
            )
        except Exception as exc:
            messagebox.showerror("Не удалось экспортировать PNG", str(exc), parent=self)
            return
        self._set_status(
            f"SPS-график экспортирован: {target} · "
            f"{settings.width}×{settings.height} (16:9)"
        )

    def export_measurements(self) -> None:
        timeline = self.session.sps_timeline
        if timeline is None:
            messagebox.showinfo(
                "Нет measurements",
                "Сначала передайте ASS во вкладку «Точный SPS».",
                parent=self,
            )
            return
        stem = self.session.subtitle_path.stem if self.session.subtitle_path else "sps"
        kwargs = {}
        if self.session.project_root is not None:
            kwargs["initialdir"] = str(self.session.project_root / "exports")
        elif self.session.subtitle_path is not None:
            kwargs["initialdir"] = str(self.session.subtitle_path.parent)
        path = filedialog.asksaveasfilename(
            title="Экспорт measurements",
            defaultextension=".json",
            initialfile=f"{stem}.measurements.json",
            filetypes=(("SPS measurements", "*.json"), ("Все файлы", "*.*")),
            **kwargs,
        )
        if not path:
            return
        try:
            target = Path(path).resolve()
            sidecar = self.session.measurement_sidecar_path()
            if sidecar is not None and sidecar.exists():
                if sidecar.resolve() != target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sidecar, target)
                update_measurements(target, timeline, (item.id for item in timeline.syllables))
            else:
                save_measurements(target, timeline)
            count = len(read_measurements(target))
        except Exception as exc:
            messagebox.showerror("Не удалось экспортировать measurements", str(exc), parent=self)
            return
        self._set_status(f"Measurements экспортированы: {target} · записей: {count}")

    def import_measurements(self) -> None:
        if self.session.karaoke_timeline is None:
            messagebox.showinfo("Нет ASS", "Сначала откройте ASS-файл.", parent=self)
            return
        path = filedialog.askopenfilename(
            title="Загрузить measurements",
            filetypes=(("SPS measurements", "*.json"), ("Все файлы", "*.*")),
        )
        if not path:
            return
        try:
            records = read_measurements(path)
            threshold = float(str(self.min_sps_var.get()).replace(",", "."))
            # Import against the whole ASS so a file exported from a full SPS
            # session is not silently reduced by the currently selected scope.
            result = self.session.transfer_to_sps(min_peak_sps=threshold)
            available = {item.id for item in result.timeline.syllables}
            matched = set(records).intersection(available)
            by_id = {item.id: item for item in result.timeline.syllables}
            for syllable_id in matched:
                record = records[syllable_id]
                by_id[syllable_id].with_measurement(record.measured_start, record.measured_end)
            # Loading is a replacement, not a merge: an exported file contains
            # only changed syllables, so records absent from it mean "use ASS
            # timing" and must clear older local measurements.
            replace_measurements(records, result.timeline)
            self.session.reset_measurement_history()
            sidecar = self.session.measurement_sidecar_path()
            if sidecar is not None:
                save_measurements(sidecar, result.timeline)
            self._populate_sps(result)
        except Exception as exc:
            messagebox.showerror("Не удалось загрузить measurements", str(exc), parent=self)
            return
        missing = len(records) - len(matched)
        self.notebook.select(self.sps_tab)
        self._set_status(
            f"Measurements загружены: {len(matched)}"
            + (f" · не найдено слогов: {missing}" if missing else "")
        )

    def play_sps_selection(self) -> None:
        chosen = self._selected_sps_items()
        if not chosen:
            messagebox.showinfo("Нет выделения", "Выберите один или несколько слогов.", parent=self)
            return
        start, end, reversed_fallback = selection_audition_bounds(chosen, measured=True)
        if end <= start + 1e-9:
            self._set_status("Невозможно прослушать формальный End в самом начале медиа")
            return
        label = "SPS selection · до формального End" if reversed_fallback else "SPS selection"
        self._play_interval(start, end, label=label)

    def stop_playback(self) -> None:
        try:
            final_position = self.player.position()
        except Exception:
            final_position = self.playhead_time
        # Capture this before touching the backend. Some output implementations
        # synchronously change their state/position during stop().
        return_target = self._playback_return_target
        if return_target is None:
            return_target = self._playback_origin
        self.player.stop()
        self._finish_playback_ui(final_position, return_target=return_target)
        self._set_status("Воспроизведение остановлено")

    def _ordered_candidates(self):
        return sorted(self.session.sps_candidates, key=lambda b: (-b.peak_sps, b.start))

    def _burst_selected(self, _event=None) -> None:
        selection = self.burst_tree.selection()
        if not selection:
            return
        idx = int(selection[0].split(":", 1)[1])
        ordered = self._ordered_candidates()
        if 0 <= idx < len(ordered):
            burst = ordered[idx]
            self.sps_timeline.select_ids(burst.syllable_ids)
            self._set_status(f"Burst {format_clock(burst.start)}–{format_clock(burst.end)} · peak {burst.peak_sps:.2f} SPS")

    def _burst_double_click(self, _event=None) -> None:
        selection = self.burst_tree.selection()
        if not selection:
            return
        idx = int(selection[0].split(":", 1)[1])
        ordered = self._ordered_candidates()
        if 0 <= idx < len(ordered):
            burst = ordered[idx]
            self.sps_timeline.focus_time((burst.start + burst.end) / 2)

    def return_to_karaoke(self) -> None:
        ids = set(self.sps_timeline.selected_ids)
        if ids:
            self.karaoke_timeline.select_ids(ids)
            items = [s for s in self.session.syllables if s.id in ids]
            if items:
                self.karaoke_timeline.focus_time((min(s.start for s in items) + max(s.end for s in items)) / 2)
        self.notebook.select(self.karaoke_tab)

    def _notebook_tab_changed(self, _event=None) -> None:
        """Refresh only the page that just became visible.

        Hidden canvases deliberately defer expensive redraws.  This handler
        flushes one pending frame when a tab becomes visible and avoids the
        redraw storm that used to happen after minimize/restore + tab switch.
        """
        try:
            widget = self.notebook.nametowidget(self.notebook.select())
        except Exception:
            return
        if widget == getattr(self, "karaoke_tab", None) and hasattr(self, "karaoke_timeline"):
            self.karaoke_timeline.request_redraw(delay_ms=1, force=True)
            self.karaoke_timeline.set_playhead(self.playhead_time)
        elif widget == getattr(self, "sps_tab", None):
            if hasattr(self, "sps_timeline"):
                self.sps_timeline.request_redraw(delay_ms=1, force=True)
                self.sps_timeline.set_playhead(self.playhead_time)
            if hasattr(self, "sps_graph"):
                self.sps_graph.request_redraw(delay_ms=1, force=True)
        elif widget == getattr(self, "logs_tab", None) and hasattr(self, "log_panel"):
            self.log_panel.refresh()

    def reset_active_view(self) -> None:
        widget = self.notebook.nametowidget(self.notebook.select())
        if widget == self.karaoke_tab:
            timeline = self.karaoke_timeline
        elif widget == self.sps_tab:
            timeline = self.sps_timeline
        else:
            self._set_status("Во вкладке Render отдельного временного viewport нет")
            return
        timeline.viewport.reset()
        timeline.redraw()

    def _invalidate_analysis(self) -> None:
        self._analysis_generation += 1
        self.transfer_button.configure(state="normal")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _poll_task_ui(self) -> None:
        active = None
        try:
            # Updating a large Text/Treeview log while it is hidden is wasted
            # Tk work.  Catch up incrementally when the Logs tab is shown.
            if hasattr(self, "log_panel"):
                try:
                    logs_visible = self.notebook.select() == str(self.logs_tab)
                except Exception:
                    logs_visible = False
                if logs_visible:
                    self.log_panel.refresh()
            revision = self.task_center.revision
            active = self.task_center.latest_active()
            # Do not send the same configure calls to Tk over and over while
            # nothing changed.  They still invalidate native controls and make
            # moving/restoring the main window visibly heavier on Windows.
            if revision != self._task_ui_revision:
                self._task_ui_revision = revision
                if active is None:
                    if self._task_progress_indeterminate:
                        self.task_progress.stop()
                        self._task_progress_indeterminate = False
                    self.task_progress.configure(mode="determinate", value=0)
                    self.task_stage_label.configure(text="Фоновые задачи: —")
                    self.task_percent_label.configure(text="")
                else:
                    self.task_stage_label.configure(text=f"{active.source} · {active.title} · {active.stage}")
                    if active.progress is None:
                        if not self._task_progress_indeterminate:
                            self.task_progress.configure(mode="indeterminate")
                            self.task_progress.start(12)
                            self._task_progress_indeterminate = True
                        self.task_percent_label.configure(text="…")
                    else:
                        if self._task_progress_indeterminate:
                            self.task_progress.stop()
                            self._task_progress_indeterminate = False
                        self.task_progress.configure(mode="determinate", value=active.progress)
                        self.task_percent_label.configure(text=f"{active.progress:.0f}%")
        finally:
            if self.winfo_exists():
                self._task_poll_job = self.after(180 if active is not None else 500, self._poll_task_ui)
            else:
                self._task_poll_job = None

    def _poll_autosave_timer(self) -> None:
        try:
            mode = self.autosave_mode_var.get()
            if mode in {"1", "5", "10"}:
                interval_seconds = int(mode) * 60
                now = time.monotonic()
                if now - self._last_autosave_time >= interval_seconds:
                    focused = self.focus_get()
                    if focused in (getattr(self, "karaoke_text_editor", None), getattr(self, "karaoke_romanization_entry", None)):
                        return
                    self._last_autosave_time = now
                    if (
                        self.session.document is not None
                        and self.session.subtitle_path is not None
                        and self.session.dirty
                    ):
                        self._commit_text_drafts(preserve_selection=set(self._selected_karaoke_ids()))
                        target = self.session.save_subtitles()
                        self._refresh_labels()
                        self._set_status(f"Автосохранение ASS выполнено ({mode} мин) · {target.name}")
        except Exception:
            pass
        finally:
            if self.winfo_exists():
                self._autosave_poll_job = self.after(5000, self._poll_autosave_timer)
            else:
                self._autosave_poll_job = None

    def _close(self) -> None:
        if not self._confirm_dirty():
            return
        self._save_preferences()
        for job_name in ("_task_poll_job", "_playback_poll_job", "_prime_audio_job", "_autosave_poll_job", "_text_apply_debounce_job"):
            job = getattr(self, job_name, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        self.player.close()
        self.destroy()


def main() -> int:
    app = KaraokeApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

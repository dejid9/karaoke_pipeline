from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from karaoke_core.alignment import (
    AlignmentConversionSettings,
    AlignmentError,
    MFACommandSettings,
    command_for_display,
    convert_textgrid_to_ass,
    load_textgrid,
)
from karaoke_core.ass import KaraokeTagType
from karaoke_core.language import (
    detect_language_profile,
    language_labels,
    profile_for_language,
)
from karaoke_core.mfa import (
    MFAError,
    MFAInstalledModelCatalog,
    MFAProcess,
    adopt_textgrid,
    build_conda_mfa_prefix,
    build_conda_run_prefix,
    build_find_oovs_command,
    build_model_command,
    build_runtime_align_command,
    build_validate_command,
    detect_mfa_installation,
    find_oov_artifacts,
    find_textgrid,
    list_installed_mfa_models,
    list_conda_environments,
    matching_model_variant,
    model_language_key,
    parse_conda_mfa_launcher,
    prepare_mfa_workspace,
    read_oov_summary,
)
from karaoke_core.project import save_project
from karaoke_core.textprep import (
    TextPreprocessError, TextPreprocessSettings, prepare_text_local,
    probe_python_packages, tokenize_japanese_sudachi,
)
from karaoke_core.doctor import run_health_checks
from karaoke_gui.theme import DEFAULT_THEME, ThemePalette, apply_text_theme, get_theme
from karaoke_gui.task_center import TaskCenter, TaskHandle


_TAG_LABELS = {
    r"\k (резкий)": KaraokeTagType.K,
    r"\kf (плавный)": KaraokeTagType.KF,
    r"\ko (outline)": KaraokeTagType.KO,
    r"\K (плавный alias)": KaraokeTagType.CAPITAL_K,
}
_MODE_LABELS = {
    "Auto (HF, если доступен)": "auto",
    "HF model": "hf",
    "Legacy dictionary + acoustic": "legacy",
}

_PREPROCESS_LABELS = {
    "Без обработки": "none",
    "Unicode + пробелы": "normalize",
    "Japanese Sudachi": "japanese_sudachi",
}

_CUSTOM_BEAM_PRESET = "Вручную"
_BEAM_PRESETS: dict[str, tuple[int, int] | None] = {
    "Обычная речь · 10 / 40": (10, 40),
    "Быстрая речь · 50 / 200": (50, 200),
    "Очень быстрый рэп · 100 / 400": (100, 400),
    "Экстремальный поиск · 250 / 1000": (250, 1000),
    "Максимальный поиск (чоппер) · 1500 / 5000": (1500, 5000),
    "Ультра поиск · 2500 / 10000": (2500, 10000),
    _CUSTOM_BEAM_PRESET: None,
}
_DEFAULT_BEAM_PRESET = "Очень быстрый рэп · 100 / 400"


class AlignmentPanel(ttk.Frame):
    """MFA runner + timing-exact TextGrid -> ASS conversion."""

    _PROJECT_STATE_VARS = (
        "textgrid_var", "media_var", "transcript_var", "output_var",
        "word_tier_var", "phone_tier_var", "tag_var", "max_words_var",
        "max_gap_var", "max_line_var", "playres_x_var", "playres_y_var",
        "phone_boundaries_var", "open_after_var", "conda_executable_var",
        "conda_env_var", "mfa_use_conda_var", "mfa_command_var",
        "mfa_mode_var", "mfa_model_var", "mfa_dictionary_var",
        "mfa_auto_language_var", "mfa_language_var", "mfa_dialect_var",
        "mfa_g2p_var", "mfa_jobs_var", "mfa_auto_convert_var",
        "mfa_beam_preset_var", "mfa_beam_var", "mfa_retry_beam_var",
        "mfa_validate_ignore_acoustics_var", "mfa_model_kind_var",
        "mfa_model_name_var", "mfa_force_download_var",
        "text_preprocess_var", "sudachi_mode_var", "preprocess_strip_punct_var",
    )
    _PROJECT_PATH_VARS = {"textgrid_var", "media_var", "transcript_var", "output_var"}

    def __init__(
        self,
        master,
        *,
        session,
        open_generated: Callable[[Path], None],
        set_status: Callable[[str], None],
        task_center: TaskCenter | None = None,
    ) -> None:
        super().__init__(master, padding=8)
        self.session = session
        self.open_generated = open_generated
        self.set_status = set_status
        self.task_center = task_center
        self._active_task: TaskHandle | None = None

        self.textgrid_var = tk.StringVar()
        self.media_var = tk.StringVar()
        self.transcript_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.word_tier_var = tk.StringVar(value="words")
        self.phone_tier_var = tk.StringVar(value="phones")
        self.tag_var = tk.StringVar(value=r"\kf (плавный)")
        self.max_words_var = tk.StringVar(value="8")
        self.max_gap_var = tk.StringVar(value="0.65")
        self.max_line_var = tk.StringVar(value="8.0")
        self.playres_x_var = tk.StringVar(value="1920")
        self.playres_y_var = tk.StringVar(value="1080")
        self.phone_boundaries_var = tk.BooleanVar(value=True)
        self.open_after_var = tk.BooleanVar(value=True)
        self.restore_transcript_var = tk.BooleanVar(value=True)

        self.conda_executable_var = tk.StringVar(value="conda")
        self.conda_env_var = tk.StringVar(value="mfa")
        self.mfa_use_conda_var = tk.BooleanVar(value=True)
        self.mfa_command_var = tk.StringVar(value="mfa")
        self.mfa_mode_var = tk.StringVar(value="Auto (HF, если доступен)")
        self.mfa_model_var = tk.StringVar()
        self.mfa_dictionary_var = tk.StringVar()
        self.mfa_auto_language_var = tk.BooleanVar(value=True)
        self.mfa_language_var = tk.StringVar(value=profile_for_language("en").label)
        self.language_status_var = tk.StringVar(value="Язык ещё не определён")
        self.mfa_dialect_var = tk.StringVar()
        self.mfa_g2p_var = tk.BooleanVar(value=False)
        self.mfa_jobs_var = tk.StringVar(value="3")
        self.mfa_beam_preset_var = tk.StringVar(value=_DEFAULT_BEAM_PRESET)
        self.mfa_beam_var = tk.StringVar(value="100")
        self.mfa_retry_beam_var = tk.StringVar(value="400")
        self.mfa_auto_convert_var = tk.BooleanVar(value=False)
        self.mfa_validate_ignore_acoustics_var = tk.BooleanVar(value=False)
        self.mfa_model_kind_var = tk.StringVar(value="acoustic")
        self.mfa_model_name_var = tk.StringVar()
        self.mfa_force_download_var = tk.BooleanVar(value=False)
        self.mfa_status_var = tk.StringVar(value="MFA не проверен")
        self.text_preprocess_var = tk.StringVar(value="Без обработки")
        self.sudachi_mode_var = tk.StringVar(value="C")
        self.preprocess_strip_punct_var = tk.BooleanVar(value=False)

        self._mfa_installation = None
        self._installed_models = MFAInstalledModelCatalog()
        self._language_key_by_label = {
            label: profile_for_language(label).name for label in language_labels()
        }
        self._language_label_by_key = {
            key: label for label, key in self._language_key_by_label.items()
        }
        self._mfa_process: Optional[MFAProcess] = None
        self._mfa_cancel = threading.Event()
        self._mfa_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._mfa_running = False
        self._loaded_project_root: Optional[Path] = None
        self.palette: ThemePalette = get_theme(DEFAULT_THEME)
        self.advanced_mode = True

        self._build()
        # The catalogue query runs outside the Tk thread and is delayed until
        # after the first paint so Conda startup does not hold up window creation.
        self.after(1200, lambda: self.refresh_installed_models(silent=True))

    def _build(self) -> None:
        title = ttk.Frame(self)
        title.pack(fill="x")
        ttk.Label(title, text="MFA / TextGrid → karaoke ASS", style="Header.TLabel").pack(side="left")
        ttk.Label(title, text="Финальный pipeline: Conda/MFA + language preprocessing", style="Muted.TLabel").pack(side="right")

        runner = ttk.LabelFrame(self, text="Montreal Forced Aligner (Conda)", padding=8)
        self.runner_frame = runner
        runner.pack(fill="x", pady=(8, 6))
        self._path_row(runner, 0, "Медиа:", self.media_var, self._browse_media)
        self._path_row(runner, 1, "Текст:", self.transcript_var, self._browse_transcript)
        self._path_row(runner, 2, "Conda executable:", self.conda_executable_var, self._browse_conda)
        self._path_row(runner, 3, "MFA executable:", self.mfa_command_var, self._browse_mfa)

        conda_row = ttk.Frame(runner)
        self.conda_row = conda_row
        conda_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Checkbutton(conda_row, text="Запускать MFA через Conda", variable=self.mfa_use_conda_var, command=self._launcher_changed).pack(side="left")
        ttk.Label(conda_row, text="Окружение:").pack(side="left", padx=(16, 4))
        self.conda_env_combo = ttk.Combobox(conda_row, textvariable=self.conda_env_var, width=22)
        self.conda_env_combo.pack(side="left")
        self.conda_check_button = ttk.Button(conda_row, text="Найти окружения", command=self.check_conda)
        self.conda_check_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            conda_row,
            text="Автоязык и модели",
            variable=self.mfa_auto_language_var,
            command=self._auto_language_toggled,
        ).pack(side="left", padx=(16, 0))
        ttk.Label(conda_row, text="Язык:").pack(side="left", padx=(10, 4))
        self.language_combo = ttk.Combobox(
            conda_row,
            textvariable=self.mfa_language_var,
            values=language_labels(),
            state="readonly",
            width=22,
        )
        self.language_combo.pack(side="left")
        self.language_combo.bind("<<ComboboxSelected>>", self._language_selected)

        ttk.Label(runner, text="Режим:").grid(row=5, column=0, sticky="w", pady=(5, 2))
        ttk.Combobox(runner, textvariable=self.mfa_mode_var, values=tuple(_MODE_LABELS), state="readonly", width=29).grid(row=5, column=1, sticky="w", padx=(7, 6), pady=(5, 2))
        status = ttk.Label(runner, textvariable=self.mfa_status_var, style="Muted.TLabel")
        status.grid(row=5, column=2, sticky="w", padx=(6, 0), pady=(5, 2))

        model_row = ttk.Frame(runner)
        self.model_row = model_row
        model_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Label(model_row, text="Model / HF ID:").pack(side="left")
        self.mfa_model_combo = ttk.Combobox(model_row, textvariable=self.mfa_model_var, width=28)
        self.mfa_model_combo.pack(side="left", padx=(6, 12))
        self.mfa_model_combo.bind("<<ComboboxSelected>>", self._acoustic_model_selected)
        ttk.Label(model_row, text="Dictionary (validate/legacy/OOV):").pack(side="left")
        self.mfa_dictionary_combo = ttk.Combobox(model_row, textvariable=self.mfa_dictionary_var, width=28)
        self.mfa_dictionary_combo.pack(side="left", padx=(6, 0), fill="x", expand=True)
        ttk.Label(model_row, text="Поиск:").pack(side="left", padx=(12, 4))
        self.mfa_beam_preset_combo = ttk.Combobox(
            model_row,
            textvariable=self.mfa_beam_preset_var,
            values=tuple(_BEAM_PRESETS),
            state="readonly",
            width=31,
        )
        self.mfa_beam_preset_combo.pack(side="left")
        self.mfa_beam_preset_combo.bind("<<ComboboxSelected>>", self._beam_preset_selected)

        beam_manual = ttk.Frame(runner)
        self.beam_manual_row = beam_manual
        beam_manual.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Label(beam_manual, text="Точный поиск MFA:").pack(side="left")
        ttk.Label(beam_manual, text="Beam").pack(side="left", padx=(10, 4))
        beam_entry = ttk.Entry(beam_manual, textvariable=self.mfa_beam_var, width=8)
        beam_entry.pack(side="left")
        beam_entry.bind("<KeyRelease>", self._beam_value_edited)
        ttk.Label(beam_manual, text="Retry beam").pack(side="left", padx=(12, 4))
        retry_entry = ttk.Entry(beam_manual, textvariable=self.mfa_retry_beam_var, width=8)
        retry_entry.pack(side="left")
        retry_entry.bind("<KeyRelease>", self._beam_value_edited)
        ttk.Label(
            beam_manual,
            text="Большие значения медленнее, но устойчивее для плотной быстрой речи",
            style="Muted.TLabel",
        ).pack(side="left", padx=(12, 0))

        opt_row = ttk.Frame(runner)
        self.opt_row = opt_row
        opt_row.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        ttk.Label(opt_row, text="Dialect:").pack(side="left")
        ttk.Entry(opt_row, textvariable=self.mfa_dialect_var, width=20).pack(side="left", padx=(6, 12))
        ttk.Checkbutton(opt_row, text="Use G2P (HF)", variable=self.mfa_g2p_var).pack(side="left")
        ttk.Label(opt_row, text="Jobs:").pack(side="left", padx=(16, 4))
        ttk.Entry(opt_row, textvariable=self.mfa_jobs_var, width=5).pack(side="left")
        ttk.Checkbutton(opt_row, text="Validate без acoustics", variable=self.mfa_validate_ignore_acoustics_var).pack(side="left", padx=(16, 0))
        ttk.Checkbutton(opt_row, text="После MFA сразу создать ASS", variable=self.mfa_auto_convert_var).pack(side="left", padx=(16, 0))

        actions = ttk.Frame(runner)
        self.actions_frame = actions
        actions.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        self.mfa_check_button = ttk.Button(actions, text="Проверить MFA", command=self.check_mfa)
        self.mfa_check_button.pack(side="left")
        self.mfa_prepare_button = ttk.Button(actions, text="Подготовить corpus", command=self.prepare_corpus_only)
        self.mfa_prepare_button.pack(side="left", padx=(6, 0))
        self.mfa_validate_button = ttk.Button(actions, text="Validate", command=self.validate_corpus)
        self.mfa_validate_button.pack(side="left", padx=(6, 0))
        self.mfa_oov_button = ttk.Button(actions, text="OOV-отчёт", command=self.find_oovs)
        self.mfa_oov_button.pack(side="left", padx=(6, 0))
        self.mfa_run_button = ttk.Button(actions, text="Запустить MFA", command=self.run_mfa)
        self.mfa_run_button.pack(side="left", padx=(6, 0))
        self.mfa_cancel_button = ttk.Button(actions, text="Отмена", command=self.cancel_mfa, state="disabled")
        self.mfa_cancel_button.pack(side="left", padx=(6, 0))
        self._mfa_secondary_buttons = [self.mfa_check_button, self.mfa_prepare_button, self.mfa_validate_button, self.mfa_oov_button]

        model_tools = ttk.Frame(runner)
        self.model_tools_frame = model_tools
        model_tools.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        ttk.Label(model_tools, text="Модели:").pack(side="left")
        ttk.Combobox(model_tools, textvariable=self.mfa_model_kind_var, values=("acoustic", "dictionary", "g2p", "tokenizer"), state="readonly", width=12).pack(side="left", padx=(5, 5))
        ttk.Entry(model_tools, textvariable=self.mfa_model_name_var, width=28).pack(side="left")
        self.mfa_model_list_button = ttk.Button(model_tools, text="Установленные", command=lambda: self.model_action("list"))
        self.mfa_model_list_button.pack(side="left", padx=(6, 0))
        self.mfa_model_download_button = ttk.Button(model_tools, text="Скачать", command=lambda: self.model_action("download"))
        self.mfa_model_download_button.pack(side="left", padx=(6, 0))
        self.mfa_model_inspect_button = ttk.Button(model_tools, text="Inspect", command=lambda: self.model_action("inspect"))
        self.mfa_model_inspect_button.pack(side="left", padx=(6, 0))
        ttk.Checkbutton(model_tools, text="Force", variable=self.mfa_force_download_var).pack(side="left", padx=(8, 0))

        prep = ttk.Frame(runner)
        self.preprocess_frame = prep
        prep.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        ttk.Label(prep, text="Предобработка текста:").pack(side="left")
        ttk.Combobox(prep, textvariable=self.text_preprocess_var, values=tuple(_PREPROCESS_LABELS), state="readonly", width=20).pack(side="left", padx=(5, 8))
        ttk.Label(prep, text="Sudachi:").pack(side="left")
        ttk.Combobox(prep, textvariable=self.sudachi_mode_var, values=("A", "B", "C"), state="readonly", width=3).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(prep, text="Убрать пунктуацию", variable=self.preprocess_strip_punct_var).pack(side="left")
        ttk.Button(prep, text="Preview", command=self.preview_preprocessing).pack(side="left", padx=(8, 0))
        ttk.Button(prep, text="Проверить deps", command=self.check_preprocess_dependencies).pack(side="left", padx=(5, 0))
        ttk.Button(prep, text="Диагностика", command=self.run_diagnostics).pack(side="right")

        files = ttk.LabelFrame(self, text="Результат MFA / импорт TextGrid", padding=8)
        self.files_frame = files
        files.pack(fill="x", pady=(0, 6))
        self._path_row(files, 0, "TextGrid:", self.textgrid_var, self._browse_textgrid)
        self._path_row(files, 1, "Выходной ASS:", self.output_var, self._browse_output)

        opts = ttk.LabelFrame(self, text="TextGrid → ASS", padding=8)
        self.textgrid_options_frame = opts
        opts.pack(fill="x", pady=(0, 6))
        ttk.Label(opts, text="Words tier:").grid(row=0, column=0, sticky="w")
        ttk.Entry(opts, textvariable=self.word_tier_var, width=14).grid(row=0, column=1, sticky="w", padx=(5, 14))
        ttk.Label(opts, text="Phones tier:").grid(row=0, column=2, sticky="w")
        ttk.Entry(opts, textvariable=self.phone_tier_var, width=14).grid(row=0, column=3, sticky="w", padx=(5, 14))
        ttk.Checkbutton(opts, text="Привязывать границы к phone tier", variable=self.phone_boundaries_var).grid(row=0, column=4, sticky="w")

        ttk.Label(opts, text="Karaoke tag:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        ttk.Combobox(opts, textvariable=self.tag_var, values=tuple(_TAG_LABELS), state="readonly", width=19).grid(row=1, column=1, sticky="w", padx=(5, 14), pady=(7, 0))
        ttk.Label(opts, text="Макс. слов/строку:").grid(row=1, column=2, sticky="w", pady=(7, 0))
        ttk.Entry(opts, textvariable=self.max_words_var, width=7).grid(row=1, column=3, sticky="w", padx=(5, 14), pady=(7, 0))
        ttk.Label(opts, text="Макс. пауза, с:").grid(row=1, column=4, sticky="w", pady=(7, 0))
        ttk.Entry(opts, textvariable=self.max_gap_var, width=7).grid(row=1, column=5, sticky="w", padx=(5, 14), pady=(7, 0))
        ttk.Label(opts, text="Макс. строка, с:").grid(row=1, column=6, sticky="w", pady=(7, 0))
        ttk.Entry(opts, textvariable=self.max_line_var, width=7).grid(row=1, column=7, sticky="w", padx=(5, 0), pady=(7, 0))

        ttk.Label(opts, text="PlayRes:").grid(row=2, column=0, sticky="w", pady=(7, 0))
        res = ttk.Frame(opts)
        res.grid(row=2, column=1, sticky="w", padx=(5, 14), pady=(7, 0))
        ttk.Entry(res, textvariable=self.playres_x_var, width=6).pack(side="left")
        ttk.Label(res, text=" × ").pack(side="left")
        ttk.Entry(res, textvariable=self.playres_y_var, width=6).pack(side="left")
        ttk.Checkbutton(opts, text="Открыть созданный ASS в Karaoke", variable=self.open_after_var).grid(row=2, column=2, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(
            opts,
            text="Восстанавливать регистр и пунктуацию из TXT (≥90% совпадение)",
            variable=self.restore_transcript_var,
        ).grid(row=2, column=4, columnspan=4, sticky="w", padx=(5, 0), pady=(7, 0))

        buttons = ttk.Frame(self)
        self.convert_buttons_frame = buttons
        buttons.pack(fill="x", pady=(0, 6))
        ttk.Button(buttons, text="Проверить TextGrid", command=self.inspect_textgrid).pack(side="left")
        ttk.Button(buttons, text="Преобразовать в ASS", command=self.convert).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Очистить лог", command=lambda: self._write_report("")).pack(side="right")

        # Keep the log visible at the application's initial 1220x820 size even
        # when Advanced exposes the extra MFA controls.
        self.report = tk.Text(self, height=6, wrap="word", font=("TkFixedFont", 9), state="disabled")
        self.report.pack(fill="both", expand=True)
        apply_text_theme(self.report, self.palette, panel=True)

    def apply_theme(self, palette: ThemePalette) -> None:
        self.palette = palette
        if hasattr(self, "report"):
            apply_text_theme(self.report, palette, panel=True)

    def set_advanced_mode(self, advanced: bool) -> None:
        self.advanced_mode = bool(advanced)
        # Executable paths are useful for troubleshooting, but normally Conda env + model are enough.
        for row in (2, 3):
            for widget in self.runner_frame.grid_slaves(row=row):
                if advanced:
                    widget.grid()
                else:
                    widget.grid_remove()
        if advanced:
            self.beam_manual_row.grid()
            self.opt_row.grid()
            self.model_tools_frame.grid()
            self.textgrid_options_frame.pack(fill="x", pady=(0, 6), before=self.convert_buttons_frame)
            for button in self._mfa_secondary_buttons:
                if not button.winfo_manager():
                    button.pack(side="left", padx=(6, 0), before=self.mfa_run_button)
        else:
            self.beam_manual_row.grid_remove()
            self.opt_row.grid_remove()
            self.model_tools_frame.grid_remove()
            self.textgrid_options_frame.pack_forget()
            for button in self._mfa_secondary_buttons:
                button.pack_forget()

    def _beam_preset_selected(self, _event=None) -> None:
        values = _BEAM_PRESETS.get(self.mfa_beam_preset_var.get())
        if values is None:
            return
        beam, retry_beam = values
        self.mfa_beam_var.set(str(beam))
        self.mfa_retry_beam_var.set(str(retry_beam))

    def _beam_value_edited(self, _event=None) -> None:
        if self.advanced_mode:
            self.mfa_beam_preset_var.set(_CUSTOM_BEAM_PRESET)

    @staticmethod
    def _portable_state_path(raw: str, root: Path) -> str:
        if not raw.strip():
            return ""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            return raw
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except (OSError, ValueError):
            return str(path)

    @staticmethod
    def _resolved_state_path(raw: object, root: Path) -> str:
        value = str(raw or "")
        if not value:
            return ""
        path = Path(value)
        return str((root / path).resolve()) if not path.is_absolute() else str(path)

    def project_state(self, root: Path) -> dict:
        state: dict[str, object] = {}
        for name in self._PROJECT_STATE_VARS:
            value = getattr(self, name).get()
            if name in self._PROJECT_PATH_VARS:
                value = self._portable_state_path(str(value), root)
            state[name.removesuffix("_var")] = value
        return state

    def apply_project_state(self, state: object, root: Path) -> None:
        if not isinstance(state, dict):
            return
        for name in self._PROJECT_STATE_VARS:
            key = name.removesuffix("_var")
            if key not in state:
                continue
            value = state[key]
            if name in self._PROJECT_PATH_VARS:
                value = self._resolved_state_path(value, root)
            try:
                getattr(self, name).set(value)
            except (tk.TclError, TypeError, ValueError):
                continue
        self._launcher_changed()
        if self.mfa_auto_language_var.get():
            self.language_status_var.set("Автоязык и модели будут проверены перед запуском MFA")
        else:
            self.language_status_var.set("Ручной выбор языка и моделей")

    def _path_row(self, parent, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(7, 6), pady=3)
        ttk.Button(parent, text="…", width=3, command=command).grid(row=row, column=2, pady=3)
        parent.columnconfigure(1, weight=1)

    def _browse_media(self) -> None:
        path = filedialog.askopenfilename(title="Медиа для MFA", filetypes=(("Media", "*.wav *.flac *.mp3 *.m4a *.mp4 *.mkv *.webm *.mov"), ("Все файлы", "*.*")))
        if path:
            self.media_var.set(path)
            candidate = Path(path).with_suffix(".TextGrid")
            if candidate.exists():
                self.textgrid_var.set(str(candidate))
                self.output_var.set(str(self._default_output(candidate)))

    def _browse_conda(self) -> None:
        path = filedialog.askopenfilename(title="Conda executable", filetypes=(("Executable", "*.exe *.bat *.cmd"), ("Все файлы", "*.*")))
        if path:
            self.conda_executable_var.set(path)
            self._launcher_changed()

    def _launcher_changed(self) -> None:
        self._mfa_installation = None
        self.mfa_status_var.set("MFA не проверен")

    def _selected_language_key(self) -> str:
        value = self.mfa_language_var.get().strip()
        return self._language_key_by_label.get(value, profile_for_language(value).name)

    def _language_label(self, key: str) -> str:
        label = self._language_label_by_key.get(key)
        if label:
            return label
        return f"{key.replace('_', ' ').title()} (MFA)"

    def _apply_model_catalog(self, catalog: MFAInstalledModelCatalog) -> None:
        selected_key = self._selected_language_key()
        self._installed_models = catalog
        for key in catalog.language_keys():
            if key not in self._language_label_by_key:
                label = self._language_label(key)
                self._language_label_by_key[key] = label
                self._language_key_by_label[label] = key

        static_labels = list(language_labels())
        dynamic_labels = sorted(
            (label for key, label in self._language_label_by_key.items() if label not in static_labels),
            key=str.casefold,
        )
        labels = tuple(static_labels + dynamic_labels)
        self.language_combo.configure(values=labels)
        selected_label = self._language_label_by_key.get(selected_key)
        if selected_label:
            self.mfa_language_var.set(selected_label)
        self._refresh_model_choices(preserve=True)
        self._append_report(
            "Каталог MFA обновлён: "
            f"языков {len(catalog.language_keys())}, acoustic {len(catalog.acoustic)}, "
            f"dictionary {len(catalog.dictionary)}"
        )

    def _refresh_model_choices(self, *, preserve: bool) -> None:
        key = self._selected_language_key()
        profile = profile_for_language(key)
        acoustics = self._installed_models.for_language("acoustic", key)
        dictionaries = self._installed_models.for_language("dictionary", key)
        self.mfa_model_combo.configure(values=acoustics)
        self.mfa_dictionary_combo.configure(values=dictionaries)

        def keep_current(value: str, choices: tuple[str, ...]) -> bool:
            if not preserve or not value:
                return False
            if value in choices or not choices:
                return True
            inferred = model_language_key(value)
            # Preserve same-language catalogue variants and explicit custom
            # paths/HF IDs. A value clearly belonging to another language is
            # replaced when auto-detection or the language selector changes.
            return inferred == key or any(marker in value for marker in ("/", "\\", ":"))

        current_acoustic = self.mfa_model_var.get().strip()
        if not keep_current(current_acoustic, acoustics):
            current_acoustic = (
                profile.acoustic_model if profile.acoustic_model in acoustics
                else (acoustics[0] if acoustics else profile.acoustic_model)
            )
            self.mfa_model_var.set(current_acoustic)

        current_dictionary = self.mfa_dictionary_var.get().strip()
        if not keep_current(current_dictionary, dictionaries):
            current_dictionary = matching_model_variant(
                dictionaries,
                current_acoustic,
                preferred=profile.dictionary_model,
            )
            if not current_dictionary and profile.dictionary_model:
                current_dictionary = profile.dictionary_model
            self.mfa_dictionary_var.set(current_dictionary)

    def _language_selected(self, _event=None) -> None:
        self._refresh_model_choices(preserve=False)
        key = self._selected_language_key()
        acoustics = self._installed_models.for_language("acoustic", key)
        dictionaries = self._installed_models.for_language("dictionary", key)
        self.language_status_var.set(
            f"Выбран: {key} · acoustic {len(acoustics)}, dictionary {len(dictionaries)}"
        )

    def _acoustic_model_selected(self, _event=None) -> None:
        key = self._selected_language_key()
        dictionaries = self._installed_models.for_language("dictionary", key)
        profile = profile_for_language(key)
        selected = matching_model_variant(
            dictionaries,
            self.mfa_model_var.get().strip(),
            preferred=profile.dictionary_model,
        )
        if selected:
            self.mfa_dictionary_var.set(selected)
        self.language_status_var.set(
            f"Пара MFA: {self.mfa_model_var.get().strip()} + {self.mfa_dictionary_var.get().strip()}"
        )

    def _browse_mfa(self) -> None:
        path = filedialog.askopenfilename(title="MFA executable", filetypes=(("Executable", "*.exe *.bat *.cmd"), ("Все файлы", "*.*")))
        if path:
            self.mfa_command_var.set(path)
            self._launcher_changed()

    def _browse_textgrid(self) -> None:
        path = filedialog.askopenfilename(title="Открыть TextGrid", filetypes=(("Praat TextGrid", "*.TextGrid *.textgrid"), ("Все файлы", "*.*")))
        if not path:
            return
        self.textgrid_var.set(path)
        self.output_var.set(str(self._default_output(Path(path))))

    def _browse_transcript(self) -> None:
        path = filedialog.askopenfilename(title="Текст песни", filetypes=(("Текст", "*.txt *.lab"), ("Все файлы", "*.*")))
        if path:
            self.transcript_var.set(path)
            if self.mfa_auto_language_var.get():
                try:
                    self._resolve_language_profile(apply_models=True, strict=True)
                except Exception as exc:
                    messagebox.showerror("Автоопределение языка", str(exc), parent=self)

    def _auto_language_toggled(self) -> None:
        if not self.mfa_auto_language_var.get():
            self.language_status_var.set("Ручной выбор языка и моделей")
            return
        try:
            self._resolve_language_profile(apply_models=True, strict=False)
        except Exception as exc:
            self.language_status_var.set(str(exc))

    def _resolve_language_profile(self, *, apply_models: bool, strict: bool):
        if not self.mfa_auto_language_var.get():
            profile = profile_for_language(self._selected_language_key())
            self.language_status_var.set(f"Выбран вручную: {profile.name}")
            return profile
        raw_path = self.transcript_var.get().strip()
        path = Path(raw_path) if raw_path else None
        if path is None or not path.is_file():
            if strict:
                raise MFAError("Для автоопределения языка укажите существующий TXT/LAB")
            return profile_for_language(self._selected_language_key())
        previous_key = self._selected_language_key()
        profile = detect_language_profile(path.read_text(encoding="utf-8-sig"))
        self.mfa_language_var.set(profile.label)
        if apply_models:
            self._refresh_model_choices(preserve=previous_key == profile.name)
        model = self.mfa_model_var.get().strip()
        dictionary = self.mfa_dictionary_var.get().strip()
        if model and dictionary:
            self.language_status_var.set(
                f"Определён: {profile.name} · {dictionary} + {model}"
            )
        else:
            self.language_status_var.set(
                f"Определён: {profile.name} · готового MFA-профиля нет; для MFA выберите модели вручную"
            )
        return profile

    def _require_auto_mfa_defaults(self, profile) -> None:
        if (
            self.mfa_auto_language_var.get()
            and (not profile.acoustic_model or not profile.dictionary_model)
        ):
            raise MFAError(
                f"Язык {profile.name} распознан, но для него нет встроенной пары "
                "MFA acoustic + dictionary. Снимите «Автоязык и модели» и "
                "укажите совместимые пользовательские модели вручную."
            )

    def _browse_output(self) -> None:
        initial = self.output_var.get().strip()
        path = filedialog.asksaveasfilename(title="Сохранить karaoke ASS", defaultextension=".ass", initialfile=Path(initial).name if initial else "aligned.ass", filetypes=(("Advanced SubStation Alpha", "*.ass"),))
        if path:
            self.output_var.set(path)

    def _default_output(self, textgrid: Path) -> Path:
        if self.session.project_root is not None:
            return self.session.project_root / "subtitles" / f"{textgrid.stem}.ass"
        return textgrid.with_suffix(".ass")

    def refresh_project(self) -> None:
        root = self.session.project_root
        if root is None:
            return
        if self.session.media_path is not None:
            self.media_var.set(str(self.session.media_path))
        if self.session.project is not None and self.session.project.transcript:
            resolved = self.session.project.resolve(root, self.session.project.transcript)
            if resolved and resolved.exists():
                self.transcript_var.set(str(resolved))
        alignment_dir = root / "alignment"
        candidates = sorted(alignment_dir.glob("*.TextGrid")) + sorted(alignment_dir.glob("*.textgrid"))
        if candidates and (not self.textgrid_var.get().strip() or not Path(self.textgrid_var.get()).exists()):
            preferred = candidates[0]
            if self.session.media_path is not None:
                media_stem = self.session.media_path.stem.casefold()
                matching = [c for c in candidates if c.stem.casefold() == media_stem]
                if matching:
                    preferred = matching[0]
            self.textgrid_var.set(str(preferred))
            self.output_var.set(str(self._default_output(preferred)))
        if self._loaded_project_root != root and self.session.project is not None:
            self._loaded_project_root = root
            saved = self.session.project.metadata.get("mfa_runner", {}) if isinstance(self.session.project.metadata, dict) else {}
            raw_mfa = self.session.project.resolve_mfa_command(root)
            migrated = parse_conda_mfa_launcher(raw_mfa)
            if migrated is not None:
                conda_exe, env_name, mfa_exe = migrated
                self.conda_executable_var.set(conda_exe)
                self.conda_env_var.set(env_name)
                self.mfa_command_var.set(mfa_exe)
                self.mfa_use_conda_var.set(True)
            else:
                self.mfa_command_var.set(raw_mfa)
                self.conda_executable_var.set(self.session.project.resolve_conda_command(root))
            self.conda_env_var.set(self.session.project.mfa_conda_env or str(saved.get("conda_env", "mfa")))
            self.mfa_use_conda_var.set(bool(getattr(self.session.project, "mfa_use_conda", saved.get("use_conda", True))))
            reverse_modes = {v: k for k, v in _MODE_LABELS.items()}
            self.mfa_mode_var.set(reverse_modes.get(saved.get("mode", "auto"), "Auto (HF, если доступен)"))
            self.mfa_model_var.set(str(saved.get("model", "")))
            self.mfa_dictionary_var.set(str(saved.get("dictionary", "")))
            self.mfa_auto_language_var.set(bool(saved.get("auto_language_models", True)))
            saved_language = profile_for_language(str(saved.get("language", "en")))
            self.mfa_language_var.set(saved_language.label)
            self.mfa_dialect_var.set(str(saved.get("dialect", "")))
            self.mfa_g2p_var.set(bool(saved.get("use_g2p", False)))
            self.mfa_jobs_var.set(str(saved.get("num_jobs", 3) or 3))
            preset = str(saved.get("beam_preset", _DEFAULT_BEAM_PRESET))
            if preset not in _BEAM_PRESETS:
                preset = _CUSTOM_BEAM_PRESET
            preset_values = _BEAM_PRESETS.get(preset) or (100, 400)
            self.mfa_beam_preset_var.set(preset)
            self.mfa_beam_var.set(str(saved.get("beam", preset_values[0])))
            self.mfa_retry_beam_var.set(str(saved.get("retry_beam", preset_values[1])))
            self.mfa_validate_ignore_acoustics_var.set(bool(saved.get("validate_ignore_acoustics", False)))
            reverse_pre = {v: k for k, v in _PREPROCESS_LABELS.items()}
            self.text_preprocess_var.set(reverse_pre.get(str(saved.get("text_preprocess", "none")), "Без обработки"))
            self.sudachi_mode_var.set(str(saved.get("sudachi_mode", "C")).upper() if str(saved.get("sudachi_mode", "C")).upper() in {"A","B","C"} else "C")
            self.preprocess_strip_punct_var.set(bool(saved.get("strip_punctuation", False)))
            self.restore_transcript_var.set(bool(saved.get("restore_transcript", True)))
            self._launcher_changed()
            self._auto_language_toggled()

    def _append_report(self, text: str) -> None:
        self.report.configure(state="normal")
        self.report.insert("end", text + ("\n" if not text.endswith("\n") else ""))
        self.report.see("end")
        self.report.configure(state="disabled")

    def _write_report(self, text: str) -> None:
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        self.report.configure(state="disabled")

    def _runner_settings(self) -> MFACommandSettings:
        mode = _MODE_LABELS[self.mfa_mode_var.get()]
        raw_jobs = self.mfa_jobs_var.get().strip()
        jobs = None
        if raw_jobs:
            try:
                jobs = int(raw_jobs)
            except ValueError as exc:
                raise MFAError("Jobs должен быть целым числом") from exc
            if jobs < 1:
                raise MFAError("Jobs должен быть >= 1")
        try:
            beam = int(self.mfa_beam_var.get().strip())
            retry_beam = int(self.mfa_retry_beam_var.get().strip())
        except ValueError as exc:
            raise MFAError("Beam и Retry beam должны быть целыми числами") from exc
        if beam < 1:
            raise MFAError("Beam должен быть >= 1")
        if retry_beam <= beam:
            raise MFAError("Retry beam должен быть больше Beam")
        return MFACommandSettings(
            executable=self.mfa_command_var.get().strip() or "mfa",
            mode=mode,
            model=self.mfa_model_var.get().strip(),
            dictionary=self.mfa_dictionary_var.get().strip(),
            dialect=self.mfa_dialect_var.get().strip(),
            use_g2p=self.mfa_g2p_var.get(),
            num_jobs=jobs,
            beam=beam,
            retry_beam=retry_beam,
            single_speaker=True,
            clean_textgrids=True,
        )

    def _save_runner_settings(self, settings: MFACommandSettings) -> None:
        if self.session.project is None or self.session.project_root is None:
            return
        raw_mfa = self.mfa_command_var.get().strip() or "mfa"
        mfa_candidate = Path(raw_mfa.strip('"'))
        if mfa_candidate.exists():
            try:
                self.session.project.mfa = str(mfa_candidate.resolve().relative_to(self.session.project_root))
            except ValueError:
                self.session.project.mfa = str(mfa_candidate.resolve())
        else:
            self.session.project.mfa = raw_mfa
        raw_conda = self.conda_executable_var.get().strip() or "conda"
        conda_candidate = Path(raw_conda.strip('"'))
        if conda_candidate.exists():
            try:
                self.session.project.conda_executable = str(conda_candidate.resolve().relative_to(self.session.project_root))
            except ValueError:
                self.session.project.conda_executable = str(conda_candidate.resolve())
        else:
            self.session.project.conda_executable = raw_conda
        self.session.project.mfa_conda_env = self.conda_env_var.get().strip() or "mfa"
        self.session.project.mfa_use_conda = bool(self.mfa_use_conda_var.get())
        def portable(raw: str):
            if not raw.strip():
                return None
            path = Path(raw).resolve()
            try:
                return str(path.relative_to(self.session.project_root))
            except ValueError:
                return str(path)
        self.session.project.media = portable(self.media_var.get()) or self.session.project.media
        self.session.project.transcript = portable(self.transcript_var.get()) or self.session.project.transcript
        self.session.project.metadata.setdefault("mfa_runner", {})
        self.session.project.metadata["mfa_runner"] = {
            "mode": settings.mode,
            "model": settings.model,
            "dictionary": settings.dictionary,
            "auto_language_models": bool(self.mfa_auto_language_var.get()),
            "language": profile_for_language(self._selected_language_key()).code,
            "dialect": settings.dialect,
            "use_g2p": settings.use_g2p,
            "num_jobs": settings.num_jobs,
            "beam_preset": self.mfa_beam_preset_var.get(),
            "beam": settings.beam,
            "retry_beam": settings.retry_beam,
            "use_conda": bool(self.mfa_use_conda_var.get()),
            "conda_env": self.conda_env_var.get().strip() or "mfa",
            "validate_ignore_acoustics": bool(self.mfa_validate_ignore_acoustics_var.get()),
            "text_preprocess": _PREPROCESS_LABELS.get(self.text_preprocess_var.get(), "none"),
            "sudachi_mode": self.sudachi_mode_var.get().strip().upper() or "C",
            "strip_punctuation": bool(self.preprocess_strip_punct_var.get()),
            "restore_transcript": bool(self.restore_transcript_var.get()),
        }
        save_project(self.session.project_root, self.session.project)

    def _current_mfa_command(self):
        mfa = self.mfa_command_var.get().strip() or "mfa"
        if not self.mfa_use_conda_var.get():
            return mfa
        return build_conda_mfa_prefix(
            self.conda_executable_var.get().strip() or "conda",
            self.conda_env_var.get().strip(),
            mfa,
        )

    def _set_running(self, running: bool) -> None:
        self._mfa_running = running
        state = "disabled" if running else "normal"
        for button in (
            self.conda_check_button, self.mfa_check_button, self.mfa_prepare_button,
            self.mfa_validate_button, self.mfa_oov_button, self.mfa_run_button,
            self.mfa_model_list_button, self.mfa_model_download_button, self.mfa_model_inspect_button,
        ):
            button.configure(state=state)
        self.mfa_cancel_button.configure(state="normal" if running else "disabled")

    def _start_worker(self, target, *, title: str = "MFA / операция") -> None:
        if self._mfa_running:
            return
        self._mfa_cancel.clear()
        self._set_running(True)
        self._active_task = self.task_center.start("MFA", title, stage="Запуск", progress=0) if self.task_center else None
        threading.Thread(target=target, daemon=True).start()
        self.after(60, self._poll_mfa_queue)

    def _update_task_from_status(self, text: str) -> None:
        task = self._active_task
        if task is None:
            return
        low = text.casefold()
        pct = None
        if "подготов" in low and "corpus" in low:
            pct = 10.0
        elif "alignment" in low and ("выполня" in low or "запуск" in low):
            pct = 20.0
        elif "textgrid" in low:
            pct = 95.0
        elif "заверш" in low or "готов" in low:
            pct = 100.0
        task.update(pct, text)
        task.log(text, "STAGE")

    def _update_task_from_log(self, line: str) -> None:
        task = self._active_task
        if task is None:
            return
        task.log(line)
        match = re.search(r"(?<!\d)(\d{1,3}(?:[.,]\d+)?)\s*%", line)
        if match:
            try:
                raw = max(0.0, min(100.0, float(match.group(1).replace(",", "."))))
                # Reserve the first 20% for corpus/model setup and the last 5%
                # for TextGrid adoption. This keeps MFA's internal 0..100
                # meaningful while still reflecting the whole GUI task.
                current = self.task_center.task(task.id) if self.task_center else None
                stage = current.title if current is not None else "MFA"
                task.update(20.0 + raw * 0.75, stage)
            except ValueError:
                pass
            return
        low = line.casefold()
        coarse = (
            (("setting up corpus", "loading corpus", "dictionary"), 22.0, "MFA: подготовка corpus"),
            (("generating pronunciations", "pronunciation"), 30.0, "MFA: произношения"),
            (("compiling training graphs", "compile", "training graph"), 42.0, "MFA: графы"),
            (("acoustic alignment", "aligning", "alignment"), 58.0, "MFA: выравнивание"),
            (("transcription", "phone confidence"), 76.0, "MFA: постобработка"),
            (("exporting textgrid", "writing textgrid", "textgrid"), 92.0, "MFA: экспорт TextGrid"),
        )
        current = self.task_center.task(task.id) if self.task_center else None
        current_pct = current.progress if current and current.progress is not None else 0.0
        for needles, pct, stage in coarse:
            if any(word in low for word in needles) and pct > current_pct:
                task.update(pct, stage)
                break

    def _poll_mfa_queue(self) -> None:
        keep_polling = self._mfa_running
        try:
            while True:
                kind, payload = self._mfa_queue.get_nowait()
                if kind == "log":
                    self._append_report(str(payload))
                    self._update_task_from_log(str(payload))
                elif kind == "status":
                    self.set_status(str(payload))
                    self._update_task_from_status(str(payload))
                elif kind == "detected":
                    self._mfa_installation = payload
                    commands = ", ".join(sorted(payload.commands))
                    self.mfa_status_var.set(f"{payload.version} · {commands or 'команды не распознаны'}")
                elif kind == "conda_envs":
                    envs = tuple(payload)
                    names = [env.name for env in envs]
                    self.conda_env_combo.configure(values=names)
                    if names and self.conda_env_var.get().strip() not in names:
                        active = next((env.name for env in envs if env.active), None)
                        self.conda_env_var.set(active or names[0])
                    self._append_report("Conda environments: " + (", ".join(names) if names else "не найдены"))
                elif kind == "model_catalog":
                    self._apply_model_catalog(payload)
                elif kind == "model_catalog_error":
                    self._append_report(f"[warning] Каталог моделей MFA не обновлён: {payload}")
                elif kind == "textgrid":
                    path = Path(payload)
                    self.textgrid_var.set(str(path))
                    self.output_var.set(str(self._default_output(path)))
                elif kind == "auto_convert":
                    self.convert()
                elif kind == "error":
                    if self._active_task is not None:
                        self._active_task.fail(str(payload))
                    messagebox.showerror("MFA", str(payload), parent=self)
                elif kind == "done":
                    if self._active_task is not None:
                        snap = self.task_center.task(self._active_task.id) if self.task_center else None
                        if snap is not None and snap.status == "running":
                            if self._mfa_cancel.is_set():
                                self._active_task.cancel("Операция MFA отменена")
                            else:
                                self._active_task.done("Операция MFA завершена")
                    self._active_task = None
                    self._set_running(False)
                    keep_polling = False
        except queue.Empty:
            pass
        if keep_polling:
            self.after(60, self._poll_mfa_queue)

    def _detect(self, command_value):
        inst = detect_mfa_installation(command_value)
        self._mfa_queue.put(("detected", inst))
        return inst

    def check_conda(self) -> None:
        conda = self.conda_executable_var.get().strip() or "conda"
        def worker():
            try:
                envs = list_conda_environments(conda)
                self._mfa_queue.put(("conda_envs", envs))
                wanted = self.conda_env_var.get().strip()
                if wanted and envs and wanted not in {e.name for e in envs}:
                    self._mfa_queue.put(("log", f"[warning] Conda-окружение {wanted!r} не найдено в списке"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="Проверка Conda")

    def check_mfa(self) -> None:
        try:
            command_value = self._current_mfa_command()
        except Exception as exc:
            messagebox.showerror("MFA", str(exc), parent=self)
            return
        def worker():
            try:
                inst = self._detect(command_value)
                self._mfa_queue.put(("log", f"MFA: {inst.version}"))
                self._mfa_queue.put(("log", "Launcher: " + command_for_display(inst.command_prefix)))
                self._mfa_queue.put(("log", "Команды: " + ", ".join(sorted(inst.commands))))
                try:
                    catalog = list_installed_mfa_models(inst)
                    self._mfa_queue.put(("model_catalog", catalog))
                except Exception as exc:
                    self._mfa_queue.put(("model_catalog_error", exc))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="Проверка MFA")

    def refresh_installed_models(self, *, silent: bool = False) -> None:
        if self._mfa_running:
            return
        try:
            command_value = self._current_mfa_command()
            cached_installation = self._mfa_installation
        except Exception as exc:
            if not silent:
                messagebox.showerror("MFA models", str(exc), parent=self)
            return

        def worker():
            try:
                # A catalogue read only needs `mfa model list`; do not run the
                # much slower version/help probes during automatic startup.
                catalog = list_installed_mfa_models(cached_installation or command_value)
                self._mfa_queue.put(("model_catalog", catalog))
                self._mfa_queue.put(("status", "Список языков и моделей MFA обновлён"))
            except Exception as exc:
                self._mfa_queue.put((("model_catalog_error" if silent else "error"), exc))
            finally:
                self._mfa_queue.put(("done", None))

        self._start_worker(worker, title="Каталог моделей MFA")

    def _source_paths(self, media_raw: Optional[str] = None, transcript_raw: Optional[str] = None) -> tuple[Path, Path, Path]:
        media_value = media_raw if media_raw is not None else self.media_var.get().strip()
        transcript_value = transcript_raw if transcript_raw is not None else self.transcript_var.get().strip()
        if not media_value:
            raise MFAError("Укажите media-файл")
        if not transcript_value:
            raise MFAError("Укажите текст")
        media = Path(media_value)
        transcript = Path(transcript_value)
        if not media.is_file():
            raise MFAError("Укажите существующий media-файл")
        if not transcript.is_file():
            raise MFAError("Укажите существующий текст")
        if self.session.project_root is not None:
            workspace = self.session.project_root / "alignment" / "mfa"
        else:
            workspace = media.parent / ".karaoke_mfa"
        return media, transcript, workspace

    def _preprocess_settings(self) -> TextPreprocessSettings:
        return TextPreprocessSettings(
            mode=_PREPROCESS_LABELS.get(self.text_preprocess_var.get(), "none"),
            sudachi_split_mode=self.sudachi_mode_var.get().strip().upper() or "C",
            strip_punctuation=bool(self.preprocess_strip_punct_var.get()),
        )

    def _conda_python_prefix(self):
        if not self.mfa_use_conda_var.get():
            return ()
        return build_conda_run_prefix(
            self.conda_executable_var.get().strip() or "conda",
            self.conda_env_var.get().strip(),
            no_capture_output=False,
        )

    def _prepare_transcript(self, transcript: Path):
        raw = transcript.read_text(encoding="utf-8-sig")
        settings = self._preprocess_settings()
        if settings.mode == "japanese_sudachi":
            prefix = self._conda_python_prefix()
            if not prefix:
                raise TextPreprocessError("Japanese Sudachi в этом проекте запускается через выбранное Conda-окружение")
            report = tokenize_japanese_sudachi(
                raw, prefix, split_mode=settings.sudachi_split_mode,
                unicode_form=settings.unicode_form,
                strip_punctuation=settings.strip_punctuation,
            )
        else:
            report = prepare_text_local(raw, settings)
        if not report.text.strip():
            raise TextPreprocessError("После предобработки текст пуст")
        return report

    def _prepare_workspace(self, media: Path, transcript: Path, workspace_root: Path, ffmpeg: Path):
        self._mfa_queue.put(("status", "Подготовка corpus…"))
        report = self._prepare_transcript(transcript)
        task = self._active_task
        task_snap = self.task_center.task(task.id) if (task is not None and self.task_center is not None) else None
        full_progress = bool(task_snap and task_snap.title == "Подготовка MFA corpus")
        def corpus_progress(value, stage):
            if task is None:
                return
            if value is None:
                task.update(None, stage)
            else:
                mapped = value if full_progress else min(15.0, float(value) * 0.15)
                task.update(mapped, stage)
        ws = prepare_mfa_workspace(
            media, transcript, workspace_root, ffmpeg=ffmpeg, clean=True,
            transcript_text=report.text,
            progress=corpus_progress,
            log=(lambda line: task.log(line) if task is not None else None),
        )
        prepared_copy = ws.root / "prepared_transcript.txt"
        prepared_copy.write_text(report.text + "\n", encoding="utf-8")
        self._mfa_queue.put(("log", f"Corpus: {ws.corpus_directory}"))
        self._mfa_queue.put(("log", f"WAV: {ws.audio_path.name} · transcript: {ws.transcript_path.name}"))
        self._mfa_queue.put(("log", f"Text preprocessing: {report.mode}; tokens={report.token_count}; prepared={prepared_copy}"))

        # Build composite dictionary if multilingual tags, foreign words or custom pronunciations exist
        raw_text = transcript.read_text(encoding="utf-8-sig")
        has_lang_tags = bool(
            re.search(r"\[/?(?:ru|en|ja|de|es|fr|it|pl|pt|tr)\]", raw_text, re.IGNORECASE)
            or re.search(r"\{[a-z]{2}:[^}]*\}", raw_text, re.IGNORECASE)
        )
        has_latin = bool(re.search(r"[a-zA-Z]", report.text))
        has_cyrillic = bool(re.search(r"[\u0400-\u04ff]", report.text))
        proj_root = self.session.project_root
        custom_pron_path = proj_root / "project_pronunciations.txt" if proj_root else None
        if not custom_pron_path or not custom_pron_path.is_file():
            candidate = transcript.parent / "project_pronunciations.txt"
            if candidate.is_file():
                custom_pron_path = candidate

        if has_lang_tags or (has_latin and has_cyrillic) or (custom_pron_path and custom_pron_path.is_file()):
            from karaoke_core.multilang import build_composite_dictionary
            base_models = Path.home() / "Documents" / "MFA" / "pretrained_models"
            acoustic_model = self.mfa_model_var.get().strip() or "russian_mfa"
            dict_model = self.mfa_dictionary_var.get().strip() or "russian_mfa"

            acoustic_path = base_models / "acoustic" / f"{acoustic_model}.zip"
            primary_dict = base_models / "dictionary" / f"{dict_model}.dict"
            secondary_dict = base_models / "dictionary" / "english_mfa.dict"

            composite_dict_path = ws.root / "composite.dict"
            build_composite_dictionary(
                report.text.split(),
                composite_dict_path,
                acoustic_model_path=acoustic_path if acoustic_path.is_file() else None,
                primary_dict_path=primary_dict if primary_dict.is_file() else None,
                secondary_dict_path=secondary_dict if secondary_dict.is_file() else None,
                custom_pronunciations_path=custom_pron_path if (custom_pron_path and custom_pron_path.is_file()) else None,
            )
            ws = replace(ws, composite_dict_path=composite_dict_path)
            self._mfa_queue.put(("log", f"Composite dictionary built: {composite_dict_path}"))
        return ws

    def preview_preprocessing(self) -> None:
        try:
            raw_path = Path(self.transcript_var.get().strip())
            if not raw_path.is_file():
                raise TextPreprocessError("Укажите существующий текстовый файл")
            report = self._prepare_transcript(raw_path)
            raw = raw_path.read_text(encoding="utf-8-sig").strip()
            preview_raw = raw[:1800] + ("…" if len(raw) > 1800 else "")
            preview_prepared = report.text[:1800] + ("…" if len(report.text) > 1800 else "")
            self._write_report(
                f"Предобработка: {report.mode}\n"
                f"Символы: {report.original_characters} → {report.prepared_characters}; tokens={report.token_count}\n\n"
                f"[ORIGINAL]\n{preview_raw}\n\n[PREPARED FOR MFA]\n{preview_prepared}"
            )
            self.set_status("Preview предобработки готов")
        except Exception as exc:
            messagebox.showerror("Предобработка текста", str(exc), parent=self)

    def check_preprocess_dependencies(self) -> None:
        try:
            prefix = self._conda_python_prefix()
            if not prefix:
                raise TextPreprocessError("Включите запуск через Conda")
        except Exception as exc:
            messagebox.showerror("Conda", str(exc), parent=self)
            return
        def worker():
            try:
                packages = probe_python_packages(prefix, ("sudachipy", "sudachidict_core", "numpy"))
                for name, present in packages.items():
                    self._mfa_queue.put(("log", f"{name}: {'OK' if present else 'НЕ УСТАНОВЛЕН'}"))
                self._mfa_queue.put(("status", "Проверка Python-зависимостей завершена"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="Проверка Python-зависимостей")

    def run_diagnostics(self) -> None:
        root = self.session.project_root
        if root is None:
            messagebox.showinfo("Диагностика", "Откройте проект, чтобы проверить project.json и Conda/MFA.", parent=self)
            return
        def worker():
            try:
                report = run_health_checks(root)
                self._mfa_queue.put(("log", "\n=== Диагностика ===\n" + report.format_text()))
                self._mfa_queue.put(("status", "Диагностика завершена"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="Диагностика проекта")

    def prepare_corpus_only(self) -> None:
        try:
            media, transcript, workspace_root = self._source_paths()
            ffmpeg = self.session.resolved_ffmpeg()
            if ffmpeg is None:
                raise MFAError("FFmpeg не найден; он нужен для подготовки mono PCM WAV для MFA")
        except Exception as exc:
            messagebox.showerror("MFA", str(exc), parent=self)
            return
        def worker():
            try:
                self._prepare_workspace(media, transcript, workspace_root, ffmpeg)
                self._mfa_queue.put(("status", "MFA corpus подготовлен"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="Подготовка MFA corpus")

    def run_mfa(self) -> None:
        try:
            profile = self._resolve_language_profile(apply_models=True, strict=True)
            self._require_auto_mfa_defaults(profile)
            settings = self._runner_settings()
            self._save_runner_settings(settings)
            command_value = self._current_mfa_command()
            media, transcript, workspace_root = self._source_paths()
            ffmpeg = self.session.resolved_ffmpeg()
            if ffmpeg is None:
                raise MFAError("FFmpeg не найден; он нужен для подготовки mono PCM WAV для MFA")
            auto_convert = self.mfa_auto_convert_var.get()
            cached_installation = self._mfa_installation
            project_root = self.session.project_root
        except Exception as exc:
            messagebox.showerror("MFA", str(exc), parent=self)
            return
        # A failed run must not leave an unrelated TextGrid from the previous
        # song looking like the current result. It caused the misleading 1.4%
        # text-restoration error after this alignment had actually failed.
        self.textgrid_var.set("")
        def worker():
            try:
                self._mfa_queue.put(("status", "Проверка MFA через Conda…"))
                self._mfa_queue.put((
                    "log",
                    f"Language: {profile.name}; dictionary={settings.dictionary}; acoustic={settings.model}; "
                    f"beam={settings.beam}; retry_beam={settings.retry_beam}",
                ))
                inst = cached_installation or self._detect(command_value)
                if self._mfa_cancel.is_set():
                    return
                ws = self._prepare_workspace(media, transcript, workspace_root, ffmpeg)
                if self._mfa_cancel.is_set():
                    return
                comp_dict = getattr(ws, "composite_dict_path", None)
                active_settings = settings
                if comp_dict is not None and Path(comp_dict).is_file():
                    active_settings = replace(settings, dictionary=str(comp_dict))
                command = build_runtime_align_command(ws, active_settings, inst)
                self._mfa_queue.put(("log", "\n> " + command_for_display(command)))
                self._mfa_queue.put(("status", "MFA alignment выполняется…"))
                proc = MFAProcess(command, cwd=ws.root, on_line=lambda line: self._mfa_queue.put(("log", line)))
                self._mfa_process = proc
                rc = proc.run()
                self._mfa_process = None
                if proc.cancelled or self._mfa_cancel.is_set():
                    self._mfa_queue.put(("status", "MFA отменён"))
                    self._mfa_queue.put(("log", "[cancelled]"))
                    return
                if rc != 0:
                    raise MFAError(
                        f"MFA завершился с кодом {rc}; TextGrid не создан. "
                        "Попробуйте более широкий preset Beam и проверьте OOV в логе."
                    )
                generated = find_textgrid(ws.output_directory, ws.stem)
                if generated is None:
                    raise MFAError("MFA завершился успешно, но TextGrid в output не найден")
                if project_root is not None:
                    final = project_root / "alignment" / f"{ws.stem}.TextGrid"
                    generated = adopt_textgrid(generated, final)
                self._mfa_queue.put(("textgrid", generated))
                self._mfa_queue.put(("log", f"TextGrid: {generated}"))
                self._mfa_queue.put(("status", "MFA завершён"))
                if auto_convert:
                    self._mfa_queue.put(("auto_convert", None))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
                self._mfa_queue.put(("status", "Ошибка MFA"))
            finally:
                self._mfa_process = None
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title="MFA alignment")

    def cancel_mfa(self) -> None:
        if not self._mfa_running:
            return
        self._mfa_cancel.set()
        proc = self._mfa_process
        if proc is not None:
            threading.Thread(target=proc.cancel, daemon=True).start()
        self.set_status("Отмена MFA…")
        if self._active_task is not None:
            self._active_task.update(None, "Отмена процесса…")

    def _run_preflight(self, kind: str) -> None:
        try:
            profile = self._resolve_language_profile(apply_models=True, strict=True)
            self._require_auto_mfa_defaults(profile)
            settings = self._runner_settings()
            self._save_runner_settings(settings)
            command_value = self._current_mfa_command()
            media, transcript, workspace_root = self._source_paths()
            ffmpeg = self.session.resolved_ffmpeg()
            if ffmpeg is None:
                raise MFAError("FFmpeg не найден; он нужен для подготовки corpus")
            cached_installation = self._mfa_installation
        except Exception as exc:
            messagebox.showerror("MFA", str(exc), parent=self)
            return

        def worker():
            try:
                self._mfa_queue.put((
                    "log",
                    f"Language: {profile.name}; dictionary={settings.dictionary}; acoustic={settings.model}; "
                    f"beam={settings.beam}; retry_beam={settings.retry_beam}",
                ))
                inst = cached_installation or self._detect(command_value)
                ws = self._prepare_workspace(media, transcript, workspace_root, ffmpeg)
                comp_dict = getattr(ws, "composite_dict_path", None)
                active_settings = settings
                if comp_dict is not None and Path(comp_dict).is_file():
                    active_settings = replace(settings, dictionary=str(comp_dict))
                if kind == "validate":
                    out = ws.root / "validation"
                    command = build_validate_command(
                        ws, active_settings, inst, out,
                        ignore_acoustics=self.mfa_validate_ignore_acoustics_var.get(),
                    )
                    label = "MFA validate"
                else:
                    out = ws.root / "oov"
                    command = build_find_oovs_command(ws, active_settings, inst, out)
                    label = "MFA find_oovs"
                self._mfa_queue.put(("log", "\n> " + command_for_display(command)))
                self._mfa_queue.put(("status", label + " выполняется…"))
                proc = MFAProcess(command, cwd=ws.root, on_line=lambda line: self._mfa_queue.put(("log", line)))
                self._mfa_process = proc
                rc = proc.run()
                self._mfa_process = None
                if proc.cancelled or self._mfa_cancel.is_set():
                    self._mfa_queue.put(("status", label + " отменён"))
                    return
                artifacts = find_oov_artifacts(out)
                if artifacts:
                    self._mfa_queue.put(("log", "OOV artifacts: " + ", ".join(str(p) for p in artifacts)))
                    self._mfa_queue.put(("log", "\n" + read_oov_summary(out)))
                if rc != 0:
                    raise MFAError(
                        f"{label} завершился с кодом {rc}. OOV-отчёт выведен в лог; "
                        "для плотной речи попробуйте более широкий preset Beam."
                    )
                self._mfa_queue.put(("log", f"\n{label}: OK"))
                if not artifacts and kind == "oov":
                    self._mfa_queue.put(("log", "OOV-файлы не найдены; проверьте вывод MFA выше."))
                self._mfa_queue.put(("status", label + " завершён"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
                self._mfa_queue.put(("status", "Ошибка MFA preflight"))
            finally:
                self._mfa_process = None
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title=f"MFA {kind}")

    def validate_corpus(self) -> None:
        self._run_preflight("validate")

    def find_oovs(self) -> None:
        self._run_preflight("oov")

    def model_action(self, action: str) -> None:
        try:
            command_value = self._current_mfa_command()
            kind = self.mfa_model_kind_var.get().strip() or "acoustic"
            name = self.mfa_model_name_var.get().strip()
            cached_installation = self._mfa_installation
        except Exception as exc:
            messagebox.showerror("MFA models", str(exc), parent=self)
            return
        def worker():
            try:
                # Model management does not need the costly version/help
                # probes; the command itself reports unsupported MFA builds.
                inst = cached_installation or command_value
                cmd = build_model_command(inst, action, kind, name, force=self.mfa_force_download_var.get())
                self._mfa_queue.put(("log", "\n> " + command_for_display(cmd)))
                self._mfa_queue.put(("status", f"MFA model {action}…"))
                proc = MFAProcess(cmd, on_line=lambda line: self._mfa_queue.put(("log", line)))
                self._mfa_process = proc
                rc = proc.run()
                self._mfa_process = None
                if proc.cancelled or self._mfa_cancel.is_set():
                    self._mfa_queue.put(("status", "Операция с моделью отменена"))
                    return
                if rc != 0:
                    raise MFAError(f"mfa model {action} завершился с кодом {rc}")
                if action in {"download", "list"}:
                    try:
                        catalog = list_installed_mfa_models(inst)
                        self._mfa_queue.put(("model_catalog", catalog))
                    except Exception as exc:
                        self._mfa_queue.put(("model_catalog_error", exc))
                self._mfa_queue.put(("status", f"MFA model {action}: готово"))
            except Exception as exc:
                self._mfa_queue.put(("error", exc))
            finally:
                self._mfa_process = None
                self._mfa_queue.put(("done", None))
        self._start_worker(worker, title=f"MFA model {action}")

    def inspect_textgrid(self) -> None:
        try:
            source = Path(self.textgrid_var.get().strip())
            grid = load_textgrid(source)
        except Exception as exc:
            messagebox.showerror("TextGrid", str(exc), parent=self)
            return
        rows = [f"Диапазон: {grid.xmin:.3f}–{grid.xmax:.3f} с", "", "Tiers:"]
        for tier in grid.tiers:
            nonempty = sum(1 for i in tier.intervals if i.text.strip())
            rows.append(f"  {tier.name!r}: {len(tier.intervals)} intervals, {nonempty} non-empty")
        self._write_report("\n".join(rows))
        self.set_status(f"TextGrid прочитан: {len(grid.tiers)} tiers")

    def _settings(self, language: str | None = None) -> AlignmentConversionSettings:
        try:
            max_words = int(self.max_words_var.get())
            max_gap = float(self.max_gap_var.get().replace(",", "."))
            max_line = float(self.max_line_var.get().replace(",", "."))
            rx = int(self.playres_x_var.get())
            ry = int(self.playres_y_var.get())
        except ValueError as exc:
            raise AlignmentError("Числовые настройки содержат некорректное значение") from exc
        if max_gap < 0 or max_line <= 0 or rx <= 0 or ry <= 0:
            raise AlignmentError("Пауза должна быть ≥0, длительность строки и PlayRes — >0")
        return AlignmentConversionSettings(
            word_tier=self.word_tier_var.get().strip() or "words",
            phone_tier=self.phone_tier_var.get().strip() or "phones",
            karaoke_tag=_TAG_LABELS[self.tag_var.get()],
            max_words_per_line=max_words,
            max_gap_seconds=max_gap,
            max_line_seconds=max_line,
            play_res_x=rx,
            play_res_y=ry,
            use_phone_boundaries=self.phone_boundaries_var.get(),
            syllabify=True,
            language=language or profile_for_language(self._selected_language_key()).code,
            flatten_dialogues=True,
            restore_transcript_text=bool(self.restore_transcript_var.get()),
        )

    def convert(self) -> None:
        task = self.task_center.start("TextGrid", "TextGrid → ASS", stage="Проверка входных файлов", progress=5) if self.task_center else None
        try:
            textgrid = Path(self.textgrid_var.get().strip())
            if not textgrid.exists():
                raise AlignmentError("Укажите существующий TextGrid")
            output_raw = self.output_var.get().strip()
            output = Path(output_raw) if output_raw else self._default_output(textgrid)
            self.output_var.set(str(output))
            transcript_raw = self.transcript_var.get().strip()
            transcript: Optional[Path] = Path(transcript_raw) if transcript_raw else None
            restore_text = bool(self.restore_transcript_var.get())
            if restore_text:
                if transcript is None:
                    raise AlignmentError(
                        "Укажите исходный TXT: он обязателен для восстановления пунктуации, регистра и переносов "
                        "(или снимите галочку 'Восстанавливать регистр и пунктуацию из TXT')"
                    )
                if not transcript.is_file():
                    raise AlignmentError("Указанный исходный TXT не найден")
            else:
                if transcript is not None and not transcript.is_file():
                    transcript = None
            profile = self._resolve_language_profile(
                apply_models=self.mfa_auto_language_var.get(),
                strict=False,
            )
            if task:
                task.log(f"TextGrid: {textgrid}")
                task.update(30, "Чтение tiers и построение timing")
            report = convert_textgrid_to_ass(
                textgrid,
                output,
                transcript_path=transcript,
                settings=self._settings(profile.code),
            )
            if task:
                task.update(90, "Сохранение ASS")
        except Exception as exc:
            if task:
                task.fail(str(exc))
            messagebox.showerror("TextGrid → ASS", str(exc), parent=self)
            return

        lines = [
            f"Создано: {report.output_path}",
            f"Words: {report.words}",
            f"Dialogue lines: {report.lines}",
            f"Видимых karaoke-сегментов: {report.visible_syllables}",
            f"Timing-only пауз: {report.timing_gaps}",
            f"Phone tier использован: {'да' if report.phone_tier_used else 'нет'}",
            f"Текст пользователя сопоставлен: {'да' if report.transcript_tokens_used else 'нет'}",
            f"Язык: {report.language}",
            f"Сегменты собраны в слоги: {'да' if report.syllabified else 'нет'}",
            f"Исходный текст восстановлен: {'да' if report.text_restored else 'нет'}",
        ]
        if report.text_match_ratio is not None:
            lines.append(f"Совпадение текста: {report.text_match_ratio:.1%}")
        if report.warnings:
            lines += ["", "Предупреждения:", *[f"  • {w}" for w in report.warnings]]
        self._write_report("\n".join(lines))
        if task:
            task.log("; ".join(lines[:4]))
            task.log(
                f"Восстановление исходного TXT: {'да' if report.text_restored else 'нет'}; "
                f"совпадение: {report.text_match_ratio:.1%}"
                if report.text_match_ratio is not None
                else f"Восстановление исходного TXT: {'да' if report.text_restored else 'нет'}"
            )
            task.done(f"ASS создан: {report.output_path.name}")
        self.set_status(f"TextGrid преобразован: {report.output_path}")
        if self.open_after_var.get():
            try:
                self.open_generated(report.output_path)
            except Exception as exc:
                messagebox.showerror("ASS создан, но не открыт", str(exc), parent=self)

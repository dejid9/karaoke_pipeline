from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import re
import json
import shlex
import shutil
import subprocess
import sys
import threading
import time
import signal
from typing import Callable, Iterable, Optional, Sequence

from .alignment import AlignmentError, MFACommandSettings, command_for_display
from .media import media_tool_subprocess_env, probe_media_duration


class MFAError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class CondaEnvironment:
    name: str
    prefix: Path
    active: bool = False


def build_conda_run_prefix(
    conda_executable: str | Path | Sequence[str] = "conda",
    environment: str = "mfa",
    *,
    no_capture_output: bool = False,
) -> tuple[str, ...]:
    """Build ``conda run`` up to (but not including) the program name."""
    env = str(environment).strip()
    if not env:
        raise MFAError("Укажите имя Conda-окружения с MFA")
    conda = _split_command_prefix(conda_executable)
    cmd = conda + ["run"]
    if no_capture_output:
        cmd.append("--no-capture-output")
    cmd += ["-n", env]
    return tuple(cmd)


def build_conda_mfa_prefix(
    conda_executable: str | Path | Sequence[str] = "conda",
    environment: str = "mfa",
    mfa_executable: str | Path | Sequence[str] = "mfa",
    *,
    no_capture_output: bool = True,
) -> tuple[str, ...]:
    """Build the MFA launcher used by this project when MFA lives in Conda.

    ``conda run --no-capture-output`` keeps MFA output streaming to our parent
    process, which is important for the live log/cancellation UI.  Both conda
    and MFA executable values may be paths or small command prefixes.
    """
    mfa = _split_command_prefix(mfa_executable)
    return build_conda_run_prefix(
        conda_executable, environment, no_capture_output=no_capture_output
    ) + tuple(mfa)


def parse_conda_mfa_launcher(value: str | Path | Sequence[str]) -> Optional[tuple[str, str, str]]:
    """Recognize launchers saved by Update 011, e.g. ``conda run -n mfa mfa``.

    Returns ``(conda_executable, environment, mfa_executable)`` for the common
    single-executable form.  This is primarily a migration helper for existing
    project.json files; complex prefixes remain supported through the custom
    MFA command field when Conda mode is disabled.
    """
    try:
        parts = _split_command_prefix(value)
    except MFAError:
        return None
    if len(parts) < 5:
        return None
    try:
        run_i = parts.index("run")
    except ValueError:
        return None
    if run_i < 1 or "conda" not in Path(parts[0]).name.casefold():
        return None
    env = None
    env_i = None
    for flag in ("-n", "--name"):
        if flag in parts[run_i + 1:]:
            env_i = parts.index(flag, run_i + 1)
            if env_i + 1 < len(parts):
                env = parts[env_i + 1]
            break
    if not env or env_i is None:
        return None
    tail = parts[env_i + 2:]
    tail = [x for x in tail if x not in {"--no-capture-output", "--live-stream"}]
    if not tail:
        return None
    return parts[0], env, " ".join(tail)


def list_conda_environments(
    conda_executable: str | Path | Sequence[str] = "conda",
    *,
    timeout: float = 20.0,
) -> tuple[CondaEnvironment, ...]:
    """Return environments reported by ``conda env list --json``."""
    prefix = _split_command_prefix(conda_executable)
    result = _run_probe(prefix + ["env", "list", "--json"], timeout=timeout)
    if result.returncode != 0:
        raise MFAError("Conda не смогла перечислить окружения" + (f": {(result.stdout or '').strip()[-800:]}" if result.stdout else ""))
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MFAError("Conda вернула некорректный JSON списка окружений") from exc
    raw_envs = data.get("envs", [])
    active_prefix = os.environ.get("CONDA_PREFIX", "")
    default_prefix = str(data.get("default_prefix", "") or "")
    out: list[CondaEnvironment] = []
    for raw in raw_envs:
        p = Path(str(raw))
        name = "base" if default_prefix and os.path.normcase(str(p)) == os.path.normcase(default_prefix) else p.name
        if not name:
            name = str(p)
        active = bool(active_prefix and os.path.normcase(str(p)) == os.path.normcase(active_prefix))
        out.append(CondaEnvironment(name=name, prefix=p, active=active))
    return tuple(out)


def build_validate_command(
    workspace: "MFAWorkspace",
    settings: MFACommandSettings,
    installation: "MFAInstallation",
    output_directory: str | Path,
    *,
    ignore_acoustics: bool = False,
) -> list[str]:
    """Build MFA corpus validation using an explicit dictionary.

    MFA 3.x ``validate`` still has the legacy-style CORPUS + DICTIONARY
    signature even when alignment itself uses an HF model.  We therefore never
    invent a dictionary from the HF model ID.
    """
    if "validate" not in installation.commands:
        raise MFAError("Эта установка MFA не сообщает команду validate")
    dictionary = settings.dictionary.strip()
    if not dictionary:
        raise MFAError("mfa validate требует явный pronunciation dictionary; укажите Dictionary даже при HF alignment")
    out = Path(output_directory)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    cmd = list(installation.command_prefix) + ["validate", str(workspace.corpus_directory), dictionary, "--output_directory", str(out)]
    mode = settings.mode.casefold().strip()
    effective_legacy = mode == "legacy" or (mode == "auto" and not installation.has_hf)
    if effective_legacy and settings.model.strip():
        cmd += ["--acoustic_model_path", settings.model.strip()]
        if not ignore_acoustics:
            if settings.beam < 1:
                raise MFAError("beam должен быть >= 1")
            if settings.retry_beam <= settings.beam:
                raise MFAError("retry_beam должен быть больше beam")
            cmd += ["--beam", str(settings.beam), "--retry_beam", str(settings.retry_beam)]
    if ignore_acoustics:
        cmd.append("--ignore_acoustics")
    if settings.num_jobs is not None:
        cmd += ["--num_jobs", str(settings.num_jobs)]
    if settings.single_speaker:
        cmd.append("--single_speaker")
    cmd.append("--clean")
    return cmd


def build_find_oovs_command(
    workspace: "MFAWorkspace",
    settings: MFACommandSettings,
    installation: "MFAInstallation",
    output_directory: str | Path,
) -> list[str]:
    if "find_oovs" not in installation.commands:
        raise MFAError("Эта установка MFA не сообщает команду find_oovs")
    dictionary = settings.dictionary.strip()
    if not dictionary:
        raise MFAError("mfa find_oovs требует явный pronunciation dictionary")
    out = Path(output_directory)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    cmd = list(installation.command_prefix) + ["find_oovs", str(workspace.corpus_directory), dictionary, str(out)]
    if settings.num_jobs is not None:
        cmd += ["--num_jobs", str(settings.num_jobs)]
    if settings.single_speaker:
        cmd.append("--single_speaker")
    cmd.append("--clean")
    return cmd


def find_oov_artifacts(output_directory: str | Path) -> tuple[Path, ...]:
    root = Path(output_directory)
    if not root.exists():
        return ()
    candidates = [p for p in root.rglob("*") if p.is_file() and "oov" in p.name.casefold()]
    return tuple(sorted(candidates, key=lambda p: str(p).casefold()))


def read_oov_summary(output_directory: str | Path, *, max_lines: int = 200) -> str:
    files = find_oov_artifacts(output_directory)
    if not files:
        return "OOV-файлы не найдены в output MFA."
    blocks: list[str] = []
    remaining = max(1, max_lines)
    for path in files:
        blocks.append(f"[{path.name}]")
        try:
            lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError as exc:
            blocks.append(f"<не удалось прочитать: {exc}>")
            continue
        take = lines[:remaining]
        blocks.extend(take)
        remaining -= len(take)
        if len(lines) > len(take):
            blocks.append(f"… ещё {len(lines) - len(take)} строк")
        if remaining <= 0:
            blocks.append("… отчёт обрезан")
            break
        blocks.append("")
    return "\n".join(blocks).rstrip()


_MODEL_TYPES = {"acoustic", "dictionary", "g2p", "ivector", "language_model", "tokenizer"}

_MODEL_FAMILIES = {"mfa", "arpa", "cv"}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_QUOTED_MODEL_RE = re.compile(r"['\"]([A-Za-z0-9][A-Za-z0-9_.-]*)['\"]")
_PLAIN_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def model_family(model_name: str) -> str:
    """Return the MFA naming-family suffix (mfa/arpa/cv), if present."""
    tail = model_name.strip().casefold().rsplit("_", 1)[-1]
    return tail if tail in _MODEL_FAMILIES else ""


def model_language_key(model_name: str) -> str:
    """Infer the language represented by an MFA model catalogue name.

    MFA names commonly use ``language[_region]_<family>``.  Region/dialect
    components belong to the selectable model variant, while the first
    component is the language used to group the GUI catalogue.
    """
    value = model_name.strip().casefold().replace("-", "_")
    if not value:
        return ""
    parts = [part for part in value.split("_") if part]
    if parts and parts[-1] in _MODEL_FAMILIES:
        parts.pop()
    return parts[0] if parts else ""


def parse_mfa_model_list_output(output: str) -> tuple[str, ...]:
    """Parse both Rich-formatted MFA 3 output and plain one-name-per-line output."""
    clean = _ANSI_ESCAPE_RE.sub("", output or "")
    names = _QUOTED_MODEL_RE.findall(clean)
    if not names:
        for raw_line in clean.splitlines():
            candidate = raw_line.strip().strip("│|,[]() ")
            if _PLAIN_MODEL_RE.fullmatch(candidate) and "_" in candidate:
                names.append(candidate)
    return tuple(dict.fromkeys(sorted(names, key=str.casefold)))


@dataclass(slots=True, frozen=True)
class MFAInstalledModelCatalog:
    acoustic: tuple[str, ...] = ()
    dictionary: tuple[str, ...] = ()
    g2p: tuple[str, ...] = ()
    tokenizer: tuple[str, ...] = ()

    def models(self, model_type: str) -> tuple[str, ...]:
        kind = model_type.casefold().strip()
        if kind not in {"acoustic", "dictionary", "g2p", "tokenizer"}:
            return ()
        return tuple(getattr(self, kind))

    def language_keys(self) -> tuple[str, ...]:
        names = (*self.acoustic, *self.dictionary)
        return tuple(sorted({model_language_key(name) for name in names if model_language_key(name)}))

    def for_language(self, model_type: str, language: str) -> tuple[str, ...]:
        key = language.strip().casefold()
        return tuple(name for name in self.models(model_type) if model_language_key(name) == key)


def matching_model_variant(
    candidates: Sequence[str],
    reference: str,
    *,
    preferred: str = "",
) -> str:
    """Choose a dictionary/model variant compatible with ``reference``."""
    choices = tuple(candidates)
    if not choices:
        return ""
    if reference in choices:
        return reference
    if preferred in choices:
        return preferred
    family = model_family(reference)
    if family:
        same_family = tuple(name for name in choices if model_family(name) == family)
        if same_family:
            # Prefer the candidate with the longest common variant prefix.
            reference_parts = reference.casefold().split("_")[:-1]
            return max(
                same_family,
                key=lambda name: sum(
                    1 for left, right in zip(reference_parts, name.casefold().split("_")[:-1])
                    if left == right
                ),
            )
    return choices[0]


def list_installed_mfa_models(
    installation: "MFAInstallation | str | Path | Sequence[str]",
    *,
    model_types: Sequence[str] = ("acoustic", "dictionary"),
    timeout: float = 45.0,
) -> MFAInstalledModelCatalog:
    """Query installed MFA models, in parallel to avoid repeated Conda startup delay."""
    if not isinstance(installation, MFAInstallation):
        installation = MFAInstallation(
            tuple(_split_command_prefix(installation)),
            "unknown",
            (),
            frozenset({"model"}),
        )
    kinds = tuple(dict.fromkeys(kind.casefold().strip() for kind in model_types))
    invalid = [kind for kind in kinds if kind not in {"acoustic", "dictionary", "g2p", "tokenizer"}]
    if invalid:
        raise MFAError(f"Неизвестный тип каталога MFA: {invalid[0]}")

    def load(kind: str) -> tuple[str, tuple[str, ...]]:
        command = build_model_command(installation, "list", kind)
        result = _run_probe(command, timeout=timeout)
        if result.returncode != 0:
            detail = (result.stdout or "").strip()[-800:]
            raise MFAError(
                f"Не удалось прочитать установленные MFA {kind} models"
                + (f": {detail}" if detail else "")
            )
        return kind, parse_mfa_model_list_output(result.stdout or "")

    found: dict[str, tuple[str, ...]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(kinds)))) as pool:
        for kind, names in pool.map(load, kinds):
            found[kind] = names
    return MFAInstalledModelCatalog(
        acoustic=found.get("acoustic", ()),
        dictionary=found.get("dictionary", ()),
        g2p=found.get("g2p", ()),
        tokenizer=found.get("tokenizer", ()),
    )

def build_model_command(
    installation: "MFAInstallation | str | Path | Sequence[str]",
    action: str,
    model_type: str,
    model_name: str = "",
    *,
    force: bool = False,
) -> list[str]:
    if isinstance(installation, MFAInstallation):
        if "model" not in installation.commands:
            raise MFAError("Эта установка MFA не сообщает команду model")
        prefix = installation.command_prefix
    else:
        prefix = tuple(_split_command_prefix(installation))
    action = action.casefold().strip()
    kind = model_type.casefold().strip()
    if kind not in _MODEL_TYPES:
        raise MFAError(f"Неизвестный тип модели: {model_type}")
    if action not in {"list", "download", "inspect"}:
        raise MFAError("Model action must be list, download or inspect")
    cmd = list(prefix) + ["model", action, kind]
    name = model_name.strip()
    if action in {"download", "inspect"}:
        if not name:
            raise MFAError(f"Для model {action} укажите имя модели")
        cmd.append(name)
    if action == "download" and force:
        cmd.append("--force")
    return cmd


@dataclass(slots=True, frozen=True)
class MFAInstallation:
    command_prefix: tuple[str, ...]
    version: str
    version_tuple: tuple[int, ...]
    commands: frozenset[str]
    help_text: str = ""

    @property
    def has_hf(self) -> bool:
        if "align_hf" in self.commands or "align_one_hf" in self.commands:
            return True
        # MFA 4.x is documented to move the HF signature to plain `align`.
        return bool(self.version_tuple[:1] >= (4,) and "align" in self.commands)

    @property
    def has_legacy(self) -> bool:
        if "align_legacy" in self.commands or "align_one_legacy" in self.commands:
            return True
        # Before MFA 4, plain `align` is the legacy dictionary+acoustic form.
        return bool(self.version_tuple[:1] < (4,) and "align" in self.commands)

    def alignment_subcommand(self, mode: str, *, single_file: bool = False) -> str:
        mode = mode.casefold().strip()
        if mode == "auto":
            mode = "hf" if self.has_hf else "legacy"
        if mode == "hf":
            preferred = "align_one_hf" if single_file else "align_hf"
            # MFA 4.x is expected to fold the HF signature into align/align_one.
            fallback = "align_one" if single_file else "align"
            if preferred in self.commands:
                return preferred
            if fallback in self.commands and self.version_tuple[:1] >= (4,):
                return fallback
            raise MFAError("Эта установка MFA не сообщает поддержку HF alignment")
        if mode == "legacy":
            preferred = "align_one_legacy" if single_file else "align_legacy"
            fallback = "align_one" if single_file else "align"
            if preferred in self.commands:
                return preferred
            if fallback in self.commands:
                return fallback
            raise MFAError("Эта установка MFA не сообщает поддержку legacy alignment")
        raise MFAError("MFA mode must be auto, hf or legacy")


@dataclass(slots=True, frozen=True)
class MFAWorkspace:
    root: Path
    corpus_directory: Path
    output_directory: Path
    audio_path: Path
    transcript_path: Path
    stem: str
    composite_dict_path: Optional[Path] = None


@dataclass(slots=True, frozen=True)
class MFAAlignmentResult:
    returncode: int
    command: tuple[str, ...]
    workspace: MFAWorkspace
    textgrid: Optional[Path]
    elapsed_seconds: float
    cancelled: bool = False


def _split_command_prefix(value: str | Path | Sequence[str]) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
        if not items:
            raise MFAError("Пустая команда MFA")
        return items
    raw = str(value).strip()
    if not raw:
        raw = "mfa"
    unquoted = raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] == '"' else raw
    p = Path(unquoted)
    if p.exists():
        return [str(p)]
    # This intentionally allows launchers such as `conda run -n mfa mfa`.
    try:
        if os.name == "nt":
            items = shlex.split(raw, posix=False)
            return [item[1:-1] if len(item) >= 2 and item[0] == item[-1] == '"' else item for item in items]
        return shlex.split(raw, posix=True)
    except ValueError as exc:
        raise MFAError(f"Некорректная команда MFA: {raw}") from exc


def _version_tuple(text: str) -> tuple[int, ...]:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return ()
    return tuple(int(x) for x in match.groups() if x is not None)


def mfa_subprocess_env(
    executable_or_command: str | Path | Sequence[str] = "mfa",
    base_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Return an execution environment with paths resolved for portable MFA.

    When MFA is invoked directly on Windows (outside `conda run`), its native DLLs
    (such as `libsndfile.dll`, `kaldi-*.dll`, `openfst.dll`, `mkl_*.dll`) reside in
    `Library/bin` relative to the environment root. This function prepends the
    relevant directories to PATH if found, and configures MFA_ROOT_DIR if a local
    data/mfa directory exists.
    """
    env = dict(os.environ if base_env is None else base_env)
    if not sys.platform.startswith("win"):
        return env
    try:
        parts = _split_command_prefix(executable_or_command) if not isinstance(executable_or_command, (list, tuple)) else list(executable_or_command)
    except Exception:
        parts = []
    if not parts:
        return env
    first = str(parts[0]).strip('"')
    candidate = Path(first)
    if not candidate.is_absolute():
        resolved = shutil.which(first)
        if resolved:
            candidate = Path(resolved)
    if candidate.is_file():
        candidate_dir = candidate.parent
        extra_paths: list[str] = [str(candidate_dir)]
        parent = candidate_dir.parent
        lib_bin = parent / "Library" / "bin"
        if lib_bin.is_dir() and str(lib_bin) not in extra_paths:
            extra_paths.append(str(lib_bin))
        scripts = parent / "Scripts"
        if scripts.is_dir() and str(scripts) not in extra_paths:
            extra_paths.append(str(scripts))
        if parent.is_dir() and str(parent) not in extra_paths:
            extra_paths.append(str(parent))
        current_path = env.get("PATH", "")
        env["PATH"] = ";".join(extra_paths) + (";" + current_path if current_path else "")
        if "MFA_ROOT_DIR" not in env:
            for p in [candidate.resolve()] + list(candidate.resolve().parents):
                mfa_data = p / "data" / "mfa"
                if mfa_data.is_dir():
                    env["MFA_ROOT_DIR"] = str(mfa_data.resolve())
                    break
    return env


def _run_probe(command: Sequence[str], *, timeout: float = 15.0, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    try:
        run_env = env if env is not None else mfa_subprocess_env(command)
        return subprocess.run(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=run_env,
        )
    except FileNotFoundError as exc:
        raise MFAError(f"MFA не найден: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MFAError("MFA не ответил во время проверки установки") from exc


def detect_mfa_installation(executable: str | Path | Sequence[str] = "mfa", *, timeout: float = 45.0) -> MFAInstallation:
    prefix = _split_command_prefix(executable)
    version_text = ""
    # `conda run` can take over 15 seconds merely to start on Windows.  Probe
    # the normal version command and help concurrently so installation checks
    # have a safe timeout without doubling the wait before every first run.
    with ThreadPoolExecutor(max_workers=2) as pool:
        version_future = pool.submit(_run_probe, prefix + ["version"], timeout=timeout)
        help_future = pool.submit(_run_probe, prefix + ["--help"], timeout=timeout)
        version_result = version_future.result()
        help_result = help_future.result()

    if version_result.returncode == 0 and (version_result.stdout or "").strip():
        version_text = (version_result.stdout or "").strip().splitlines()[0].strip()
    else:
        # Older/custom launchers may expose only the conventional version flags.
        for suffix in (["--version"], ["-V"]):
            result = _run_probe(prefix + list(suffix), timeout=timeout)
            candidate = (result.stdout or "").strip()
            if result.returncode == 0 and candidate:
                version_text = candidate.splitlines()[0].strip()
                break
    help_text = help_result.stdout or ""
    if help_result.returncode != 0 and not help_text:
        raise MFAError("Не удалось получить `mfa --help`")
    known = {
        "align", "align_hf", "align_legacy", "align_one", "align_one_hf", "align_one_legacy",
        "model", "validate", "find_oovs", "validate_dictionary", "version",
    }
    commands = frozenset(name for name in known if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", help_text))
    # Some Click help renderers omit the version command in the subcommand list.
    if version_text:
        commands = frozenset(set(commands) | {"version"})
    return MFAInstallation(tuple(prefix), version_text or "unknown", _version_tuple(version_text), commands, help_text)


def build_runtime_align_command(
    workspace: MFAWorkspace,
    settings: MFACommandSettings,
    installation: MFAInstallation,
) -> list[str]:
    mode = settings.mode.casefold().strip()
    subcommand = installation.alignment_subcommand(mode)
    cmd = list(installation.command_prefix) + [subcommand, str(workspace.corpus_directory)]
    effective_mode = mode
    if mode == "auto":
        effective_mode = "hf" if subcommand in {"align_hf"} or (subcommand == "align" and installation.version_tuple[:1] >= (4,)) else "legacy"
    if effective_mode == "hf":
        if not settings.model.strip():
            raise MFAError("Для HF-режима укажите model ID")
        cmd += [settings.model.strip(), str(workspace.output_directory)]
        if settings.dialect.strip():
            cmd += ["--dialect", settings.dialect.strip()]
        if settings.use_g2p:
            cmd.append("--use_g2p")
    else:
        if not settings.dictionary.strip():
            raise MFAError("Legacy MFA требует явный pronunciation dictionary")
        if not settings.model.strip():
            raise MFAError("Legacy MFA требует явную acoustic model")
        cmd += [settings.dictionary.strip(), settings.model.strip(), str(workspace.output_directory)]
    if settings.beam < 1:
        raise MFAError("beam должен быть >= 1")
    if settings.retry_beam <= settings.beam:
        raise MFAError("retry_beam должен быть больше beam")
    cmd += ["--beam", str(settings.beam), "--retry_beam", str(settings.retry_beam)]
    cmd += ["--output_format", "long_textgrid"]
    if settings.num_jobs is not None:
        if settings.num_jobs < 1:
            raise MFAError("num_jobs должен быть >= 1")
        cmd += ["--num_jobs", str(settings.num_jobs)]
    if settings.single_speaker:
        cmd.append("--single_speaker")
    cmd.append("--cleanup_textgrids" if settings.clean_textgrids else "--no_cleanup_textgrids")
    cmd.append("--clean")
    return cmd


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or "audio"


def prepare_mfa_workspace(
    media_path: str | Path,
    transcript_path: str | Path,
    workspace_root: str | Path,
    *,
    ffmpeg: str | Path | None = None,
    sample_rate: int = 16000,
    clean: bool = True,
    transcript_text: str | None = None,
    progress: Optional[Callable[[Optional[float], str], None]] = None,
    log: Optional[Callable[[str], None]] = None,
) -> MFAWorkspace:
    media = Path(media_path).resolve()
    transcript = Path(transcript_path).resolve()
    if not media.exists():
        raise MFAError(f"Медиафайл не найден: {media}")
    if not transcript.exists():
        raise MFAError(f"Текст не найден: {transcript}")
    text = (transcript_text if transcript_text is not None else transcript.read_text(encoding="utf-8-sig")).strip()
    if not text:
        raise MFAError("Текст для MFA пуст")
    if sample_rate < 8000:
        raise MFAError("sample_rate должен быть >= 8000")

    root = Path(workspace_root).resolve()
    corpus = root / "corpus"
    output = root / "output"
    if clean:
        shutil.rmtree(corpus, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)
        if output.exists():
            for stale in list(output.rglob("*.TextGrid")) + list(output.rglob("*.textgrid")):
                try:
                    stale.unlink(missing_ok=True)
                except OSError:
                    pass
    corpus.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    try:
        docs_cache = Path.home() / "Documents" / "MFA" / corpus.name
        if docs_cache.exists():
            shutil.rmtree(docs_cache, ignore_errors=True)
    except Exception:
        pass

    stem = _safe_stem(media.stem)
    audio_out = corpus / f"{stem}.wav"
    text_out = corpus / f"{stem}.lab"
    text_out.write_text(text + "\n", encoding="utf-8")

    if ffmpeg is None:
        raise MFAError("FFmpeg не настроен. Выберите portable FFmpeg проекта или укажите ffmpeg.exe в интерфейсе.")
    ffmpeg_cmd = str(ffmpeg)
    command = [
        ffmpeg_cmd, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(media), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats", str(audio_out),
    ]
    if progress:
        progress(2.0, "Подготовка transcript")
    if log:
        log("> " + command_for_display(command))
    duration = probe_media_duration(media, ffmpeg_cmd)
    if progress:
        progress(5.0, "FFmpeg: подготовка WAV для MFA")
    output_lines: list[str] = []
    try:
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
            env=media_tool_subprocess_env(ffmpeg_cmd),
        )
    except FileNotFoundError as exc:
        raise MFAError(f"FFmpeg не найден: {ffmpeg_cmd}") from exc
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue
        output_lines.append(line)
        if line.startswith("out_time=") and duration:
            try:
                hh, mm, ss = line.split("=", 1)[1].split(":")
                current = int(hh) * 3600 + int(mm) * 60 + float(ss)
                pct = 5.0 + min(90.0, current / duration * 90.0)
                if progress:
                    progress(pct, "FFmpeg: подготовка WAV для MFA")
            except (ValueError, TypeError):
                pass
        elif "=" not in line and log:
            log(line)
    proc.stdout.close()
    rc = proc.wait()
    if rc != 0 or not audio_out.exists():
        detail = "\n".join(output_lines[-30:]).strip()
        raise MFAError("Не удалось подготовить WAV для MFA" + (f": {detail[-1200:]}" if detail else ""))
    if progress:
        progress(100.0, "MFA corpus подготовлен")
    return MFAWorkspace(root, corpus, output, audio_out, text_out, stem)


def find_textgrid(output_directory: str | Path, stem: str | None = None) -> Optional[Path]:
    root = Path(output_directory)
    candidates = sorted(root.rglob("*.TextGrid")) + sorted(root.rglob("*.textgrid"))
    if not candidates:
        return None
    if stem:
        wanted = stem.casefold()
        exact = [p for p in candidates if p.stem.casefold() == wanted]
        if exact:
            return exact[0]
        return None
    return candidates[0]


def adopt_textgrid(source: str | Path, destination: str | Path) -> Path:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_suffix(destination.suffix + ".bak")
        shutil.copy2(destination, backup)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, tmp)
    os.replace(tmp, destination)
    return destination


class MFAProcess:
    """Small cancellable process wrapper used by the Tk GUI.

    stdout/stderr are merged so the UI receives MFA messages in their original
    order. Cancellation first terminates and then escalates to kill after a
    short grace period.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        on_line: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.command = tuple(str(x) for x in command)
        self.cwd = str(cwd) if cwd is not None else None
        self.on_line = on_line
        self.process: Optional[subprocess.Popen[str]] = None
        self.cancelled = False
        self._lock = threading.Lock()

    def run(self) -> int:
        popen_kwargs = {}
        popen_kwargs["env"] = mfa_subprocess_env(self.command)
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(
                list(self.command),
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **popen_kwargs,
            )
        except FileNotFoundError as exc:
            raise MFAError(f"Не удалось запустить MFA: {self.command[0]}") from exc
        with self._lock:
            self.process = proc
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if self.on_line:
                    self.on_line(line.rstrip("\r\n"))
        finally:
            proc.stdout.close()
        return proc.wait()

    def cancel(self, *, grace_seconds: float = 2.0) -> None:
        self.cancelled = True
        with self._lock:
            proc = self.process
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name == "nt":
                # MFA can spawn Kaldi/Postgres helper processes; terminate the
                # whole process tree instead of leaving workers behind.
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            proc.terminate()
        deadline = time.monotonic() + max(0.0, grace_seconds)
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                proc.kill()

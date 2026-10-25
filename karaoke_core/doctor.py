from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import importlib.util
import platform
import shutil
import sys
from typing import Optional

from .mfa import MFAError, build_conda_mfa_prefix, build_conda_run_prefix, detect_mfa_installation, list_conda_environments
from .project import ProjectConfig, find_portable_ffmpeg, find_portable_mfa, load_project
from .textprep import probe_python_packages


@dataclass(slots=True, frozen=True)
class HealthCheck:
    name: str
    ok: bool
    detail: str
    warning: bool = False


@dataclass(slots=True, frozen=True)
class HealthReport:
    checks: tuple[HealthCheck, ...]

    @property
    def ok(self) -> bool:
        return all(item.ok or item.warning for item in self.checks)

    def format_text(self) -> str:
        rows = []
        for item in self.checks:
            mark = "OK" if item.ok else ("WARN" if item.warning else "FAIL")
            rows.append(f"[{mark}] {item.name}: {item.detail}")
        rows.append("")
        rows.append("Итог: " + ("рабочее окружение" if self.ok else "есть блокирующие проблемы"))
        return "\n".join(rows)


def _find_ffplay(ffmpeg: Optional[Path]) -> Optional[Path]:
    if ffmpeg is not None:
        name = "ffplay.exe" if ffmpeg.name.lower().endswith(".exe") else "ffplay"
        sibling = ffmpeg.with_name(name)
        if sibling.exists():
            return sibling
    return None


def run_health_checks(project_root: str | Path | None = None) -> HealthReport:
    checks: list[HealthCheck] = []
    checks.append(HealthCheck("Python", True, f"{platform.python_version()} · {sys.executable}"))
    try:
        import tkinter  # noqa: F401
        checks.append(HealthCheck("Tkinter", True, "доступен"))
    except Exception as exc:
        checks.append(HealthCheck("Tkinter", False, str(exc)))
    numpy_ok = importlib.util.find_spec("numpy") is not None
    checks.append(HealthCheck("NumPy", numpy_ok, "доступен" if numpy_ok else "нет; нужна только спектрограмма", warning=not numpy_ok))
    sounddevice_ok = importlib.util.find_spec("sounddevice") is not None
    checks.append(HealthCheck(
        "sounddevice / PortAudio", sounddevice_ok,
        "доступен; низколатентный транспорт включён" if sounddevice_ok else "нет; установите python-sounddevice для Audacity-like playback",
        warning=not sounddevice_ok,
    ))

    config: Optional[ProjectConfig] = None
    root: Optional[Path] = None
    if project_root is not None:
        root = Path(project_root).resolve()
        try:
            config = load_project(root)
            checks.append(HealthCheck("project.json", True, str(root / "project.json")))
        except Exception as exc:
            checks.append(HealthCheck("project.json", False, str(exc)))
    ffmpeg = config.resolve_ffmpeg(root) if config is not None and root is not None else None
    if ffmpeg is None and root is None:
        ffmpeg = find_portable_ffmpeg(Path.cwd())
    checks.append(HealthCheck(
        "FFmpeg",
        ffmpeg is not None,
        str(ffmpeg) if ffmpeg else "не найден; PATH/Conda намеренно не используются",
    ))
    ffplay = _find_ffplay(ffmpeg)
    checks.append(HealthCheck("ffplay", ffplay is not None, str(ffplay) if ffplay else "не найден; playback в GUI будет недоступен", warning=ffplay is None))

    if config is not None and root is not None:
        for dirname in ("source", "alignment", "subtitles", "cache", "exports"):
            path = root / dirname
            checks.append(HealthCheck(f"project/{dirname}", path.is_dir(), str(path)))
        for label, raw in (("Media", config.media), ("Transcript", config.transcript), ("ASS", config.subtitles)):
            if raw:
                path = config.resolve(root, raw)
                checks.append(HealthCheck(label, bool(path and path.exists()), str(path), warning=not bool(path and path.exists())))

        if config.mfa_use_conda:
            conda = config.resolve_conda_command(root)
            env_name = config.mfa_conda_env or "mfa"
            try:
                envs = list_conda_environments(conda)
                names = {e.name for e in envs}
                exists = env_name in names
                checks.append(HealthCheck("Conda env", exists, f"{env_name} ({'найден' if exists else 'не найден'})"))
                if exists:
                    prefix = build_conda_run_prefix(conda, env_name)
                    try:
                        packages = probe_python_packages(prefix, ("sudachipy", "sudachidict_core", "numpy", "sounddevice"))
                        for name, present in packages.items():
                            optional = name.startswith("sudachi") or name == "sounddevice"
                            if present:
                                detail = "установлен"
                            elif name == "sounddevice":
                                detail = "нет; нужен для низколатентного PortAudio-плеера"
                            elif name.startswith("sudachi"):
                                detail = "нет; нужен только для Japanese Sudachi"
                            else:
                                detail = "не установлен"
                            checks.append(HealthCheck(f"Conda package {name}", present, detail, warning=optional and not present))
                    except Exception as exc:
                        checks.append(HealthCheck("Conda Python packages", False, str(exc), warning=True))
                    try:
                        mfa_prefix = build_conda_mfa_prefix(conda, env_name, config.resolve_mfa_command(root))
                        inst = detect_mfa_installation(mfa_prefix)
                        checks.append(HealthCheck("MFA", True, f"{inst.version}; команды: {', '.join(sorted(inst.commands))}"))
                    except Exception as exc:
                        checks.append(HealthCheck("MFA", False, str(exc)))
            except Exception as exc:
                portable_mfa = find_portable_mfa(root)
                if portable_mfa is not None:
                    try:
                        inst = detect_mfa_installation(str(portable_mfa))
                        checks.append(HealthCheck("MFA (Portable)", True, f"{inst.version}; автономный режим ({portable_mfa.name})"))
                    except Exception as p_exc:
                        checks.append(HealthCheck("Conda", False, f"{exc}; портативный MFA: {p_exc}"))
                else:
                    checks.append(HealthCheck("Conda", False, str(exc)))
        else:
            try:
                inst = detect_mfa_installation(config.resolve_mfa_command(root))
                checks.append(HealthCheck("MFA", True, f"{inst.version}; direct launcher"))
            except MFAError as exc:
                checks.append(HealthCheck("MFA", False, str(exc)))
    else:
        portable_mfa = find_portable_mfa(Path.cwd())
        if portable_mfa is not None:
            try:
                inst = detect_mfa_installation(str(portable_mfa))
                checks.append(HealthCheck("MFA (Portable)", True, f"{inst.version}; автономный режим ({portable_mfa})"))
            except Exception as exc:
                checks.append(HealthCheck("MFA (Portable)", False, str(exc), warning=True))
        conda = shutil.which("conda")
        checks.append(HealthCheck("Conda", conda is not None, conda or "не найден", warning=conda is None))

    return HealthReport(tuple(checks))

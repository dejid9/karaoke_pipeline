from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
import json
import os
from typing import Optional


PROJECT_DIRS = ("source", "alignment", "subtitles", "cache", "exports")

# Deliberately local-only.  We do not auto-discover FFmpeg through PATH or
# CONDA_PREFIX anymore: when the GUI is launched from an MFA Conda environment,
# that can select Conda's ffmpeg.exe and/or inject incompatible DLLs.
LOCAL_FFMPEG_RELATIVE_PATHS = (
    Path("work/hz/ffmpeg/bin/ffmpeg.exe"),
    Path("work/hz/ffmpeg/bin/ffmpeg"),
    # Kept only for compatibility with older local layouts.  These are still
    # project-local; PATH/Conda is never consulted automatically.
    Path("work/hz/ffmpeg.exe"),
    Path("work/hz/bin/ffmpeg.exe"),
    Path("tools/ffmpeg/bin/ffmpeg.exe"),
    Path("tools/ffmpeg/ffmpeg.exe"),
    Path("ffmpeg/bin/ffmpeg.exe"),
    Path("ffmpeg.exe"),
)

LOCAL_MFA_RELATIVE_PATHS = (
    Path("runtime/Scripts/mfa.exe"),
    Path("runtime/mfa.exe"),
    Path("tools/mfa/Scripts/mfa.exe"),
    Path("tools/mfa/mfa.exe"),
    Path("mfa/Scripts/mfa.exe"),
    Path("mfa/mfa.exe"),
)


def find_local_ffmpeg(root: str | Path) -> Optional[Path]:
    root = Path(root).expanduser().resolve()
    for rel in LOCAL_FFMPEG_RELATIVE_PATHS:
        candidate = root / rel
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_portable_ffmpeg(root: str | Path) -> Optional[Path]:
    """Find the repository-local FFmpeg without ever consulting PATH.

    Projects can live below the application repository, so also walk parents.
    The package repository itself is checked as a final deterministic location.
    """
    start = Path(root).expanduser().resolve()
    seen: set[Path] = set()
    candidates = [start, *start.parents, Path(__file__).resolve().parents[1]]
    for base in candidates:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen:
            continue
        seen.add(base)
        found = find_local_ffmpeg(base)
        if found is not None:
            return found
    return None


def find_local_mfa(root: str | Path) -> Optional[Path]:
    root = Path(root).expanduser().resolve()
    for rel in LOCAL_MFA_RELATIVE_PATHS:
        candidate = root / rel
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_portable_mfa(root: str | Path) -> Optional[Path]:
    """Find the repository-local or portable standalone MFA executable."""
    start = Path(root).expanduser().resolve()
    seen: set[Path] = set()
    candidates = [start, *start.parents, Path(__file__).resolve().parents[1]]
    for base in candidates:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen:
            continue
        seen.add(base)
        found = find_local_mfa(base)
        if found is not None:
            return found
    return None


@dataclass(slots=True)
class ProjectConfig:
    version: int = 1
    name: str = "karaoke-project"
    media: Optional[str] = None
    subtitles: Optional[str] = None
    textgrid: Optional[str] = None
    transcript: Optional[str] = None
    # ffmpeg_mode is intentionally explicit.  Existing projects that only had
    # an old `ffmpeg` field default to portable mode, so stale Conda paths stop
    # being used after this update.
    ffmpeg_mode: str = "portable"  # portable | custom
    ffmpeg: Optional[str] = None
    mfa: Optional[str] = None
    conda_executable: Optional[str] = None
    mfa_conda_env: Optional[str] = "mfa"
    mfa_use_conda: bool = True
    default_karaoke_tag: str = "kf"
    metadata: dict = field(default_factory=dict)

    def resolve(self, root: str | Path, value: Optional[str]) -> Optional[Path]:
        if value is None:
            return None
        p = Path(value)
        if not p.is_absolute():
            p = Path(root) / p
        return p.resolve()

    def resolve_ffmpeg(self, root: str | Path) -> Optional[Path]:
        """Resolve FFmpeg from an explicit source only.

        * portable: repository/work folder only;
        * custom: exactly the configured executable.

        PATH, $FFMPEG and Conda are deliberately not fallback sources.
        """
        root = Path(root).resolve()
        mode = (self.ffmpeg_mode or "portable").strip().lower()
        if mode == "custom":
            if not self.ffmpeg:
                return None
            resolved = self.resolve(root, self.ffmpeg)
            return resolved if resolved and resolved.is_file() else None
        return find_portable_ffmpeg(root)

    def resolve_conda_command(self, root: str | Path) -> str:
        if self.conda_executable:
            raw = self.conda_executable.strip()
            candidate = Path(raw.strip('"'))
            if not candidate.is_absolute():
                project_candidate = Path(root) / candidate
                if project_candidate.exists():
                    return str(project_candidate.resolve())
            if candidate.exists():
                return str(candidate.resolve())
            return raw
        return os.environ.get("CONDA_EXE", "conda")

    def resolve_mfa_command(self, root: str | Path) -> str:
        # Unlike FFmpeg this may be a launcher command such as
        # `conda run -n mfa mfa`, so do not coerce it to Path.
        if self.mfa:
            raw = self.mfa.strip()
            candidate = Path(raw.strip('"'))
            if not candidate.is_absolute():
                project_candidate = Path(root) / candidate
                if project_candidate.exists():
                    return str(project_candidate.resolve())
            if candidate.exists():
                return str(candidate.resolve())
            return raw
        portable = find_portable_mfa(root)
        if portable is not None:
            return str(portable)
        return os.environ.get("MFA", "mfa")


def _config_path(root: str | Path) -> Path:
    return Path(root) / "project.json"


def create_project(root: str | Path, name: Optional[str] = None, *, exist_ok: bool = False) -> ProjectConfig:
    root = Path(root)
    if root.exists() and any(root.iterdir()) and not exist_ok:
        raise FileExistsError(f"Project directory is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for item in PROJECT_DIRS:
        (root / item).mkdir(exist_ok=True)
    config = ProjectConfig(name=name or root.name or "karaoke-project")
    save_project(root, config)
    return config


def save_project(root: str | Path, config: ProjectConfig) -> Path:
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_project(root: str | Path) -> ProjectConfig:
    path = _config_path(root)
    data = json.loads(path.read_text(encoding="utf-8"))
    valid = {f.name for f in fields(ProjectConfig)}
    return ProjectConfig(**{k: v for k, v in data.items() if k in valid})

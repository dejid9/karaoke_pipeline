from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from karaoke_core.media import media_tool_subprocess_env, resolve_ffplay, resolve_ffprobe
from karaoke_core.project import ProjectConfig, find_local_ffmpeg


def test_project_prefers_actual_work_hz_ffmpeg_distribution(tmp_path: Path, monkeypatch) -> None:
    ffmpeg = tmp_path / "work" / "hz" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"stub")
    monkeypatch.setenv("PATH", "")
    assert find_local_ffmpeg(tmp_path) == ffmpeg.resolve()
    assert ProjectConfig().resolve_ffmpeg(tmp_path) == ffmpeg.resolve()


def test_actual_nested_bundle_has_priority_over_older_layout(tmp_path: Path, monkeypatch) -> None:
    actual = tmp_path / "work" / "hz" / "ffmpeg" / "bin" / "ffmpeg.exe"
    older = tmp_path / "work" / "hz" / "ffmpeg.exe"
    actual.parent.mkdir(parents=True)
    older.parent.mkdir(parents=True, exist_ok=True)
    actual.write_bytes(b"actual")
    older.write_bytes(b"older")
    monkeypatch.setenv("PATH", "")
    assert find_local_ffmpeg(tmp_path) == actual.resolve()


def test_portable_mode_never_falls_back_to_path_or_stale_explicit_value(tmp_path: Path, monkeypatch) -> None:
    conda_ffmpeg = tmp_path / "conda" / "envs" / "mfa" / "Library" / "bin" / "ffmpeg.exe"
    conda_ffmpeg.parent.mkdir(parents=True)
    conda_ffmpeg.write_bytes(b"conda")
    monkeypatch.setenv("PATH", str(conda_ffmpeg.parent))
    monkeypatch.setenv("FFMPEG", str(conda_ffmpeg))
    # When isolating to tmp_path, portable mode only searches tmp_path and its parents
    monkeypatch.setattr("karaoke_core.project.find_portable_ffmpeg", lambda root: find_local_ffmpeg(root))
    # Old project.json may still contain ffmpeg, but without ffmpeg_mode it now
    # defaults to portable and therefore must ignore that stale Conda path.
    cfg = ProjectConfig(ffmpeg=str(conda_ffmpeg), ffmpeg_mode="portable")
    assert cfg.resolve_ffmpeg(tmp_path) is None


def test_custom_mode_uses_only_selected_executable(tmp_path: Path, monkeypatch) -> None:
    custom = tmp_path / "portable" / "ffmpeg.exe"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"custom")
    monkeypatch.setenv("PATH", str(tmp_path / "other"))
    cfg = ProjectConfig(ffmpeg_mode="custom", ffmpeg=str(custom))
    assert cfg.resolve_ffmpeg(tmp_path) == custom.resolve()


def test_ffprobe_and_ffplay_must_be_siblings_not_path_fallback(tmp_path: Path, monkeypatch) -> None:
    ffmpeg = tmp_path / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"x")
    other = tmp_path / "conda" / "Library" / "bin"
    other.mkdir(parents=True)
    (other / "ffprobe.exe").write_bytes(b"bad")
    (other / "ffplay.exe").write_bytes(b"bad")
    monkeypatch.setenv("PATH", str(other))
    assert resolve_ffprobe(ffmpeg) is None
    assert resolve_ffplay(ffmpeg) is None
    sibling_probe = ffmpeg.with_name("ffprobe.exe")
    sibling_play = ffmpeg.with_name("ffplay.exe")
    sibling_probe.write_bytes(b"good")
    sibling_play.write_bytes(b"good")
    assert resolve_ffprobe(ffmpeg) == sibling_probe.resolve()
    assert resolve_ffplay(ffmpeg) == sibling_play.resolve()


def test_standalone_ffmpeg_strips_active_conda_prefix_from_child_path(tmp_path: Path, monkeypatch) -> None:
    conda = tmp_path / "conda" / "envs" / "mfa"
    conda_bin = conda / "Library" / "bin"
    conda_scripts = conda / "Scripts"
    standalone = tmp_path / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    standalone.parent.mkdir(parents=True)
    standalone.write_bytes(b"stub")
    other = tmp_path / "Windows" / "System32"
    monkeypatch.setenv("CONDA_PREFIX", str(conda))
    monkeypatch.setenv("PATH", os.pathsep.join((str(conda_bin), str(other), str(conda_scripts))))
    with patch("karaoke_core.media.sys.platform", "win32"):
        env = media_tool_subprocess_env(standalone)
    parts = env["PATH"].split(os.pathsep)
    assert parts[0] == str(standalone.parent.resolve())
    assert str(other) in parts
    assert str(conda_bin) not in parts
    assert str(conda_scripts) not in parts


def test_ffmpeg_inside_active_conda_keeps_environment_only_when_explicitly_selected(tmp_path: Path, monkeypatch) -> None:
    conda = tmp_path / "conda" / "envs" / "mfa"
    ffmpeg = conda / "Library" / "bin" / "ffmpeg.exe"
    ffmpeg.parent.mkdir(parents=True)
    ffmpeg.write_bytes(b"stub")
    raw_path = os.pathsep.join((str(ffmpeg.parent), str(tmp_path / "other")))
    monkeypatch.setenv("CONDA_PREFIX", str(conda))
    monkeypatch.setenv("PATH", raw_path)
    with patch("karaoke_core.media.sys.platform", "win32"):
        env = media_tool_subprocess_env(ffmpeg)
    assert env["PATH"] == raw_path

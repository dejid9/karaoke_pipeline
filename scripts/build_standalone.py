"""Standalone Builder for Karaoke / SPS Workbench.

Packages the application, trimmed FFmpeg, and a stripped standalone Python/MFA
runtime from the active or specified Conda environment into a fully portable
directory ready for flash drives or zip distribution without any external dependencies.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile


EXCLUDE_SITE_PACKAGES_PREFIXES = (
    "PyQt5",
    "pyqt5",
    "Qt5",
    "plotly",
    "matplotlib",
    "mpl_toolkits",
    "pyqtgraph",
    "pip",
    "setuptools",
    "pkg_resources",
    "wheel",
    "easy_install",
    "_distutils_hack",
    "distutils-precedence",
    "llvmlite",      # ~88 MB - not needed by MFA or GUI
    "numba",         # ~10 MB - not needed by MFA or GUI
)

EXCLUDE_EXTENSIONS = {
    ".pdb",
    ".pyc",
    ".pyo",
    ".lib",
    ".exp",
    ".ilk",
    ".h",
    ".hpp",
    ".c",
    ".cpp",
}

EXCLUDE_LIBRARY_BIN_FILES = {
    # Duplicate media encoders/tools (already supplied by tools/ffmpeg/bin)
    "x265.exe",
    "libx265.dll",
    "aom.dll",
    "aomenc.exe",
    "aomdec.exe",
    "SvtAv1Enc.dll",
    "avcodec-62.dll",
    "avfilter-11.dll",
    "avformat-62.dll",
    "avutil-60.dll",
    "swresample-6.dll",
    "swscale-9.dll",
    "ffmpeg.exe",
    "ffprobe.exe",
    "ffplay.exe",
    # Debug symbols
    "libcrypto-3-x64.pdb",
    "libssl-3-x64.pdb",
    # Server / cluster MKL variants (Intel Xeon server AVX-512, future AVX10, cluster ScaLAPACK)
    # Desktop PCs use mkl_avx2.3.dll or mkl_def.3.dll + mkl_core.3.dll (~184 MB saved)
    "mkl_avx512.3.dll",
    "mkl_avx10.3.dll",
    "mkl_vml_avx512.3.dll",
    "mkl_vml_avx10.3.dll",
    "mkl_scalapack_ilp64.2.dll",
    "mkl_scalapack_lp64.2.dll",
    # Unused Vulkan / shader compiler tools
    "shaderc.dll",
    "glslang.exe",
    "glslangValidator.exe",
    "spirv-cross.dll",
    # Unused SVG tools
    "rsvg-convert.exe",
    "rsvg-2.0-vs17.dll",
    "rsvg-2-2.dll",
}

EXCLUDE_LIBRARY_BIN_PREFIXES = (
    # Graphviz CLI tools and plugins (not used by MFA)
    "dot",
    "neato",
    "circo",
    "fdp",
    "sfdp",
    "twopi",
    "osage",
    "patchwork",
    "gv",
    "cgraph",
    "gvc",
    "pathplan",
    "xdot",
    "bcomps",
    "ccomps",
    "acyclic",
    "dijkstra",
    "tred",
    "unflatten",
    "spirv-",
)


def get_dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total / (1024 * 1024)


def find_conda_mfa_env() -> Path | None:
    # 1. Environment variable
    env_dir = os.environ.get("CONDA_PREFIX")
    if env_dir:
        p = Path(env_dir)
        if (p / "Scripts" / "mfa.exe").exists() or (p / "python.exe").exists():
            return p

    # 2. Typical Miniconda / Anaconda paths on Windows
    user_home = Path.home()
    candidates = [
        user_home / "miniconda3" / "envs" / "mfa",
        user_home / "anaconda3" / "envs" / "mfa",
        Path("C:/Users") / user_home.name / "miniconda3" / "envs" / "mfa",
        Path("C:/miniconda3/envs/mfa"),
        Path("C:/anaconda3/envs/mfa"),
    ]
    for c in candidates:
        if c.is_dir() and ((c / "Scripts" / "mfa.exe").exists() or (c / "python.exe").exists()):
            return c
    return None


def copy_tree_filtered(
    src: Path,
    dst: Path,
    *,
    exclude_prefixes: tuple[str, ...] = (),
    exclude_names: set[str] = set(),
    exclude_extensions: set[str] = set(),
    skip_dirs: set[str] = {"__pycache__", ".git", ".pytest_cache"},
) -> int:
    """Copy directory recursively with specific file and directory exclusions."""
    dst.mkdir(parents=True, exist_ok=True)
    copied_count = 0

    for item in src.iterdir():
        name = item.name
        if name in skip_dirs:
            continue
        if any(name.startswith(p) for p in exclude_prefixes):
            continue
        if name in exclude_names:
            continue
        if item.is_file() and item.suffix.lower() in exclude_extensions:
            continue

        target = dst / name
        if item.is_dir():
            copied_count += copy_tree_filtered(
                item,
                target,
                exclude_prefixes=exclude_prefixes,
                exclude_names=exclude_names,
                exclude_extensions=exclude_extensions,
                skip_dirs=skip_dirs,
            )
        else:
            try:
                shutil.copy2(item, target)
                copied_count += 1
            except OSError:
                pass

    return copied_count


def package_standalone(
    project_root: Path,
    output_dir: Path,
    source_env: Path,
    *,
    include_models: bool = True,
    create_zip: bool = False,
    slim: bool = False,
    verbose: bool = True,
) -> Path:
    start_time = time.time()
    output_dir = output_dir.resolve()
    print(f"=== Сборка автономного пакета Karaoke Workbench ===")
    print(f"Исходный каталог проекта: {project_root}")
    print(f"Целевой каталог: {output_dir}")
    print(f"Conda-окружение MFA: {source_env}")

    source_env_size = get_dir_size_mb(source_env)
    print(f"Размер исходного окружения: {source_env_size:.1f} MB")

    if output_dir.exists():
        print(f"Очистка существующего каталога {output_dir}...")
        shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Копирование кода приложения
    print("\n[1/6] Копирование ядра и GUI приложения...")
    for pkg in ("karaoke_core", "karaoke_gui"):
        src_pkg = project_root / pkg
        if src_pkg.exists():
            copy_tree_filtered(src_pkg, output_dir / pkg)
            print(f"  + {pkg}/")

    for root_file in (
        "run_gui.py",
        "run_portable.bat",
        "requirements.txt",
        "requirements-spectrogram.txt",
    ):
        sf = project_root / root_file
        if sf.exists():
            shutil.copy2(sf, output_dir / root_file)
            print(f"  + {root_file}")

    # Создание debug launcher
    debug_launcher = output_dir / "run_portable_debug.bat"
    debug_launcher.write_text(
        "@echo off\n"
        "setlocal\n"
        "title Karaoke SPS Workbench (Debug Console)\n"
        'echo [INFO] Запуск Karaoke SPS Workbench в режиме отладки...\n'
        'call "%~dp0run_portable.bat" %*\n'
        "if %ERRORLEVEL% neq 0 (\n"
        "    echo.\n"
        "    echo [ERROR] Приложение завершилось с кодом ошибки %ERRORLEVEL%.\n"
        "    pause\n"
        ")\n",
        encoding="utf-8",
    )
    print("  + run_portable_debug.bat")

    # Копирование скриптов проверки
    scripts_dir = output_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    if (project_root / "scripts" / "doctor.py").exists():
        shutil.copy2(project_root / "scripts" / "doctor.py", scripts_dir / "doctor.py")
        print("  + scripts/doctor.py")

    doctor_bat = output_dir / "doctor.bat"
    doctor_bat.write_text(
        "@echo off\n"
        "setlocal\n"
        'call "%~dp0run_portable.bat" "%~dp0scripts\\doctor.py" %*\n'
        "pause\n",
        encoding="utf-8",
    )
    print("  + doctor.bat")

    # 2. Копирование портативного FFmpeg
    print("\n[2/6] Копирование портативного FFmpeg...")
    ffmpeg_src = project_root / "tools" / "ffmpeg" / "bin"
    ffmpeg_dst = output_dir / "tools" / "ffmpeg" / "bin"
    if ffmpeg_src.is_dir():
        ffmpeg_dst.mkdir(parents=True, exist_ok=True)
        for f in ffmpeg_src.iterdir():
            if f.is_file():
                shutil.copy2(f, ffmpeg_dst / f.name)
        ffmpeg_size = get_dir_size_mb(ffmpeg_dst)
        print(f"  + tools/ffmpeg/bin/ ({ffmpeg_size:.1f} MB)")
    else:
        print("  [WARN] tools/ffmpeg/bin не найден в проекте!")

    # 3. Подготовка и урезание портативного Python/MFA runtime
    print("\n[3/6] Формирование облегченного runtime (удаление ненужных библиотек)...")
    runtime_dst = output_dir / "runtime"
    runtime_dst.mkdir(parents=True, exist_ok=True)

    # 3a. Корень runtime (python.exe, DLLs)
    for f in source_env.iterdir():
        if f.is_file() and f.suffix.lower() not in EXCLUDE_EXTENSIONS:
            shutil.copy2(f, runtime_dst / f.name)

    # 3b. DLLs/
    if (source_env / "DLLs").is_dir():
        copy_tree_filtered(source_env / "DLLs", runtime_dst / "DLLs", exclude_extensions=EXCLUDE_EXTENSIONS)

    # 3c. Lib/ (стандартная библиотека)
    if (source_env / "Lib").is_dir():
        lib_src = source_env / "Lib"
        lib_dst = runtime_dst / "Lib"
        lib_dst.mkdir(parents=True, exist_ok=True)
        for item in lib_src.iterdir():
            if item.name.lower() == "site-packages":
                continue
            if item.is_dir():
                copy_tree_filtered(item, lib_dst / item.name, exclude_extensions=EXCLUDE_EXTENSIONS)
            elif item.suffix.lower() not in EXCLUDE_EXTENSIONS:
                shutil.copy2(item, lib_dst / item.name)

    # 3d. Lib/site-packages/ (выборочное копирование без PyQt5, plotly, matplotlib, llvmlite, numba и т.д.)
    sp_src = source_env / "Lib" / "site-packages"
    sp_dst = runtime_dst / "Lib" / "site-packages"
    if sp_src.is_dir():
        exclude_sp = list(EXCLUDE_SITE_PACKAGES_PREFIXES)
        if slim:
            exclude_sp.append("sudachidict_core")
            print("  - Очистка Lib/site-packages (исключение PyQt5, plotly, matplotlib, pyqtgraph, pip, llvmlite, numba, sudachidict_core [slim])...")
        else:
            print("  - Очистка Lib/site-packages (исключение PyQt5, plotly, matplotlib, pyqtgraph, pip, llvmlite, numba)...")
        copy_tree_filtered(
            sp_src,
            sp_dst,
            exclude_prefixes=tuple(exclude_sp),
            exclude_extensions=EXCLUDE_EXTENSIONS,
        )

    # 3e. Library/bin/ (только необходимые DLL для Kaldi, libsndfile, openfst, mkl - без AVX512/AVX10/Scalapack и Graphviz)
    lib_bin_src = source_env / "Library" / "bin"
    lib_bin_dst = runtime_dst / "Library" / "bin"
    if lib_bin_src.is_dir():
        print("  - Очистка Library/bin (исключение MKL AVX512/AVX10/Scalapack, .pdb, Graphviz, дубликатов FFmpeg)...")
        lib_bin_dst.mkdir(parents=True, exist_ok=True)
        copy_tree_filtered(
            lib_bin_src,
            lib_bin_dst,
            exclude_names=EXCLUDE_LIBRARY_BIN_FILES,
            exclude_prefixes=EXCLUDE_LIBRARY_BIN_PREFIXES,
            exclude_extensions=EXCLUDE_EXTENSIONS,
        )

    # 3f. Library/lib/ (только Tcl/Tk ресурсы интерфейса: tcl8, tcl8.6, tk8.6, itcl - без 670MB .lib файлов!)
    lib_lib_src = source_env / "Library" / "lib"
    lib_lib_dst = runtime_dst / "Library" / "lib"
    if lib_lib_src.is_dir():
        lib_lib_dst.mkdir(parents=True, exist_ok=True)
        for tcl_item in lib_lib_src.iterdir():
            if tcl_item.is_dir() and any(tcl_item.name.lower().startswith(p) for p in ("tcl", "tk", "itcl", "dde", "reg")):
                copy_tree_filtered(tcl_item, lib_lib_dst / tcl_item.name, exclude_extensions=EXCLUDE_EXTENSIONS)
        print("  - Скопированы Tcl/Tk ресурсы интерфейса (без .lib файлов сборщика)")

    # 3g. Scripts/ (mfa.exe)
    scripts_src = source_env / "Scripts"
    scripts_dst = runtime_dst / "Scripts"
    if scripts_src.is_dir():
        scripts_dst.mkdir(parents=True, exist_ok=True)
        for f in scripts_src.iterdir():
            if f.is_file() and ("mfa" in f.name.lower() or f.name.lower().endswith(".exe")):
                shutil.copy2(f, scripts_dst / f.name)

    runtime_size = get_dir_size_mb(runtime_dst)
    saved_size = source_env_size - runtime_size
    print(f"  Размер итогового runtime: {runtime_size:.1f} MB (сэкономлено ~{saved_size:.1f} MB!)")

    # 4. Модели MFA
    print("\n[4/6] Размещение предобученных моделей MFA...")
    models_dst = output_dir / "data" / "mfa" / "pretrained_models"
    models_dst.mkdir(parents=True, exist_ok=True)
    models_src = Path.home() / "Documents" / "MFA" / "pretrained_models"
    if include_models and models_src.is_dir():
        models_copied = 0
        for m_type in ("acoustic", "dictionary", "g2p"):
            type_src = models_src / m_type
            type_dst = models_dst / m_type
            if type_src.is_dir():
                type_dst.mkdir(parents=True, exist_ok=True)
                for mf in type_src.iterdir():
                    if mf.is_file():
                        shutil.copy2(mf, type_dst / mf.name)
                        models_copied += 1
        print(f"  + Скопировано {models_copied} предобученных моделей в data/mfa/pretrained_models")
    else:
        print("  - Предобученные модели будут загружаться по требованию.")

    # 5. Шаблон проекта
    print("\n[5/6] Создание структуры каталогов рабочего пространства...")
    for d in ("source", "alignment", "subtitles", "cache", "exports"):
        (output_dir / d).mkdir(exist_ok=True)

    # 6. Проверка сборки
    print("\n[6/6] Верификация собранного пакета...")
    verify_cmd = [
        str(runtime_dst / "python.exe"),
        "-c",
        "import karaoke_core, karaoke_gui, numpy, tkinter; root=tkinter.Tk(); root.withdraw(); print('[OK] Core modules and Tkinter initialized successfully')",
    ]
    env = os.environ.copy()
    env["PATH"] = f"{runtime_dst / 'Library' / 'bin'};{runtime_dst / 'Scripts'};{runtime_dst};{env.get('PATH', '')}"
    env["PYTHONPATH"] = str(output_dir)
    if (runtime_dst / "Library" / "lib" / "tcl8.6").is_dir():
        env["TCL_LIBRARY"] = str(runtime_dst / "Library" / "lib" / "tcl8.6")
        env["TK_LIBRARY"] = str(runtime_dst / "Library" / "lib" / "tk8.6")

    try:
        proc = subprocess.run(verify_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        if proc.returncode == 0:
            print(f"  {proc.stdout.strip()}")
        else:
            print(f"  [WARN] Ошибка импорта: {proc.stderr.strip()}")
    except Exception as exc:
        print(f"  [WARN] Не удалось выполнить тестовый запуск: {exc}")

    # Проверка mfa.exe
    mfa_exe = runtime_dst / "Scripts" / "mfa.exe"
    if mfa_exe.exists():
        try:
            mfa_proc = subprocess.run([str(mfa_exe), "version"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=50)
            if mfa_proc.returncode == 0:
                print(f"  [OK] MFA version: {mfa_proc.stdout.strip()}")
            else:
                print(f"  [WARN] MFA вернул код {mfa_proc.returncode}: {mfa_proc.stderr.strip()}")
        except Exception as exc:
            print(f"  [WARN] Проверка MFA не удалась: {exc}")

    total_size = get_dir_size_mb(output_dir)
    print(f"\n==========================================")
    print(f"Сборка завершена успешно за {time.time() - start_time:.1f} сек.")
    print(f"Итоговый размер дистрибутива: {total_size:.1f} MB")
    print(f"Расположение: {output_dir}")
    print(f"==========================================")

    # Создание zip-архива при необходимости
    if create_zip:
        zip_path = output_dir.with_suffix(".zip")
        print(f"\nСоздание zip-архива: {zip_path}...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _, files in os.walk(output_dir):
                for f in files:
                    full_p = Path(root) / f
                    rel_p = full_p.relative_to(output_dir.parent)
                    zf.write(full_p, rel_p)
        zip_size = get_dir_size_mb(zip_path)
        print(f"Zip-архив готов: {zip_path} ({zip_size:.1f} MB)")

    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка standalone-версии Karaoke SPS Workbench")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dist" / "karaoke_pipeline_portable",
        help="Целевой каталог для портативного дистрибутива",
    )
    parser.add_argument(
        "--conda-env",
        "-e",
        type=Path,
        default=None,
        help="Путь к окружению Conda с MFA (по умолчанию определяется автоматически)",
    )
    parser.add_argument(
        "--no-models",
        action="store_true",
        help="Не включать локальные предобученные модели MFA",
    )
    parser.add_argument(
        "--slim",
        action="store_true",
        help="Максимально облегченная сборка (исключает 207 МБ словарь Sudachi для японского языка)",
    )
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Создать zip-архив после сборки",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    env_path = args.conda_env or find_conda_mfa_env()
    if not env_path or not env_path.exists():
        print(f"[ERROR] Окружение Conda MFA не найдено! Укажите через --conda-env.", file=sys.stderr)
        return 1

    package_standalone(
        project_root,
        args.output_dir,
        env_path,
        include_models=not args.no_models,
        create_zip=args.zip,
        slim=args.slim,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

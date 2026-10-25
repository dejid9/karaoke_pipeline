@echo off
setlocal enabledelayedexpansion
title Karaoke SPS Workbench (Portable)

set "APP_DIR=%~dp0"
set "PYTHONPATH=%APP_DIR%"

:: 1. Add portable FFmpeg to PATH if present
if exist "%APP_DIR%tools\ffmpeg\bin" (
    set "PATH=%APP_DIR%tools\ffmpeg\bin;!PATH!"
) else if exist "%APP_DIR%ffmpeg\bin" (
    set "PATH=%APP_DIR%ffmpeg\bin;!PATH!"
)

:: 2. Set portable MFA data directory if present
if exist "%APP_DIR%data\mfa" (
    set "MFA_ROOT_DIR=%APP_DIR%data\mfa"
)

:: 3. Detect Python runtime (priority: local portable runtime -> conda mfa -> system python)
if exist "%APP_DIR%runtime\python.exe" (
    set "PY_EXE=%APP_DIR%runtime\python.exe"
    set "PATH=%APP_DIR%runtime\Library\bin;%APP_DIR%runtime\Scripts;%APP_DIR%runtime;!PATH!"
    if exist "%APP_DIR%runtime\Library\lib\tcl8.6" (
        set "TCL_LIBRARY=%APP_DIR%runtime\Library\lib\tcl8.6"
        set "TK_LIBRARY=%APP_DIR%runtime\Library\lib\tk8.6"
    )
    if exist "%APP_DIR%runtime\Scripts\mfa.exe" (
        set "MFA=%APP_DIR%runtime\Scripts\mfa.exe"
    )
    goto :LAUNCH
)

if exist "%APP_DIR%tools\python\python.exe" (
    set "PY_EXE=%APP_DIR%tools\python\python.exe"
    set "PATH=%APP_DIR%tools\python\Library\bin;%APP_DIR%tools\python\Scripts;%APP_DIR%tools\python;!PATH!"
    goto :LAUNCH
)

:: Check for existing conda mfa environment
if exist "%USERPROFILE%\miniconda3\envs\mfa\python.exe" (
    set "PY_EXE=%USERPROFILE%\miniconda3\envs\mfa\python.exe"
    set "PATH=%USERPROFILE%\miniconda3\envs\mfa\Library\bin;%USERPROFILE%\miniconda3\envs\mfa\Scripts;%USERPROFILE%\miniconda3\envs\mfa;!PATH!"
    set "MFA=%USERPROFILE%\miniconda3\envs\mfa\Scripts\mfa.exe"
    goto :LAUNCH
)

:: Check conda command
where conda >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [INFO] Running via conda mfa environment...
    conda run --no-capture-output -n mfa python "%APP_DIR%run_gui.py" %*
    goto :END
)

:: Fallback to system python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_EXE=python"
    goto :LAUNCH
)

echo [ERROR] Python not found! Neither portable runtime nor Conda nor system Python was detected.
pause
exit /b 1

:LAUNCH
if not "%~1"=="" (
    if "%~x1"==".py" (
        "%PY_EXE%" %*
        goto :END
    )
)
"%PY_EXE%" "%APP_DIR%run_gui.py" %*

:END
exit /b %ERRORLEVEL%

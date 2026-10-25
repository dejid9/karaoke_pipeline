@echo off
setlocal
set "ENV_NAME=%~1"
if not defined ENV_NAME set "ENV_NAME=%KARAOKE_CONDA_ENV%"
if not defined ENV_NAME set "ENV_NAME=mfa"
set "CONDA_CMD=%CONDA_EXE%"
if not defined CONDA_CMD set "CONDA_CMD=conda"
"%CONDA_CMD%" run --no-capture-output -n "%ENV_NAME%" python "%~dp0run_gui.py"
exit /b %ERRORLEVEL%

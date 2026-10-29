@echo off
REM One-time setup for the PageVoice Server, run on first launch (and safe to
REM re-run). Installs the uv toolchain if needed, picks the CPU or GPU build of
REM PyTorch, and syncs all dependencies (including the tray app).

cd /d "%~dp0"
title PageVoice Server - Setup

REM Keep uv's managed Python on a local, non-redirected path. Some Windows
REM profiles redirect/sync %APPDATA% (Roaming) to OneDrive or a network share,
REM which uv can't traverse ("untrusted mount point", os error 448).
set "UV_PYTHON_INSTALL_DIR=%LOCALAPPDATA%\uv\python"

echo Setting up the PageVoice Server.
echo.

where uv >nul 2>nul
if %errorlevel% neq 0 (
  if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  ) else (
    echo Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
  )
)

REM Remove a stale/broken .venv (no Python executable) left by a failed run.
if exist ".venv" if not exist ".venv\Scripts\python.exe" rmdir /s /q ".venv"

REM Only offer the GPU build if an NVIDIA GPU is actually present. nvidia-smi
REM ships with the driver and succeeds only when a usable GPU is installed, so
REM machines without one don't download ~2.5 GB of CUDA torch for nothing (it
REM would just fall back to CPU anyway).
set "USEGPU=n"
if /i "%~1"=="--choose-device" goto chooseDevice
if exist "gpu.flag" (
  set "USEGPU=y"
  goto syncDependencies
)
if exist ".venv\Scripts\python.exe" goto syncDependencies
:chooseDevice
nvidia-smi >nul 2>nul
if %errorlevel% equ 0 (
  echo An NVIDIA GPU was detected.
  echo The GPU build downloads about 2.5 GB more and speeds up long narration;
  echo the CPU build is smaller and already faster than real time for most use.
  set /p USEGPU="Install the GPU (CUDA) build? [y/N]: "
) else (
  echo No NVIDIA GPU detected -- installing the CPU build.
)
:syncDependencies
echo.

if /i "%USEGPU%"=="y" (
  echo Installing the GPU build. This downloads several GB and can take a while...
  type nul > gpu.flag
  uv sync --group tray --extra cuda
) else (
  if exist gpu.flag del gpu.flag
  echo Installing the CPU build. This downloads several hundred MB...
  uv sync --group tray
)

if %errorlevel% neq 0 (
  echo.
  echo Setup failed. Check your internet connection, then run setup again.
  pause
  exit /b 1
)

echo.
if exist "dependency-version.txt" copy /y "dependency-version.txt" ".environment-ready" >nul
echo Setup complete.
exit /b 0

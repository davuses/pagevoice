@echo off
REM PageVoice Server - easy start (Windows). Double-click to run the server in a
REM visible console. (The installer's tray icon is the background alternative.)
REM First run builds the environment and asks whether to use the CPU or GPU build.

cd /d "%~dp0"
title PageVoice Server

REM Keep uv's managed Python on a local, non-redirected path (see setup.bat).
set "UV_PYTHON_INSTALL_DIR=%LOCALAPPDATA%\uv\python"

REM Make sure uv is on PATH (setup installs it to %USERPROFILE%\.local\bin).
where uv >nul 2>nul
if %errorlevel% neq 0 set "PATH=%USERPROFILE%\.local\bin;%PATH%"

REM First run: build the environment (setup.bat prompts for CPU vs GPU).
if not exist ".venv\Scripts\python.exe" call "%~dp0setup.bat" || exit /b 1

REM Use the GPU build at runtime if it was chosen during setup.
set "GPUARG="
if exist "gpu.flag" set "GPUARG=--extra cuda"

echo.
echo Server is starting. Keep this window open while you use the extension.
echo Close this window to stop the server.
echo If something goes wrong, the log is at %LOCALAPPDATA%\KokoroTTSServer\server.log
echo.
uv run --group tray %GPUARG% python -m uvicorn server:app --host 127.0.0.1 --port 18001

echo.
echo The server has stopped.
pause

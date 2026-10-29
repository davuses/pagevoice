#!/usr/bin/env bash
# PageVoice Server — easy start (Linux).
#
# Run this file to start the server (double-click and choose "Run in Terminal"
# if your file manager offers it, or run ./start-server.sh from a terminal).
# The first run installs the "uv" toolchain and downloads the speech model
# (a few hundred MB), so it can take several minutes; later runs start quickly.
#
# Keep this window open while you use the extension. Close it (or press Ctrl+C)
# to stop the server.

cd "$(dirname "$0")" || exit 1

pause_on_exit() {
  echo
  read -r -p "Press Enter to close this window..."
}

echo "Starting PageVoice Server setup..."
echo

# Make sure uv (the Python toolchain manager) is available. It manages its own
# Python and dependencies, so nothing else needs to be installed first.
if ! command -v uv >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "Installing uv (one-time setup)..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
      echo
      echo "Could not install uv. Check your internet connection and try again."
      pause_on_exit
      exit 1
    fi
    export PATH="$HOME/.local/bin:$PATH"
  fi
fi

echo "Installing dependencies (first run can take several minutes)..."
if ! uv sync; then
  echo
  echo "Could not install dependencies. Check your internet connection and try again."
  pause_on_exit
  exit 1
fi

echo
echo "Server is starting. Keep this window open while you use the extension."
echo "When you see 'Application startup complete', it's ready to use."
echo "Close this window (or press Ctrl+C) to stop the server."
echo
# Run uvicorn as a module (`python -m`) rather than via uv's console-script
# trampoline (`uv run uvicorn`), which can fail to canonicalize its path when the
# project lives under a folder with non-ASCII characters (e.g. a Chinese
# username on Windows).
uv run python -m uvicorn server:app --host 127.0.0.1 --port 18001

echo
echo "The server has stopped."
pause_on_exit

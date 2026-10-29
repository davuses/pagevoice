"""System-tray launcher for the PageVoice Server (Windows background mode).

Runs the FastAPI server in a background thread and shows a tray icon, so the
server can run with no visible console window. Launched hidden via
start-tray.vbs (also used for auto-start on login). Needs the optional 'tray'
dependency group:  uv sync --group tray

The tray icon doubles as a status light: green = ready, amber = starting, red =
not responding. "Open log file" opens the diagnostic log so a stuck or failed
start can be understood (there is no console in this mode).
"""

import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

import pystray
import uvicorn
from PIL import Image, ImageDraw

from app_logging import log_file_path, setup_logging
from server import app

setup_logging()
logger = logging.getLogger("kokoro.tray")

HOST = "127.0.0.1"
PORT = 18001

# Status -> (ring color, human label).
STATUS = {
    "starting": ((234, 179, 8, 255), "starting…"),
    "running": ((34, 197, 94, 255), "running"),
    "failed": ((239, 68, 68, 255), "not responding"),
}


def make_icon_image(ring=(59, 130, 246, 255)):
    """A small speaker glyph, drawn so we don't have to ship a binary asset.
    The disc color encodes server status."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((6, 6, 58, 58), fill=ring)
    d.polygon(
        [(22, 27), (30, 27), (40, 18), (40, 46), (30, 37), (22, 37)], fill="white"
    )
    d.line((44, 24, 48, 40), fill="white", width=3)
    return img


def port_in_use(host, port):
    """True if something is already listening — avoids a second server instance."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def probe_health():
    """Return 'running', 'starting', or None (unreachable) from /health."""
    try:
        with urllib.request.urlopen(
            f"http://{HOST}:{PORT}/health", timeout=1
        ) as resp:
            import json

            data = json.load(resp)
            return "running" if data.get("ready") else "starting"
    except Exception:
        return None


def open_log():
    path = str(log_file_path())
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: PGH004 - Windows-only
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        logger.exception("Could not open log file at %s", path)


class ServerThread:
    """Runs uvicorn in a background daemon thread.

    uvicorn skips installing signal handlers when not on the main thread, so
    this is safe; we stop it cooperatively via ``should_exit``. ``log_config``
    is None so uvicorn uses the logging we already configured (its records then
    reach our log file) instead of installing a console-only config.
    """

    def __init__(self):
        config = uvicorn.Config(
            app, host=HOST, port=PORT, log_level="info", log_config=None
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.should_exit = True

    def alive(self):
        return self.thread.is_alive()


def main():
    # If a server is already up (manual run, or a second launch), just show the
    # tray without starting another one.
    server = None if port_in_use(HOST, PORT) else ServerThread()
    if server:
        server.start()

    state = {"status": "starting"}

    def status_label():
        return STATUS.get(state["status"], STATUS["starting"])[1]

    def on_open(icon, item):
        webbrowser.open(f"http://{HOST}:{PORT}/voices")

    def on_open_log(icon, item):
        open_log()

    def on_quit(icon, item):
        if server:
            server.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: f"PageVoice Server — {status_label()}", None, enabled=False
        ),
        pystray.MenuItem(f"http://{HOST}:{PORT}", None, enabled=False),
        pystray.MenuItem("Open test page", on_open),
        pystray.MenuItem("Open log file", on_open_log),
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        "kokoro-tts", make_icon_image(STATUS["starting"][0]), "PageVoice Server", menu
    )

    def poll():
        # Give the server a moment to bind before the first probe.
        while True:
            health = probe_health()
            if health is not None:
                status = health
            elif server is not None and not server.alive():
                status = "failed"  # worker thread crashed
            else:
                # Not reachable yet, but nothing has crashed — still coming up.
                status = "starting"

            if status != state["status"]:
                state["status"] = status
                color, label = STATUS[status]
                icon.icon = make_icon_image(color)
                icon.title = f"PageVoice Server — {label}"
                try:
                    icon.update_menu()
                except Exception:
                    pass
                logger.info("Server status: %s", label)
            time.sleep(3)

    threading.Thread(target=poll, daemon=True).start()
    icon.run()


if __name__ == "__main__":
    main()

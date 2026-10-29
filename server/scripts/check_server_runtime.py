"""Start an isolated server, check real HTTP synthesis/cancellation, then stop it.

Run with uv run python scripts/check_server_runtime.py --output-dir /tmp/pagevoice-check.
Downloads weights on first use. Never touches an already-running user server.
"""

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = (args.output_dir or Path(tempfile.mkdtemp(prefix="pagevoice-runtime-"))).resolve()
    output.mkdir(parents=True, exist_ok=True)
    server_dir = Path(__file__).resolve().parents[1]
    # Bind the socket before spawning so the test cannot collide with another
    # server. Uvicorn inherits the listening descriptor on macOS/Linux.
    with socket.socket() as listener, (output / "server.log").open("w") as log:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        env = {**os.environ, "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"}
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app", "--fd", str(listener.fileno())],
            cwd=server_dir, env=env, pass_fds=(listener.fileno(),), stdout=log, stderr=log,
        )
        try:
            with httpx.Client(trust_env=False, timeout=2) as client:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError(f"Server exited early; see {output / 'server.log'}")
                    try:
                        response = client.get(f"{url}/health")
                        if response.status_code == 200 and response.json().get("ready"):
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Server did not become ready within 60 seconds")
            subprocess.run(
                [sys.executable, "scripts/smoke_tts_api.py", "--server", url,
                 "--output-dir", str(output), "--cancel-timeout", "60"],
                cwd=server_dir, env=env, check=True, timeout=600,
            )
            print(f"PASS isolated server runtime; samples and log: {output}", flush=True)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()

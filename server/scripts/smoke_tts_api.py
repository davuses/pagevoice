"""Opt-in real HTTP streaming/cancellation check; start PageVoice Server first."""

import argparse
import base64
import json
import time
import httpx
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--server", default="http://127.0.0.1:18001")
args = parser.parse_args()
# Bypass environment proxies so closing the client actually closes the server connection.
with httpx.Client(base_url=args.server, timeout=120, trust_env=False) as client:
    for engine, voice in [
        ("pocket", "alba"),
        ("pocket", "anna"),
        ("pocket", "michael"),
        ("kokoro", "bf_emma"),
    ]:
        response = client.post(
            "/tts/stream",
            json={
                "engine": engine,
                "voice": voice,
                "text": "Hello world. This is another sentence.",
            },
        )
        response.raise_for_status()
        lines = [json.loads(l) for l in response.text.splitlines()]
        assert lines[-1] == {"done": True}, lines[-1]
        chunks = [l for l in lines if "pcm_b64" in l]
        assert chunks and any(
            np.frombuffer(base64.b64decode(l["pcm_b64"]), dtype="<i2").any()
            for l in chunks
        )
        if engine == "pocket":
            assert len([l for l in lines if l.get("type") == "sentence_start"]) == 2
            assert len([l for l in lines if l.get("type") == "sentence_end"]) == 2
        print("PASS real API", engine, voice, len(chunks), flush=True)
    with client.stream(
        "POST",
        "/tts/stream",
        json={
            "engine": "pocket",
            "voice": "alba",
            "text": "This is a very long reading test. " * 400,
        },
    ) as stream:
        for line in stream.iter_lines():
            if "pcm_b64" in line:
                break
    started = time.monotonic()
    response = client.post(
        "/tts/stream",
        json={
            "engine": "kokoro",
            "voice": "af_bella",
            "text": "The next engine can speak.",
        },
    )
    assert json.loads(response.text.splitlines()[-1]) == {"done": True}
    assert time.monotonic() - started < 15
    print("PASS real cancellation releases shared engine lock", flush=True)

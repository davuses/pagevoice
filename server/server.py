import asyncio
import base64
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from concurrent.futures import TimeoutError as FutureTimeout

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app_logging import setup_logging
from engines import ENGINES, engine_info

setup_logging()
logger = logging.getLogger(__name__)

# Signals that the HTTP server accepts requests; models load lazily.
ready_event = threading.Event()

# Reject oversized bodies: each request holds the single inference lock for the
# whole stream, so an unbounded text could pin the GPU indefinitely.
MAX_TEXT_LENGTH = 50_000


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Accept requests immediately; each engine loads on its first request.
    ready_event.set()
    yield
    ready_event.clear()


app = FastAPI(title="PageVoice Server", version="3.0.0", lifespan=lifespan)

# Comma-separated list of allowed origins, e.g.
# ALLOWED_ORIGINS="https://example.com,https://app.example.com".
# A wildcard with credentials is rejected by browsers, so we don't combine
# them: default to allowing any origin *without* credentials.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The Kokoro pipeline holds a single model instance and is not safe to run
# concurrently, so serialize inference with a lock. Each request still runs
# off the event loop (in a worker thread) so the server stays responsive.
_inference_lock = asyncio.Lock()


class TextRequest(BaseModel):
    text: str
    voice: str
    engine: str = "kokoro"
    # Playback rate; 1.0 is natural. Optional so older clients that omit it keep
    # working. Out-of-range values are rejected by validation (422).
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.get("/health")
def health():
    """HTTP readiness and independent model loading status."""
    return {
        "ready": ready_event.is_set(),
        "engines": [engine_info(e) for e in ENGINES.values()],
    }


@app.get("/engines")
def engines():
    return {"engines": [engine_info(e) for e in ENGINES.values()]}


@app.get("/voices")
def voices(engine: str = "kokoro"):
    """Return the list of allowed voices.

    This is the single source of truth for the voice list (the model owns it);
    the extension can fetch it to populate its dropdown instead of hardcoding.
    Cheap to call — reading the class attribute does not load the model.
    """
    if engine not in ENGINES:
        raise HTTPException(status_code=400, detail="Unknown speech engine")
    return {"voices": ENGINES[engine].voices}


@app.post("/tts/stream")
async def tts_stream(body: TextRequest, request: Request):
    """Stream local speech as NDJSON PCM chunks and optional sentence events.

    Each line is a JSON object:
      {"sr": 24000, "index": i, "pcm_b64": "<base64 Int16 mono PCM>"}
    terminated by {"done": true}, or {"error": "..."} if generation fails
    mid-stream (the HTTP status is already 200 by then, so failures are
    reported in-band).
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="No text provided")
    if len(body.text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long (max {MAX_TEXT_LENGTH} characters)",
        )
    if body.engine not in ENGINES:
        raise HTTPException(status_code=400, detail="Unknown speech engine")
    engine = ENGINES[body.engine]
    if not engine.supports_speed and body.speed != 1.0:
        raise HTTPException(
            status_code=400, detail="This engine does not support synthesis speed"
        )
    if body.voice not in engine.voices:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice. Allowed: {engine.voices}",
        )

    async def ndjson():
        # Both models are serialized. Bounded transport backpressure keeps a
        # slow/disconnected client from accumulating unlimited generated PCM.
        async with _inference_lock:
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue(maxsize=8)
            cancel = threading.Event()
            DONE = object()

            def send(item):
                if cancel.is_set():
                    return False
                pending = asyncio.run_coroutine_threadsafe(queue.put(item), loop)
                while not cancel.is_set():
                    try:
                        pending.result(timeout=0.1)
                        return True
                    except FutureTimeout:
                        continue
                pending.cancel()
                return False

            def produce():
                try:
                    for pair in engine.stream(
                        body.text, body.voice, body.speed, cancel
                    ):
                        if not send(pair):
                            break
                    send(DONE)
                except Exception as exc:  # surfaced as an in-band error line
                    logger.exception("%s streaming generation failed", engine.name)
                    send(exc)

            fut = loop.run_in_executor(None, produce)
            index = 0
            try:
                while True:
                    # StreamingResponse owns the ASGI disconnect listener.
                    # Reading receive() here as well can consume its disconnect
                    # message and leave generation running after the tab closes.
                    item = await queue.get()
                    if item is DONE:
                        yield json.dumps({"done": True}) + "\n"
                        break
                    if isinstance(item, Exception):
                        yield json.dumps({"error": str(item)}) + "\n"
                        break
                    if "audio" not in item:
                        yield json.dumps(item) + "\n"
                        continue
                    audio = item["audio"]
                    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                    yield (
                        json.dumps(
                            {
                                "sr": item["sr"],
                                "index": index,
                                "pcm_b64": base64.b64encode(pcm16).decode("ascii"),
                                **({"text": item["text"]} if "text" in item else {}),
                                **(
                                    {"sentence_id": item["sentence_id"]}
                                    if "sentence_id" in item
                                    else {}
                                ),
                            }
                        )
                        + "\n"
                    )
                    index += 1
            finally:
                # Signal the worker to stop and wait for it to actually exit
                # before releasing the lock, so the next request can't start GPU
                # work while this generation is still finishing its last chunk.
                # Loop through cancellation: if this coroutine is itself being
                # cancelled, keep waiting until the worker thread is really done.
                cancel.set()
                while not fut.done():
                    try:
                        await asyncio.shield(fut)
                    except asyncio.CancelledError:
                        pass

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")

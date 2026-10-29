"""Opt-in real-model check: run from server/ with uv run python scripts/smoke_tts_environment.py.

Downloads model weights/preset voices on first use. Kept outside pytest so the
normal API tests remain fast and do not require model downloads.
"""

import argparse
import importlib.metadata
from pathlib import Path
import sys
import tempfile
import time
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kokoro_model import SAMPLE_RATE, kokoro_model
from engines import POCKET_MODEL


TEXT = "Hello world. Both speech engines share the same Python environment."


def check_audio(audio):
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise RuntimeError("Expected nonempty, finite mono audio")
    if not np.any(audio):
        raise RuntimeError("Generated audio is entirely silent")
    return audio


def save_audio(path, audio, sample_rate):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def check_kokoro(voice, output_dir, suffix):
    started = time.perf_counter()
    chunks = [audio for _, audio in kokoro_model.stream_audio(TEXT, voice)]
    if not chunks:
        raise RuntimeError("Kokoro produced no audio chunks")
    audio = check_audio(np.concatenate(chunks))
    save_audio(output_dir / f"kokoro-{voice}-{suffix}.wav", audio, SAMPLE_RATE)
    print(
        f"PASS Kokoro {voice}: {audio.size / SAMPLE_RATE:.2f}s audio, "
        f"{time.perf_counter() - started:.2f}s elapsed",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--pocket-model", default=POCKET_MODEL)
    parser.add_argument("--pocket-voice", default="alba")
    args = parser.parse_args()
    output_dir = args.output_dir or Path(tempfile.mkdtemp(prefix="tts-smoke-"))
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Audio samples: {output_dir.resolve()}", flush=True)
    for package in ("numpy", "kokoro", "pocket-tts", "torch", "spacy", "thinc"):
        print(f"{package}=={importlib.metadata.version(package)}", flush=True)

    # Load Kokoro first, then Pocket, then synthesize with Kokoro again. This
    # catches import-order/process-wide effects that isolated tests would miss.
    check_kokoro("af_bella", output_dir, "before-pocket")
    check_kokoro("bf_emma", output_dir, "before-pocket")

    from pocket_tts import TTSModel

    print(f"Loading Pocket model {args.pocket_model}...", flush=True)
    model = TTSModel.load_model(language=args.pocket_model)
    voice = model.get_state_for_audio_prompt(args.pocket_voice)
    chunks = []
    started = time.perf_counter()
    first_audio = None
    for chunk in model.generate_audio_stream(voice, TEXT, copy_state=True):
        if first_audio is None:
            first_audio = time.perf_counter() - started
        chunks.append(chunk.detach().cpu().numpy())
    if not chunks:
        raise RuntimeError("Pocket produced no audio chunks")
    audio = check_audio(np.concatenate(chunks))
    save_audio(output_dir / "pocket.wav", audio, model.sample_rate)
    print(
        f"PASS Pocket: {len(chunks)} chunks, {audio.size / model.sample_rate:.2f}s audio, "
        f"{first_audio:.2f}s first audio, {time.perf_counter() - started:.2f}s elapsed",
        flush=True,
    )

    check_kokoro("af_bella", output_dir, "after-pocket")
    check_kokoro("bf_emma", output_dir, "after-pocket")
    print("PASS both engines generated audio in one Python process", flush=True)


if __name__ == "__main__":
    main()

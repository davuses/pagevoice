"""Save repeatable ending comparisons; no ASR or automatic speech-quality verdict.

Run from server/: uv run python scripts/diagnose_pocket_endings.py
Use --models english_2026-09_2 english_2026-10 for the upstream regression.
Weights download on first use. JSON records PCM lengths and tail energy;
listen to the WAVs to judge pronunciation and unwanted trailing speech.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines import POCKET_MODEL
from scripts.smoke_tts_environment import save_audio


TEXTS = [
    "Nobody in math is ever going to forget the year 2026.",
    "Nobody in math is ever going to forget the year twenty twenty-six.",
    "The leaves are ablaze here in Ithaca, fiery reds and oranges.",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=[POCKET_MODEL])
    parser.add_argument("--voices", nargs="+", default=["alba"])
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    output = args.output_dir or Path(tempfile.mkdtemp(prefix="pocket-endings-"))
    output.mkdir(parents=True, exist_ok=True)
    print(f"Samples: {output.resolve()}", flush=True)
    torch.set_num_threads(2)
    from pocket_tts import TTSModel

    records = []
    for model_name in args.models:
        model = TTSModel.load_model(language=model_name)
        for voice in args.voices:
            state = model.get_state_for_audio_prompt(voice)
            for seed in range(args.seeds):
                for index, text in enumerate(TEXTS):
                    torch.manual_seed(seed)
                    chunks = [chunk.detach().cpu().numpy() for chunk in
                              model.generate_audio_stream(state, text, copy_state=True)]
                    audio = np.concatenate(chunks)
                    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
                    filename = f"{model_name}-{voice}-seed{seed}-text{index}.wav"
                    save_audio(output / filename, audio, model.sample_rate)
                    tail = audio[-model.sample_rate // 20:]
                    record = dict(model=model_name, voice=voice, seed=seed, text=text,
                                  file=filename, samples=len(audio),
                                  sample_rate=model.sample_rate,
                                  seconds=len(audio) / model.sample_rate,
                                  tail_50ms_rms=float(np.sqrt(np.mean(tail ** 2))),
                                  pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest())
                    records.append(record)
                    (output / "results.json").write_text(json.dumps(records, indent=2))
                    print(json.dumps(record), flush=True)
        del model


if __name__ == "__main__":
    main()

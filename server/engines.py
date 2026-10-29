"""Small engine registry; importing this module never downloads model weights."""

import numpy as np

from kokoro_model import SAMPLE_RATE, kokoro_model

# 09_2 was trained with truncated sentence-final numbers. Pocket 4.0.1
# includes retrained weights; pin these explicitly rather than a moving alias.
POCKET_MODEL = "english_2026-10"


class KokoroEngine:
    id = "kokoro"
    name = "Kokoro"
    supports_speed = True
    voices = kokoro_model.ALLOWED_VOICES

    @property
    def loaded(self):
        return bool(kokoro_model.pipelines)

    def stream(self, text, voice, speed, cancel):
        for words, audio in kokoro_model.stream_audio(text, voice, speed=speed):
            if cancel.is_set():
                return
            yield {"audio": audio, "sr": SAMPLE_RATE, "text": words}


class PocketEngine:
    id = "pocket"
    name = "Pocket TTS"
    model_id = POCKET_MODEL
    supports_speed = False
    # Presets from the official catalog; no arbitrary paths/URLs are accepted.
    voices = [
        "alba", "anna", "azelma", "bill_boerst", "charles", "cosette",
        "eponine", "eve", "george", "jane", "mary", "michael",
    ]

    def __init__(self):
        self.model = None
        self.voice_states = {}

    @property
    def loaded(self):
        return self.model is not None

    def stream(self, text, voice, speed, cancel):
        if self.model is None:
            from pocket_tts import TTSModel

            self.model = TTSModel.load_model(language=self.model_id)
        if cancel.is_set():
            return
        if voice not in self.voice_states:
            self.voice_states[voice] = self.model.get_state_for_audio_prompt(voice)
        state = self.voice_states[voice]
        # The project already depends on spaCy's English model. Its sentence
        # tokenizer handles abbreviations/quotes better than punctuation alone.
        import spacy

        if not hasattr(self, "sentencizer"):
            self.sentencizer = spacy.blank("en")
            self.sentencizer.add_pipe("sentencizer")
        self.sentencizer.max_length = max(self.sentencizer.max_length, len(text) + 1)
        for index, sentence in enumerate(self.sentencizer(text).sents):
            words = sentence.text.strip()
            if cancel.is_set():
                return
            if not words:
                continue
            yield {"type": "sentence_start", "sentence_id": index, "text": words}
            for audio in self.model.generate_audio_stream(
                state,
                words,
                copy_state=True,
                stop=cancel,
            ):
                if cancel.is_set():
                    return
                yield {
                    "audio": np.asarray(audio.detach().cpu(), dtype=np.float32),
                    "sr": self.model.sample_rate,
                    "sentence_id": index,
                }
            if cancel.is_set():
                return
            yield {"type": "sentence_end", "sentence_id": index}


ENGINES = {engine.id: engine for engine in (KokoroEngine(), PocketEngine())}


def engine_info(engine):
    return {
        "id": engine.id,
        "name": engine.name,
        "installed": True,
        "loaded": engine.loaded,
        **({"model": engine.model_id} if hasattr(engine, "model_id") else {}),
        "capabilities": {
            "speed": engine.supports_speed,
            "streaming": True,
            "sentence_highlighting": True,
        },
    }

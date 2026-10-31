"""Hearing the wake word. Feed a detector 50 ms audio frames; it says when it heard the
phrase. No mic, no threads, no UI: the listener in localflow.py owns those.

"Hey Jarvis" uses openWakeWord's small offline model, which scores every 80 ms of
audio, so it hears you at a normal speaking volume. Any other phrase (or a missing
model) uses speech bursts instead: short bursts of speech (0.35-3 s, then a pause)
are transcribed with the speech model and compared with the phrase by how they
sound, so "he whispered" still counts as "Hey Wispr"."""
import difflib
import logging
import re
import time

import numpy as np

log = logging.getLogger("localflow")

SR, FRAME = 16000, 800
# sensitivity -> (model score, speech-burst match) needed to wake
SENSITIVITY = {"low": (0.7, 0.9), "normal": (0.5, 0.85), "high": (0.3, 0.75)}
MODEL_PHRASES = {"hey jarvis": "hey_jarvis"}


def _phrase_key(phrase):
    return " ".join(phrase.lower().split()).strip(" .!,")


def _sound_shape(text):
    """Rough sound of each word: first letter + consonants ("whispered" -> "wsprd")."""
    words = re.sub(r"[^a-z ]", " ", text.lower().replace("wh", "w")).split()
    return [w[0] + re.sub(r"[aeiouy]", "", w[1:]) for w in words]


def wake_score(text, phrase):
    heard, want = _sound_shape(text), _sound_shape(phrase)
    if not heard or not want or len(heard) > len(want) + 3:
        return 0.0
    best = 0.0
    for i in range(min(2, len(heard))):          # allow one leading "um"
        if heard[i] != want[0]:                  # "hey"/"he"/"hi" yes, "she"/"a" no
            continue
        for k in (len(want), len(want) + 1):
            part = heard[i:i + k]
            if part:
                best = max(best, difflib.SequenceMatcher(None, " ".join(part), " ".join(want)).ratio())
    return best


class SpeechWake:
    """Wakes when a short burst of speech, transcribed, sounds like the phrase."""
    SEG_MIN, SEG_MAX = 0.35, 3.0   # length of speech that could be the wake phrase
    END_PAUSE = 0.5                # quiet that ends a burst of speech

    def __init__(self, phrase, transcribe, threshold=0.85):
        self.phrase, self.transcribe, self.threshold = phrase, transcribe, threshold
        self.floor = 0.004          # background noise level, adapted as it listens
        self.last_heard = ""
        self.seg, self.quiet, self.speaking = [], 0, False
        self.pre = []

    def feed(self, a):
        rms = float(np.sqrt((a ** 2).mean()))
        if not self.speaking and rms < self.floor * 2.5:
            self.floor = 0.98 * self.floor + 0.02 * max(rms, 0.001)
        heard = False
        if rms > max(0.006, self.floor * 3):
            if not self.speaking:
                self.speaking, self.seg = True, list(self.pre)
            self.seg.append(a)
            self.quiet = 0
        elif self.speaking:
            self.seg.append(a)
            self.quiet += 1
            if self.quiet * FRAME / SR >= self.END_PAUSE:
                self.speaking = False
                length = (len(self.seg) - self.quiet) * FRAME / SR
                if self.SEG_MIN <= length <= self.SEG_MAX:
                    heard = self._check(np.concatenate(self.seg))
                self.seg = []
        else:
            self.pre = (self.pre + [a])[-4:]
        if len(self.seg) * FRAME / SR > self.SEG_MAX + 2:
            self.speaking, self.seg = False, []   # long speech: not a wake phrase
        return heard

    def _check(self, audio):
        text = self.transcribe(audio)
        if not text:
            return False
        score = wake_score(text, self.phrase)
        self.last_heard = text
        if score < self.threshold:
            log.info("Wake word: rejected %r (score %.2f)", text, score)
        return score >= self.threshold


class ModelWake:
    """openWakeWord's model for the phrase: scores every 80 ms of audio."""
    CHUNK = 1280         # 80 ms at 16 kHz
    REFRACTORY = 2.0     # seconds after a wake before it can wake again
    HANG = 1.5           # seconds the model keeps running after the last sound
    PRE = 6              # chunks (about 0.5 s) replayed when sound starts

    def __init__(self, phrase, threshold=0.5):
        from openwakeword.model import Model
        self.phrase = phrase
        self.name = MODEL_PHRASES[_phrase_key(phrase)]
        self.model = Model(wakeword_models=[self.name], inference_framework="onnx")
        self.threshold = threshold
        self.buf = np.zeros(0, np.int16)
        self.quiet_until = 0.0
        self.peak = 0.0          # best score of the current near miss, for the log
        self.last_heard = ""
        self.floor = 0.002       # background noise level, adapted as it listens
        self.open_until = 0.0
        self.pre = []

    def feed(self, a):
        # Only run the model around sound: in a quiet room it costs nothing. The gate is
        # far below speech level, and the last half second is replayed when it opens.
        rms = float(np.sqrt((a ** 2).mean()))
        if rms < self.floor * 2:
            self.floor = 0.98 * self.floor + 0.02 * max(rms, 0.0005)
        if rms > max(0.0015, self.floor * 1.6):
            self.open_until = time.time() + self.HANG
        self.buf = np.concatenate([self.buf, (np.clip(a, -1, 1) * 32767).astype(np.int16)])
        heard = False
        while len(self.buf) >= self.CHUNK:
            chunk, self.buf = self.buf[:self.CHUNK], self.buf[self.CHUNK:]
            if time.time() > self.open_until:
                self.pre = (self.pre + [chunk])[-self.PRE:]
                continue
            for early in self.pre:
                self.model.predict(early)
            self.pre = []
            score = float(self.model.predict(chunk)[self.name])
            if score >= self.threshold and time.time() >= self.quiet_until:
                heard = True
                self.last_heard = f"{self.phrase} ({score:.2f})"
                self.quiet_until = time.time() + self.REFRACTORY
                self.model.reset()
                self.peak = 0.0
            elif score > 0.1:
                self.peak = max(self.peak, score)
            elif self.peak:
                log.info("Wake word: near miss (score %.2f, needs %.2f)", self.peak, self.threshold)
                self.last_heard = f"almost ({self.peak:.2f})"
                self.peak = 0.0
        return heard


def make_detector(phrase, sensitivity, transcribe):
    """The model for "Hey Jarvis", speech bursts for any other phrase or a missing model."""
    model_th, speech_th = SENSITIVITY.get(sensitivity, SENSITIVITY["normal"])
    if _phrase_key(phrase) in MODEL_PHRASES:
        try:
            return ModelWake(phrase, model_th)
        except Exception as e:
            log.warning("Wake word model unavailable, using speech bursts: %r", e)
    return SpeechWake(phrase, transcribe, speech_th)

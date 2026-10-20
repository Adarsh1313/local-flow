"""LocalFlow: offline push-to-talk dictation for Windows.

Hold the hold key, speak, release: the text is typed wherever your cursor is.
Speech-to-text runs on this machine (faster-whisper or Parakeet); optional
cleanup runs through a local Ollama model. Settings live in config.json.
"""

import ctypes
import ctypes.wintypes
import difflib
import functools
import json
import math
import os
import queue
import re
import site
import subprocess
import sys
import threading
import time
import wave
import winreg
import winsound
from collections import deque
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
HISTORY_PATH = APP_DIR / "history.jsonl"
OLD_HISTORY_PATH = APP_DIR / "history.txt"
NOTES_PATH = APP_DIR / "notes.txt"
DICT_PATH = APP_DIR / "dictionary.json"
TRAIN_DIR = APP_DIR / "training"
LAST_AUDIO_PATH = APP_DIR / "last_recording.wav"
LOG_PATH = APP_DIR / "localflow.log"
ICON_PATH = APP_DIR / "localflow.ico"

# pythonw has no console, so send prints and errors to a log file.
if sys.stdout is None or Path(sys.executable).name.lower() == "pythonw.exe":
    sys.stdout = sys.stderr = open(LOG_PATH, "a", encoding="utf-8", buffering=1)

# Make the CUDA DLLs installed by the nvidia-* pip packages findable.
for _sp in site.getsitepackages():
    for _sub in ("cublas", "cudnn"):
        _bin = os.path.join(_sp, "nvidia", _sub, "bin")
        if os.path.isdir(_bin):
            os.add_dll_directory(_bin)
            os.environ["PATH"] = _bin + os.pathsep + os.environ["PATH"]

import tkinter as tk
import tkinter.font as tkfont

import keyboard
import numpy as np
import pyperclip
import pystray
import requests
import sounddevice as sd
from PIL import Image, ImageDraw, ImageFont, ImageTk

SR = 16000
FRAME = 800  # 50 ms analysis frames

DEFAULTS = {
    "hold_keys": ["right ctrl"],
    "engine": "parakeet",           # "parakeet" (CPU, fastest) or "whisper"
    "whisper_model": "small.en",
    "device": "auto",               # "auto", "cuda" or "cpu"
    "beam_size": 1,
    "language": "en",               # null = auto-detect (needs a non-.en model)
    "vocabulary": [],               # names and jargon to spell right (Whisper only)
    "replacements": {},             # {"heard": "wanted"}, applied after transcription
    "voice_commands": True,         # "new line", "new paragraph"
    "remove_fillers": True,         # drop "um", "uh"
    "smart_lists": True,            # "one, two, three" / "next point" become a list
    "llm_cleanup": False,
    "ollama_model": "qwen2.5:3b",
    "sounds": True,
    "show_idle_pill": True,
    "paste_last_keys": "ctrl+alt+v",   # opens recent transcripts
    "mic": "auto",                 # "auto" = best available, or a microphone name
    "keep_mic_ready_seconds": 60,  # keep the mic open after dictating: no cut-off first words
    "ambient_mode": False,         # listen on the laptop mic for the wake phrase
    "wake_phrase": "Hey Jarvis",
    "ambient_end_silence": 2.0,    # seconds of quiet that end a wake-word dictation
    "learn_corrections": True,     # learn from words you fix right after dictating
    "save_training_data": False,   # keep audio + final text for fine-tuning later
}

CLEANUP_PROMPT = """Clean up this dictated text. Remove filler words (um, uh, you know),
fix punctuation, capitalization and obvious grammar mistakes, and apply
self-corrections (e.g. "at 5, no, at 6" -> "at 6"). Keep the speaker's wording,
meaning and line breaks. Do not answer questions in it or add anything.
Output only the cleaned text.

Text: {text}"""


def log(*args):
    print(datetime.now().strftime("%H:%M:%S"), *args, flush=True)


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            log("config.json unreadable, using defaults:", e)
    save_config(cfg)
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def key_label(keys):
    return " + ".join(k.title() for k in keys)


def save_wav(path, a):
    """Keep the last recording so a bad transcript can be checked."""
    try:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    except Exception as e:
        log("Could not save last recording:", e)


# -------------------------------------------------------------------- history

def migrate_history():
    """Move the old plain-text history into history.jsonl (once)."""
    if HISTORY_PATH.exists() or not OLD_HISTORY_PATH.exists():
        return
    with open(HISTORY_PATH, "w", encoding="utf-8") as out:
        for line in OLD_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d)\] (.*)", line)
            if m:
                ts = datetime.strptime(m[1], "%Y-%m-%d %H:%M").isoformat(timespec="seconds")
                out.write(json.dumps({"ts": ts, "text": m[2], "secs": 0,
                                      "words": len(m[2].split())}) + "\n")
    OLD_HISTORY_PATH.rename(APP_DIR / "history_old.txt")


def add_history(text, secs):
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "text": text,
             "secs": round(secs, 2), "words": len(text.split())}
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def read_history():
    if not HISTORY_PATH.exists():
        return []
    entries = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            pass
    return entries


def stats(entries):
    today = datetime.now().date().isoformat()
    t = [e for e in entries if e["ts"].startswith(today)]
    words = sum(e["words"] for e in t)
    secs = sum(e["secs"] for e in t if e["secs"])
    timed_words = sum(e["words"] for e in t if e["secs"])
    wpm = round(timed_words / secs * 60) if secs else 0
    saved = max(0, words / 40 - secs / 60)  # vs typing at 40 wpm
    return words, wpm, saved


# ------------------------------------------------------------------ audio utils

def frame_rms(a):
    n = len(a) // FRAME
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    return np.sqrt((a[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))


def speech_threshold(rms):
    if len(rms) == 0:
        return 0.005
    return float(np.clip(np.percentile(rms, 10) * 3, 0.005, 0.03))


def normalize(a):
    """Boost quiet speech (soft voice, far-away mic) to a consistent level."""
    peak = float(np.abs(a).max()) if len(a) else 0.0
    if 0 < peak < 0.5:
        a = a * min(12.0, 0.5 / peak)
    return a.astype(np.float32)


def trim_silence(a, threshold=None):
    """Cut leading/trailing silence. Returns None if there is no real speech,
    which also stops Whisper from inventing text like "Thank you." on silence."""
    rms = frame_rms(a)
    th = threshold or speech_threshold(rms)
    loud = np.where(rms > th)[0]
    if len(loud) < 5:  # under 0.25 s of speech
        return None
    start = max(0, loud[0] - 4) * FRAME
    end = min(len(a), (loud[-1] + 5) * FRAME)
    return a[start:end]


# ----------------------------------------------------------------- microphones

class Mics:
    """Lists microphones (rescanned every few seconds, so a Bluetooth headset that
    connects shows up) and picks the best one: an external/USB mic, then a headset,
    then the laptop's built-in mic. Virtual devices like Stereo Mix are skipped."""

    VIRTUAL = ("stereo mix", "what u hear", "cable output", "voicemeeter", "virtual",
               "steam streaming", "wave out", "loopback", "mix (")
    HEADSET = ("hands-free", "handsfree", "headset", "headphone", "airpods", "buds",
               "bluetooth", "earbuds")
    BUILTIN = ("microphone array", "internal", "built-in", "integrated")

    def __init__(self):
        self.lock = threading.Lock()
        self.devices = []  # (index, name)
        self.default = None
        self._jobs = queue.Queue()
        self.before_restart = lambda: None  # set by the app: close the open mic first
        threading.Thread(target=self._audio_thread, daemon=True).start()
        self.scan()

    def _audio_thread(self):
        # PortAudio's Windows backends use COM objects that belong to the thread that
        # (re)starts PortAudio. Started from the UI thread (a single-threaded COM
        # apartment), recordings opened from the keyboard thread fail with
        # "Unanticipated host error". Restarting it only here, in a multithreaded
        # apartment, makes its objects usable from any thread.
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
        while True:
            fn, done, out = self._jobs.get()
            try:
                out["result"] = fn()
            finally:
                done.set()

    @staticmethod
    def signature():
        """Cheap list of input devices (no PortAudio restart), to notice changes."""
        class WAVEINCAPSW(ctypes.Structure):
            _fields_ = [("wMid", ctypes.wintypes.WORD), ("wPid", ctypes.wintypes.WORD),
                        ("vDriverVersion", ctypes.wintypes.UINT), ("szPname", ctypes.c_wchar * 32),
                        ("dwFormats", ctypes.wintypes.DWORD), ("wChannels", ctypes.wintypes.WORD),
                        ("wReserved1", ctypes.wintypes.WORD)]
        winmm = ctypes.windll.winmm
        names = []
        for i in range(winmm.waveInGetNumDevs()):
            caps = WAVEINCAPSW()
            if winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                names.append(caps.szPname)
        return tuple(names)

    def scan(self):
        """Re-read the device list (on the audio thread). Returns True if it changed."""
        done, out = threading.Event(), {}
        self._jobs.put((self._scan, done, out))
        done.wait(15)
        return out.get("result", False)

    @classmethod
    def score(cls, name):
        n = name.lower()
        if any(v in n for v in cls.VIRTUAL):
            return -1
        if any(h in n for h in cls.HEADSET):
            return 2
        if any(b in n for b in cls.BUILTIN):
            return 1
        return 3

    def _scan(self):
        with self.lock:
            try:
                self.before_restart()  # a restart would kill any open stream
                sd._terminate()
                sd._initialize()
                apis = sd.query_hostapis()
                wasapi = next(i for i, a in enumerate(apis) if "WASAPI" in a["name"])
                devices = [(d["index"], d["name"]) for d in sd.query_devices()
                           if d["max_input_channels"] > 0 and d["hostapi"] == wasapi]
                default = apis[wasapi]["default_input_device"]
            except Exception as e:
                log("Mic scan failed:", repr(e))
                return False
            changed = [n for _, n in devices] != [n for _, n in self.devices]
            self.devices = devices
            self.default = next((n for i, n in devices if i == default), None)
            return changed

    def names(self):
        return sorted((n for _, n in self.devices), key=lambda n: (-self.score(n), n))

    def best(self):
        usable = [n for _, n in self.devices if self.score(n) >= 0]
        if not usable:
            return self.default
        return max(usable, key=lambda n: (self.score(n), n == self.default))

    def pick(self, preference):
        """(device index, name) for the preference ("auto" or a name)."""
        name = preference if preference != "auto" and any(n == preference for _, n in self.devices)             else self.best()
        index = next((i for i, n in self.devices if n == name), None)
        return index, name


# ------------------------------------------------------------- wake word
#
# Ambient mode keeps the laptop mic open and watches for short bursts of speech
# (0.35-3 s, then a pause). Only those are transcribed, with the same speech model,
# and compared with the wake phrase by how they sound, so "he whispered" still
# counts as "Hey Wispr" (or whatever phrase you set). Then a hands-free dictation starts and ends after a pause.

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


class AmbientListener:
    SEG_MIN, SEG_MAX = 0.35, 3.0   # length of speech that could be the wake phrase
    END_PAUSE = 0.5                # quiet that ends a burst of speech
    THRESHOLD = 0.85

    def __init__(self, app):
        self.app = app
        self.mic = None
        self.mic_name = None
        self.running = False
        self.frames = queue.Queue()
        self.floor = 0.004              # background noise level, adapted as it listens
        self.last_heard = ""
        self.voice_level = 0.012        # level that counts as speech (for auto-stop)

    # -- life cycle
    def start(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self._loop, daemon=True).start()
            log("Wake word listening started")

    def stop(self):
        self.running = False
        self.close_mic()
        log("Wake word listening stopped")

    def close_mic(self):
        mic, self.mic = self.mic, None
        if mic:
            mic.close()

    def _laptop_mic(self):
        mics = self.app.mics
        name = next((n for n in mics.names() if Mics.score(n) == 1), None) or mics.default
        return next((i for i, n in mics.devices if n == name), None), name

    def _open(self):
        with self.app.mics.lock:
            index, name = self._laptop_mic()
            self.mic = open_mic(index)
            self.mic_name = name
        self.mic.attach(self.frames.put)
        log(f"Wake word mic: {name}")

    # -- listening
    def _loop(self):
        seg, quiet, speaking = [], 0, False
        pre = deque(maxlen=4)
        while self.running:
            try:
                if self.mic is None or not self.mic.alive:
                    self._open()
                elif self.mic.consumer is None and not self.app.session:
                    self.mic.attach(self.frames.put)  # a wake-word dictation just finished
                a = self.frames.get(timeout=0.5)
            except queue.Empty:
                continue
            except MicStuck as e:
                log("Wake word mic failed:", repr(e))
                self.app._audio_stuck()
                self.running = False
                break
            except Exception as e:
                log("Wake word mic failed:", repr(e))
                self.close_mic()
                time.sleep(3)
                continue
            rms = float(np.sqrt((a ** 2).mean()))
            if not speaking and rms < self.floor * 2.5:
                self.floor = 0.98 * self.floor + 0.02 * max(rms, 0.001)
            threshold = max(0.006, self.floor * 3)
            self.voice_level = threshold
            if rms > threshold:
                if not speaking:
                    speaking, seg = True, list(pre)
                seg.append(a)
                quiet = 0
            elif speaking:
                seg.append(a)
                quiet += 1
                if quiet * FRAME / SR >= self.END_PAUSE:
                    speaking = False
                    length = (len(seg) - quiet) * FRAME / SR
                    if self.SEG_MIN <= length <= self.SEG_MAX:
                        self._check(np.concatenate(seg))
                    seg = []
            else:
                pre.append(a)
            if len(seg) * FRAME / SR > self.SEG_MAX + 2:
                speaking, seg = False, []   # long speech: not a wake phrase

    def _check(self, audio):
        app = self.app
        if app.engine is None or app.session or app.starting or app.busy:
            return
        text = app.engine.transcribe(normalize(audio))
        score = wake_score(text, app.cfg["wake_phrase"])
        self.last_heard = text
        if score >= self.THRESHOLD:
            log(f"Wake word: heard {text!r} (score {score:.2f})")
            app.on_wake(self.mic)


# --------------------------------------------------------------------- engine

class Engine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.vocab = lambda: cfg["vocabulary"]
        if cfg["engine"] == "parakeet":
            import onnx_asr
            self.model = onnx_asr.load_model(
                "nemo-parakeet-tdt-0.6b-v2", quantization="int8",
                providers=["CPUExecutionProvider"])
            self.name = "Parakeet (CPU)"
        else:
            self.model, self.name = self._load_whisper()
        self.transcribe(np.zeros(SR, dtype=np.float32) + 1e-4)  # warm up

    def _load_whisper(self):
        from faster_whisper import WhisperModel
        name = self.cfg["whisper_model"]
        if self.cfg["device"] in ("auto", "cuda"):
            try:
                m = WhisperModel(name, device="cuda", compute_type="int8_float32")
                list(m.transcribe(np.zeros(SR, dtype=np.float32))[0])
                return m, f"Whisper {name} (GPU)"
            except Exception as e:
                log("GPU unavailable, using CPU:", e)
        return WhisperModel(name, device="cpu", compute_type="int8"), f"Whisper {name} (CPU)"

    def transcribe(self, audio, context=""):
        with self.lock:
            if self.cfg["engine"] == "parakeet":
                return self.model.recognize(audio, sample_rate=SR).strip()
            prompt = ""
            vocab = self.vocab()
            if vocab:
                prompt = "Glossary: " + ", ".join(vocab[:60]) + ". "
            prompt += context[-200:]
            segments, _ = self.model.transcribe(
                audio,
                language=self.cfg["language"] or None,
                beam_size=self.cfg["beam_size"],
                vad_filter=False,
                condition_on_previous_text=False,
                without_timestamps=True,
                initial_prompt=prompt or None,
            )
            return " ".join(s.text.strip() for s in segments).strip()


# -------------------------------------------------------------------- session

# ------------------------------------------------------------ joining phrases
#
# Long dictations are transcribed phrase by phrase (at pauses) so they finish fast.
# The model treats every phrase as a whole sentence: it capitalises the first word
# and ends it with a period. When you only paused to think, that leaves a false
# sentence break, so the joins are repaired here.

FILLERS = {"uh", "um", "uhm", "erm", "hmm", "mm", "ah", "eh"}
CONTINUES = {"the", "a", "an", "to", "of", "for", "with", "and", "or", "but", "that", "my", "your",
             "our", "their", "his", "her", "its", "in", "on", "at", "by", "from", "as", "be", "is",
             "are", "was", "were", "if", "so", "because", "which", "who", "about", "into", "than",
             "then", "this", "these", "those", "like", "very", "really", "just", "also", "can",
             "could", "would", "should", "will", "going", "want", "have", "has", "had", "do", "does",
             "not", "more", "most", "some", "any", "every", "each", "where", "when", "what", "how",
             "basically", "actually", "even", "only", "i'm", "it's", "we", "you", "they", "he", "she"}


def zipf(text):
    from wordfreq import zipf_frequency
    return zipf_frequency(text, "en")


def join_pieces(pieces):
    out = ""
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        words = [w.strip(".,!?").lower() for w in piece.split()]
        if out and all(w in FILLERS for w in words):
            continue  # a lone "Uh" between phrases
        if not out:
            out = piece
            continue
        first = piece.split()[0]
        bare = first.strip(".,!?;:\"'")
        last = out.split()[-1].strip(".,!?;:\"'").lower()
        # lower-case a capitalised everyday word ("The", "New"), never "I" or names
        common = (bare[:1].isupper() and bare != "I" and not bare.isupper() and zipf(bare) >= 4.0)
        if out.endswith(".") and (bare[:1].islower() or last in CONTINUES):
            out = out[:-1]  # the "sentence" only ended because you paused
            if common:
                piece = bare.lower() + piece[len(bare):]
        elif out[-1:] not in ".?!" and common:
            piece = bare.lower() + piece[len(bare):]
        out += " " + piece
    return out


def remove_fillers(text):
    text = re.sub(r"(?i)(^|[\s,(])(?:uh+|um+|uhm|erm|hmm+)\b[,.]?(?=\s|$)", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).replace(" ,", ",").strip(" ,")
    # sentences that now start lower-case ("Uh what should I do" -> "What should I do")
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


class MicStream:
    """An open microphone. It stays open between dictations for a while, so the next
    one starts instantly (Bluetooth headsets otherwise need about a second to switch
    into headset mode, cutting off your first words) and includes the 0.3 s before you
    pressed the key."""

    PREROLL = 0.3

    def __init__(self, device):
        self.device = device
        self.lock = threading.Lock()
        self.consumer = None
        self.preroll = deque(maxlen=int(self.PREROLL * SR / FRAME))
        self.last_used = time.time()
        self.last_audio = 0.0
        self.audio_event = threading.Event()
        self.stream = None
        attempts = [(device, sd.WasapiSettings(auto_convert=True))] if device is not None else []
        attempts.append((None, None))  # Windows default mic
        for i, (dev, extra) in enumerate(attempts):
            try:
                stream = sd.InputStream(device=dev, samplerate=SR, channels=1, dtype="float32",
                                        blocksize=FRAME, callback=self._callback, extra_settings=extra)
                stream.start()
                self.stream = stream
                break
            except Exception as e:
                log(f"Mic {'default' if dev is None else dev} failed to start:", repr(e))
                if i == len(attempts) - 1:
                    raise

    def _callback(self, data, frames, t, status):
        a = data[:, 0].copy()
        self.last_audio = time.time()
        self.audio_event.set()
        with self.lock:
            if self.consumer:
                self.consumer(a)
            else:
                self.preroll.append(a)

    def attach(self, consumer):
        with self.lock:
            for chunk in self.preroll:
                consumer(chunk)
            self.preroll.clear()
            self.consumer = consumer

    def detach(self):
        with self.lock:
            self.consumer = None
            self.last_used = time.time()

    def wait_audio(self, timeout):
        """True once the mic is actually delivering audio."""
        if time.time() - self.last_audio < 0.3:
            return True
        self.audio_event.clear()
        return self.audio_event.wait(timeout)

    @property
    def alive(self):
        return self.stream is not None and self.stream.active

    def close(self):
        # abort, not stop: stop() waits for audio to drain, which hangs for ~15 s
        # when a Bluetooth headset is stuck
        try:
            self.stream.abort()
            self.stream.close()
        except Exception:
            pass
        self.stream = None


class MicStuck(RuntimeError):
    """Starting a mic hung inside the audio library. Every later start in this
    process then hangs behind it, so only a fresh process recovers."""


def open_mic(index, timeout=4.0):
    """Open a MicStream, but don't let a stuck device hang the app."""
    box = {"late": False}

    def run():
        try:
            mic = MicStream(index)
            if box["late"]:
                mic.close()
            else:
                box["mic"] = mic
        except Exception as e:
            box["err"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if "mic" in box:
        return box["mic"]
    if "err" in box:
        raise box["err"]
    box["late"] = True
    raise MicStuck(f"the mic took longer than {timeout:.0f} s to open")


class Session:
    """One hold of the key. While you talk, finished phrases are transcribed in
    the background at natural pauses, so on release only the last phrase is left."""

    MIN_CHUNK = 4.0   # seconds of audio before a pause may trigger a cut
    PAUSE = 0.7       # seconds of quiet that count as a pause (short ones split sentences)

    def __init__(self, engine, on_level, mic):
        self.engine = engine
        self.on_level = on_level
        self.chunks = []
        self.lock = threading.Lock()
        self.committed = 0
        self.parts = []
        self.duration = 0.0
        self.stopping = threading.Event()
        self.mic = mic
        mic.attach(self._callback)
        self.started = time.time()
        self.worker = threading.Thread(target=self._pretranscribe, daemon=True)
        self.worker.start()

    def _callback(self, a):
        with self.lock:
            self.chunks.append(a)
        self.on_level(float(np.sqrt((a ** 2).mean())))

    def _audio(self):
        with self.lock:
            return np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)

    def _pretranscribe(self):
        pause_frames = int(self.PAUSE * SR / FRAME)
        while not self.stopping.wait(0.15):
            a = self._audio()
            pending = a[self.committed:]
            if len(pending) < self.MIN_CHUNK * SR:
                continue
            th = speech_threshold(frame_rms(a))
            rms = frame_rms(pending)
            if (rms[-pause_frames:] < th).all():
                cut = self.committed + len(rms) * FRAME - int(self.PAUSE * SR / 2)
                self._commit(a[self.committed:cut], th)
                self.committed = cut

    def _commit(self, audio, threshold=None):
        seg = trim_silence(audio, threshold)
        if seg is not None:
            text = self.engine.transcribe(normalize(seg), context=" ".join(self.parts))
            if text:
                self.parts.append(text)

    def _close(self):
        self.stopping.set()
        self.mic.detach()

    def finish(self):
        self._close()
        self.worker.join()
        a = self._audio()
        self.duration = len(a) / SR
        self.audio = a
        self._commit(a[self.committed:], speech_threshold(frame_rms(a)))
        save_wav(LAST_AUDIO_PATH, a)
        return join_pieces(self.parts)

    def cancel(self):
        self._close()


# ---------------------------------------------------------------- text output

# ------------------------------------------------------------- spoken lists
#
# "Here's my plan. One, buy milk. Two, call the bank." becomes
#   Here's my plan:
#   1. Buy milk
#   2. Call the bank
# A run of at least two consecutive markers is needed (1 then 2), and a bare
# "one"/"first" only counts at the start of a sentence, so "I have one question
# and two concerns" stays a sentence. "Bullet point" / "next point" make "-" bullets.

NUM_WORDS = {w: i for i, w in enumerate("one two three four five six seven eight nine ten".split(), 1)}
ORDINALS = {w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth".split(), 1)}
ORDINALS.update({"firstly": 1, "secondly": 2, "thirdly": 3})
_ALT = lambda words: "|".join(sorted(words, key=len, reverse=True))
LIST_MARKER = re.compile(
    r"(?P<pre>^|(?<=[.!?:;,])\s+)(?:"
    r"(?P<digit>\d{1,2})[.):]\s+"
    rf"|(?P<word>{_ALT(NUM_WORDS)})[,.:]\s+"
    rf"|(?P<ord>{_ALT(ORDINALS)})\b[,.:]?\s+"
    r")"
    rf"|\b(?:number|point|step|item)\s+(?P<pword>{_ALT(NUM_WORDS)}|\d{{1,2}})\b[,.:]?\s*"
    r"|\b(?P<bullet>bullet point|bullet|next point|next bullet|new point|another point)\b[,.:]?\s*",
    re.I)


def format_lists(text):
    marks = []
    for m in LIST_MARKER.finditer(text):
        g = m.groupdict()
        if g["bullet"]:
            kind, value = "bullet", None
        else:
            raw = (g["digit"] or g["word"] or g["ord"] or g["pword"]).lower()
            kind, value = "num", int(raw) if raw.isdigit() else NUM_WORDS.get(raw) or ORDINALS.get(raw)
        marks.append((m.start() + len(g["pre"] or ""), m.end(), kind, value))

    run = []
    for i, mark in enumerate(marks):  # longest 1, 2, 3... sequence
        if mark[2] == "num" and mark[3] == 1:
            seq, want = [mark], 2
            for nxt in marks[i + 1:]:
                if nxt[2] == "num" and nxt[3] == want:
                    seq.append(nxt)
                    want += 1
            run = seq if len(seq) > len(run) else run
    numbered = len(run) >= 2
    if not numbered:
        run = [mk for mk in marks if mk[2] == "bullet"]
        if len(run) < 2:
            return text

    items = []
    for j, mark in enumerate(run):
        item = text[mark[1]:run[j + 1][0] if j + 1 < len(run) else len(text)].strip()
        item = re.sub(r"(?:[\s,;.]|\band)+$", "", item, flags=re.I).strip()
        if item:
            items.append(item[0].upper() + item[1:])
    if len(items) < 2:
        return text
    lead = text[:run[0][0]].strip()
    if lead:
        lead = lead.rstrip(".,;") + ("" if lead[-1] in ":?!" else ":")
    lines = ([lead] if lead else []) + [f"{n}. {it}" if numbered else f"- {it}" for n, it in enumerate(items, 1)]
    return "\n".join(lines)


def postprocess(text, cfg, dictionary=None):
    if cfg.get("remove_fillers", True):
        text = remove_fillers(text)
    if dictionary:
        text = dictionary.apply(text)
    for heard, wanted in cfg["replacements"].items():
        text = re.sub(r"\b" + re.escape(heard) + r"\b", wanted, text, flags=re.I)
    if cfg["voice_commands"]:
        text = re.sub(r"[,.]?\s*\bnew paragraph\b[,.]?\s*", "\n\n", text, flags=re.I)
        text = re.sub(r"[,.]?\s*\bnew line\b[,.]?\s*", "\n", text, flags=re.I)
    if cfg.get("smart_lists", True):
        text = format_lists(text)
    return text.strip()


def llm_cleanup(text, cfg):
    r = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": cfg["ollama_model"], "prompt": CLEANUP_PROMPT.format(text=text),
              "stream": False, "keep_alive": "30m", "options": {"temperature": 0}},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["response"].strip() or text


def foreground_app():
    """File name of the app in front (for the log), e.g. "Claude.exe"."""
    try:
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        pid = ctypes.wintypes.DWORD()
        u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), ctypes.byref(pid))
        h = k32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        buf, size = ctypes.create_unicode_buffer(512), ctypes.wintypes.DWORD(512)
        k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        k32.CloseHandle(h)
        return Path(buf.value).name or "?"
    except Exception:
        return "?"


def paste(text):
    try:
        previous = pyperclip.paste()
    except Exception:
        previous = None
    pyperclip.copy(text)
    # Let go of Alt/Shift first (e.g. after a shortcut), or Ctrl+V becomes another shortcut.
    end = time.time() + 1
    while time.time() < end and any(keyboard.is_pressed(k) for k in ("alt", "shift")):
        time.sleep(0.02)
    time.sleep(0.05)
    keyboard.send("ctrl+v")
    log(f"Pasted {len(text)} characters into {foreground_app()}")

    # Apps that are busy (e.g. an Electron app rendering a long reply) can read the
    # clipboard a moment late. Restoring it after 0.25 s made them paste your old
    # clipboard instead of the dictation, so wait, and only restore if it's unchanged.
    def restore():
        time.sleep(1.5)
        try:
            if previous is not None and pyperclip.paste() == text:
                pyperclip.copy(previous)
        except Exception:
            pass

    threading.Thread(target=restore, daemon=True).start()


# ---------------------------------------------------------- self-learning dictionary

COMMON = 3.0   # word frequency (zipf) from which a word counts as everyday
STOPWORD = 5.5  # too frequent ("the", "in") to tell contexts apart


def is_common(phrase):
    return zipf(phrase) >= (COMMON if " " not in phrase.strip() else 2.5)


class Dictionary:
    """Words the speech model gets wrong for you, swapped in every transcript.

    A rare mishearing ("Sio bhan" -> "Siobhan") is swapped everywhere. When the misheard
    word is an everyday one ("New" -> "Nuvo"), swapping it everywhere would break
    normal sentences, so it's only swapped next to the words it was learned with
    ("Nuvo Health"), and "a new idea" stays untouched. Edits between two everyday
    words ("Thursday" -> "Friday") are changes of mind, not mishearings, and aren't
    learned at all. Modes: "always", "context", "off" (kept, not applied)."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.entries = []
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log("dictionary.json unreadable:", e)
        self._migrate()

    def _migrate(self):
        changed = False
        for e in self.entries:
            if "mode" not in e:
                learned_common = e.get("source") == "learned" and is_common(e["heard"])
                e["mode"] = "off" if learned_common else "always"
                e.setdefault("context", [])
                changed = True
        if changed:
            self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _find(self, heard):
        return next((e for e in self.entries if e["heard"].lower() == heard.lower()), None)

    def add(self, heard, wanted, source="manual"):
        """Added by hand in the Dictionary tab: always applied."""
        with self.lock:
            e = self._find(heard)
            if e:
                e.update(wanted=wanted, mode="always", source="manual")
                e["count"] = e.get("count", 1) + 1
            else:
                self.entries.append({"heard": heard, "wanted": wanted, "source": source, "mode": "always",
                                     "context": [], "count": 1,
                                     "added": datetime.now().isoformat(timespec="seconds")})
            self.save()

    def learn(self, heard, wanted, context, source):
        """From a correction. Returns the entry, or None if it isn't worth learning."""
        if is_common(heard) and is_common(wanted):
            return None
        context = [c for c in context if c and zipf(c) < STOPWORD]
        with self.lock:
            e = self._find(heard)
            if e and e["wanted"].lower() == wanted.lower():
                e["count"] = e.get("count", 1) + 1
                e["context"] = sorted(set(e.get("context", [])) | {c.lower() for c in context})
            else:
                if e:
                    self.entries.remove(e)
                e = {"heard": heard, "wanted": wanted, "source": source, "count": 1,
                     "context": sorted({c.lower() for c in context}),
                     "added": datetime.now().isoformat(timespec="seconds")}
                self.entries.append(e)
            if e.get("mode") != "always":
                e["mode"] = "always" if not is_common(heard) else ("context" if e["context"] else "off")
            self.save()
            return dict(e)

    def set_mode(self, heard, mode):
        with self.lock:
            e = self._find(heard)
            if e:
                e["mode"] = mode
                self.save()

    def remove(self, heard):
        with self.lock:
            self.entries = [e for e in self.entries if e["heard"] != heard]
            self.save()

    def apply(self, text):
        for e in sorted(self.entries, key=lambda e: -len(e["heard"])):
            mode = e.get("mode", "always")
            if mode == "off":
                continue
            pattern = r"(?<!\w)" + re.escape(e["heard"]) + r"(?!\w)"
            if mode == "always":
                text = re.sub(pattern, lambda m, w=e["wanted"]: w, text, flags=re.I)
                continue
            ctx = set(e.get("context", []))

            def swap(m, w=e["wanted"], ctx=ctx):
                left = re.search(r"([\w'-]+)\W*$", m.string[:m.start()])
                right = re.match(r"\W*([\w'-]+)", m.string[m.end():])
                near = {g.group(1).lower() for g in (left, right) if g}
                return w if near & ctx else m.group(0)

            text = re.sub(pattern, swap, text, flags=re.I)
        return text

    def words(self):
        return sorted({e["wanted"] for e in self.entries if e.get("mode", "always") != "off"})


def _clean(word):
    return re.sub(r"^[^\w]+|[^\w]+$", "", word)


def _norm(word):
    return _clean(word).lower()


def find_span(original, text):
    """Locate the pasted words inside a whole text box, allowing for edits.
    Returns those words as they are now, or None if they're no longer there."""
    o, t = original.split(), text.split()
    if not o or not t:
        return None
    on, tn = [_norm(w) for w in o], [_norm(w) for w in t]
    sm = difflib.SequenceMatcher(None, on, tn, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size]
    if not blocks:
        return None
    anchor = max(blocks, key=lambda b: b.size)
    reach = len(o) * 1.5 + 3
    blocks = [b for b in blocks if abs(b.b - anchor.b) <= reach]
    if sum(b.size for b in blocks) < 0.6 * len(o):
        return None
    first, last = blocks[0], blocks[-1]
    j0 = max(0, first.b - first.a)
    j1 = min(len(t), last.b + last.size + (len(o) - last.a - last.size))
    return t[j0:j1]


def extract_corrections(original, edited, strict=True):
    """Word-level fixes between what was pasted and what it became, as
    (heard, wanted, context) with the words next to the fix as context.
    strict (automatic learning) ignores rewrites, and needs a rare word in the fix."""
    o = original.split()
    e = edited if isinstance(edited, list) else edited.split()
    on, en = [_norm(w) for w in o], [_norm(w) for w in e]
    ops = [op for op in difflib.SequenceMatcher(None, on, en, autojunk=False).get_opcodes()
           if op[0] != "equal"]
    changed = sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in ops)
    if strict and changed > max(3, 0.3 * len(o)):
        return []  # rewritten, not corrected
    letters = lambda ws: re.sub(r"\W", "", "".join(ws)).lower()
    pairs = []
    for tag, i1, i2, j1, j2 in ops:
        if tag != "replace" or i2 - i1 > 3 or j2 - j1 > 3:
            continue
        if strict and j2 == len(e) and j2 - j1 > 1:
            # at the end of what we could see, the edit may have swallowed the next
            # word you typed ("well found" -> "WellFound while"): keep the best match
            j2 = max(range(j1 + 1, j2 + 1), key=lambda j: difflib.SequenceMatcher(
                None, letters(o[i1:i2]), letters(e[j1:j]), autojunk=False).ratio())
        heard = " ".join(_clean(w) for w in o[i1:i2]).strip()
        wanted = " ".join(_clean(w) for w in e[j1:j2]).strip()
        if not heard or not wanted or heard.lower() == wanted.lower():
            continue
        if strict and not any(zipf(w) < 4.5 for w in wanted.split()):
            continue
        if is_common(heard) and is_common(wanted):
            continue  # an edit, not a mishearing
        context = [_clean(e[j]) for j in (j1 - 1, j2) if 0 <= j < len(e)]
        pairs.append((heard, wanted, context))
    return pairs


class CorrectionWatcher:
    """After a paste, reads the text box you pasted into (Windows UI Automation)
    for up to a minute. If you fix a word in what was just pasted, it reports it.
    Works in most browsers and native apps; some apps don't expose their text."""

    WATCH_SECONDS = 60

    def __init__(self, on_result):
        self.on_result = on_result
        self.on_missing = lambda: None  # the pasted text isn't in the box
        self.token = None

    def cancel(self):
        self.token = None

    def watch(self, pasted, sample=None, control=None):
        token = object()
        self.token = token
        threading.Thread(target=self._run, args=(pasted, sample, token, control), daemon=True).start()

    @staticmethod
    def _read(ctrl):
        for get in (lambda: ctrl.GetValuePattern().Value,
                    lambda: ctrl.GetTextPattern().DocumentRange.GetText(-1)):
            try:
                text = get()
                if text:
                    return text
            except Exception:
                pass
        return None

    def _run(self, pasted, sample, token, control):
        import uiautomation as auto
        auto.Logger.SetLogFile(str(LOG_PATH))  # instead of @AutomationLog.txt
        try:
            with auto.UIAutomationInitializerInThread():
                time.sleep(0.6)
                ctrl = control or auto.GetFocusedControl()
                if ctrl is None or ctrl.IsPassword:
                    return
                text = self._read(ctrl)
                if not text or len(text) > 200_000:
                    return
                span = find_span(pasted, text)
                if span is None:
                    log("Pasted text not found in the text box")
                    self.on_missing()
                    return
                end = time.time() + self.WATCH_SECONDS
                while time.time() < end and self.token is token:
                    time.sleep(1.0)
                    if control is None:
                        focused = auto.GetFocusedControl()
                        if focused is None or not auto.ControlsAreSame(focused, ctrl):
                            break
                    text = self._read(ctrl)
                    now = find_span(pasted, text) if text else None
                    if now is None:
                        break  # message sent or text deleted
                    span = now
                pairs = extract_corrections(pasted, span)
                if pairs:
                    self.on_result(pairs, " ".join(span), sample)
        except Exception as e:
            log("Correction watcher:", repr(e))


def update_history_text(ts, old, new):
    entries = read_history()
    for e in entries:
        if e["ts"] == ts and e["text"] == old:
            e["text"], e["words"] = new, len(new.split())
    tmp = HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    os.replace(tmp, HISTORY_PATH)


# ------------------------------------------------- training data (opt-in)
#
# training/metadata.jsonl gets {"audio": "<file>.wav", "text": "..."}; if you later
# fix the text, another line with the corrected text is added (the last one wins).

def save_training_sample(audio, text):
    TRAIN_DIR.mkdir(exist_ok=True)
    name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".wav"
    save_wav(TRAIN_DIR / name, audio)
    save_training_text(name, text)
    return name


def save_training_text(name, text):
    with open(TRAIN_DIR / "metadata.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"audio": name, "text": text}) + "\n")


# ------------------------------------------------------------------- hold key

class HoldKey:
    """Watches the keyboard for the hold key (one key or a combo)."""

    def __init__(self, keys, on_press, on_release, on_cancel, on_escape):
        self.keys = set(keys)
        self.on_press, self.on_release, self.on_cancel = on_press, on_release, on_cancel
        self.on_escape = on_escape
        self.down = set()
        self.active = False
        self.capture = None
        keyboard.hook(self._event)

    def _event(self, e):
        name = (e.name or f"sc{e.scan_code}").lower()
        if self.capture:
            self.capture(e.event_type, name)
            return
        if e.event_type == keyboard.KEY_DOWN:
            if name in self.down:
                return  # key auto-repeat
            self.down.add(name)
            if name == "esc":
                self.on_escape()
            if self.active and name not in self.keys:
                self.active = False  # another key: it's a shortcut, not dictation
                self.on_cancel()
            elif not self.active and self.keys <= self.down:
                self.active = True
                self.on_press()
        else:
            self.down.discard(name)
            if self.active and name in self.keys:
                self.active = False
                self.down.clear()
                self.on_release()

    def pick(self, on_done):
        """Record the next key or combo pressed; on_done(list) once all are released."""
        pressed, seen = set(), []

        def capture(event_type, name):
            if event_type == keyboard.KEY_DOWN:
                pressed.add(name)
                if name not in seen:
                    seen.append(name)
            else:
                pressed.discard(name)
                if seen and not pressed:
                    self.capture = None
                    on_done(seen)

        self.down.clear()
        self.capture = capture


# ---------------------------------------------------------------- overlay UI
#
# Look and feel: design/tokens.css and design/design-brief.md ("Graphite Capsule").
# Every colour, font, spacing, radius and motion value below comes from those tokens.

T = {
    "bg": "#161618", "nav": "#111113", "surface": "#1f1f22", "surface_hover": "#27272b",
    "control": "#2a2a2e", "control_hover": "#333338", "control_active": "#232327",
    "border": "#34343a", "edge": "#3e3e45", "edge_glow": "#55555d", "divider": "#2b2b30",
    "text": "#f2f2f3", "muted": "#9c9ca4", "dim": "#c9c9ce", "disabled": "#5e5e66",
    "select": "#ededee", "select_hover": "#ffffff", "select_contrast": "#161618",
    "accent": "#9cc3e6", "focus": "#ffffff", "recording": "#ff6b5b", "danger": "#ff9a92",
    "success": "#8fd3a6", "stat1": "#9cc3e6", "stat2": "#d9bb85", "stat3": "#8fd3a6",
    "popup_border": "#2a2a2f", "idle_pill": "#4a4a50", "selection": "#2f4a63",
}
KEY = "#010203"  # transparent colour key for the pill and the hover bar
SPACE = {1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24}
RADIUS = {"chip": 6, "control": 8, "card": 12}
MOTION = {"hover": 120, "move": 200, "enter": 220, "confirm": 1400, "rise": 8}
F = {}           # fonts, filled by init_fonts()
S = 1.0          # display scale (125% -> 1.25)

GLYPH = {"notes": "", "settings": "", "mic": "", "paste": "",
         "dictionary": "", "history": "", "check": "", "close": "",
         "pin": "", "pinned": "", "delete": "", "prev": "", "next": "",
         "chev": "", "edit": ""}

user32 = ctypes.windll.user32


def init_fonts(root):
    global S
    S = root.winfo_fpixels("1i") / 96
    have = set(tkfont.families(root))
    pick = lambda *names: next((n for n in names if n in have), "Segoe UI")
    strong = pick("Segoe UI Variable Text Semibold", "Segoe UI Semibold")
    display = pick("Segoe UI Variable Display Semib", "Segoe UI Semibold")
    F.update({
        "caption": (pick("Segoe UI Variable Small", "Segoe UI"), 9),
        "small": (pick("Segoe UI Variable Small", "Segoe UI"), 8),
        "body": (pick("Segoe UI Variable Text", "Segoe UI"), 10),
        "body_strong": (strong, 10),
        "heading": (strong, 10),          # group headings, in muted
        "subtitle": (strong, 11),         # popup titles
        "title": (display, 16),           # page titles
        "stat": (display, 16),            # stats corner numbers
        "icon": (pick("Segoe Fluent Icons", "Segoe MDL2 Assets"), 11),
        "icon_small": (pick("Segoe Fluent Icons", "Segoe MDL2 Assets"), 9),
        "mono": (pick("Cascadia Mono", "Consolas"), 9),
    })


def px(v):
    return int(round(v * S))


# ---------------------------------------------------------------------- motion

def animations_on():
    """Windows' "Animation effects" switch (Accessibility > Visual effects)."""
    on = ctypes.c_int(1)
    try:
        user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0)  # SPI_GETCLIENTAREAANIMATION
    except Exception:
        pass
    return bool(on.value)


def ease_out(t):     # --ease-out: fast start, soft landing
    return 1 - (1 - t) ** 4


def ease_colour(t):  # --ease-colour
    return t * t * (3 - 2 * t)


class Tween:
    """Moves one number toward a target over a few frames. Retargeting mid-way carries
    on from where it is; nothing is scheduled once it arrives."""

    FRAME = 15  # ms

    def __init__(self, widget, apply, value=0.0):
        self.widget, self.apply, self.value = widget, apply, value
        self.target, self.job = value, None

    def _cancel(self):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None

    def set(self, value):
        self._cancel()
        self.value = self.target = value
        self.apply(value)

    def to(self, target, ms=None, ease=ease_out, done=None):
        ms = MOTION["move"] if ms is None else ms
        self._cancel()
        self.target = target
        if ms <= 0 or target == self.value or not animations_on():
            self.value = target
            self.apply(target)
            if done:
                done()
            return
        start, t0 = self.value, time.perf_counter()

        def step():
            k = min(1.0, (time.perf_counter() - t0) * 1000 / ms)
            self.value = start + (target - start) * ease(k)
            try:
                self.apply(self.value)
            except tk.TclError:  # widget destroyed mid-animation
                self.job = None
                return
            if k < 1:
                self.job = self.widget.after(self.FRAME, step)
            else:
                self.job = None
                if done:
                    done()

        step()


class Redraw:
    """Coalesces several tweens into one draw per frame."""

    def __init__(self, widget, draw):
        self.widget, self.draw, self.job = widget, draw, None

    def __call__(self, _=None):
        if not self.job:
            self.job = self.widget.after_idle(self._run)

    def _run(self):
        self.job = None
        try:
            self.draw()
        except tk.TclError:
            pass


def rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


# --------------------------------------------------------- smooth (AA) shapes
# tk's canvas can't anti-alias, so rounded shapes are drawn 4x larger with PIL,
# scaled down, and shown as images. Widgets keep a reference to the image they show,
# so the cache can drop it without the shape vanishing.

def _shape(w, h, r, fill, outline, width, edge):
    ss = 4 if w * h < 60000 else 2
    W, H = w * ss, h * ss
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rr = min(r, w / 2, h / 2) * ss
    if outline:
        d.rounded_rectangle((0, 0, W - 1, H - 1), rr, fill=rgb(outline) + (255,))
        i = width * ss
        d.rounded_rectangle((i, i, W - 1 - i, H - 1 - i), max(0, rr - i),
                            fill=rgb(fill) + (255,) if fill else (0, 0, 0, 0))
    elif fill:
        d.rounded_rectangle((0, 0, W - 1, H - 1), rr, fill=rgb(fill) + (255,))
    im = im.resize((w, h), Image.BOX)
    if edge and w > 8:  # the lit top edge: brightest in the middle, gone by 10% from each end
        a = np.asarray(im).copy()
        u = np.clip((np.arange(w) - 0.1 * w) / (0.8 * w), 0, 1)
        al = (np.sin(np.pi * u) * (a[0, :, 3] / 255))[:, None]
        a[0, :, :3] = (a[0, :, :3] * (1 - al) + np.array(rgb(edge)) * al).astype(np.uint8)
        im = Image.fromarray(a, "RGBA")
    return im


@functools.lru_cache(maxsize=400)
def shape(w, h, r, fill, outline="", width=1, edge=""):
    """Rounded rectangle (or capsule/circle when r >= h/2) as a PhotoImage."""
    return ImageTk.PhotoImage(_shape(max(1, int(w)), max(1, int(h)), r, fill, outline, width, edge))


ICON_FILES = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
              for f in ("SegoeIcons.ttf", "segmdl2.ttf")]


@functools.lru_cache(maxsize=8)
def _icon_font(size_px):
    path = next((f for f in ICON_FILES if os.path.exists(f)), None)
    return ImageFont.truetype(path, size_px) if path else None


@functools.lru_cache(maxsize=256)
def glyph(ch, pt, color):
    """An icon rendered with greyscale smoothing. tk draws text with ClearType, which
    fringes dark icons red/blue on light backgrounds (the white hover-bar circle)."""
    font = _icon_font(px(pt * 96 / 72))
    if font is None:
        return None
    size = px(pt * 96 / 72 * 1.5)
    im = Image.new("RGBA", (size, size), rgb(color) + (0,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).text((size / 2, size / 2), ch, font=font, fill=255, anchor="mm")
    im.putalpha(mask)
    return ImageTk.PhotoImage(im)


def icon(c, x, y, ch, color, pt=11):
    """Draw an icon centred on (x, y)."""
    img = glyph(ch, pt, color)
    if img is None:
        return c.create_text(x, y, text=ch, font=F["icon"], fill=color)
    return put(c, x, y, img, anchor="center")


@functools.lru_cache(maxsize=64)
def fade_line(w, color):
    """1 px line that fades out toward both ends (row dividers)."""
    w = max(1, int(w))
    u = np.arange(w) / max(1, w - 1)
    alpha = np.clip(np.minimum(u, 1 - u) / 0.12, 0, 1) * 255
    a = np.zeros((1, w, 4), np.uint8)
    a[0, :, :3] = rgb(color)
    a[0, :, 3] = alpha
    return ImageTk.PhotoImage(Image.fromarray(a, "RGBA"))


def work_area():
    rect = ctypes.wintypes.RECT()
    user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)
    return rect


def cursor_pos():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def hwnd_of(win):
    return user32.GetParent(win.winfo_id())


def force_foreground(hwnd):
    """Bring our window to the front even when Windows' focus-stealing rules would
    block it (e.g. when opened from a keyboard shortcut)."""
    kernel32 = ctypes.windll.kernel32
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if other and other != me:
        user32.AttachThreadInput(other, me, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    if other and other != me:
        user32.AttachThreadInput(other, me, False)


def set_ex_style(win, bits):
    hwnd = hwnd_of(win)
    user32.SetWindowLongW(hwnd, -20, user32.GetWindowLongW(hwnd, -20) | bits)  # GWL_EXSTYLE


def round_corners(win):
    """Windows 11 rounded window corners (ignored on Windows 10)."""
    try:
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd_of(win), 33, ctypes.byref(pref), 4)
    except Exception:
        pass


WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, WS_EX_LAYERED = 0x08000000, 0x80, 0x20, 0x80000


def put(c, x, y, img, tags=(), anchor="nw"):
    """Draw a shape image on a canvas, keeping it alive as long as the canvas shows it."""
    if not hasattr(c, "_imgs"):
        c._imgs = []
    c._imgs.append(img)
    return c.create_image(x, y, image=img, anchor=anchor, tags=tags)


def clear(c, tag="all"):
    c.delete(tag)
    if tag == "all":
        c._imgs = []


def pill(c, x0, y0, x1, y1, fill, outline="", edge=""):
    h = y1 - y0
    return put(c, x0, y0, shape(round(x1 - x0), round(h), h / 2, fill, outline, 1, edge))


def dot(c, cx, cy, r, fill):
    d = max(2, round(2 * r))
    return put(c, cx - d / 2, cy - d / 2, shape(d, d, d / 2, fill))


# --------------------------------------------------------------------- widgets

class Card(tk.Canvas):
    """A rounded surface holding a frame (self.body). Cards get a lit top edge;
    outline colour changes (e.g. focus) fade."""

    def __init__(self, parent, fill=None, radius=RADIUS["card"], pad=None, outline="", stretch=False,
                 edge=True):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, height=1)
        self.fill, self.r, self.outline = fill or T["surface"], px(radius), outline
        # keep the square body frame inside the rounded corners
        self.pad = px(pad) if pad is not None else math.ceil(self.r * (1 - 1 / math.sqrt(2))) + 1
        self.edge = T["edge_glow"] if edge else ""
        self.stretch = stretch  # fill the space it's packed into, instead of fitting its content
        self.body = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(self.pad, self.pad, window=self.body, anchor="nw")
        self._from = self._to = outline
        self._fade = Tween(self, lambda v: self._set_outline(mix(self._from, self._to, v)) if self._to else None, 1.0)
        self._paint = Redraw(self, self._render)
        self.bind("<Configure>", self._layout)
        self.body.bind("<Configure>", self._layout)

    def _set_outline(self, color):
        self.outline = color
        self._paint()

    def set_outline(self, color):
        self._from, self._to = self.outline or self.fill, color
        self._fade.set(0)
        self._fade.to(1, MOTION["hover"], ease_colour)

    def _layout(self, _=None):
        w = self.winfo_width()
        if self.stretch:
            h = self.winfo_height()
            self.itemconfig(self._win, width=max(1, w - 2 * self.pad), height=max(1, h - 2 * self.pad))
        else:
            h = self.body.winfo_reqheight() + 2 * self.pad
            if int(float(self.cget("height"))) != h:
                self.config(height=h)
            self.itemconfig(self._win, width=max(1, w - 2 * self.pad))
        self._paint()

    def _render(self):
        w, h = self.winfo_width(), int(float(self.cget("height"))) if not self.stretch else self.winfo_height()
        if w < 4 or h < 4:
            return
        clear(self, "bg")
        self._img = shape(w, h, self.r, self.fill, self.outline, max(1, px(1)), self.edge)
        self.create_image(0, 0, image=self._img, anchor="nw", tags="bg")
        self.tag_lower("bg")


class Button(tk.Canvas):
    """Rounded button. kind: standard, primary (white, one per view), subtle (no fill),
    selected. Hover fades, press dips. confirm="Copied" briefly swaps the label for a
    green check and that word after a click."""

    STYLES = {
        "standard": ("control", "control_hover", "control_active", "text", "border"),
        "primary": ("select", "select_hover", "dim", "select_contrast", ""),
        "subtle": (None, "surface_hover", "control_active", "text", ""),
        "selected": ("control_hover", "control_hover", "control_active", "text", "border"),
    }

    def __init__(self, parent, text, command, kind="standard", font=None, icon=False, pad_x=12, confirm=None):
        self.text, self.command, self.kind, self.confirm = text, command, kind, confirm
        self.icon = icon
        self.font = font or (F["icon_small"] if icon else F["body"])
        self.pad_x = pad_x
        f = tkfont.Font(font=self.font)
        self.h = f.metrics("linespace") + px(10)
        super().__init__(parent, height=self.h + px(4), bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self._measure()
        self.pressed = self.focused = self.confirming = False
        self.enabled = True
        self.redraw = Redraw(self, self.draw)
        self.hover = Tween(self, self.redraw, 0.0)
        self.bind("<Enter>", lambda e: self.hover.to(1, MOTION["hover"], ease_colour))
        self.bind("<Leave>", lambda e: (self._press(False), self.hover.to(0, MOTION["hover"], ease_colour)))
        self.bind("<ButtonPress-1>", lambda e: self._press(True))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda e: self._focus(True))
        self.bind("<FocusOut>", lambda e: self._focus(False))
        for key in ("<space>", "<Return>"):
            self.bind(key, lambda e: self._fire())
        self.draw()

    def _measure(self):
        f = tkfont.Font(font=self.font)
        w = f.measure(self.text)
        if self.confirm:  # room for the confirmation so the layout doesn't jump
            w = max(w, f.measure(self.confirm) + tkfont.Font(font=F["icon_small"]).measure(GLYPH["check"]) + px(6))
        self.w = w + px(self.pad_x) * 2
        self.config(width=self.w + px(4))

    def _press(self, on):
        if self.pressed != on:
            self.pressed = on
            self.draw()

    def _focus(self, on):
        self.focused = on
        self.draw()

    def _release(self, e):
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        self._press(False)
        if inside:
            self._fire()

    def _fire(self):
        if self.enabled and self.command:
            self.command()
            if self.confirm and self.winfo_exists():
                self.confirming = True
                self.draw()
                self.after(MOTION["confirm"], self._unconfirm)

    def _unconfirm(self):
        self.confirming = False
        self.draw()

    def set_kind(self, kind):
        self.kind = kind
        self.draw()

    def set_text(self, text):
        self.text = text
        self._measure()
        self.draw()

    def draw(self):
        clear(self)
        base, hover, active, fg, line = self.STYLES[self.kind]
        bg = self.cget("bg")
        base = T[base] if base else bg
        fill = T[active] if self.pressed else mix(base, T[hover], self.hover.value)
        o = px(2)
        if self.focused:
            put(self, 0, 0, shape(self.w + px(4), self.h + px(4), px(RADIUS["control"] + 2), "", T["focus"],
                                  max(1, px(1.5))))
        i = px(1) if self.pressed else 0  # the press dip (~97%)
        put(self, o + i, o + i, shape(self.w - 2 * i, self.h - 2 * i, px(RADIUS["control"]), fill,
                                      T[line] if line else "", max(1, px(1))))
        cx, cy = o + self.w / 2, o + self.h / 2
        color = T[fg] if self.enabled else T["disabled"]
        if self.confirming:
            f = tkfont.Font(font=self.font)
            gw = tkfont.Font(font=F["icon_small"]).measure(GLYPH["check"])
            x = cx - (gw + px(6) + f.measure(self.confirm)) / 2
            self.create_text(x, cy, text=GLYPH["check"], font=F["icon_small"], fill=T["success"], anchor="w")
            self.create_text(x + gw + px(6), cy, text=self.confirm, font=self.font, fill=color, anchor="w")
        else:
            self.create_text(cx, cy, text=self.text, font=self.font, fill=color)


class Switch(tk.Canvas):
    """Capsule toggle: white when on. The knob glides, and stretches while pressed."""

    def __init__(self, parent, value, command):
        self.value, self.command = bool(value), command
        self.sw, self.sh = px(40), px(22)
        super().__init__(parent, width=self.sw + px(6), height=self.sh + px(6), bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.focused = False
        self.redraw = Redraw(self, self.draw)
        self.pos = Tween(self, self.redraw, float(self.value))
        self.hover = Tween(self, self.redraw, 0.0)
        self.stretch = Tween(self, self.redraw, 0.0)
        self.bind("<Enter>", lambda e: self.hover.to(1, MOTION["hover"], ease_colour))
        self.bind("<Leave>", lambda e: (self.hover.to(0, MOTION["hover"], ease_colour),
                                        self.stretch.to(0, MOTION["hover"])))
        self.bind("<ButtonPress-1>", lambda e: self.stretch.to(1, MOTION["hover"]))
        self.bind("<ButtonRelease-1>", lambda e: (self.stretch.to(0, MOTION["hover"]), self.toggle()))
        for key in ("<space>", "<Return>"):
            self.bind(key, lambda e: self.toggle())
        self.bind("<FocusIn>", lambda e: self._f(True))
        self.bind("<FocusOut>", lambda e: self._f(False))
        self.draw()

    def _f(self, v):
        self.focused = v
        self.draw()

    def set(self, value):
        self.value = bool(value)
        self.pos.to(float(self.value))

    def toggle(self):
        self.value = not self.value
        self.pos.to(float(self.value))
        self.command(self.value)

    def draw(self):
        clear(self)
        o, w, h = px(3), self.sw, self.sh
        t, hv, s = self.pos.value, self.hover.value, self.stretch.value
        if self.focused:
            put(self, 0, 0, shape(w + px(6), h + px(6), (h + px(6)) / 2, "", T["focus"], max(1, px(1.5))))
        off = mix(T["control"], T["control_hover"], hv)
        on = mix(T["select"], T["select_hover"], hv)
        track = mix(off, on, ease_colour(t))
        put(self, o, o, shape(w, h, h / 2, track, mix(T["border"], track, t), max(1, px(1))))
        k, gap = px(14), px(4)
        kw = k + s * px(4)
        x = o + gap + t * (w - 2 * gap - k) - s * t * px(4)
        put(self, x, o + (h - k) / 2, shape(round(kw), k, k / 2, mix(T["muted"], T["select_contrast"], t)))


class Segmented(tk.Canvas):
    """Pick one of a few options; a white capsule slides to the chosen one."""

    def __init__(self, parent, options, value, command):
        self.options, self.value, self.command = options, value, command
        f = tkfont.Font(font=F["caption"])
        self.pad, self.h = px(3), f.metrics("linespace") + px(12)
        self.widths = [f.measure(text) + px(24) for _, text in options]
        self.xs = [self.pad + sum(self.widths[:i]) for i in range(len(options))]
        self.w = sum(self.widths) + 2 * self.pad
        super().__init__(parent, width=self.w, height=self.h, bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.focused = False
        i = self._index(value)
        self.redraw = Redraw(self, self.draw)
        self.thumb = Tween(self, self.redraw, float(i))
        self.bind("<Button-1>", self._click)
        self.bind("<Left>", lambda e: self.choose(max(0, self._index(self.value) - 1)))
        self.bind("<Right>", lambda e: self.choose(min(len(options) - 1, self._index(self.value) + 1)))
        self.bind("<FocusIn>", lambda e: (setattr(self, "focused", True), self.draw()))
        self.bind("<FocusOut>", lambda e: (setattr(self, "focused", False), self.draw()))
        self.draw()

    def _index(self, value):
        return next((i for i, (v, _) in enumerate(self.options) if v == value), 0)

    def _click(self, e):
        for i, x in enumerate(self.xs):
            if x <= e.x < x + self.widths[i]:
                self.choose(i)

    def choose(self, i):
        value = self.options[i][0]
        if value != self.value:
            self.value = value
            self.thumb.to(float(i))
            self.command(value)

    def draw(self):
        clear(self)
        put(self, 0, 0, shape(self.w, self.h, self.h / 2, T["control"],
                              T["focus"] if self.focused else "", max(1, px(1.5))))
        t = self.thumb.value
        lo = int(math.floor(t))
        hi = min(lo + 1, len(self.options) - 1)
        k = t - lo
        x = self.xs[lo] + (self.xs[hi] - self.xs[lo]) * k
        tw = self.widths[lo] + (self.widths[hi] - self.widths[lo]) * k
        ih = self.h - 2 * self.pad
        put(self, x, self.pad, shape(round(tw), ih, ih / 2, T["select"]))
        for i, (_, text) in enumerate(self.options):
            near = max(0.0, 1 - abs(t - i))
            self.create_text(self.xs[i] + self.widths[i] / 2, self.h / 2, text=text, font=F["caption"],
                             fill=mix(T["dim"], T["select_contrast"], near))


def key_chip(parent, text):
    f = tkfont.Font(font=F["caption"])
    w, h = f.measure(text) + px(16), f.metrics("linespace") + px(8)
    c = tk.Canvas(parent, width=w, height=h + px(2), bg=parent.cget("bg"), highlightthickness=0, bd=0)
    r = px(RADIUS["chip"])
    put(c, 0, px(2), shape(w, h, r, T["border"]))                       # bottom edge (key cap)
    put(c, 0, 0, shape(w, h, r, T["control"], T["border"], max(1, px(1))))
    c.create_text(w / 2, h / 2, text=text, font=F["caption"], fill=T["dim"])
    return c


def label(parent, text, kind="body", color="text", **kw):
    return tk.Label(parent, text=text, font=F[kind], fg=T[color], bg=parent.cget("bg"),
                    anchor="w", justify="left", **kw)


class RoundedEntry(Card):
    def __init__(self, parent, width=14, placeholder=""):
        super().__init__(parent, fill=T["control"], radius=RADIUS["control"], outline=T["border"], edge=False)
        self.entry = tk.Entry(self.body, width=width, bg=T["control"], fg=T["text"], insertbackground=T["text"],
                              relief="flat", bd=0, font=F["body"], highlightthickness=0,
                              selectbackground=T["selection"])
        self.entry.pack(fill="x", padx=px(6), pady=px(3))
        self.entry.bind("<FocusIn>", lambda e: self.set_outline(T["accent"]))
        self.entry.bind("<FocusOut>", lambda e: self.set_outline(T["border"]))


class RoundedText(Card):
    """Multi-line text. In the scratchpad the text area is the card itself (no border
    until it has focus)."""

    def __init__(self, parent, height=None, stretch=False, fill=None, quiet=False):
        fill = fill or T["control"]
        rest = fill if quiet else T["border"]
        super().__init__(parent, fill=fill, radius=RADIUS["card"], outline=rest, stretch=stretch, edge=quiet)
        self.text = tk.Text(self.body, bg=fill, fg=T["text"], insertbackground=T["text"], relief="flat",
                            bd=0, font=F["body"], wrap="word", undo=True, padx=px(10), pady=px(8),
                            spacing1=px(2), spacing2=px(2), spacing3=px(2), highlightthickness=0,
                            selectbackground=T["selection"], height=height or 4)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<FocusIn>", lambda e: self.set_outline(T["accent"]))
        self.text.bind("<FocusOut>", lambda e: self.set_outline(rest))


class ScrollArea(tk.Frame):
    """Vertical scrolling content (wheel scrolls; a thin capsule thumb shows the position)."""

    def __init__(self, parent):
        super().__init__(parent, bg=parent.cget("bg"))
        self.canvas = tk.Canvas(self, bg=self.cget("bg"), highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.thumb = tk.Canvas(self, width=px(6), bg=self.cget("bg"), highlightthickness=0, bd=0)
        self.thumb.pack(side="right", fill="y")
        self.inner = tk.Frame(self.canvas, bg=self.cget("bg"))
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._sync)
        self.canvas.bind("<Configure>", lambda e: (self.canvas.itemconfig(self._win, width=e.width), self._sync()))
        self.bind_all_wheel()

    def bind_all_wheel(self):
        def wheel(e):
            w = e.widget
            while w is not None and w is not self:
                w = getattr(w, "master", None)
            if w is self and self.inner.winfo_reqheight() > self.canvas.winfo_height():
                self.canvas.yview_scroll(-e.delta // 120 * 3, "units")
                self._sync()
        self.canvas.bind_all("<MouseWheel>", wheel, add="+")

    def _sync(self, _=None):
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.inner.winfo_reqheight()))
        clear(self.thumb)
        top, bottom = self.canvas.yview()
        if bottom - top < 0.999:
            h = self.thumb.winfo_height()
            y0, y1 = top * h, bottom * h
            put(self.thumb, px(1), y0, shape(px(4), max(px(8), round(y1 - y0)), px(2), T["border"]))

    def top(self):
        self.canvas.yview_moveto(0)
        self._sync()


def group(parent, title=None, note=None):
    """A heading and a rounded card; returns the frame to add rows to."""
    if title:
        label(parent, title, "heading", "muted").pack(fill="x", padx=px(SPACE[1]),
                                                       pady=(px(SPACE[5]), px(SPACE[1])))
    if note:
        label(parent, note, "caption", "muted", wraplength=px(440)).pack(
            fill="x", padx=px(SPACE[1]), pady=(0, px(SPACE[1])))
    card = Card(parent)
    card.pack(fill="x", pady=(px(SPACE[1]), 0))
    card.body.rows = 0
    return card.body


def divider(body):
    """Row divider: a 1 px line inset from the card edge that fades out at both ends."""
    c = tk.Canvas(body, height=max(1, px(1)), bg=body.cget("bg"), highlightthickness=0, bd=0)
    c.pack(fill="x", padx=px(SPACE[3]))
    c.bind("<Configure>", lambda e: (clear(c), put(c, 0, 0, fade_line(e.width, T["divider"]))))
    return c


def row(body, title, desc=None, on_click=None):
    """A setting row: title + description on the left; returns the right-hand frame."""
    if body.rows:
        divider(body)
    body.rows += 1
    r = tk.Frame(body, bg=body.cget("bg"))
    r.pack(fill="x")
    left = tk.Frame(r, bg=r.cget("bg"))
    left.pack(side="left", fill="x", expand=True, padx=(px(SPACE[4]), px(SPACE[2])), pady=px(SPACE[3] - 1))
    label(left, title).pack(fill="x")
    if desc:
        label(left, desc, "caption", "muted", wraplength=px(330)).pack(fill="x")
    right = tk.Frame(r, bg=r.cget("bg"))
    right.pack(side="right", padx=(0, px(SPACE[3])))
    if on_click:
        def paint(v, frames=(r, left, right)):
            color = mix(T["surface"], T["surface_hover"], v)
            for fr in frames:
                fr.config(bg=color)
                for ch in fr.winfo_children():
                    if isinstance(ch, tk.Label):
                        ch.config(bg=color)
        fade = Tween(r, paint)
        for w in (r, left, right, *left.winfo_children()):
            w.bind("<Enter>", lambda e: fade.to(1, MOTION["hover"], ease_colour), add="+")
            w.bind("<Leave>", lambda e: fade.to(0, MOTION["hover"], ease_colour), add="+")
            w.bind("<Button-1>", lambda e: on_click(), add="+")
            w.config(cursor="hand2")
    return right


# --------------------------------------------------------------------- overlay

class Overlay:
    """Floating pill above the taskbar. Never takes focus and ignores clicks."""

    W, H = 520, 64

    def __init__(self, root, show_idle, key_text):
        self.root = root
        self.show_idle = show_idle
        self.key_text = key_text
        self.hover = False  # the hover bar is showing in the pill's place
        self.listening = False  # wake word mode is on
        self.finish_hint = None
        self.scale = S
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True, "-transparentcolor", KEY, "-alpha", 0.97)
        w, h = px(self.W), px(self.H)
        self.canvas = tk.Canvas(self.win, width=w, height=h, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        rect = work_area()
        self.x = rect.left + (rect.right - rect.left - w) // 2
        self.y = rect.bottom - h - px(12)
        self.w, self.h = w, h
        self.win.geometry(f"{w}x{h}+{self.x}+{self.y}")
        self.win.update_idletasks()
        set_ex_style(self.win, WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED)
        self.state, self.text, self.until = "idle", "", 0
        self.levels = deque([0.0] * 28, maxlen=28)
        self.tick = 0

    def pill_zone(self):
        """Screen area around the idle pill that brings up the hover bar."""
        cx = self.x + self.w // 2
        return cx - px(70), self.y + self.h - px(30), cx + px(70), self.y + self.h + px(8)

    def set(self, state, text="", seconds=0):
        if state in ("recording", "handsfree") and self.state not in ("recording", "handsfree"):
            self.levels.extend([0.0] * self.levels.maxlen)
        self.state, self.text = state, text
        self.until = time.time() + seconds if seconds else 0

    def push_level(self, level):
        self.levels.append(level)

    def _pill(self, w, h, fill=None):
        x0, y0 = round((px(self.W) - w) / 2), px(self.H) - h - px(4)
        pill(self.canvas, x0, y0, x0 + w, y0 + h, fill or T["surface"], T["popup_border"], T["edge_glow"])
        return x0, y0, x0 + w, y0 + h

    def _wave(self, x, cy):
        for i, lv in enumerate(self.levels):
            bh = max(px(2), min(1.0, (lv / 0.06) ** 0.6) * px(22))
            self.canvas.create_rectangle(x + i * px(5), cy - bh / 2, x + i * px(5) + px(2.5),
                                         cy + bh / 2, fill=T["text"], outline="")

    def _rec_dot(self, x, cy):
        dot(self.canvas, x, cy, px(4 + 1.5 * np.sin(self.tick / 4)), T["recording"])

    def draw(self):
        self.tick += 1
        if self.until and time.time() > self.until:
            self.set("idle")
        c = self.canvas
        clear(c)

        if self.state == "idle":
            if (self.show_idle or self.listening) and not self.hover:
                x0, y0 = round((px(self.W) - px(44)) / 2), px(self.H) - px(12)  # HoverBar grows from here
                pill(c, x0, y0, x0 + px(44), y0 + px(6), T["idle_pill"])
                if self.listening:  # a quiet "I'm listening for the wake word" mark
                    dot(c, x0 - px(8), y0 + px(3), px(3), T["accent"])
            return

        if self.state == "recording":
            x0, y0, x1, y1 = self._pill(px(200), px(40))
            cy = (y0 + y1) / 2
            self._rec_dot(x0 + px(18), cy)
            self._wave(x0 + px(34), cy)
            return

        if self.state == "handsfree":
            hint = f"{self.finish_hint or self.key_text + ' to finish'} · Esc to cancel"
            tw = tkfont.Font(font=F["caption"]).measure(hint)
            x0, y0, x1, y1 = self._pill(px(200) + tw + px(14), px(40))
            cy = (y0 + y1) / 2
            self._rec_dot(x0 + px(18), cy)
            self._wave(x0 + px(34), cy)
            c.create_text(x0 + px(186), cy, text=hint, fill=T["muted"], font=F["caption"], anchor="w")
            return

        if self.state == "busy":
            x0, y0, x1, y1 = self._pill(px(120), px(40))
            cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
            for i in range(3):
                r = px(2.5 + 1.5 * max(0, np.sin(self.tick / 5 - i * 0.6)))
                dot(c, cx + (i - 1) * px(14), cy, r, T["dim"])
            return

        # "message" / "error": text pill sized to its text
        tw = tkfont.Font(font=F["body"]).measure(self.text)
        width = min(px(self.W) - px(8), tw + px(44))
        x0, y0, x1, y1 = self._pill(width, px(40))
        mark = T["danger"] if self.state == "error" else T["accent"]
        cy = (y0 + y1) / 2
        dot(c, x0 + px(18), cy, px(3), mark)
        c.create_text(x0 + px(30), cy, text=self.text, fill=T["text"], font=F["body"], anchor="w")


class HoverBar:
    """Replaces the idle pill while you hover it: scratchpad, settings and microphone
    on the left, paste-last on the right. It grows out of the idle pill, and a white
    circle slides under whatever you point at. Clicking it doesn't take focus from your app."""

    W, H = 300, 96        # includes room above the bar for tooltips
    BAR_H, ITEM = 44, 36
    IDLE_W, IDLE_H, IDLE_BOTTOM = 44, 6, 6   # the Overlay's idle pill, which the bar grows from

    def __init__(self, app):
        self.app = app
        ov = app.overlay
        self.s = S
        self.w, self.h = px(self.W), px(self.H)
        self.x = ov.x + ov.w // 2 - self.w // 2
        self.y = ov.y + ov.h - self.h
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True, "-transparentcolor", KEY)
        self.canvas = tk.Canvas(self.win, width=self.w, height=self.h, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.win.geometry(f"{self.w}x{self.h}+-20000+-20000")
        self.win.update_idletasks()
        set_ex_style(self.win, WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
        self.visible = False
        self.hot = None

        # layout of the full bar: three round icon buttons | paste-last capsule
        item = px(self.ITEM)
        self.paste_w = px(10 + 16 + 8 + 14) + tkfont.Font(font=F["body"]).measure("Paste last")
        self.bar_w = px(4) + 3 * item + px(13) + self.paste_w + px(4)
        self.bx0 = round((self.w - self.bar_w) / 2)
        self.by1 = self.h - px(2)
        self.by0 = self.by1 - px(self.BAR_H)
        x = self.bx0 + px(4)
        self.items = []  # name, glyph, x0 (relative to the bar), width
        for name in ("notes", "settings", "mic"):
            self.items.append((name, GLYPH[name], x - self.bx0, item))
            x += item
        self.sep_x = x + px(6) - self.bx0
        self.items.append(("paste", GLYPH["paste"], x + px(13) - self.bx0, self.paste_w))

        redraw = Redraw(self.canvas, self.draw)
        self.grow = Tween(self.canvas, redraw)        # 0 = idle pill, 1 = full bar
        self.dot_x = Tween(self.canvas, redraw)       # the white circle
        self.dot_w = Tween(self.canvas, redraw, float(item))
        self.dot_a = Tween(self.canvas, redraw)
        self.tip_a = Tween(self.canvas, redraw)
        self.tip_x = Tween(self.canvas, redraw)
        self.tip = ""
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda e: self._set_hot(None))
        self.canvas.bind("<Button-1>", self._click)

    def _item_at(self, x, y):
        if not (self.by0 <= y <= self.by1) or self.grow.value < 0.9:
            return None
        for name, _, x0, w in self.items:
            if x0 <= x - self.bx0 <= x0 + w:
                return name
        return None

    def _motion(self, e):
        self._set_hot(self._item_at(e.x, e.y))

    def _tip_text(self, name):
        mic = self.app.mic_name or self.app.mics.pick(self.app.cfg["mic"])[1] or "Windows default"
        return {"notes": "Scratchpad", "settings": "Settings & history", "mic": f"Microphone · {mic}"[:48],
                "paste": f"Recent transcripts · {self.app.cfg['paste_last_keys'].title()}"}[name]

    def _set_hot(self, name):
        if name == self.hot:
            return
        appearing = self.hot is None
        self.hot = name
        self.canvas.config(cursor="hand2" if name else "")
        if not name:
            self.dot_a.to(0, MOTION["hover"], ease_colour)
            self.tip_a.to(0, MOTION["hover"], ease_colour)
            return
        _, _, x0, w = next(i for i in self.items if i[0] == name)
        self.tip = self._tip_text(name)
        tw = tkfont.Font(font=F["caption"]).measure(self.tip) + px(20)
        tip_x = max(px(2), min(self.w - tw - px(2), self.bx0 + x0 + w / 2 - tw / 2))
        if appearing and self.dot_a.value < 0.05:  # appear in place, don't fly in from the last spot
            self.dot_x.set(x0)
            self.dot_w.set(w)
            self.tip_x.set(tip_x)
        else:
            self.dot_x.to(x0)
            self.dot_w.to(w)
            self.tip_x.to(tip_x)
        self.dot_a.to(1, MOTION["hover"], ease_colour)
        self.tip_a.to(1, MOTION["hover"])

    def _click(self, e):
        name = self._item_at(e.x, e.y)
        if name == "notes":
            self.app.open_panel("notes")
        elif name == "settings":
            self.app.open_panel("settings")
        elif name == "mic":
            self.app.mic_menu.show()
        elif name == "paste":
            self.app.picker.show()

    def draw(self):
        c = self.canvas
        clear(c)
        g = self.grow.value
        if g <= 0 and not self.visible:
            return
        lerp = lambda a, b: a + (b - a) * g
        w, h = lerp(px(self.IDLE_W), self.bar_w), lerp(px(self.IDLE_H), px(self.BAR_H))
        bottom = lerp(self.h - px(self.IDLE_BOTTOM), self.by1)
        x0 = round(self.w / 2 - w / 2)
        y0 = round(bottom - h)
        fill = mix(T["idle_pill"], T["surface"], g)
        pill(c, x0, y0, x0 + round(w), y0 + round(h), fill, mix(T["idle_pill"], T["popup_border"], g),
             T["edge_glow"] if g > 0.6 else "")
        a = max(0.0, min(1.0, (g - 0.55) / 0.45))  # contents fade in near the end of the growth
        if a <= 0:
            return
        shift = x0 - self.bx0  # follow the bar while it's still growing
        cy = y0 + h / 2
        item = px(self.ITEM)
        sx = self.bx0 + shift + self.sep_x
        c.create_line(sx, cy - px(9), sx, cy + px(9), fill=mix(fill, T["border"], a), width=max(1, px(1)))
        da = self.dot_a.value * a
        if da > 0.01:
            dx, dw = self.bx0 + shift + self.dot_x.value, self.dot_w.value
            put(c, round(dx), round(cy - item / 2),
                shape(round(dw), item, item / 2, mix(T["surface"], T["select"], da)))
        for name, glyph_, ix, iw in self.items:
            # icons turn dark as the circle passes under them
            under = da * max(0.0, 1 - abs(self.dot_x.value - ix) / item)
            color = mix(mix(fill, T["dim"], a), T["select_contrast"], under)
            if name == "paste":
                left = self.bx0 + shift + ix + px(10)
                icon(c, left + px(8), cy, glyph_, color)
                c.create_text(left + px(24), cy, text="Paste last", anchor="w", font=F["body"], fill=color)
            else:
                icon(c, self.bx0 + shift + ix + iw / 2, cy, glyph_, color)
        ta = self.tip_a.value * a
        if self.tip and ta > 0.05:
            f = tkfont.Font(font=F["caption"])
            tw, th = f.measure(self.tip) + px(20), px(28)
            ty1 = self.by0 - px(8) + round((1 - ta) * px(4))  # rises 4 px as it appears
            tx0 = round(self.tip_x.value)
            put(c, tx0, ty1 - th, shape(tw, th, px(RADIUS["control"]), T["surface"], T["popup_border"],
                                        max(1, px(1))))
            c.create_text(tx0 + px(10), ty1 - th / 2, text=self.tip, anchor="w", font=F["caption"],
                          fill=mix(T["surface"], T["text"], ta))

    def contains(self, x, y):
        return (self.visible and self.x + self.bx0 - px(6) <= x <= self.x + self.bx0 + self.bar_w + px(6)
                and self.y + self.by0 - px(6) <= y <= self.y + self.by1 + px(10))

    def show(self):
        if not self.visible:
            self.win.geometry(f"+{self.x}+{self.y}")
            self.win.update_idletasks()
            self.visible = True
            self.hot = None
            self.dot_a.set(0)
            self.tip_a.set(0)
            self.grow.to(1, MOTION["enter"])

    def hide(self, animate=True):
        """Shrinks back into the idle pill. animate=False when something else (the
        recording pill) is about to take its place."""
        if self.visible:
            self.visible = False
            self.hot = None
            self.dot_a.to(0, MOTION["hover"])
            self.tip_a.set(0)
            self.grow.to(0, MOTION["enter"] if animate else 0, done=self._park)

    def _park(self):
        if not self.visible:
            self.win.geometry("+-20000+-20000")


# ---------------------------------------------------------------- popup windows

class Popup:
    """A borderless window that opens above the hover bar and closes when you click away."""

    OFFSCREEN = "+-20000+-20000"

    def __init__(self, app):
        self.app = app
        self.visible = False
        self.pinned = False
        self.had_focus = False
        self.shown_at = 0
        self.win = tk.Toplevel(app.root, bg=T["popup_border"])
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(self.OFFSCREEN)
        self.win.update_idletasks()
        round_corners(self.win)
        self.frame = tk.Frame(self.win, bg=T["bg"])
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)
        self.win.bind("<Button-1>", lambda e: self.win.focus_force(), add="+")
        self._xy = (0, 0)
        self._enter = Tween(self.win, self._entering, 1.0)

    def _entering(self, v):
        """Fade in while rising the last few pixels into place."""
        x, y = self._xy
        self.win.geometry(f"+{x}+{y + round((1 - v) * px(MOTION['rise']))}")
        self.win.attributes("-alpha", v)

    def place(self, w, h):
        bar = self.app.bar
        x = bar.x + bar.w // 2 - w // 2
        y = bar.y + int(bar.by0) - h - px(10)
        self._xy = (x, y)
        appearing = not self.visible
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        if appearing:
            self._enter.set(0)
        self.win.update_idletasks()  # apply the move before focusing, or it can stay off-screen
        self.win.lift()
        if appearing:
            self._enter.to(1, MOTION["enter"])
        self.visible, self.had_focus, self.shown_at = True, False, time.time()

    def take_focus(self, widget=None):
        force_foreground(hwnd_of(self.win))
        target = widget or self.win
        target.focus_force()
        for delay in (60, 200):  # first showing isn't ready for focus yet
            self.win.after(delay, lambda: self.visible and target.focus_force())

    def hide(self):
        if self.visible:
            self._enter.set(1)
            self.win.geometry(self.OFFSCREEN)
            self.visible = False
            self.set_pinned(False)

    def set_pinned(self, value):
        self.pinned = value

    def contains(self, x, y):
        if not self.visible:
            return False
        rx, ry = self.win.winfo_rootx(), self.win.winfo_rooty()
        return rx <= x < rx + self.win.winfo_width() and ry <= y < ry + self.win.winfo_height()

    def focused(self):
        return self.visible and user32.GetForegroundWindow() == hwnd_of(self.win)

    def header(self, parent, title, subtitle=None, pin=True):
        head = tk.Frame(parent, bg=parent.cget("bg"))
        head.pack(fill="x", padx=(px(SPACE[5]), px(SPACE[3])), pady=(px(SPACE[4]), px(SPACE[1])))
        lbl = label(head, title, "title")
        lbl.pack(side="left")
        Button(head, GLYPH["close"], self.hide, kind="subtle", icon=True, pad_x=8).pack(side="right")
        pin_btn = None
        if pin:
            pin_btn = Button(head, GLYPH["pin"], lambda: self.set_pinned(not self.pinned), kind="subtle",
                             icon=True, pad_x=8)
            pin_btn.pack(side="right")
        sub = None
        if subtitle is not None:
            sub = label(parent, subtitle, "caption", "muted")
            sub.pack(fill="x", padx=px(SPACE[5]))
        return lbl, sub, pin_btn


# ------------------------------------------------- recent transcripts (clipboard)

RECENT_KEEP, PER_PAGE = 9, 3


def recent_pages():
    entries = read_history()[-RECENT_KEEP:][::-1]
    return entries, max(1, math.ceil(len(entries) / PER_PAGE))


def when_label(entry):
    when = datetime.fromisoformat(entry["ts"])
    day = "Today" if when.date() == datetime.now().date() else when.strftime("%d %b")
    return f"{day} {when:%H:%M}"


def transcript_card(parent, entry, number, buttons, on_body=None, wrap=360):
    """One transcript: number, time and buttons on top, the text below."""
    card = Card(parent)
    card.pack(fill="x", pady=(0, px(SPACE[2])))
    b = card.body
    top = tk.Frame(b, bg=b.cget("bg"))
    top.pack(fill="x", padx=px(SPACE[3]), pady=(px(SPACE[2]), 0))
    if number:
        key_chip(top, str(number)).pack(side="left", padx=(0, px(SPACE[2])))
    label(top, when_label(entry), "caption", "muted").pack(side="left")
    for text, fn, kind, *confirm in reversed(buttons):
        Button(top, text, fn, kind=kind, font=F["caption"], pad_x=10, confirm=confirm[0] if confirm else None).pack(
            side="right", padx=(px(SPACE[1]), 0))
    body = tk.Frame(b, bg=b.cget("bg"))
    body.pack(fill="x", padx=px(SPACE[3]), pady=(px(SPACE[1]), px(SPACE[3])))
    text = entry["text"] if len(entry["text"]) < 220 else entry["text"][:217] + "…"
    lbl = label(body, text, wraplength=px(wrap))
    lbl.pack(fill="x")
    if on_body:
        for w in (body, lbl):
            w.config(cursor="hand2")
            w.bind("<Button-1>", lambda e: on_body(), add="+")
    return card, body


def pager(parent, on_prev, on_next):
    row_ = tk.Frame(parent, bg=parent.cget("bg"))
    Button(row_, GLYPH["prev"], on_prev, kind="subtle", icon=True, pad_x=7).pack(side="left")
    lbl = label(row_, "", "caption", "muted")
    lbl.pack(side="left", padx=px(2))
    Button(row_, GLYPH["next"], on_next, kind="subtle", icon=True, pad_x=7).pack(side="left")
    return row_, lbl


class Picker(Popup):
    """Like Windows' clipboard history, for your dictations: the 9 most recent,
    3 per page. Click one (or press 1-3) to paste it where you were typing."""

    W = 440
    HINT = "Press 1–3 or click to paste · ←/→ pages · Esc closes"

    def __init__(self, app):
        super().__init__(app)
        self.page = 0
        self.shown = []
        f = self.frame
        head = tk.Frame(f, bg=T["bg"])
        head.pack(fill="x", padx=px(SPACE[4]), pady=(px(SPACE[3]), px(SPACE[2])))
        label(head, "Recent transcripts", "subtitle").pack(side="left")
        Button(head, GLYPH["close"], self.hide, kind="subtle", icon=True, pad_x=8).pack(side="right")
        pg, self.page_lbl = pager(head, lambda: self.turn(-1), lambda: self.turn(1))
        pg.pack(side="right", padx=px(SPACE[1]))
        self.cards = tk.Frame(f, bg=T["bg"])
        self.cards.pack(fill="x", padx=px(SPACE[4]))
        self.status = label(f, self.HINT, "caption", "muted")
        self.status.pack(fill="x", padx=px(SPACE[4]), pady=(0, px(SPACE[3])))
        for key, fn in (("<Escape>", lambda e: self.hide()), ("<Left>", lambda e: self.turn(-1)),
                        ("<Right>", lambda e: self.turn(1)), ("<Return>", lambda e: self.choose(0))):
            self.win.bind(key, fn)
        for n in (1, 2, 3):
            self.win.bind(str(n), lambda e, i=n - 1: self.choose(i))

    def render(self):
        for w in self.cards.winfo_children():
            w.destroy()
        entries, pages = recent_pages()
        self.page = max(0, min(self.page, pages - 1))
        self.page_lbl.config(text=f"{self.page + 1} / {pages}")
        self.status.config(text=self.HINT)
        self.shown = entries[self.page * PER_PAGE:(self.page + 1) * PER_PAGE]
        if not self.shown:
            label(self.cards, "Nothing yet. Your dictations will show up here.", "body", "muted").pack(
                fill="x", pady=px(SPACE[2]))
        for i, e in enumerate(self.shown):
            transcript_card(self.cards, e, i + 1,
                            [("Copy", lambda t=e["text"]: pyperclip.copy(t), "standard", "Copied"),
                             ("Paste", lambda i=i: self.choose(i), "primary")],
                            on_body=lambda i=i: self.choose(i))
        if self.visible:
            self._resize()

    def _resize(self):
        self.win.update_idletasks()
        self.place(px(self.W), self.frame.winfo_reqheight() + 2)

    def turn(self, step):
        self.page += step
        self.render()

    def choose(self, i):
        if i < len(self.shown):
            text = self.shown[i]["text"]
            self.hide()
            self.app.paste_text(text, restore_focus=True)

    def show(self):
        self.app.panel.hide()
        self.app.mic_menu.hide()
        self.page = 0
        self.render()
        self._resize()
        self.take_focus()


def mic_rows(parent, app, on_choose):
    """The microphone choices as rows with a tick on the selected one."""
    body = group(parent)
    pref = app.cfg["mic"]
    mics = app.mics
    _, best = mics.pick("auto")
    using = app.mic_name or mics.pick(pref)[1]
    choices = [("auto", "Automatic", f"Best available · now {best or 'Windows default'}")]
    choices += [(n, n, "In use" if n == using and pref != "auto" else
                 ("Not connected" if n not in mics.names() else None))
                for n in mics.names() if Mics.score(n) >= 0]
    if pref != "auto" and pref not in mics.names():
        choices.append((pref, pref, "Not connected · using the best available"))
    for value, title, desc in choices:
        right = row(body, title, desc, on_click=lambda v=value: on_choose(v))
        tk.Label(right, text=GLYPH["check"] if pref == value else "", font=F["icon"], fg=T["accent"],
                 bg=right.cget("bg"), width=2).pack()
    return body


class MicMenu(Popup):
    """Pick the microphone straight from the hover bar."""

    W = 380

    def __init__(self, app):
        super().__init__(app)
        self.win.bind("<Escape>", lambda e: self.hide())

    def render(self):
        for w in self.frame.winfo_children():
            w.destroy()
        inner = tk.Frame(self.frame, bg=T["bg"])
        inner.pack(fill="both", expand=True, padx=px(SPACE[4]), pady=(px(SPACE[3]), px(SPACE[4])))
        label(inner, "Microphone", "subtitle").pack(fill="x")
        mic_rows(inner, self.app, self.choose)

    def choose(self, value):
        self.app.set_option("mic", value)
        self.app.post("overlay", "message",
                      "Mic: automatic" if value == "auto" else f"Mic: {value}"[:70], 1.5)
        if self.app.panel.visible:
            self.app.panel.refresh()
        self.hide()

    def show(self):
        self.app.panel.hide()
        self.app.picker.hide()
        self.render()
        self.win.update_idletasks()
        self.place(px(self.W), self.frame.winfo_reqheight() + 2)
        self.take_focus()


# --------------------------------------------------------- scratchpad + settings

class NavList(tk.Canvas):
    """Settings sidebar: a filled capsule slides to the chosen page.
    Keyboard: Tab in, Up/Down to move, Enter or Space opens."""

    def __init__(self, parent, pages, icons, current, on_choose):
        self.pages, self.icons, self.current, self.on_choose = pages, icons, current, on_choose
        self.ih, self.gap = px(36), px(2)
        super().__init__(parent, height=len(pages) * (self.ih + self.gap), bg=parent.cget("bg"),
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.hot = self.focus_i = None
        redraw = Redraw(self, self.draw)
        self.cap = Tween(self, redraw, float(pages.index(current)))
        self.hover = [Tween(self, redraw) for _ in pages]
        self.bind("<Configure>", redraw)
        self.bind("<Motion>", lambda e: self._set_hot(self._at(e.y)))
        self.bind("<Leave>", lambda e: self._set_hot(None))
        self.bind("<Button-1>", self._click)
        self.bind("<FocusIn>", lambda e: (setattr(self, "focus_i", self.pages.index(self.current)), redraw()))
        self.bind("<FocusOut>", lambda e: (setattr(self, "focus_i", None), redraw()))
        self.bind("<Up>", lambda e: self._move(-1))
        self.bind("<Down>", lambda e: self._move(1))
        for key in ("<space>", "<Return>"):
            self.bind(key, lambda e: self.focus_i is not None and self.on_choose(self.pages[self.focus_i]))

    def _at(self, y):
        i = int(y // (self.ih + self.gap))
        return i if 0 <= i < len(self.pages) else None

    def _click(self, e):
        i = self._at(e.y)
        if i is not None:
            self.on_choose(self.pages[i])

    def _set_hot(self, i):
        if i != self.hot:
            if self.hot is not None:
                self.hover[self.hot].to(0, MOTION["hover"], ease_colour)
            if i is not None:
                self.hover[i].to(1, MOTION["hover"], ease_colour)
            self.hot = i

    def _move(self, step):
        self.focus_i = max(0, min(len(self.pages) - 1, (self.focus_i or 0) + step))
        self.draw()

    def select(self, name):
        self.current = name
        self.cap.to(float(self.pages.index(name)))

    def draw(self):
        clear(self)
        w, ih, step = self.winfo_width(), self.ih, self.ih + self.gap
        if w < 10:
            return
        for i, hv in enumerate(self.hover):
            if hv.value > 0.01:
                put(self, 0, i * step, shape(w, ih, ih / 2, mix(T["nav"], T["surface"], hv.value)))
        put(self, 0, round(self.cap.value * step), shape(w, ih, ih / 2, T["surface_hover"], "", 1, T["edge_glow"]))
        if self.focus_i is not None:
            put(self, 0, self.focus_i * step, shape(w, ih, ih / 2, "", T["focus"], max(1, px(1.5))))
        for i, name in enumerate(self.pages):
            near = max(0.0, 1 - abs(self.cap.value - i), self.hover[i].value)
            color = mix(T["dim"], T["text"], near)
            cy = i * step + ih / 2
            self.create_text(px(14), cy, text=self.icons[name], font=F["icon"], fill=color, anchor="w")
            self.create_text(px(44), cy, text=name, font=F["body"], fill=color, anchor="w")


class StatsCorner(tk.Canvas):
    """Bottom of the sidebar: today's numbers, each with a thin colour bar."""

    def __init__(self, parent):
        super().__init__(parent, height=1, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.items = []
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, words, wpm, saved):
        self.items = [(f"{words:,}", "words today", T["stat1"])]
        if wpm:
            self.items.append((f"{wpm}", "wpm", T["stat2"]))
        if saved >= 1:
            self.items.append((f"~{saved:.0f} min", "saved today", T["stat3"]))
        self.draw()

    def draw(self):
        clear(self)
        num, small = tkfont.Font(font=F["stat"]), tkfont.Font(font=F["small"])
        nh, lh = num.metrics("linespace"), small.metrics("linespace")
        cell, col = nh + lh + px(SPACE[3]), self.winfo_width() / 2
        for i, (value, what, color) in enumerate(self.items):
            # the first two share a row; a third (time saved) gets its own
            x, y = ((i % 2) * col if i < 2 else 0), (i // 2) * cell
            put(self, x, y + px(5), shape(max(1, px(2)), nh - px(9), px(1), color))
            self.create_text(x + px(8), y, text=value, font=F["stat"], fill=T["text"], anchor="nw")
            self.create_text(x + px(8), y + nh, text=what, font=F["small"], fill=T["muted"], anchor="nw")
        h = max(1, math.ceil(len(self.items) / 2) * cell)
        if int(float(self.cget("height"))) != h:
            self.config(height=h)


def brand_mark(parent):
    """White circle with a dark microphone: the app's mark."""
    d = px(24)
    c = tk.Canvas(parent, width=d, height=d, bg=parent.cget("bg"), highlightthickness=0, bd=0)
    dot(c, d / 2, d / 2, d / 2, T["select"])
    icon(c, d / 2, d / 2, GLYPH["mic"], T["select_contrast"], pt=9)
    return c


class Panel(Popup):
    """Two pages in one window: the scratchpad, and settings with a sidebar
    (General, Microphone, Dictionary, History)."""

    PAGES = ("General", "Microphone", "Dictionary", "History")
    ICONS = {"General": GLYPH["settings"], "Microphone": GLYPH["mic"],
             "Dictionary": GLYPH["dictionary"], "History": GLYPH["history"]}
    NOTES_SIZE, SETTINGS_SIZE = (440, 560), (720, 600)

    def __init__(self, app):
        super().__init__(app)
        self.page = "notes"
        self.tab = "General"
        self.hist_page = 0
        self._save_job = None
        self._pages = {}  # built settings pages, kept while their data hasn't changed
        self.notes_root = tk.Frame(self.frame, bg=T["bg"])
        self.settings_root = tk.Frame(self.frame, bg=T["bg"])
        self._build_notes(self.notes_root)
        self._build_settings(self.settings_root)

    # -- show / hide
    def show(self, page, tab=None, pinned=False):
        self.app.picker.hide()
        self.app.mic_menu.hide()
        self.page = "notes" if page == "notes" else "settings"
        if self.page == "notes":
            self.settings_root.pack_forget()
            self.notes_root.pack(fill="both", expand=True)
            size = self.NOTES_SIZE
        else:
            self.notes_root.pack_forget()
            self.settings_root.pack(fill="both", expand=True)
            size = self.SETTINGS_SIZE
            tab = {"Settings": "General"}.get(tab, tab)
            self.open_tab(tab or self.tab)
        if pinned:
            self.set_pinned(True)
        self.refresh()
        self.place(px(size[0]), px(size[1]))
        self.take_focus(self.notes.text if self.page == "notes" else None)

    def hide(self):
        if self.visible and self._save_job:
            self.win.after_cancel(self._save_job)
            self.save_notes()
        super().hide()

    def set_pinned(self, value):
        self.pinned = value
        for btn in (getattr(self, "notes_pin", None), getattr(self, "settings_pin", None)):
            if btn:
                btn.set_text(GLYPH["pinned"] if value else GLYPH["pin"])
                btn.set_kind("selected" if value else "subtle")

    def refresh(self):
        if self.page == "notes":
            return
        self.stats.set(*stats(read_history()))
        for name in [n for n in self._pages if n != self.tab]:  # rebuilt when next visited
            self._pages.pop(name).destroy()
        self.open_tab(self.tab, keep_scroll=True)

    # -- scratchpad
    def _build_notes(self, f):
        _, self.notes_sub, self.notes_pin = self.header(f, "Scratchpad", "Saves as you type. Dictating while it's open types here.")
        self.notes = RoundedText(f, height=10, stretch=True, fill=T["surface"], quiet=True)
        self.notes.pack(fill="both", expand=True, padx=px(SPACE[4]), pady=(px(SPACE[3]), px(SPACE[2])))
        t = self.notes.text
        if NOTES_PATH.exists():
            t.insert("1.0", NOTES_PATH.read_text(encoding="utf-8"))
        t.edit_reset()
        t.edit_modified(False)
        t.bind("<<Modified>>", self._notes_changed)
        foot = tk.Frame(f, bg=T["bg"])
        foot.pack(fill="x", padx=px(SPACE[4]), pady=(0, px(SPACE[3])))
        self.notes_status = label(foot, "", "caption", "muted")
        self.notes_status.pack(side="left")
        Button(foot, "Open file", lambda: os.startfile(NOTES_PATH) if NOTES_PATH.exists() else None,
               kind="subtle").pack(side="right")
        Button(foot, "Copy all", lambda: pyperclip.copy(t.get("1.0", "end-1c")), confirm="Copied").pack(
            side="right", padx=px(SPACE[1]))

    def _notes_changed(self, _):
        t = self.notes.text
        if not t.edit_modified():
            return
        t.edit_modified(False)
        self.notes_status.config(text="Saving…")
        if self._save_job:
            self.win.after_cancel(self._save_job)
        self._save_job = self.win.after(600, self.save_notes)

    def save_notes(self):
        self._save_job = None
        tmp = NOTES_PATH.with_suffix(".tmp")
        tmp.write_text(self.notes.text.get("1.0", "end-1c"), encoding="utf-8")
        os.replace(tmp, NOTES_PATH)
        self.notes_status.config(text=f"Saved {datetime.now():%H:%M}")

    # -- settings window: sidebar + scrolling page
    def _build_settings(self, f):
        nav = tk.Frame(f, bg=T["nav"], width=px(196))
        nav.pack(side="left", fill="y")
        nav.pack_propagate(False)
        brand = tk.Frame(nav, bg=T["nav"])
        brand.pack(fill="x", padx=px(SPACE[4]), pady=(px(SPACE[4]), px(SPACE[5])))
        brand_mark(brand).pack(side="left")
        label(brand, "LocalFlow", "body_strong").pack(side="left", padx=px(SPACE[2]))
        self.nav = NavList(nav, list(self.PAGES), self.ICONS, self.tab, self.open_tab)
        self.nav.pack(fill="x", padx=px(SPACE[2]))
        bottom = tk.Frame(nav, bg=T["nav"])
        bottom.pack(side="bottom", fill="x", padx=px(SPACE[3]), pady=px(SPACE[3]))
        self.stats = StatsCorner(bottom)
        self.stats.pack(fill="x", padx=px(SPACE[1]), pady=(0, px(SPACE[3])))
        btns = tk.Frame(bottom, bg=T["nav"])
        btns.pack(fill="x")
        Button(btns, "Restart", self.app.restart, kind="standard", font=F["caption"]).pack(side="left")
        Button(btns, "Quit", self.app.quit, kind="subtle", font=F["caption"]).pack(side="left", padx=px(SPACE[1]))

        main = tk.Frame(f, bg=T["bg"])
        main.pack(side="left", fill="both", expand=True)
        self.page_title, _, self.settings_pin = self.header(main, "General")
        self.scroll = ScrollArea(main)
        self.scroll.pack(fill="both", expand=True, padx=(px(SPACE[5]), px(SPACE[1])),
                         pady=(0, px(SPACE[4])))

    def open_tab(self, name, keep_scroll=False):
        if name not in self.PAGES:
            name = "General"
        changed = name != self.tab
        self.tab = name
        self.page_title.config(text=name)
        inner = self.scroll.inner
        y = self.scroll.canvas.yview()[0]
        page = self._pages.get(name)
        if page is None or keep_scroll:  # keep_scroll: this page's data changed, rebuild it
            if page is not None:
                page.destroy()
            page = self._pages[name] = tk.Frame(inner, bg=T["bg"])
            getattr(self, "_page_" + name.lower())(page)
        for other in self._pages.values():
            if other is not page:
                other.pack_forget()
        page.pack(fill="x")
        self.scroll.inner.update_idletasks()
        if changed or not keep_scroll:
            self.scroll.top()
        else:
            self.scroll.canvas.yview_moveto(y)
            self.scroll._sync()
        self.nav.select(name)  # after building the page, so the slide isn't swallowed by it

    def _switch(self, right, key, getter=None, setter=None):
        cfg = self.app.cfg
        value = getter() if getter else cfg[key]
        Switch(right, value, setter or (lambda v: self.app.set_option(key, v))).pack()

    # -- General
    def _page_general(self, p):
        cfg = self.app.cfg
        b = group(p, "Dictation")
        r = row(b, "Hold to talk", "Double-tap for hands-free · Esc cancels")
        Button(r, "Change", self.app.change_hotkey, font=F["caption"]).pack(side="right", padx=(px(SPACE[2]), 0))
        key_chip(r, key_label(cfg["hold_keys"])).pack(side="right")
        r = row(b, "Recent transcripts", "Shows your last 9 to paste again")
        Button(r, "Change", lambda: self.app.change_hotkey("paste"), font=F["caption"]).pack(
            side="right", padx=(px(SPACE[2]), 0))
        key_chip(r, cfg["paste_last_keys"].title()).pack(side="right")

        b = group(p, "Wake word")
        self._switch(row(b, "Start with your voice",
                         f'Say "{cfg["wake_phrase"]}", wait for the chime, then talk. Stops after a '
                         f'{cfg["ambient_end_silence"]:.0f} s pause. The laptop mic stays on.'), "ambient_mode")
        r = row(b, "Wake phrase", "Two short words work best")
        phrase = RoundedEntry(r, 14)
        phrase.entry.insert(0, cfg["wake_phrase"])

        def save_phrase():
            self.app.set_option("wake_phrase", phrase.entry.get().strip() or DEFAULTS["wake_phrase"])
            self.refresh()

        Button(r, "Save", save_phrase, font=F["caption"]).pack(side="right", padx=(px(SPACE[2]), 0))
        phrase.pack(side="right")
        phrase.entry.bind("<Return>", lambda e: save_phrase())
        if cfg["ambient_mode"]:
            heard = self.app.ambient.last_heard
            row(b, "Last heard", (f'"{heard}"' if heard else "Nothing yet") +
                f' · listening on {self.app.ambient.mic_name or "the laptop mic"}')

        b = group(p, "Text")
        self._switch(row(b, "Remove filler words", 'Drops "um" and "uh"'), "remove_fillers")
        self._switch(row(b, "Voice commands", 'Say "new line" or "new paragraph"'), "voice_commands")
        self._switch(row(b, "Lists", 'Say "one… two…" or "next point…" to make a list'), "smart_lists")
        self._switch(row(b, "Learn from my fixes", "Adds names you correct to the dictionary"),
                     "learn_corrections")
        self._switch(row(b, "AI cleanup", "Fixes grammar with Ollama · adds 1–3 s"), "llm_cleanup")

        b = group(p, "Speech engine")
        running = "parakeet" if self.app.engine and "Parakeet" in self.app.engine.name else \
            ("whisper" if self.app.engine else cfg["engine"])
        desc = "Parakeet is fastest on this PC" if cfg["engine"] == running else "Restart to switch engines"
        r = row(b, "Engine", desc)
        Segmented(r, (("whisper", "Whisper"), ("parakeet", "Parakeet")), cfg["engine"],
                  lambda v: (self.app.set_option("engine", v),
                             self.win.after(MOTION["move"], self.refresh))).pack()
        if cfg["engine"] != running:
            r = row(b, "Restart LocalFlow", "Takes about 10 seconds")
            Button(r, "Restart now", self.app.restart, kind="primary", font=F["caption"]).pack()

        b = group(p, "App")
        self._switch(row(b, "Sounds", "Beep when recording starts and stops"), "sounds")
        self._switch(row(b, "Show the idle bar", "The small bar above the taskbar"), "show_idle_pill")
        self._switch(row(b, "Start with Windows"), "startup", getter=startup_enabled, setter=set_startup)
        self._switch(row(b, "Save recordings for fine-tuning", "Keeps audio and final text in the training folder"),
                     "save_training_data")
        foot = tk.Frame(p, bg=T["bg"])
        foot.pack(fill="x", pady=(px(SPACE[3]), 0))
        Button(foot, "Open config.json", lambda: os.startfile(CONFIG_PATH), kind="subtle",
               font=F["caption"]).pack(side="left")

    # -- Microphone
    def _page_microphone(self, p):
        label(p, "Input", "heading", "muted").pack(fill="x", padx=px(SPACE[1]), pady=(px(SPACE[2]), px(SPACE[1])))
        mic_rows(p, self.app, lambda v: (self.app.set_option("mic", v), self.refresh()))
        b = group(p, "Startup")
        self._switch(row(b, "Keep the mic ready for a minute",
                         "No cut-off first words. Bluetooth stays in call mode meanwhile"),
                     "keep_mic_ready_seconds", getter=lambda: self.app.cfg["keep_mic_ready_seconds"] > 0,
                     setter=lambda on: self.app.set_option("keep_mic_ready_seconds", 60 if on else 0))

    # -- Dictionary
    def _page_dictionary(self, p):
        d = self.app.dictionary
        b = group(p, "Add a word", "When a word keeps coming out wrong, add what it's heard as and what it "
                                   "should be. Words you fix after dictating are added automatically.")
        r = tk.Frame(b, bg=b.cget("bg"))
        r.pack(fill="x", padx=px(SPACE[4]), pady=px(SPACE[3]))
        r.columnconfigure(0, weight=1)
        r.columnconfigure(2, weight=1)
        label(r, "Heard as", "caption", "muted").grid(row=0, column=0, sticky="w")
        label(r, "Should be", "caption", "muted").grid(row=0, column=2, sticky="w")
        self.heard_in = RoundedEntry(r, 14)
        self.heard_in.grid(row=1, column=0, sticky="ew")
        tk.Label(r, text=GLYPH["next"], font=F["icon_small"], fg=T["muted"], bg=r.cget("bg")).grid(
            row=1, column=1, padx=px(SPACE[2]))
        self.wanted_in = RoundedEntry(r, 14)
        self.wanted_in.grid(row=1, column=2, sticky="ew")
        Button(r, "Add", self._add_word, kind="primary").grid(row=1, column=3, padx=(px(SPACE[2]), 0))
        self.wanted_in.entry.bind("<Return>", lambda e: self._add_word())

        active = [e for e in d.entries if e.get("mode", "always") != "off"]
        off = [e for e in d.entries if e.get("mode") == "off"]
        newest = lambda es: sorted(es, key=lambda e: e.get("added", ""), reverse=True)
        b = group(p, f"Active · {len(active)}")
        if not active:
            row(b, "No words yet")
        for e in newest(active):
            where = "Everywhere" if e.get("mode", "always") == "always" else \
                "Only next to “" + "”, “".join(e.get("context", [])[:3]) + "”"
            r = row(b, f"{e['heard']}  →  {e['wanted']}", where)
            Button(r, GLYPH["delete"], lambda h=e["heard"]: (d.remove(h), self.refresh()), kind="subtle",
                   icon=True, pad_x=8).pack(side="right")
            if e.get("mode", "always") == "always":
                Button(r, "Turn off", lambda h=e["heard"]: (d.set_mode(h, "off"), self.refresh()), kind="subtle",
                       font=F["caption"]).pack(side="right")
        if off:
            b = group(p, f"Not applied · {len(off)}", "Everyday words would change normal sentences "
                                                      "(\"new\" in \"a new idea\"), so these stay off. "
                                                      "Fixing one again next to the same word turns it on there.")
            for e in newest(off):
                r = row(b, f"{e['heard']}  →  {e['wanted']}", "Off")
                Button(r, GLYPH["delete"], lambda h=e["heard"]: (d.remove(h), self.refresh()), kind="subtle",
                       icon=True, pad_x=8).pack(side="right")
                Button(r, "Turn on everywhere", lambda h=e["heard"]: (d.set_mode(h, "always"), self.refresh()),
                       kind="subtle", font=F["caption"]).pack(side="right")

    def _add_word(self):
        heard, wanted = self.heard_in.entry.get().strip(), self.wanted_in.entry.get().strip()
        if heard and wanted:
            self.app.dictionary.add(heard, wanted, "manual")
            self.refresh()
            self.heard_in.entry.focus_set()

    # -- History
    def _page_history(self, p):
        entries, pages = recent_pages()
        self.hist_page = max(0, min(self.hist_page, pages - 1))
        top = tk.Frame(p, bg=T["bg"])
        top.pack(fill="x", pady=(px(SPACE[2]), px(SPACE[2])))
        self.hist_status = label(top, "Your last 9 dictations. Fix one to teach LocalFlow the right words.",
                                 "caption", "muted")
        self.hist_status.pack(side="left")
        pg, self.hist_page_lbl = pager(top, lambda: self._turn_history(-1), lambda: self._turn_history(1))
        pg.pack(side="right")
        self.hist_page_lbl.config(text=f"{self.hist_page + 1} / {pages}")
        self.cards = tk.Frame(p, bg=T["bg"])
        self.cards.pack(fill="x")
        shown = entries[self.hist_page * PER_PAGE:(self.hist_page + 1) * PER_PAGE]
        if not shown:
            label(self.cards, "Nothing yet.", "body", "muted").pack(fill="x")
        for i, e in enumerate(shown):
            holder = {}
            _, body = transcript_card(
                self.cards, e, self.hist_page * PER_PAGE + i + 1,
                [("Fix", lambda e=e, h=holder: self._fix(e, h["body"]), "subtle"),
                 ("Copy", lambda t=e["text"]: pyperclip.copy(t), "standard", "Copied"),
                 ("Paste", lambda t=e["text"]: self.app.paste_text(t, restore_focus=True), "primary")],
                wrap=440)
            holder["body"] = body
        foot = tk.Frame(p, bg=T["bg"])
        foot.pack(fill="x", pady=(px(SPACE[1]), 0))
        Button(foot, "Open full history", lambda: os.startfile(HISTORY_PATH) if HISTORY_PATH.exists() else None,
               kind="subtle", font=F["caption"]).pack(side="left")

    def _hist_note(self, text):
        self.hist_status.config(text=text)
        self.win.after(2000, lambda: self.visible and self.tab == "History" and self.hist_status.winfo_exists()
                       and self.hist_status.config(text="Your last 9 dictations. Fix one to teach "
                                                        "LocalFlow the right words."))

    def _turn_history(self, step):
        self.hist_page += step
        self.open_tab("History", keep_scroll=True)

    def _fix(self, entry, body):
        for w in body.winfo_children():
            w.destroy()
        box = RoundedText(body, height=4)
        box.pack(fill="x")
        box.text.insert("1.0", entry["text"])
        box.text.focus_set()
        r = tk.Frame(body, bg=body.cget("bg"))
        r.pack(fill="x", pady=(px(SPACE[2]), 0))

        def save():
            new = " ".join(box.text.get("1.0", "end-1c").split())
            msg = None
            if new and new != entry["text"]:
                pairs = extract_corrections(entry["text"], new, strict=False)
                pairs = [(h, w) for h, w, c in pairs if self.app.dictionary.learn(h, w, c, "manual")]
                update_history_text(entry["ts"], entry["text"], new)
                self.app.last_text = new
                msg = (f"Learned: {', '.join(f'{h} → {w}' for h, w in pairs)}" if pairs
                       else "Saved. Nothing to learn: the changes were everyday words.")
            self.open_tab("History", keep_scroll=True)
            if msg:
                self._hist_note(msg)

        Button(r, "Save", save, kind="primary", font=F["caption"]).pack(side="right")
        Button(r, "Cancel", lambda: self.open_tab("History", keep_scroll=True), font=F["caption"]).pack(
            side="right", padx=(0, px(SPACE[1])))


# ------------------------------------------------------------------------ app

def make_icon_image(size=64, color=(96, 205, 255)):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 64
    d.ellipse((2 * s, 2 * s, 62 * s, 62 * s), fill=(20, 20, 22, 255))
    d.rounded_rectangle((24 * s, 12 * s, 40 * s, 38 * s), radius=8 * s, fill=color)
    d.arc((17 * s, 22 * s, 47 * s, 46 * s), 0, 180, fill=color, width=max(1, int(3 * s)))
    d.line((32 * s, 46 * s, 32 * s, 52 * s), fill=color, width=max(1, int(3 * s)))
    d.line((24 * s, 52 * s, 40 * s, 52 * s), fill=color, width=max(1, int(3 * s)))
    return img


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def startup_command():
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" "{Path(__file__).resolve()}"'


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "LocalFlow")
            return True
    except OSError:
        return False


def set_startup(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, "LocalFlow", 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, "LocalFlow")
            except OSError:
                pass


class App:
    DOUBLE_TAP = 0.45     # max seconds between the two taps
    TAP = 0.3             # a press shorter than this is a tap, not a hold
    HANDSFREE_MAX = 600   # stop hands-free automatically after 10 minutes

    def __init__(self):
        self.cfg = load_config()
        migrate_history()
        self.audio_stuck = False
        if not self.cfg.get("startup_default_applied"):
            try:
                set_startup(True)
                log("Start with Windows turned on (default)")
            except Exception as e:
                log("Couldn't turn on start with Windows:", repr(e))
            self.cfg["startup_default_applied"] = True
            save_config(self.cfg)
        self.dictionary = Dictionary(DICT_PATH)
        self.mics = Mics()
        self.mic = None            # the open MicStream, kept ready between dictations
        self.ambient = AmbientListener(self)
        self.mics.before_restart = lambda: (self._close_mic(), self.ambient.close_mic())
        self.wake_session = False   # the current dictation was started by the wake word
        self.last_voice = 0
        self.state_lock = threading.Lock()
        self.starting = False      # mic is being opened in the background
        self.release_pending = False
        self.cancel_pending = False
        self.release_time = 0
        self.bad_mic = (None, 0)   # a mic that stopped responding, avoided for a while
        self.mic_name = None
        self.watcher = CorrectionWatcher(self._on_corrections)
        self.watcher.on_missing = lambda: self.post(
            "overlay", "message", f"Didn't land? {self.cfg['paste_last_keys'].title()} pastes it again", 4)
        self.ui = queue.Queue()
        self.engine = None
        self.session = None
        self.busy = False
        self.press_time = 0
        self.last_tap = 0
        self.second_tap = False
        self.handsfree = False
        self.ignore_release = False
        history = read_history()
        self.last_text = history[-1]["text"] if history else ""
        self.last_external = None
        self.hover_since = None
        self.bar_leave = None
        self.panel_leave = None

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.root = tk.Tk()
        self.root.withdraw()
        init_fonts(self.root)
        self.overlay = Overlay(self.root, self.cfg["show_idle_pill"], key_label(self.cfg["hold_keys"]))
        self.overlay.set("message", "Loading speech model…")
        self.bar = HoverBar(self)
        self.last_tick = time.time()
        self.last_area_check = 0
        self.area = self._area()
        self.panel = Panel(self)
        self.picker = Picker(self)
        self.mic_menu = MicMenu(self)
        self.pid = os.getpid()

        self.keys = HoldKey(self.cfg["hold_keys"], self.on_press, self.on_release,
                            self.on_cancel, self.on_escape)
        if self.cfg["paste_last_keys"] == "alt+shift+v":
            # The old default: some apps (e.g. overlays) swallow Alt shortcuts on this PC.
            self.set_option("paste_last_keys", DEFAULTS["paste_last_keys"])
        self._paste_hotkey = None
        self._register_paste_hotkey()
        self._start_tray()
        threading.Thread(target=self._load_engine, daemon=True).start()
        threading.Thread(target=self._watch_mics, daemon=True).start()
        self.root.after(30, self._tick)

    # -- background events -> UI thread
    def post(self, *msg):
        self.ui.put(msg)

    def _tick(self):
        try:
            while True:
                msg = self.ui.get_nowait()
                getattr(self, "_ui_" + msg[0])(*msg[1:])
        except queue.Empty:
            pass
        now = time.time()
        if now - self.last_tick > 5:
            self._rebuild_bars("woke from sleep")  # no ticks while the PC slept
        elif now - self.last_area_check > 2:
            self.last_area_check = now
            if self._area() != self.area:
                self._rebuild_bars("screen or taskbar changed")
        self.last_tick = now
        fg = user32.GetForegroundWindow()
        if fg:  # remember the last app you were in (any window not owned by LocalFlow)
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if pid.value != self.pid:
                self.last_external = fg
        if self.starting and not self.session and now - self.press_time > 0.25 \
                and self.overlay.state not in ("message", "error"):
            self.overlay.set("message", "Starting mic…")
        self.overlay.listening = self.ambient.running and self.ambient.mic is not None
        self.overlay.finish_hint = "Pause to finish" if self.wake_session else None
        if self.session and self.wake_session:
            quiet = now - self.last_voice
            if getattr(self, "wake_heard_voice", False) and quiet > self.cfg["ambient_end_silence"]:
                self.handsfree = False
                self._stop()
            elif not getattr(self, "wake_heard_voice", False) and quiet > 8:
                self.on_escape()  # woke up but nothing was said
        if self.session:
            if self.handsfree:
                if self.overlay.state != "handsfree":
                    self.overlay.set("handsfree")
                if now - self.press_time > self.HANDSFREE_MAX:
                    self.handsfree = False
                    self._stop()
            elif self.overlay.state != "recording" and (now - self.press_time > 0.25
                                                         or self.overlay.state == "message"):
                self.overlay.set("recording")
                self._beep(880)
        self._hover(now)
        self.overlay.draw()
        self.root.after(33, self._tick)

    @staticmethod
    def _area():
        r = work_area()
        return (r.left, r.top, r.right, r.bottom, user32.GetDpiForSystem())

    def _rebuild_bars(self, why):
        """After the PC sleeps, Windows can stop showing the see-through pill and hover
        bar even though their windows still exist (normal windows are fine), so build
        fresh ones. Also re-centres them if the screen or taskbar changed."""
        old_overlay, old_bar = self.overlay, self.bar
        overlay = Overlay(self.root, self.cfg["show_idle_pill"], old_overlay.key_text)
        overlay.state, overlay.text, overlay.until = old_overlay.state, old_overlay.text, old_overlay.until
        overlay.levels = old_overlay.levels
        self.overlay = overlay
        self.bar = HoverBar(self)
        for w in (old_overlay.win, old_bar.win):
            try:
                w.destroy()
            except Exception:
                pass
        self.area = self._area()
        self.hover_since = self.bar_leave = None
        log(f"Rebuilt the bar ({why})")

    def _hover(self, now):
        x, y = cursor_pos()
        zx0, zy0, zx1, zy1 = self.overlay.pill_zone()
        over_zone = zx0 <= x <= zx1 and zy0 <= y <= zy1
        over_bar = self.bar.contains(x, y)
        idle = self.overlay.state == "idle" and not self.session

        # hover bar: appears after a short hover on the idle pill
        if not idle and not self.panel.visible and not self.picker.visible and not self.mic_menu.visible:
            self.bar.hide(animate=False)
            self.hover_since = None
        elif not self.bar.visible:
            if over_zone and idle:
                self.hover_since = self.hover_since or now
                if now - self.hover_since > 0.2:
                    self.bar.show()
            else:
                self.hover_since = None
        else:
            self.hover_since = None
            if over_bar or over_zone or self.panel.visible or self.picker.visible or self.mic_menu.visible:
                self.bar_leave = None
            else:
                self.bar_leave = self.bar_leave or now
                if now - self.bar_leave > 0.4:
                    self.bar.hide()
        self.overlay.hover = self.bar.visible

        # popups: close once you've clicked away (or after 10 s if they never got focus)
        for p in (self.picker, self.mic_menu):
            if p.visible:
                if p.focused():
                    p.had_focus = True
                elif not p.contains(x, y) and (p.had_focus or now - p.shown_at > 10):
                    p.hide()

        # panel: closes once you've clicked away and the mouse isn't over it
        if self.panel.visible:
            keep = (self.panel.pinned or self.panel.focused() or self.panel.contains(x, y)
                    or over_bar)
            if keep:
                self.panel_leave = None
            else:
                self.panel_leave = self.panel_leave or now
                if now - self.panel_leave > 0.3:
                    self.panel.hide()

    def _ui_overlay(self, state, text="", seconds=0):
        self.overlay.set(state, text, seconds)

    def _ui_level(self, level):
        self.overlay.push_level(level)

    def _ui_call(self, fn):
        fn()

    def _beep(self, freq):
        if self.cfg["sounds"]:
            threading.Thread(target=winsound.Beep, args=(freq, 50), daemon=True).start()

    def set_option(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        if key == "ambient_mode":
            (self.ambient.start if value and self.engine else self.ambient.stop)()
        if key == "show_idle_pill":
            self.overlay.show_idle = value

    def open_panel(self, page, tab=None, pinned=False):
        self.panel.show(page, tab=tab, pinned=pinned)

    def _load_engine(self):
        try:
            t = time.time()
            self.engine = Engine(self.cfg)
            self.engine.vocab = lambda: self.cfg["vocabulary"] + self.dictionary.words()
            log(f"Loaded {self.engine.name} in {time.time() - t:.1f}s")
            if self.cfg["ambient_mode"]:
                self.ambient.start()
            self.post("overlay", "message",
                      f"Ready · hold {key_label(self.cfg['hold_keys'])} to dictate", 4)
            self._refresh_tray()
            self.post("call", lambda: self.panel.visible and self.panel.refresh())
        except Exception as e:
            log("Model failed to load:", repr(e))
            self.post("overlay", "error", f"Model failed to load: {e}"[:80], 15)

    # -- hold key callbacks (keyboard hook thread)
    #
    # Hold: press, talk, release.  Hands-free: tap, then tap again quickly and
    # let go; recording keeps going until the next tap (or Esc to cancel).
    def on_press(self):
        if self.handsfree:
            self.handsfree = False
            self.ignore_release = True
            self._stop()
            return
        if self.engine is None:
            self.post("overlay", "message", "Still loading the model…", 2)
            return
        if self.busy or self.session or self.starting:
            return
        self.watcher.cancel()
        now = time.time()
        self.second_tap = now - self.last_tap < self.DOUBLE_TAP
        self.press_time = now
        with self.state_lock:
            self.starting, self.release_pending, self.cancel_pending = True, False, False
        # Opening a mic can take a second (Bluetooth); never block the keyboard hook,
        # or Windows may stop sending it key presses.
        threading.Thread(target=self._open_session, daemon=True).start()

    def on_wake(self, mic):
        """Called by the listener (its thread) when it hears the wake phrase."""
        with self.state_lock:
            if self.session or self.starting or self.busy:
                return
            self.starting = True
        self.watcher.cancel()
        for freq, ms in ((660, 70), (990, 110)):  # always play: it's your cue to talk
            winsound.Beep(freq, ms)
        try:
            mic.detach()
            session = Session(self.engine, self._wake_level, mic)
        except Exception as e:
            log("Wake word dictation failed:", repr(e))
            with self.state_lock:
                self.starting = False
            return
        now = time.time()
        self.press_time = self.last_voice = now
        self.wake_heard_voice = False
        with self.state_lock:
            self.handsfree, self.wake_session = True, True
            self.session, self.starting = session, False

    def _wake_level(self, level):
        self.ui.put(("level", level))
        if level > self.ambient.voice_level:
            self.last_voice = time.time()
            self.wake_heard_voice = True

    def _close_mic(self):
        mic, self.mic = self.mic, None
        if mic:
            mic.close()

    def _ensure_mic(self, name=None):
        with self.mics.lock:
            if name is None:
                index, name = self.mics.pick(self.cfg["mic"])
                bad, until = self.bad_mic
                if self.cfg["mic"] == "auto" and name == bad and time.time() < until:
                    name = self._fallback_mic(bad) or name
            index = next((i for i, n in self.mics.devices if n == name), None)
            if self.mic and self.mic.device == index and self.mic.alive:
                return self.mic
            self._close_mic()
            self.mic = open_mic(index)
            self.mic_name = name
            log(f"Mic opened: {name}")
            return self.mic

    def _fallback_mic(self, bad):
        others = [n for n in self.mics.names() if n != bad and Mics.score(n) >= 0]
        return next((n for n in others if Mics.score(n) == 1), others[0] if others else None)

    def _audio_stuck(self):
        """A mic start hung. Retrying only piles up more stuck attempts (they all wait
        behind the first), so restart LocalFlow, which clears it. Once only, to avoid loops."""
        if self.audio_stuck:
            return
        self.audio_stuck = True
        if "--after-audio-restart" in sys.argv:
            log("Mic start hung again right after a restart; not restarting again")
            self.post("overlay", "error", "Windows audio isn't responding. Restarting the PC usually fixes it.", 8)
            return
        log("Mic start hung; restarting LocalFlow to recover")
        self.post("overlay", "message", "The mic got stuck · restarting LocalFlow…", 4)
        self.post("call", lambda: self.root.after(1500, lambda: self.restart("--after-audio-restart")))

    def _ready_mic(self):
        if self.audio_stuck:
            raise MicStuck("waiting for LocalFlow to restart the audio system")
        """An open mic that is actually sending audio. Bluetooth headsets sometimes open
        without sending anything (stuck switching into headset mode); a fresh open
        usually fixes it, and if it doesn't, auto mode falls back to another mic."""
        try:
            mic = self._ensure_mic()
            if mic.wait_audio(2.0):  # Bluetooth needs up to ~1 s to start sending
                return mic
        except MicStuck:
            self._audio_stuck()
            raise
        except Exception as e:
            log("Mic failed to open:", repr(e))
        name = self.mic_name or self.mics.pick(self.cfg["mic"])[1]
        log(f"Mic opened but sent no audio: {name}; reopening it")
        with self.mics.lock:
            self._close_mic()
        try:
            mic = self._ensure_mic(name)
            if mic.wait_audio(2.0):
                return mic
        except MicStuck:
            self._audio_stuck()
            raise
        except Exception as e:
            log("Mic failed to reopen:", repr(e))
        fallback = self._fallback_mic(name) if self.cfg["mic"] == "auto" else None
        with self.mics.lock:
            self._close_mic()
        if fallback:
            log(f"Falling back to {fallback} for a while")
            self.bad_mic = (name, time.time() + 120)
            self.post("overlay", "message", f"{name} isn't responding · using {fallback}"[:70], 3)
            mic = self._ensure_mic(fallback)
            if mic.wait_audio(1.5):
                return mic
            with self.mics.lock:
                self._close_mic()
        raise RuntimeError(f"{name} isn't sending any audio")

    def _open_session(self):
        try:
            mic = self._ready_mic()
            session = Session(self.engine, lambda lv: self.ui.put(("level", lv)), mic)
            session.late_start = time.time() - self.press_time > 0.6
        except Exception as e:
            log("Microphone error:", repr(e))
            with self.state_lock:
                self.starting = False
            _, name = self.mics.pick(self.cfg["mic"])
            if not isinstance(e, MicStuck):
                self.post("overlay", "error", f"Couldn't start the mic ({name or 'none found'})"[:70], 4)
            threading.Thread(target=self.mics.scan, daemon=True).start()
            return
        with self.state_lock:
            self.starting = False
            self.session = session
            release, cancel = self.release_pending, self.cancel_pending
        if cancel:
            self.on_cancel()
        elif release:
            self._handle_release(self.release_time)

    def on_cancel(self):
        with self.state_lock:
            if self.starting:
                self.cancel_pending = True
                return
        if self.session and not self.handsfree:
            self.session.cancel()
            self.session = None
            self.post("overlay", "idle")

    def on_escape(self):
        if self.handsfree and self.session:
            self.wake_session = False
            self.handsfree = False
            self.session.cancel()
            self.session = None
            self.post("overlay", "message", "Cancelled", 1.2)

    def on_release(self):
        if self.ignore_release:
            self.ignore_release = False
            return
        with self.state_lock:
            if self.starting:
                self.release_pending, self.release_time = True, time.time()
                return
        self._handle_release(time.time())

    def _handle_release(self, now):
        if not self.session:
            return
        if now - self.press_time < self.TAP:
            if self.second_tap:
                self.handsfree = True  # keep the session running
                self.second_tap = False
                self._beep(880)
                return
            self.session.cancel()
            self.session = None
            self.last_tap = now
            self.post("overlay", "idle")
            return
        self._stop()

    def _stop(self):
        self.wake_session = False
        session, self.session = self.session, None
        if not session:
            return
        self.busy = True
        self._beep(660)
        self.post("overlay", "busy")
        threading.Thread(target=self._finish, args=(session,), daemon=True).start()

    def _finish(self, session):
        try:
            t = time.time()
            text = session.finish()
            asr_time = time.time() - t
            if self.cfg["llm_cleanup"] and text:
                try:
                    text = llm_cleanup(text, self.cfg)
                except Exception as e:
                    log("Cleanup skipped:", repr(e))
            text = postprocess(text, self.cfg, self.dictionary)
            log(f"[{session.duration:.1f}s audio, {asr_time:.2f}s asr, "
                f"{time.time() - t:.2f}s total] {text!r}")
            if not text:
                msg = ("The mic was still starting, try again" if getattr(session, "late_start", False)
                       and session.duration < 1 else "Didn't catch that")
                self.post("overlay", "message", msg, 2)
                return
            paste(text if text.endswith("\n") else text + " ")
            self.last_text = text
            add_history(text, session.duration)
            sample = None
            if self.cfg["save_training_data"]:
                sample = save_training_sample(session.audio, text)
            self.watcher.watch(text, sample)
            self.post("overlay", "idle")
            self.post("call", lambda: self.panel.visible and self.panel.refresh())
        except Exception as e:
            log("Transcription failed:", repr(e))
            self.post("overlay", "error", "Transcription failed (see localflow.log)", 4)
        finally:
            self.busy = False

    def _on_corrections(self, pairs, corrected, sample):
        if sample:
            save_training_text(sample, corrected)
        if not self.cfg["learn_corrections"]:
            return
        learned = []
        for heard, wanted, context in pairs:
            e = self.dictionary.learn(heard, wanted, context, "learned")
            if not e:
                continue
            log(f"Learned: {heard!r} -> {wanted!r} ({e['mode']}, context {e['context']})")
            if e["mode"] == "always":
                learned.append(f"{heard} → {wanted}")
            elif e["mode"] == "context":
                learned.append(f"{heard} → {wanted} (next to “{'/'.join(e['context'][:2])}”)")
        if learned:
            self.post("overlay", "message", ("Learned: " + ", ".join(learned))[:70], 3)
        self.post("call", lambda: self.panel.visible and self.panel.refresh())

    # -- paste last
    def paste_last(self, wait_keys=False):
        if not self.last_text:
            self.post("overlay", "message", "Nothing to paste yet", 1.5)
            return
        self.paste_text(self.last_text, wait_keys=wait_keys)

    def paste_text(self, text, restore_focus=False, wait_keys=False):
        target = self.last_external

        def run():
            if wait_keys:  # let go of the shortcut keys first, or they'd mix with Ctrl+V
                end = time.time() + 2
                while time.time() < end and any(keyboard.is_pressed(k) for k in ("alt", "shift", "ctrl")):
                    time.sleep(0.02)
            if restore_focus and target:
                # give the app you were in its focus back, and wait until Windows has
                # actually done it, or Ctrl+V lands nowhere
                end = time.time() + 0.6
                while time.time() < end and user32.GetForegroundWindow() != target:
                    force_foreground(target)
                    time.sleep(0.08)
                time.sleep(0.1)
            paste(text if text.endswith("\n") else text + " ")
            self.post("overlay", "message", "Pasted last transcript" if text == self.last_text
                      else "Pasted", 1.2)

        threading.Thread(target=run, daemon=True).start()

    def _watch_mics(self):
        """Rescan microphones every few seconds so a headset that connects is used."""
        last = self.mics.pick(self.cfg["mic"])[1]
        seen = Mics.signature()
        while True:
            time.sleep(2)
            if self.session or self.busy or self.starting:
                continue
            mic = self.mic
            if mic and time.time() - mic.last_used > self.cfg["keep_mic_ready_seconds"]:
                with self.mics.lock:
                    if self.mic is mic and not self.session and not self.starting:
                        self._close_mic()
            if self.mic and self.mics.pick(self.cfg["mic"])[0] != self.mic.device:
                with self.mics.lock:  # setting changed: reopen the right mic next time
                    if not self.session and not self.starting:
                        self._close_mic()
            now_sig = Mics.signature()
            if now_sig == seen:
                continue
            time.sleep(1.5)  # Bluetooth headsets add their devices in stages
            seen = Mics.signature()
            if self.mics.scan():
                now = self.mics.pick(self.cfg["mic"])[1]
                log("Microphones changed:", self.mics.names(), "-> using", now)
                if now != last:
                    self.post("overlay", "message", f"Mic: {now}"[:70], 2.5)
                    last = now
                self.post("call", lambda: self.panel.visible and self.panel.refresh())

    def _register_paste_hotkey(self):
        if self._paste_hotkey is not None:
            try:
                keyboard.remove_hotkey(self._paste_hotkey)
            except Exception:
                pass
        try:
            self._paste_hotkey = keyboard.add_hotkey(self.cfg["paste_last_keys"],
                                                     lambda: self.post("call", self.picker.show))
        except Exception as e:
            self._paste_hotkey = None
            log("Recent-transcripts shortcut not set:", e)

    # -- key pickers (hold key, recent-transcripts shortcut)
    def change_hotkey(self, target="hold"):
        what = "hold" if target == "hold" else "use for recent transcripts"
        self.post("overlay", "message", f"Press and release the key (or combo) you want to {what}…", 10)
        token = object()
        self._pick_token = token

        def done(keys):
            self._pick_token = None
            if keys == ["esc"]:
                self.post("overlay", "message", "Unchanged", 2)
                return
            if target == "paste":
                if len(keys) < 2:
                    self.post("overlay", "error", "Use a combination, e.g. Ctrl + Alt + V", 3)
                    return
                self.set_option("paste_last_keys", "+".join(keys))
                self._register_paste_hotkey()
                self.post("overlay", "message", f"Recent transcripts: {key_label(keys)}", 3)
            else:
                self.cfg["hold_keys"] = keys
                save_config(self.cfg)
                self.keys.keys = set(keys)
                self.overlay.key_text = key_label(keys)
                self.post("overlay", "message", f"Hold key set to {key_label(keys)}", 3)
            self.post("call", self.panel.refresh)
            self._refresh_tray()

        def timeout():
            if self._pick_token is token:
                self.keys.capture = None
                self.post("overlay", "error",
                          "No key detected. Fn is usually invisible to Windows; pick another key.", 6)

        self.keys.pick(done)
        self.post("call", lambda: self.root.after(10000, timeout))

    # -- tray
    def _start_tray(self):
        img = make_icon_image()
        if not ICON_PATH.exists():
            make_icon_image(256).save(ICON_PATH, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        self.tray = pystray.Icon("LocalFlow", img, "LocalFlow", menu=self._menu())
        self.tray.run_detached()

    def _menu(self):
        M = pystray.MenuItem
        engine = self.engine.name if self.engine else "loading…"
        tray_open = lambda page, tab=None: (lambda: self.post(
            "call", lambda: self.open_panel(page, tab=tab, pinned=True)))
        return pystray.Menu(
            M("Scratchpad", tray_open("notes"), default=True),
            M(f"Hold {key_label(self.cfg['hold_keys'])} · double-tap for hands-free", None, enabled=False),
            M(f"Engine: {engine}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            M("Settings", tray_open("settings", "Settings")),
            M("History", tray_open("settings", "History")),
            M("Dictionary", tray_open("settings", "Dictionary")),
            M(f"Recent transcripts ({self.cfg['paste_last_keys'].title()})",
              lambda: self.post("call", self.picker.show)),
            pystray.Menu.SEPARATOR,
            M("Restart", lambda: self.post("call", self.restart)),
            M("Quit", lambda: self.post("call", self.quit)),
        )

    def _refresh_tray(self):
        self.tray.menu = self._menu()
        self.tray.update_menu()

    def restart(self, *args):
        self.panel.hide()
        release_single_instance()
        subprocess.Popen([str(Path(sys.executable).with_name("pythonw.exe")), str(Path(__file__).resolve()), *args])
        self.quit()

    def quit(self):
        try:
            self.panel.hide()
        except Exception:
            pass
        self.tray.stop()
        keyboard.unhook_all()
        self.root.destroy()
        os._exit(0)

    def run(self):
        self.root.mainloop()


_mutex = None


def acquire_single_instance():
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LocalFlowSingleInstance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def release_single_instance():
    if _mutex:
        ctypes.windll.kernel32.CloseHandle(_mutex)


if __name__ == "__main__":
    if not acquire_single_instance():
        ctypes.windll.user32.MessageBoxW(None, "LocalFlow is already running (see the tray icon).",
                                         "LocalFlow", 0x40)
        sys.exit(0)
    log("Starting LocalFlow")
    App().run()

"""Training recordings (opt-in): each Dictation's audio kept with its final text, so a
fine-tuning dataset builds up while you use the app. Nothing leaves this PC.

The folder holds <time>.wav files and metadata.jsonl lines {"audio": ..., "text": ...};
when you fix a Dictation, another line with the corrected text is added (the last
one wins)."""
import json
import shutil
import wave
from datetime import datetime

import numpy as np

RATE = 16000


class Clips:
    def __init__(self, folder):
        self.folder = folder

    def save(self, audio, text):
        self.folder.mkdir(parents=True, exist_ok=True)
        name = datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".wav"
        with wave.open(str(self.folder / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        self.update_text(name, text)
        return name

    def update_text(self, name, text):
        self.folder.mkdir(parents=True, exist_ok=True)
        with open(self.folder / "metadata.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"audio": name, "text": text}) + "\n")

    def pairs(self):
        """{audio file: final text}"""
        meta = self.folder / "metadata.jsonl"
        if not meta.exists():
            return {}
        out = {}
        for line in meta.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                out[e["audio"]] = e["text"]
        return out

    def size(self):
        if not self.folder.exists():
            return 0
        return sum(p.stat().st_size for p in self.folder.iterdir() if p.is_file())

    def delete_all(self):
        if self.folder.exists():
            shutil.rmtree(self.folder)

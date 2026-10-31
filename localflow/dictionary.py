"""The Dictionary: words the speech model gets wrong for you, each with what you meant,
swapped into every Dictation. It learns from your Fixes. Pure: no UI, keyboard or audio.

A rare mishearing ("Sio bhan" -> "Siobhan") is swapped everywhere. A Fix to a name or
brand ("cloud" -> "Claude") is learned at once too. When the misheard word is a very
common one ("New" -> "Nuvo"), swapping it everywhere would break normal sentences, so it
is only swapped next to the words it was learned with ("Nuvo Health"), until you make
the same Fix again. A Rewording between two everyday words ("patch" -> "batch") waits
for a second identical Fix, so changes of mind aren't learned.

Modes: "always", "context", "waiting" (seen once), "off" (kept, not applied)."""
import difflib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime

from textfx import zipf

log = logging.getLogger("localflow")

COMMON = 3.0     # word frequency (zipf) from which a word counts as everyday
VERY_COMMON = 5.0  # swapping this word everywhere would break normal sentences ("new", "man")
STOPWORD = 5.5   # too frequent ("the", "in") to tell contexts apart
RULES = 2        # version of the learning rules; older entries are re-checked once


def is_common(phrase):
    return zipf(phrase) >= (COMMON if " " not in phrase.strip() else 2.5)


def is_name(word):
    """Capitalised, or written like a brand ("ChatGPT", "enjoy.dev", "Adarsh1313")."""
    return any(c.isupper() for c in word) or bool(re.search(r"\w[.\d]\w|\d", word))


# ------------------------------------------------------------------ outcomes

@dataclass(frozen=True)
class Learned:
    heard: str
    wanted: str
    mode: str
    context: tuple = ()


@dataclass(frozen=True)
class Waiting:
    """A Rewording seen once: learned if you make the same Fix again."""
    heard: str
    wanted: str


@dataclass(frozen=True)
class Refused:
    heard: str
    wanted: str
    reason: str


def describe(outcome):
    """(verb, object) for the card shown after a Fix."""
    if isinstance(outcome, Learned):
        near = f" · next to “{'/'.join(outcome.context[:2])}”" if outcome.mode == "context" else ""
        return "Added to dictionary", outcome.wanted + near
    if isinstance(outcome, Waiting):
        return "Not added yet", f"Fix “{outcome.wanted}” once more to add it"
    return "Not added", outcome.reason


# ------------------------------------------------------------------ swapping

def swap(text, entries):
    """Swap each entry's `heard` for its `wanted` (longest first), by its mode."""
    for e in sorted(entries, key=lambda e: -len(e["heard"])):
        mode = e.get("mode", "always")
        if mode not in ("always", "context"):
            continue
        pattern = r"(?<!\w)" + re.escape(e["heard"]) + r"(?!\w)"
        if mode == "always":
            text = re.sub(pattern, lambda m, w=e["wanted"]: w, text, flags=re.I)
            continue
        ctx = set(e.get("context", []))

        def near(m, w=e["wanted"], ctx=ctx):
            left = re.search(r"([\w'-]+)\W*$", m.string[:m.start()])
            right = re.match(r"\W*([\w'-]+)", m.string[m.end():])
            words = {g.group(1).lower() for g in (left, right) if g}
            return w if words & ctx else m.group(0)

        text = re.sub(pattern, near, text, flags=re.I)
    return text


class Dictionary:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.entries = []
        if path.exists():
            try:
                self.entries = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("dictionary.json unreadable: %r", e)
        self._migrate()

    def _migrate(self):
        changed = False
        for e in self.entries:
            if "mode" not in e:
                learned_common = e.get("source") == "learned" and is_common(e["heard"])
                e["mode"] = "off" if learned_common else "always"
                e.setdefault("context", [])
                changed = True
            if e.get("rules", 1) < RULES:
                if e["mode"] == "off" and e.get("source") == "learned" and not e.get("muted"):
                    mode = self._mode(e["heard"], e["wanted"], e.get("context", []), e.get("count", 1))
                    if mode == "always" and is_common(e["heard"]) and e.get("count", 1) < 2:
                        # never seen on a card: don't start swapping an everyday word everywhere
                        mode = "context" if e.get("context") else "off"
                    e["mode"] = mode if mode != "waiting" else "off"
                e["rules"] = RULES
                changed = True
        if changed:
            self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _find(self, heard):
        return next((e for e in self.entries if e["heard"].lower() == heard.lower()), None)

    @staticmethod
    def _mode(heard, wanted, context, count):
        """How a Fix seen `count` times is applied."""
        if not is_common(heard):
            return "always"
        if is_name(wanted) or count >= 2 or not is_common(wanted):
            if zipf(heard) < VERY_COMMON or count >= 2:
                return "always"
            return "context" if context else "off"
        return "waiting"   # a Rewording, seen once

    def add(self, heard, wanted, source="manual"):
        """Added by hand in the Dictionary tab: always applied."""
        with self.lock:
            e = self._find(heard)
            if e:
                e.update(wanted=wanted, mode="always", source="manual", muted=False)
                e["count"] = e.get("count", 1) + 1
            else:
                self.entries.append({"heard": heard, "wanted": wanted, "source": source, "mode": "always",
                                     "context": [], "count": 1, "rules": RULES,
                                     "added": datetime.now().isoformat(timespec="seconds")})
            self.save()

    def learn(self, heard, wanted, context, source="learned"):
        """From a Fix. Returns Learned, Waiting or Refused."""
        context = [c for c in context if c and zipf(c) < STOPWORD]
        with self.lock:
            e = self._find(heard)
            if e and e.get("muted") and e["wanted"].lower() == wanted.lower():
                return Refused(heard, wanted, "You turned this fix off in the Dictionary")
            if e and e["wanted"].lower() == wanted.lower():
                e["count"] = e.get("count", 1) + 1
                e["context"] = sorted(set(e.get("context", [])) | {c.lower() for c in context})
            else:
                if e:
                    self.entries.remove(e)
                e = {"heard": heard, "wanted": wanted, "source": source, "count": 1, "rules": RULES,
                     "context": sorted({c.lower() for c in context}),
                     "added": datetime.now().isoformat(timespec="seconds")}
                self.entries.append(e)
            if e.get("mode") != "always":
                count = e["count"] + (1 if source == "manual" else 0)  # a Fix in History is deliberate
                e["mode"] = self._mode(heard, wanted, e["context"], count)
            self.save()
            if e["mode"] == "waiting":
                return Waiting(heard, wanted)
            if e["mode"] == "off":
                return Refused(heard, wanted, "Too common to swap without words around it")
            return Learned(heard, e["wanted"], e["mode"], tuple(e["context"]))

    def set_mode(self, heard, mode):
        with self.lock:
            e = self._find(heard)
            if e:
                e["mode"] = mode
                e["muted"] = mode == "off"
                self.save()

    def remove(self, heard):
        with self.lock:
            self.entries = [e for e in self.entries if e["heard"] != heard]
            self.save()

    def apply(self, text):
        return swap(text, self.entries)

    def applied(self):
        return [e for e in self.entries if e.get("mode", "always") in ("always", "context")]

    def not_applied(self):
        """Saved Fixes that aren't swapped: switched off, or waiting for a second Fix."""
        return [e for e in self.entries if e.get("mode") in ("off", "waiting")]

    def words(self):
        return sorted({e["wanted"] for e in self.applied()})


# ------------------------------------------------------------- finding Fixes

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
    """Word-level Fixes between what was pasted and what it became, as
    (heard, wanted, context) with the words next to the Fix as context.
    strict (automatic learning) ignores rewrites, and needs a rarer word in the Fix.
    Whether a Fix is worth learning is up to Dictionary.learn."""
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
        if strict and not is_name(wanted) and not any(zipf(w) < 4.5 for w in wanted.split()):
            continue
        context = [_clean(e[j]) for j in (j1 - 1, j2) if 0 <= j < len(e)]
        pairs.append((heard, wanted, context))
    return pairs

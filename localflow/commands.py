"""Voice Commands: decide what a Hands-free turn means and carry it out.

Pure logic (no tkinter, mic or model) so it can be tested. Everything that touches
Windows goes through the `actions` object in the Context. Terms: see GLOSSARY.md.
"""
import difflib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    id: str
    name: str


@dataclass(frozen=True)
class Card:
    verb: str          # muted first line: "Opening"
    obj: str           # title line: "Spotify"
    icon: str = ""     # Target id, or "" for a glyph
    kind: str = "done" # "done", "no_match" or "failed": picks the glyph, hold time and sound


@dataclass(frozen=True)
class Dictation:
    text: str


@dataclass(frozen=True)
class Done:
    card: Card


@dataclass(frozen=True)
class NoMatch:
    card: Card


@dataclass(frozen=True)
class Failed:
    card: Card


@dataclass
class Context:
    catalog: list
    actions: object
    log: object = print   # where details of failures go (localflow.log in the app)


OPEN_VERBS = ("open", "launch", "start", "switch to", "go to")
MATCH_THRESHOLD = 0.85   # how close a heard name must sound to an app's name
MAX_COMMAND_WORDS = 6    # longer than this is always Dictation


def normalise(text):
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def spoken_forms(name):
    """Ways a person might say an app's name: "google chrome", "chrome", "vs code"."""
    words = normalise(name).split()
    forms = {" ".join(words[i:]) for i in range(len(words))}
    if len(words) > 1:
        forms.add("".join(w[0] for w in words[:-1]) + " " + words[-1])
    return forms


def score(heard, target):
    return max(difflib.SequenceMatcher(None, heard, f).ratio() for f in spoken_forms(target.name))


def best_target(name, catalog):
    best = max(catalog, key=lambda t: score(name, t), default=None)
    return best if best and score(name, best) >= MATCH_THRESHOLD else None


def handle(heard, ctx):
    words = normalise(heard)
    if len(words.split()) > MAX_COMMAND_WORDS:
        return Dictation(heard)
    for verb in OPEN_VERBS:
        if words.startswith(verb + " "):
            name = words[len(verb) + 1:]
            t = best_target(name, ctx.catalog)
            if not t:
                return NoMatch(Card("No app called", name, kind="no_match"))
            if ctx.actions.switch_to(t):
                return Done(Card("Switching to", t.name, t.id))
            try:
                ctx.actions.launch(t)
            except Exception as e:
                ctx.log(f"Couldn't open {t.name}: {e!r}")
                return Failed(Card("Couldn't open", t.name, t.id, "failed"))
            return Done(Card("Opening", t.name, t.id))
    return Dictation(heard)

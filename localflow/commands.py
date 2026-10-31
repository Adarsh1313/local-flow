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
    glyph: str = ""    # Segoe Fluent glyph when there's no app icon (volume, folders)


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


@dataclass(frozen=True)
class Intent:
    """A Command understood but not yet carried out."""
    kind: str               # "open", "media", "volume", "mute", "unmute", "volume up", ...
    target: Target = None
    action: str = ""        # media: "pause", "play", "next", "previous"
    level: int = 0          # volume: 0-100


MEDIA_VERBS = {"pause": "pause", "stop": "pause", "play": "play", "resume": "play",
               "next": "next", "skip": "next", "next song": "next", "next track": "next",
               "previous": "previous", "back": "previous", "previous song": "previous", "previous track": "previous"}
MEDIA_DONE = {"pause": "Paused", "play": "Playing", "next": "Next track", "previous": "Previous track"}
NUMBERS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
NUMBERS.update({w: 10 * i for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)})
NUMBERS["hundred"] = 100
VOLUME_STEP = 10
GLYPH_VOLUME, GLYPH_MUTE = "", ""


def spoken_number(words):
    """ "30", "thirty", "thirty five", "a hundred" -> int, else None."""
    words = words.replace("percent", "").replace("%", "").split()
    if len(words) == 1 and words[0].isdigit():
        return int(words[0])
    words = [w for w in words if w not in ("a", "one") or len(words) == 1]
    if words and all(w in NUMBERS for w in words):
        return sum(NUMBERS[w] for w in words)
    return None


def understand(heard, ctx):
    """What the turn asks for: an Intent, a NoMatch, or None for Dictation. Never acts."""
    words = normalise(heard)
    if len(words.split()) > MAX_COMMAND_WORDS:
        return None
    if words in ("mute", "unmute", "volume up", "volume down", "louder", "quieter"):
        return Intent(words)
    if words.startswith("volume "):
        level = spoken_number(words[len("volume "):])
        return Intent("volume", level=min(100, level)) if level is not None else None
    for phrase in sorted(MEDIA_VERBS, key=len, reverse=True):
        if words == phrase:
            return Intent("media", action=MEDIA_VERBS[phrase])
        if words.startswith(phrase + " "):
            t = best_target(words[len(phrase) + 1:], ctx.catalog)
            return Intent("media", t, action=MEDIA_VERBS[phrase]) if t else None
    for verb in OPEN_VERBS:
        if words.startswith(verb + " "):
            name = words[len(verb) + 1:]
            t = best_target(name, ctx.catalog)
            return Intent("open", t) if t else NoMatch(Card("No app called", name, kind="no_match"))
    return None


def is_complete_command(heard, ctx):
    """True when what's been said so far is a whole Command, so the turn can end early."""
    return isinstance(understand(heard, ctx), Intent)


def find_by_name(name, catalog):
    return next((t for t in catalog if t.name == name), None)


def carry_out(intent, ctx):
    a = ctx.actions
    if intent.kind == "media":
        player = a.media(intent.action, intent.target)
        if not player:
            return NoMatch(Card("Nothing", "playing", kind="no_match"))
        app = intent.target or find_by_name(player, ctx.catalog)
        return Done(Card(MEDIA_DONE[intent.action], player, app.id if app else ""))
    if intent.kind == "volume":
        a.set_volume(intent.level)
        return Done(Card("Volume", f"{intent.level}%", glyph=GLYPH_VOLUME))
    if intent.kind in ("volume up", "louder", "volume down", "quieter"):
        level = a.change_volume(VOLUME_STEP if intent.kind in ("volume up", "louder") else -VOLUME_STEP)
        return Done(Card("Volume", f"{level}%", glyph=GLYPH_VOLUME))
    if intent.kind in ("mute", "unmute"):
        a.mute(intent.kind == "mute")
        return Done(Card("Muted" if intent.kind == "mute" else "Sound", "Sound" if intent.kind == "mute" else "On",
                         glyph=GLYPH_MUTE if intent.kind == "mute" else GLYPH_VOLUME))
    t = intent.target
    if ctx.actions.switch_to(t):
        return Done(Card("Switching to", t.name, t.id))
    try:
        ctx.actions.launch(t)
    except Exception as e:
        ctx.log(f"Couldn't open {t.name}: {e!r}")
        return Failed(Card("Couldn't open", t.name, t.id, "failed"))
    return Done(Card("Opening", t.name, t.id))


def handle(heard, ctx):
    found = understand(heard, ctx)
    if found is None:
        return Dictation(heard)
    return found if isinstance(found, NoMatch) else carry_out(found, ctx)

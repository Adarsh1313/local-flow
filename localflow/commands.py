"""Voice Commands: decide what a Hands-free turn means and carry it out.

Pure logic (no tkinter, mic or model) so it can be tested. Everything that touches
Windows goes through the `actions` object in the Context. Terms: see GLOSSARY.md.
"""
import difflib
import re
from dataclasses import dataclass, field
from urllib.parse import quote, quote_plus


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    kind: str = "app"   # "app", or a Place: "folder", "settings", "website"
    path: str = ""      # where a Place opens: folder path, ms-settings: page or URL


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


@dataclass(frozen=True)
class NeedsConfirmation:
    """A Command that closes several apps waits for a yes or no."""
    question: str      # "Close 6 apps?"
    apps: list         # [(Target, [window titles])]


@dataclass(frozen=True)
class Alias:
    say: str             # the spoken name: "music"
    target_id: str       # what it opens: Spotify
    suggested: bool = False


@dataclass
class Context:
    catalog: list
    actions: object
    log: object = print   # where details of failures go (localflow.log in the app)
    aliases: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)          # target id -> times used by voice
    windows_usage: dict = field(default_factory=dict)  # target id -> minutes Windows saw it in use
    on_use: object = lambda target_id: None            # records a use (the command log)


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


def target_forms(target):
    forms = spoken_forms(target.name)
    if target.kind == "folder":
        forms.add(normalise(target.name) + " folder")   # "open downloads folder"
    return forms


def score(heard, target):
    return max(difflib.SequenceMatcher(None, heard, f).ratio() for f in target_forms(target))


def preference(t, ctx):
    """Between apps with the same name: used by voice most, then used most in Windows,
    then the Store version (its launch ID names a package: "Claude_pzs8...!Claude")."""
    if ctx is None:
        return (0, 0, "!" in t.id)
    return (ctx.usage.get(t.id, 0), ctx.windows_usage.get(t.id, 0), "!" in t.id)


def alias_target(name, ctx):
    if ctx is None:
        return None
    by_id = {t.id: t for t in ctx.catalog}
    scored = [(difflib.SequenceMatcher(None, name, normalise(a.say)).ratio(), a) for a in ctx.aliases
              if a.target_id in by_id]
    best = max(scored, key=lambda x: x[0], default=None)
    return by_id[best[1].target_id] if best and best[0] >= MATCH_THRESHOLD else None


def best_target(name, catalog, ctx=None):
    """The Target a heard name means: an Alias first, then the closest-sounding name;
    ties (duplicate Start entries) go by preference."""
    aliased = alias_target(name, ctx)
    if aliased and (aliased in catalog or not catalog):
        return aliased
    scored = [(score(name, t), t) for t in catalog]
    top = max((sc for sc, _ in scored), default=0)
    if top < MATCH_THRESHOLD:
        return None
    return max((t for sc, t in scored if sc >= top - 1e-9), key=lambda t: preference(t, ctx))


@dataclass(frozen=True)
class Intent:
    """A Command understood but not yet carried out."""
    kind: str               # "open", "media", "volume", "mute", "unmute", "volume up", ...
    target: Target = None
    action: str = ""        # media: "pause", "play", "next", "previous"
    level: int = 0          # volume: 0-100
    query: str = ""         # search: what to look for


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


SEARCH = re.compile(r"^(?:search (?P<where>.+?) for|search (?:the web )?for|google|look up) (?P<q>.+)$")
MAX_SEARCH_WORDS = 14    # searches carry a query, so they may run longer
GLYPH_SEARCH = ""
PLACE_GLYPHS = {"folder": "", "settings": "", "website": ""}  # when the shell has no icon


CLOSE_VERBS = ("close", "quit", "exit")
MINIMISE_VERBS = ("minimise", "minimize", "hide")
CLOSE_ALL = {"close everything", "close all", "close all apps", "close all windows", "close all the apps"}
MINIMISE_ALL = {"minimise everything", "minimize everything", "minimise all", "minimize all",
                "show desktop", "show the desktop", "hide everything"}
NEVER_CLOSE = {"localflow"}            # the assistant stays available
YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "do it", "close them", "go ahead", "confirm", "yes please"}
NO = {"no", "nope", "cancel", "stop", "dont", "keep them", "never mind", "no thanks"}
GLYPH_MINIMISE, GLYPH_CLOSED, GLYPH_KEPT = "", "", ""


def understand(heard, ctx):
    """What the turn asks for: an Intent, a NoMatch, or None for Dictation. Never acts."""
    words = normalise(heard)
    m = SEARCH.match(words)
    if m and len(words.split()) <= MAX_SEARCH_WORDS:
        query, where = heard_query(heard, m.group("q")), (m.group("where") or "web")
        if where in ("spotify", "youtube", "web", "the web", "google"):
            return Intent("search", find_by_name("Spotify", ctx.catalog) if where == "spotify" else None,
                          action="web" if where in ("the web", "google") else where, query=query)
        return NoMatch(Card("Can't search", where, kind="no_match"))
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
            t = best_target(words[len(phrase) + 1:], ctx.catalog, ctx)
            return Intent("media", t, action=MEDIA_VERBS[phrase]) if t else None
    if words in CLOSE_ALL:
        return Intent("close_all")
    if words in MINIMISE_ALL:
        return Intent("minimise_all")
    for verbs, kind in ((CLOSE_VERBS, "close"), (MINIMISE_VERBS, "minimise")):
        for verb in verbs:
            if words.startswith(verb + " "):
                t = best_target(words[len(verb) + 1:], [t for t in ctx.catalog if t.kind == "app"], ctx)
                return Intent(kind, t) if t else NoMatch(Card("No app called", words[len(verb) + 1:], kind="no_match"))
    for verb in OPEN_VERBS:
        if words.startswith(verb + " "):
            name = words[len(verb) + 1:]
            t = best_target(name, ctx.catalog, ctx)
            return Intent("open", t) if t else NoMatch(Card("No app called", name, kind="no_match"))
    aliased = alias_target(words, ctx)    # saying just an Alias opens it: "music"
    if aliased:
        return Intent("open", aliased)
    return None


def is_complete_command(heard, ctx):
    """True when what's been said so far is a whole Command, so the turn can end early."""
    return isinstance(understand(heard, ctx), Intent)


def heard_query(heard, normalised_query):
    """The query as spoken (keeps "lo-fi"): the last words of what was heard."""
    spoken = heard.strip().rstrip(".!?,").split()
    n = len(normalised_query.split())
    return " ".join(spoken[-n:]) if 0 < n <= len(spoken) else normalised_query


SEARCH_URLS = {"spotify": lambda q: "spotify:search:" + quote(q),
               "youtube": lambda q: "https://www.youtube.com/results?search_query=" + quote_plus(q),
               "web": lambda q: "https://www.google.com/search?q=" + quote_plus(q)}
SEARCH_NAMES = {"spotify": "Spotify", "youtube": "YouTube", "web": "the web"}


def find_by_name(name, catalog):
    return next((t for t in catalog if t.name == name), None)


def used(target, ctx):
    if target is not None:
        ctx.usage[target.id] = ctx.usage.get(target.id, 0) + 1
        ctx.on_use(target.id)


def carry_out(intent, ctx):
    a = ctx.actions
    used(intent.target, ctx)
    if intent.kind == "media":
        player = a.media(intent.action, intent.target)
        if not player:
            return NoMatch(Card("Nothing", "playing", kind="no_match"))
        app = intent.target or find_by_name(player, ctx.catalog)
        return Done(Card(MEDIA_DONE[intent.action], player, app.id if app else ""))
    if intent.kind == "search":
        q = intent.query if intent.action == "spotify" else intent.query.lower()
        a.open_url(SEARCH_URLS[intent.action](q))
        return Done(Card("Searching " + SEARCH_NAMES[intent.action], intent.query,
                         intent.target.id if intent.target else "", glyph=GLYPH_SEARCH))
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
    if intent.kind == "minimise_all":
        a.minimise_all()
        return Done(Card("Minimised", "Everything", glyph=GLYPH_MINIMISE))
    if intent.kind == "close_all":
        apps = closable(ctx)
        if len(apps) >= 2:
            return NeedsConfirmation(f"Close {len(apps)} apps?", apps)
        if not apps:
            return NoMatch(Card("Nothing", "to close", kind="no_match"))
        intent = Intent("close", apps[0][0])
    if intent.kind in ("close", "minimise"):
        t = intent.target
        if not any(r[0].id == t.id for r in a.running_apps([t])):
            return NoMatch(Card("Not open", t.name, t.id, "no_match"))
        if normalise(t.name).replace(" ", "") in NEVER_CLOSE and intent.kind == "close":
            return NoMatch(Card("Can't close", t.name, t.id, "no_match"))
        (a.close if intent.kind == "close" else a.minimise)(t)
        return Done(Card("Closing" if intent.kind == "close" else "Minimised", t.name, t.id))
    t = intent.target
    if t.kind != "app":
        try:
            a.open_place(t)
        except Exception as e:
            ctx.log(f"Couldn't open {t.name}: {e!r}")
            return Failed(Card("Couldn't open", t.name, t.id, "failed"))
        return Done(Card("Opening", t.name, t.id, glyph=PLACE_GLYPHS.get(t.kind, "")))
    if ctx.actions.switch_to(t):
        return Done(Card("Switching to", t.name, t.id))
    try:
        ctx.actions.launch(t)
    except Exception as e:
        ctx.log(f"Couldn't open {t.name}: {e!r}")
        return Failed(Card("Couldn't open", t.name, t.id, "failed"))
    return Done(Card("Opening", t.name, t.id))


def closable(ctx):
    return [(t, titles) for t, titles in ctx.actions.running_apps([t for t in ctx.catalog if t.kind == "app"])
            if normalise(t.name).replace(" ", "") not in NEVER_CLOSE]


def answer(heard):
    """A spoken reply to a Confirmation: "yes", "no" (silence is no), or None if unclear."""
    words = normalise(heard)
    if not words:
        return "no"
    for phrase, reply in sorted([(p, "yes") for p in YES] + [(p, "no") for p in NO], key=lambda x: -len(x[0])):
        if words == phrase or words.startswith(phrase + " "):
            return reply
    return None


def confirm(asked, yes, ctx):
    """Carry out (or drop) what a Confirmation asked about."""
    n = f"{len(asked.apps)} apps"
    if not yes:
        return Done(Card("Kept open", n, glyph=GLYPH_KEPT))
    for t, _ in asked.apps:
        try:
            ctx.actions.close(t)
        except Exception as e:
            ctx.log(f"Couldn't close {t.name}: {e!r}")
    return Done(Card("Closed", n, glyph=GLYPH_CLOSED))


SUGGESTED_ALIASES = [("codex", "ChatGPT"), ("antigravity", "Antigravity"), ("explorer", "File Explorer"),
                     ("files", "File Explorer"), ("music", "Spotify")]
FAVOURITES = ["Google Chrome", "Spotify", "Claude", "ChatGPT", "Antigravity", "File Explorer", "LocalFlow",
              "Agent Kanban"]


def suggested_aliases(catalog, dismissed):
    """Aliases LocalFlow proposes, for apps that are installed and not dismissed."""
    out = []
    for say, name in SUGGESTED_ALIASES:
        matches = [t for t in catalog if t.name == name]
        if matches and say not in dismissed:
            out.append(Alias(say, max(matches, key=lambda t: preference(t, None)).id, suggested=True))
    return out


def top_apps(catalog, usage, windows_usage, favourites=FAVOURITES):
    """Apps to suggest first: used by voice, then used in Windows, then the favourites."""
    apps = [t for t in catalog if t.kind == "app"]
    ranked = sorted((t for t in apps if usage.get(t.id)), key=lambda t: -usage[t.id])
    ranked += sorted((t for t in apps if windows_usage.get(t.id)), key=lambda t: -windows_usage[t.id])
    for name in favourites:
        ranked += [t for t in apps if t.name == name]
    seen, out = set(), []
    for t in ranked:
        if t.name not in seen:
            seen.add(t.name)
            out.append(t)
    return out


def handle(heard, ctx):
    found = understand(heard, ctx)
    if found is None:
        return Dictation(heard)
    return found if isinstance(found, NoMatch) else carry_out(found, ctx)

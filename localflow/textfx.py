"""Text processing: raw transcript in, the text that gets pasted out. Pure: no UI,
keyboard or audio, so it can be tested directly."""
import re
from dataclasses import dataclass


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
    return join_parts(pieces)[0]


def join_parts(pieces):
    """The joined text, and where each piece starts in it (None for a dropped piece)."""
    out, starts = "", []
    for piece in (p.strip() for p in pieces):
        starts.append(None)
        if not piece:
            continue
        words = [w.strip(".,!?").lower() for w in piece.split()]
        if out and all(w in FILLERS for w in words):
            continue  # a lone "Uh" between phrases
        if not out:
            out = piece
            starts[-1] = 0
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
        out += ("" if out.endswith("\n") else " ")
        starts[-1] = len(out)
        out += piece
    return out, starts


def strip_fillers(text):
    text = re.sub(r"(?i)(^|[\s,(])(?:uh+|um+|uhm|erm|hmm+)\b[,.]?(?=\s|$)", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).replace(" ,", ",").strip(" ,")


def capitalise_sentences(text):
    # sentences that now start lower-case ("Uh what should I do" -> "What should I do")
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def remove_fillers(text):
    return capitalise_sentences(strip_fillers(text))


# ------------------------------------------------------------- spoken lists
#
# "Here's my plan. One, buy milk. Two, call the bank." becomes
#   Here's my plan:
#   1. Buy milk
#   2. Call the bank
# A run of at least two consecutive markers is needed (1 then 2). Numbers work
# without punctuation too ("one buy milk two call the bank"), unless they count
# something: "I have one question and two concerns" stays a sentence.
# "Bullet point" / "next point" make "-" bullets. Once a list is open, "then" said
# after a pause adds a point.
#
# Spoken sequences work too: "First, open the app. Then sign in. Finally, check
# the logs." becomes a numbered list. These need a "first" to start and at least
# three steps, so "Then I went home." on its own stays prose; explicit numbers
# ("second", "two") win over "then" when both are said. "Point one is speed"
# drops the label and the "is": "1. Speed".

NUM_WORDS = {w: i for i, w in enumerate("one two three four five six seven eight nine ten".split(), 1)}
ORDINALS = {w: i for i, w in enumerate(
    "first second third fourth fifth sixth seventh eighth ninth tenth".split(), 1)}
ORDINALS.update({"firstly": 1, "secondly": 2, "thirdly": 3, "first of all": 1, "first off": 1,
                 "to start with": 1, "to begin with": 1, "second of all": 2})
_ALT = lambda words: "|".join(sorted(words, key=len, reverse=True)).replace(" ", r"\s+")
LIST_MARKER = re.compile(
    r"(?P<pre>^|(?<=[.!?:;,])\s+|\s+(?=and\s+(?:then|finally|lastly)\b))(?:and\s+)?(?:"
    r"(?P<digit>\d{1,2})[.):]\s+"
    rf"|(?P<word>{_ALT(NUM_WORDS)})[,.:]\s+"
    rf"|(?P<ord>{_ALT(ORDINALS)})\b[,.:]?\s+"
    r"|(?P<seq>then|next(?!\s+(?:point|bullet))|after\s+that|after\s+this|afterwards)\b[,:]?\s+"
    r"|(?P<last>finally|lastly|last\s+of\s+all)\b[,:]?\s+"
    r")"
    rf"|\b(?:number|point|step|item|option|reason|phase|stage|priority)\s+"
    rf"(?P<pword>{_ALT(NUM_WORDS)}|\d{{1,2}})\b[,.:]?\s*"
    r"|\b(?P<bullet>bullet point|bullet|next point|next bullet|new point|another point)\b[,.:]?\s*"
    # "1. alpha 2. beta": the recogniser often leaves out the full stop before a digit
    r"|(?<=\s)(?P<idigit>\d{1,2})[.)]\s+(?=[^\W\d_])"
    # "one buy milk two call the bank": no punctuation at all (checked by _counts_a_noun)
    rf"|(?<![\w'-])(?P<bword>{_ALT(NUM_WORDS)})\s+(?=[^\W\d_])",
    re.I)
# "then" at the start of a phrase said after a pause
_PAUSED_THEN = re.compile(r"(?:and\s+)?then\b[,:]?\s+", re.I)
# a bare number that counts something ("one question and two concerns") isn't a marker
_COUNTED_BY = {"a", "an", "the", "no", "only", "which", "each", "any", "every", "this", "that", "per",
               "of", "those", "these", "just", "another", "than", "to", "at", "by", "for", "with"}
_COUNTS = {"of", "or", "more", "times", "hundred", "thousand", "million", "billion", "and"}
_NOT_PLURAL = {"is", "was", "has", "does", "goes", "says", "this", "thus", "its", "yes", "plus", "us",
               "bus", "as", "his", "hers", "ours", "yours", "always", "perhaps", "unless", "across"}


def _counts_a_noun(text, start, end):
    before = re.search(r"([A-Za-z'-]+)\W*$", text[:start])
    after = re.match(r"([A-Za-z'-]+)", text[end:])
    nxt = after.group(1).lower() if after else ""
    if before and before.group(1).lower() in _COUNTED_BY:
        return True
    plural = len(nxt) > 3 and nxt.endswith("s") and not nxt.endswith("ss") and nxt not in _NOT_PLURAL
    return plural or nxt in _COUNTS
# "Point one is speed" -> "Speed"
_LABEL_VERB = re.compile(r"^(?:is|are|was|will\s+be|would\s+be)\s+(?:that\s+)?", re.I)


def _longest_run(marks, follows):
    """Longest chain starting at a 1 where each later mark `follows(mark, want)`."""
    run = []
    for i, mark in enumerate(marks):
        if mark[2] == "num" and mark[3] == 1:
            seq, want = [mark], 2
            for nxt in marks[i + 1:]:
                if follows(nxt, want):
                    seq.append(nxt)
                    want += 1
                    if nxt[2] == "last":
                        break
            run = seq if len(seq) > len(run) else run
    return run


def format_lists(text, pauses=()):
    """`pauses`: where in the text a phrase said after a pause starts. "Then" there
    adds a point to a list that's already open."""
    marks = []
    for m in LIST_MARKER.finditer(text):
        g = m.groupdict()
        if g["bword"] and _counts_a_noun(text, m.start(), m.end()):
            continue
        if g["bullet"]:
            kind, value = "bullet", None
        elif g["seq"] or g["last"]:
            kind, value = "seq" if g["seq"] else "last", None
        else:
            raw = re.sub(r"\s+", " ", g["digit"] or g["word"] or g["ord"] or g["pword"] or g["idigit"]
                         or g["bword"]).lower()
            kind, value = "num", int(raw) if raw.isdigit() else NUM_WORDS.get(raw) or ORDINALS.get(raw)
        marks.append((m.start() + len(g["pre"] or ""), m.end(), kind, value, bool(g["pword"])))
    for at in pauses:
        m = _PAUSED_THEN.match(text, at)
        if m:
            marks = [mk for mk in marks if mk[0] != at] + [(at, m.end(), "then", None, False)]
    marks.sort()

    run = _longest_run(marks, lambda mk, want: mk[2] == "num" and mk[3] == want)
    numbered = len(run) >= 2
    if not numbered:
        run = _longest_run(marks, lambda mk, want: mk[2] in ("seq", "last", "then"))
        numbered = len(run) >= 3
    if not numbered:
        run = [mk for mk in marks if mk[2] == "bullet"]
        if len(run) < 2:
            return text
    run = run + [mk for mk in marks if mk[2] == "then" and mk[0] > run[-1][0] and mk not in run]

    items = []
    for j, mark in enumerate(run):
        item = text[mark[1]:run[j + 1][0] if j + 1 < len(run) else len(text)].strip()
        item = re.sub(r"(?:[\s,;.]|\band)+$", "", item, flags=re.I).strip()
        if mark[4]:
            item = _LABEL_VERB.sub("", item)
        if item:
            items.append(item[0].upper() + item[1:])
    if len(items) < 2:
        return text
    lead = text[:run[0][0]].strip()
    if lead:
        lead = lead.rstrip(".,;") + ("" if lead[-1] in ":?!" else ":")
    lines = ([lead] if lead else []) + [f"{n}. {it}" if numbered else f"- {it}" for n, it in enumerate(items, 1)]
    return "\n".join(lines)


# ------------------------------------------------------------------ numbers
#
# Spoken numbers are written the way people type them: "twenty twenty six" -> 2026,
# "the twenty dollar plan" -> "the $20 plan", "fifty percent" -> 50%, "at three thirty"
# -> 3:30, "twenty five" -> 25. One to nine stay words in prose ("one question"),
# except in amounts and times.

SMALL = r"one|two|three|four|five|six|seven|eight|nine"
# "five dollars": small numbers in amounts become digits too
_SMALL_UNIT = re.compile(rf"\b({SMALL})(?=\s+(?:dollars?|bucks|percent|per\s+cent|rupees?)\b)", re.I)
# "at three thirty": the hour of a time
_SMALL_TIME = re.compile(rf"\b(at|by|around|until|till|from|before|after)\s+({SMALL})(?=\s+(?:o'?\s?clock|"
                         r"(?:twenty|thirty|forty|fifty|fifteen|ten|oh)\b))", re.I)
_YEAR = re.compile(r"\b(19|20)\s(\d{2})\b")
_TIME = re.compile(r"\b(at|by|around|until|till|from|before|after)\s(\d{1,2})\s(?:oh\s)?([0-5]\d)\b", re.I)
_DOLLARS = re.compile(r"\b(\d[\d,.]*)\s(?:dollars?|bucks)\b", re.I)
_RUPEES = re.compile(r"\b(\d[\d,.]*)\s(?:rupees?)\b", re.I)
_PERCENT = re.compile(r"\b(\d[\d.]*)\s(?:percent|per\scent)\b", re.I)
_BIG = re.compile(r"\b(\d+(?:\.\d+)?)(?:\s(1000000000|1000000)|(000000000|000000))\b")
_THOUSANDS = re.compile(r"\b\d{5,}\b")


def _digit_word(m):
    from text_to_num import text2num
    return str(text2num(m.group(1).lower(), "en"))


def numbers_to_digits(text):
    from text_to_num import alpha2digit
    text = _SMALL_UNIT.sub(_digit_word, text)
    text = _SMALL_TIME.sub(lambda m: f"{m.group(1)} {_digit_word(re.match(r'(\w+)', m.group(2)))}", text)
    text = alpha2digit(text, "en", threshold=10)
    text = _YEAR.sub(r"\1\2", text)
    text = _TIME.sub(r"\1 \2:\3", text)
    text = _DOLLARS.sub(r"$\1", text)
    text = _RUPEES.sub("₹\\1", text)
    text = _PERCENT.sub(r"\1%", text)

    def big(m):
        scale = m.group(2) or ("1" + m.group(3))
        word = "billion" if len(scale) == 10 else "million"
        return f"{m.group(1)} {word}"
    text = _BIG.sub(big, text)
    text = re.sub(r"\ba\s(100|1000)\b", r"\1", text)   # "a hundred people" -> "100 people"
    return _THOUSANDS.sub(lambda m: f"{int(m.group()):,}", text)


@dataclass(frozen=True)
class Options:
    """What postprocess does, taken from the settings."""
    fillers: bool = True
    lists: bool = True
    numbers: bool = True
    voice_commands: bool = True
    replacements: tuple = ()   # (heard, wanted) pairs from the config

    @classmethod
    def from_cfg(cls, cfg):
        return cls(fillers=cfg.get("remove_fillers", True), lists=cfg.get("smart_lists", True),
                   numbers=cfg.get("smart_numbers", True), voice_commands=cfg.get("voice_commands", True),
                   replacements=tuple(cfg.get("replacements", {}).items()))


LIST_PAUSE = 0.6   # seconds of quiet before "then" that start a new point


@dataclass(frozen=True)
class Transcript:
    """What was said, as the phrases between pauses."""
    parts: tuple
    gaps: tuple = ()   # seconds of quiet before each part

    @property
    def text(self):
        return join_pieces(self.parts)


def _clean(part, options, swaps):
    if options.fillers:
        part = strip_fillers(part)
    for source in swaps:
        part = source.apply(part)
    for heard, wanted in options.replacements:
        part = re.sub(r"\b" + re.escape(heard) + r"\b", wanted, part, flags=re.I)
    if options.voice_commands:
        part = re.sub(r"[,.]?\s*\bnew paragraph\b[,.]?\s*", "\n\n", part, flags=re.I)
        part = re.sub(r"[,.]?\s*\bnew line\b[,.]?\s*", "\n", part, flags=re.I)
    if options.numbers:
        part = numbers_to_digits(part)
    return part


def postprocess(said, options=Options(), swaps=()):
    """Raw transcript (a Transcript or plain text) -> pasted text. `swaps` apply in
    order (your Dictionary first)."""
    if isinstance(said, str):
        said = Transcript((said,))
    gaps = said.gaps or (0.0,) * len(said.parts)
    text, starts = join_parts([_clean(p, options, swaps) for p in said.parts])
    if options.fillers:
        text = capitalise_sentences(text)
    if options.lists:
        pauses = [at for at, gap in zip(starts, gaps) if at and gap >= LIST_PAUSE]
        text = format_lists(text, pauses)
    return text.strip()

# LocalFlow user guide

Offline push-to-talk dictation for Windows. Hold **Right Ctrl**, speak, release: the
text is typed wherever your cursor is. No account, no internet, no cost.

## Install

1. Install Python 3.12 from python.org.
2. Double-click `localflow\setup.bat` (creates `.venv`, installs everything and adds
   LocalFlow to the Start menu, plus Start/Stop shortcuts on the Desktop).
3. Open **LocalFlow** from Start or double-click `localflow\run.bat`. The first start downloads the speech model
   (~650 MB, once). After that it starts in about 10 seconds.

A small bar appears above the taskbar and a mic icon in the system tray. LocalFlow
turns on **Start with Windows** the first time it runs (switch it off in Settings).
`debug.bat` runs it with a console; errors also go to `localflow.log`.

## Dictate

| How | What to do |
|---|---|
| Hold to talk | Hold **Right Ctrl**, speak, let go |
| Hands-free | Double-tap **Right Ctrl**, talk as long as you like, tap again to finish. **Esc** throws it away. Stops by itself after 10 minutes |
| Wake word (on by default) | Say **"Hey Jarvis"**, wait for the chime, talk. A 2-second pause finishes it |

While you hold the key the pill shows a live waveform; on release it shows three dots
until the text is pasted. Pressing another key while holding (e.g. Right Ctrl + C)
cancels, so normal shortcuts still work. Fn can't be used as the hold key on most
laptops: the keyboard handles it in hardware and Windows never sees it.

## What happens to the text

- **Punctuation and capitals** come from the speech model. Long dictations are
  transcribed phrase by phrase while you talk; the joins are repaired so a thinking
  pause doesn't leave a stray period or capital.
- **Filler words** ("um", "uh") are removed.
- **Lists:** "Here's my plan. One, buy milk. Two, call the bank." becomes

  ```
  Here's my plan:
  1. Buy milk
  2. Call the bank
  ```

  "First… second…" and "number one… number two…" work too, and so does speech with
  no punctuation ("one buy milk two call the bank"). "Bullet point… next point…"
  makes `-` bullets. A list needs at least two items in order. Numbers that count
  something stay in a sentence: "I have one question and two concerns". Once a list
  is open, saying "then" after a pause adds the next point.
- **Numbers** are written as digits, the way people type them:
  - "twenty twenty six" → 2026
  - "the twenty dollar plan" → "the $20 plan"
  - "fifty percent" → 50%
  - "at three thirty" → 3:30
  - "twenty five people" → 25 people

  One to nine stay words in a sentence ("one question"). To turn this off, go to
  Settings → General → Numbers.
- **Spoken formatting:** say "new line" or "new paragraph".
- **Dictionary** swaps in the right spelling for words the model gets wrong (below).
- **AI cleanup** (optional, off): grammar fixes with a local Ollama model.

## Hover bar

Hover the small bar above the taskbar and it becomes a toolbar:

- **Scratchpad** — a notepad that saves as you type. Dictating while it's open types into it.
- **Settings** — General, Microphone, Dictionary, History and Commands.
- **Microphone** — pick the mic without opening settings.
- **Paste last** — opens Recent transcripts.

Panels close when you click elsewhere; the pin keeps one open.

## Recent transcripts (like Win+V)

**Ctrl+Alt+V** (or Paste last on the bar) shows your last 9 dictations, 3 per page.
Click one or press **1–3** to paste it where you were typing; **Copy** puts it on the
clipboard instead; **←/→** change page; **Esc** closes. Change the shortcut in Settings.
Shortcuts starting with Alt can be swallowed by overlay apps (e.g. graphics-driver
overlays), which is why the default isn't Alt-based.

## Microphone

**Automatic** (default) picks the best available mic and switches when devices connect
or disconnect: a USB/external mic first, then a headset (Bluetooth or wired), then the
laptop's built-in mic. Virtual devices like Stereo Mix are never chosen. You can pin a
specific mic; if it's disconnected, the best available one is used until it's back.

- **Keep the mic ready** (on): after a dictation the mic stays open for a minute, so
  the next one starts instantly and includes the 0.3 s before you pressed the key.
  Without it, Bluetooth earbuds need about a second to switch into headset mode and
  cut off your first words. While it's open, Windows shows the mic icon and Bluetooth
  earbuds stay in call mode.
- If a Bluetooth mic opens but sends no audio, LocalFlow reopens it, and in Automatic
  mode falls back to the laptop mic for 2 minutes.
- If Windows audio hangs while starting a mic, LocalFlow restarts itself once to recover.

## Wake word

Settings → General → Wake word → **Start with your voice** is on by default. It
listens on the laptop mic, so Bluetooth earbuds aren't stuck in call mode. The mic
stays on while this is enabled. Nothing is recorded or saved while listening.

- **"Hey Jarvis"** is heard by a small offline wake-word model (openWakeWord), so you
  can say it at a normal speaking volume. It only runs while there's sound, so a quiet
  room uses almost no CPU.
- **Any other phrase** is checked a different way. Short bursts of speech (under 3 s,
  then a pause) are transcribed in memory and compared with the phrase by how they
  sound, so "hey jervis" still counts but "hey there" doesn't.
- **Settings → Microphone → Wake word** has two settings:
  - **Sensitivity**: Low, Normal or High. Higher hears quieter speech, but wakes by
    mistake more often.
  - **Mic**: which mic listens for the wake word. The laptop mic is the default.
- **Last heard** shows the latest wake or near miss. Near misses are also written to
  `localflow.log`.

## Commands

With **Settings → Commands → Run commands with the wake word** on, a short instruction
after “Hey Jarvis” acts on Windows instead of being pasted. The waveform turns ice blue
and a card shows what happened. Commands stay out of Dictation History and Paste last.
A complete Command acts after about a 0.7-second pause; ordinary Dictation still waits
for the full pause.

| Say | What happens |
|---|---|
| “Open Spotify” / “Can you open Claude?” | Opens it, or brings its existing window forward |
| “Pause” / “Next” / “Previous” | Controls the player shown in Windows media controls |
| “Volume 30” / “Mute” | Changes the main Windows output |
| “Open Downloads folder” / “Open Bluetooth settings” | Opens a folder, drive or Settings page |
| “Open LinkedIn” / “Open GitHub” | Opens common websites in the default browser |
| “Search YouTube for lo-fi” / “Google weather” | Opens results in the appropriate app or browser |
| “Close Spotify” / “Minimise everything” | Closes politely or clears the desktop |

Closing two or more apps asks first. Say **yes**, **do it**, **no** or **cancel**, or use
the card’s buttons. Silence cancels. LocalFlow never closes itself.

Holding Right Ctrl with a text field focused always dictates. Holding it on the desktop,
in a player, or somewhere else with clearly nowhere to type runs a Command. If Windows
cannot tell what has focus, LocalFlow safely treats the speech as Dictation.

### Names

The Commands page lets you give an app, folder or website a spoken name: for example,
“music” → Spotify. LocalFlow initially suggests useful names for installed apps; remove
one and it stays removed. **Add a name** can also add an `.exe`, `.bat`, shortcut,
project folder or website that is missing from the Start menu.

### Routines

A Routine runs several safe Commands from one phrase. The initial suggestions are
**Work mode**, **Break time** and **Wrap up** when their Targets are installed. Edit the
name and steps, or remove the Routine. Routine steps can open a Target, close an app,
close all except chosen apps, minimise everything or control media. A Routine cannot
run shell commands, and closing several apps still requires Confirmation.

Commands can be conversational: **please**, **can you**, **could you** and **would you**
are understood, as are endings such as **for me**. Common speech-recognition variants
such as “clawed” or “cloud” are treated as Claude.

## Dictionary

When the model keeps mishearing a word, the dictionary swaps in the right one.

1. **Automatically:** fix a word in the text box within a minute of dictating
   ("Sio bhan" → "Siobhan"). LocalFlow reads the box through Windows UI Automation and
   spots the Fix. A card then says **Added to dictionary: Siobhan**, or why the Fix
   wasn't added. This works in most browsers and native apps, and password fields are
   skipped.
2. **Fix** in History: edit a transcript and the swapped words are learned.
3. **Dictionary tab:** add or remove entries yourself.

Rules that keep it from breaking normal sentences:

- Rare words and names are learned at once and swapped everywhere. That includes a
  name that replaces an everyday word ("cloud" → "Claude").
- A swap over a very common word ("New" → "Nuvo") only applies next to the words it
  was learned with ("Nuvo Health"), so "a new idea" stays untouched. Make the same Fix
  again and it applies everywhere.
- A Rewording between two everyday words ("patch" → "batch") is learned the second
  time you make the same Fix, because the first time could be a change of mind.
- **Not applied** on the Dictionary tab lists Fixes that are saved but not swapped,
  either waiting for a second Fix or switched off. Each one has a switch.

**Starter words** are built in: about 350 names and terms the model often mishears.
They come in five groups, each with its own switch on the Dictionary tab:

- tech and AI
- apps and brands
- startup terms
- Indian names and places
- shorthand, such as "L G T M" → LGTM

When a Starter word and one of your own words match the same thing, yours wins.

With the Whisper engine, dictionary words and Starter words are also given to the
model as spelling hints.

## Settings file (`config.json`)

Most settings are in the Settings window; these are the extra ones.

| Setting | Default | Notes |
|---|---|---|
| `engine` | `parakeet` | NVIDIA Parakeet on CPU. `whisper` uses an NVIDIA GPU and supports other languages |
| `whisper_model` | `small.en` | `base.en` is ~2x faster, `distil-medium.en` more accurate |
| `device` | `auto` | `cpu` to keep the GPU free |
| `beam_size` | `1` | `5` is slightly more accurate, ~25% slower |
| `vocabulary` | `[]` | Whisper only: names and jargon to spell right |
| `replacements` | `{}` | Always-on swaps, e.g. `{"cube or net ease": "Kubernetes"}` |
| `ollama_model` | `qwen2.5:3b` | Model used for AI cleanup |
| `ambient_end_silence` | `2.0` | Seconds of quiet that end a wake-word dictation |
| `ambient_mode` | `true` | Keep listening locally for the wake phrase |
| `commands_enabled` | `true` | Run Commands after the wake word; off means wake-word Dictation only |
| `wake_sensitivity` | `normal` | `low`, `normal` or `high` |
| `wake_mic` | `""` | Mic name for the wake word; empty means the laptop mic |
| `starter_groups` | `{}` | Starter words groups switched off, e.g. `{"india": false}` |
| `smart_numbers` | `true` | Write spoken numbers as digits |
| `save_training_data` | `false` | Keep each dictation's audio and final text in `training/` for fine-tuning later |

## AI cleanup with Ollama (optional)

1. Install Ollama from https://ollama.com (free).
2. `ollama pull qwen2.5:3b`
3. Turn on **AI cleanup** in Settings. Adds 1–3 s per dictation on a mid-range laptop.

## Notes

- Elevated (admin) windows won't accept the paste unless LocalFlow also runs as admin.
- Your clipboard is restored after each paste (unless something else changed it).
- Everything LocalFlow keeps (history, dictionary, notes, settings, private command-use
  log, optional training recordings) stays in its folder on your PC.

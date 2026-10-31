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

  "First… second…", "number one… number two…" work too, and "bullet point… next
  point…" makes `-` bullets. It needs at least two items in order, and a bare "one"
  only counts at the start of a sentence, so "I have one question and two concerns"
  stays a sentence.
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

Settings → General → Wake word → **Start with your voice** is on by default. It listens on the laptop mic,
so Bluetooth earbuds aren't stuck in call mode; the mic stays on while this is enabled.
Nothing is recorded or saved while listening: only short bursts of speech (under 3 s,
then a pause) are transcribed in memory and compared with the phrase by how they sound,
so "hey jervis" still counts but "hey there" doesn't. **Last heard** shows the most
recent burst, to help tune the phrase. Pause briefly after the phrase.

## Commands

With **Settings → Commands → Run commands with the wake word** on, a short instruction
after “Hey Jarvis” acts on Windows instead of being pasted. The waveform turns ice blue
and a card shows what happened. Commands stay out of Dictation History and Paste last.
A complete Command acts after about a 0.7-second pause; ordinary Dictation still waits
for the full pause.

| Say | What happens |
|---|---|
| “Open Spotify” / “Switch to Chrome” | Opens it, or brings its existing window forward |
| “Pause” / “Next” / “Previous” | Controls the player shown in Windows media controls |
| “Volume 30” / “Mute” | Changes the main Windows output |
| “Open Downloads folder” / “Open Bluetooth settings” | Opens a folder, drive or Settings page |
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

## Dictionary

When the model keeps mishearing a word, the dictionary swaps in the right one.

1. **Automatically:** fix a word in the text box within a minute of dictating
   ("Sio bhan" → "Siobhan"). LocalFlow reads the box through Windows UI Automation,
   spots the swap and shows "Learned: …". Works in most browsers and native apps;
   password fields are skipped.
2. **Fix** in History: edit a transcript and the swapped words are learned.
3. **Dictionary tab:** add or remove entries yourself.

Rules that keep it from breaking normal sentences:

- Rare words and names are swapped everywhere.
- A swap for an everyday word ("New" → "Nuvo") only applies next to the words it was
  learned with ("Nuvo Health"), so "a new idea" stays untouched.
- Edits between two everyday words ("Thursday" → "Friday") are changes of mind, not
  mishearings, and aren't learned.

With the Whisper engine, dictionary words are also given to the model as spelling hints.

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

## AI cleanup with Ollama (optional)

1. Install Ollama from https://ollama.com (free).
2. `ollama pull qwen2.5:3b`
3. Turn on **AI cleanup** in Settings. Adds 1–3 s per dictation on a mid-range laptop.

## Notes

- Elevated (admin) windows won't accept the paste unless LocalFlow also runs as admin.
- Your clipboard is restored after each paste (unless something else changed it).
- Everything LocalFlow keeps (history, dictionary, notes, settings, private command-use
  log, optional training recordings) stays in its folder on your PC.

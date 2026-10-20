# LocalFlow and Wispr Flow: what we took, what we adapted, what we couldn't

Wispr Flow set the bar for what dictation should feel like. LocalFlow started as
"can I have that on my own laptop, offline and for free?" This document is the honest
scorecard: which ideas came from Wispr Flow, how they had to change to run on a 2019
laptop, and what was out of reach.

LocalFlow is an independent project. It isn't affiliated with or endorsed by Wispr,
contains no Wispr code, and wasn't built by inspecting Wispr's software. Everything
below about Wispr Flow comes from its public [features](https://wisprflow.ai/features)
and [pricing](https://wisprflow.ai/pricing) pages, as of October 2026.

## The starting point

| | Wispr Flow | LocalFlow |
|---|---|---|
| Where speech is processed | Wispr's servers | On the laptop |
| Price | Free up to 2,000 words a week; Pro $15/month ($12 yearly) | Free, no limits |
| Platforms | Mac, Windows, iOS, Android | Windows |
| Languages | 100+ | English (Parakeet); others via Whisper, more slowly |
| Hardware needed | Any (the cloud does the work) | Mid-range CPU; GPU optional |

Copying the product directly wasn't possible: the recognition runs in Wispr's cloud,
and the open models it competes with are too heavy for a 3 GB GPU and a 4-core CPU.
Every feature below had to fit that budget.

## Feature by feature

**Legend:** ✅ built · 🟡 built differently · ⏳ planned · ❌ not feasible here / not a goal

| Wispr Flow feature (as Wispr describes it) | LocalFlow | How, or why not |
|---|---|---|
| Works in any app | ✅ | Clipboard + Ctrl+V into whichever app you were in, with focus restored first |
| Push-to-talk on Fn | 🟡 Right Ctrl | Fn is handled by the keyboard hardware on most Windows laptops and never reaches the OS |
| Hands-free dictation | ✅ | Double-tap Right Ctrl; tap again to finish. Plus an opt-in **wake word** ("Hey Jarvis"), which isn't listed among Wispr's features |
| Filler removal ("um", "uh") | ✅ | Rule-based, instant |
| Auto punctuation | 🟡 | Comes from the Parakeet model. Because long dictations are transcribed in chunks for speed, LocalFlow repairs the false sentence breaks at the joins |
| Numbered lists | ✅ | "One… two…", "first… second…", "number one…", plus "bullet point / next point" for `-` bullets. Needs two items in order, so ordinary sentences aren't turned into lists |
| Personal dictionary that learns corrections | ✅ with guardrails | Reads the corrected text back through Windows UI Automation. After a real failure ("New → Neu" broke every "new"), everyday words only swap next to the words they were learned with |
| Context-aware spelling of uncommon names | 🟡 | The dictionary, plus spelling hints when using Whisper. No large language model in the loop by default |
| Backtrack ("2… actually 3" → "3") | ⏳ | Needs a language model to do reliably; optional Ollama cleanup is the path |
| Styles (tone by context) | ⏳ | Planned per-app styles with a local LLM. On this CPU an LLM pass adds 1–3 s per dictation, so it can't be the default |
| Snippets (spoken shortcut → saved text) | ⏳ | Easy to add; not built yet |
| Whisper mode (very quiet speech) | 🟡 | Quiet audio is amplified automatically before recognition. No dedicated mode |
| 100+ languages | ❌ for now | Parakeet is English-only. Whisper handles other languages but is slower on this GPU |
| Cross-device sync | ❌ not a goal | Everything stays on one machine by design |
| Teams: shared dictionary, dashboards, SSO, HIPAA | ❌ not a goal | A personal tool |
| Notetaker / meeting notes | ❌ not a goal | Out of scope |
| Developer features (file tagging, code syntax) | ⏳ | Would fit per-app styles |
| Command mode (select text, speak an edit) | ⏳ | Mentioned in reviews of Wispr Flow rather than on its features page. Planned with a local LLM |

## Things LocalFlow added because of its constraints

These came from building on weak hardware and using it every day, not from Wispr Flow:

- **Transcribe-while-you-talk.** Phrases are transcribed at pauses while you're still
  speaking, so on release only the last phrase is left. On this CPU, transcribing a
  minute of speech in one go took 17 s; chunked, a long dictation finishes in about 0.25 s
  in benchmarks and 1.7 s median in real use.
- **Recent transcripts picker** (Ctrl+Alt+V), modelled on Windows' own Win+V clipboard
  history: the last 9 dictations, 3 per page, click to paste again.
- **Bluetooth survival kit.** Earbuds take about a second to switch into headset mode, can
  open and send no audio, or hang the audio driver. LocalFlow keeps the mic warm with a
  0.3 s pre-roll, reopens stalled mics, falls back to the laptop mic, and restarts
  itself once if Windows audio hangs.
- **Automatic mic ranking.** An external mic beats a headset, which beats the built-in
  mic; virtual devices are skipped; it switches when devices connect.
- **Sleep-proof overlay.** Windows stops drawing see-through windows after the laptop
  wakes from sleep; LocalFlow notices the wake-up and rebuilds them.
- **Wake word without training.** Instead of a trained wake-word model, short bursts of
  speech are run through the same speech model and matched by how they sound, so any
  phrase works immediately. Nothing is stored while listening.

## Other inspiration

- **Windows 11 Settings** for the look: sidebar, grouped rows, Fluent switches. Chosen
  from three rendered design directions.
- **Win+V clipboard history** for the recent-transcripts picker.
- **Smart speakers** for the "wake word, chime, talk" interaction.
- Other open-source dictation tools (such as Handy and OpenWhispr) showed local dictation
  was viable on Windows. LocalFlow's focus is making it feel fast and dependable on
  low-end hardware.

## What I'd need to close the gap

| Gap | What it would take |
|---|---|
| Backtracking, styles, command mode | A small local LLM fast enough on this CPU, or an optional GPU path. Today it adds 1–3 s |
| Accuracy on my accent and vocabulary | Fine-tuning on my own recorded dictations (the app can already collect them) |
| Other languages | Making Whisper fast enough on a 3 GB GPU, or a multilingual model in Parakeet's class |
| Mac and mobile | A different audio, hotkey and UI layer per platform; not planned |

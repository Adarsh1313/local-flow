# Research: OS voice assistants and what a "Hey Jarvis" command mode could be

Date: 2026-10-31. Purpose: decide the scope of a voice-command mode for LocalFlow
(open apps, control them) that brings back the "Hey Cortana" feeling, offline.

## 1. Is Cortana dead?

Yes, on Windows.
- Standalone Cortana app on Windows 11 deprecated by an update in **August 2023**; the app
  now only shows a "deprecated" notice. Teams/Outlook/M365 mobile Cortana retired **fall 2023**.
- It kept working on Windows 10 until Windows 10's end of support (**Oct 2025**).
- Microsoft replaced it with **Copilot**, a cloud chatbot. "Hey, Copilot" wake word exists
  (opt-in, off by default, spotted on-device) but **every request needs the internet**.

So there is no built-in, offline "say it and it happens" assistant on Windows today
except Voice Access, which is an accessibility tool and not an assistant (below).

## 2. What each assistant could / can do

| Assistant | Local? | Open/switch apps | Act *inside* apps | How it acts inside apps |
|---|---|---|---|---|
| **Cortana** (Win10, 2015–2023) | Wake word local, rest cloud | Yes | Little: settings toggles (Wi-Fi, Bluetooth, airplane), reminders, calendar, music, web search, a few 3rd-party apps (e.g. Netflix) | App-registered voice commands |
| **Voice Access** (Win11, today) | Recognition on-device (setup needs internet) | Yes: "Open X", "Switch to X", "Start X". Falls back to Windows search if not found | Yes but literal: "click Play", show numbers/grid over the UI, dictation | UI Automation: clicks what's on screen |
| **Copilot** (Win11, today) | No | Partly | **Copilot Actions** (experimental, off by default): an agent works on local files in a sandboxed "Agent Workspace" under its own standard account | Cloud LLM + screen/UI control |
| **Siri** (macOS 27 / iOS 27, 2026) | Mixed | Yes | Yes, when the app supports it: reads app data, runs app actions, understands what's on screen | **App Intents** (apps declare actions); SiriKit deprecated |
| **Gemini** (Android, 2026) | No | Yes | Yes: utilities (alarms, timers, media, settings) and on Pixel 10 / Galaxy S26 multi-step tasks in other apps (order food, book a ride) | Android "app functions" + Computer Use model (screenshot → tap/type) |

Pattern: every assistant has two layers.
1. **Fixed commands** (open app, timer, volume, play/pause). Fast, reliable, cheap.
2. **Inside-app actions**, done either by the app exposing actions (Siri App Intents,
   Android app functions) or by an AI looking at the screen and clicking (Copilot Actions,
   Gemini Computer Use). The second is general but slow, costly and error-prone.

## 3. Does it cost a lot of AI?

Not for what you described.
- **Opening apps/files needs zero AI.** Whisper already turns speech into text; a simple
  "open / launch / start + name" rule plus fuzzy matching against Start Menu shortcuts and
  Store apps does the rest. Cost: zero, instant, fully offline.
- **A fixed list of commands needs zero AI too** (play/pause, next track, volume, open folder,
  "search Spotify for X"). Rules plus a phrase list cover ~90% of what Cortana was used for.
- **Free-form requests** ("put on something chill") need a language model to map words to
  a command. LocalFlow already supports Ollama (used for AI cleanup, adds 1–3 s). A small local
  model picking from *your* list of commands is free, but adds 1–3 s on modest hardware.
  Use it only as a fallback when the rules don't match.
- **Full computer control** (an AI that looks at the screen and clicks) is what Copilot
  Actions and Gemini do. It needs a large vision model: cloud cost per step, or a heavy local
  model your hardware won't run well. Not worth it for this app.

## 4. Can it open Spotify *and* do something in it?

Yes, without an AI agent:
- **Play/pause/next/previous for Spotify (or any media app):** Windows' system media
  controls API (`GlobalSystemMediaTransportControlsSessionManager`, Python via `winsdk`/`winrt`).
  Local, no account, works with Spotify Free.
- **Volume / mute:** Windows audio API (e.g. `pycaw`) or media keys.
- **"Search Spotify for Arijit Singh":** open the `spotify:search:<query>` link. Opens the
  desktop app on that search. Local. (Playing a *specific* song directly needs the Spotify
  Web API, which needs internet, a login and **Premium**. Skip it for v1.)
- **Other apps:** links like `ms-settings:bluetooth` (settings pages),
  `mailto:`, browser URLs, folders ("open Downloads"), and keyboard shortcuts sent to the
  window in front.

## 5. Ways to step it up

Ordered from most value per effort to least:
1. **Open / switch to apps** ("open Spotify", "switch to Chrome"): switch if already running,
   open if not, like Voice Access.
2. **Media control** ("pause", "next song", "volume 30"): works with any player.
3. **Quick links** ("open Downloads", "open Bluetooth settings", "open YouTube").
4. **Search in app** ("search Spotify for lo-fi", "Google how tall is Everest").
5. **Your own commands:** aliases ("music" → Spotify) and simple chains
   ("work mode" → open VS Code + Slack + Spotify playlist).
6. **Close / minimise windows** ("close Spotify").
7. **Optional AI fallback** via local Ollama for loosely worded requests, mapped onto the
   commands above, never free clicking.

Out of scope: screen-reading agents, anything that needs cloud AI or a paid account.

## 6. The nostalgia angle

Cortana was the last time Windows had a native "say it and it happens" assistant, and
Copilot replaced it with a cloud chatbot. LocalFlow's pitch: "Hey Jarvis" brings back that
instant, offline, private command feel, on modest hardware, at zero cost.

## 7. UI implication (for design-grill)

Wake-word commands get their own pill state, separate from the Ctrl dictation pill:
listening → understood ("Opening Spotify" + the app's real icon, pulled from its shortcut/exe)
→ done/dismiss. Siri-like: calm, minimal text, smooth morph between states. Motion is owned
by my-motion + emil-design-eng; layout/type by impeccable. Needs a DESIGN.md pass first.

## Sources
- [Microsoft: End of support for Cortana](https://support.microsoft.com/cortana)
- [Windows Central: Microsoft cuts support for Cortana on Windows 11](https://windowscentral.com/software-apps/microsoft-kills-cortana-with-update-though-you-still-have-some-time-left-with-the-assistant)
- [BleepingComputer: Microsoft killing Cortana from late 2023](https://www.bleepingcomputer.com/news/microsoft/microsoft-is-killing-cortana-on-windows-starting-late-2023)
- [Windows Central: Cortana voice commands on Windows 10](https://windowscentral.com/comprehensive-list-cortana-voice-commands-windows-10-0)
- [Microsoft: Voice access command list](https://support.microsoft.com/en-us/topic/voice-access-command-list-dac0f091-87ce-454d-8d57-bef38d3d8563)
- [Microsoft: Use voice to work with windows and apps](https://support.microsoft.com/en-US/accessibility/windows/voice-access/use-voice-to-work-with-windows-and-apps)
- [gHacks: "Hey, Copilot" wake word](https://www.ghacks.net/2025/05/15/microsoft-introduces-hey-copilot-wake-word-for-activating-the-ai-on-windows-11/)
- [Windows Insider blog: Copilot Actions](https://blogs.windows.com/windows-insider/2025/11/17/copilot-on-windows-copilot-actions-begins-rolling-out-to-windows-insiders/)
- [Microsoft: Experimental agentic features](https://support.microsoft.com/en-us/windows/experimental-agentic-features-a25ede8a-e4c2-4841-85a8-44839191dfb3)
- [Apple Developer: What's new in macOS](https://developer.apple.com/macos/whats-new/)
- [WWDC26: Advanced App Intents for Siri and Apple Intelligence](https://developer.apple.com/videos/play/wwdc2026/343/)
- [Android Authority: Gemini controls other apps on Galaxy S26 / Pixel 10](https://www.androidauthority.com/gemini-galaxy-s26-pixel-10-control-other-apps-3643939/)
- [Phil Schmid: Gemini Computer Use on Android](https://www.philschmid.de/gemini-android-use)
- [Microsoft: System media transport controls session](https://learn.microsoft.com/en-us/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)
- [Spotify community: playback API needs Premium](https://community.spotify.com/t5/Spotify-for-Developers/Premium-Required-quot-When-Attempting-to-Play-Track-via-API/m-p/6263971)

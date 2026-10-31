# Spec: Voice commands ("Hey Jarvis")

Status: ready-for-agent · Branch base: `project-setup` · Date: 2026-10-31
Read first: GLOSSARY.md, design/DESIGN.md ("Command mode", "Commands settings page"),
docs/research/voice-assistants.md.

## Problem Statement

Windows used to have "Hey Cortana": say what you want and it happens. Microsoft
retired it in 2023 and replaced it with Copilot, a cloud chatbot that needs the
internet for every request. There is no longer a fast, private, offline way to tell
Windows "open Spotify" or "pause" by voice. LocalFlow already listens for a Wake word
("Hey Jarvis"), but everything said after it is pasted as Dictation, so it can't act
on the computer.

## Solution

After the Wake word, LocalFlow decides whether the Hands-free turn is a Command. If it
is, it carries it out (open or switch to an app, control media and volume, open a
Place, search, close or minimise apps, run a Routine) and shows a small Command card
under the pill with the real app icon and what happened ("Opening" / "Spotify"). If
it isn't, it dictates exactly as today. Speech that sounds like a Command but fits no
Target shows a calm No match card and pastes nothing. Closing 2+ apps asks for
Confirmation first. Holding the hotkey with no text field focused also runs Commands.
A new "Commands" settings page manages Aliases, Places and Routines, with Suggested
ones built from the apps the user opens most. Everything runs offline with no AI.

## User Stories

### Triggering
1. As a user, I want "Hey Jarvis, open Spotify" to open Spotify, so that I can launch apps without touching the keyboard.
2. As a user, I want anything after "Hey Jarvis" that isn't a Command to be dictated as today, so that hands-free dictation keeps working.
3. As a user, I want "Hey Jarvis, open Spotfy" to show "No app called / Spotfy" and paste nothing, so that misheard commands never drop stray text into my document.
4. As a user, I want long hands-free dictation that merely starts with "open the report…" to be pasted, not run, so that I'm not surprised by apps launching.
5. As a user, I want holding the hotkey while a text field has focus to always paste, so that Hold-to-talk never surprises me.
6. As a user, I want holding the hotkey on the desktop or in Spotify (no text field) to run my speech as a Command, so that I can use the key I already hold.
7. As a user, I want Hold-to-talk to fall back to Dictation when LocalFlow can't tell whether a text field has focus, so that I never lose words.
8. As a user, I want a short Command to act after a brief pause (~0.7 s) instead of the usual 2 s, so that it feels as quick as Siri.
9. As a user, I want long dictation to still wait the full pause, so that I'm not cut off mid-thought.
10. As a user, I want a switch "Run commands with the wake word" (on by default), so that I can return the Wake word to dictation only.
11. As a user, I want to keep "Hey Jarvis" or change the phrase in settings, so that I can pick what feels natural (even "Hey Cortana" for myself).

### Apps
12. As a user, I want "open <app>" / "launch" / "start" to open any installed app, including Store apps, so that all 190+ apps are reachable.
13. As a user, I want "open Chrome" to switch to Chrome when it's already running (restoring it if minimised), so that I don't get duplicate windows.
14. As a user, I want "switch to <app>" / "go to <app>" to bring a running app forward, and open it if it isn't running, so that one phrase always works.
15. As a user, I want fuzzy matching so "VS code" finds "Visual Studio Code", so that I don't need exact names.
16. As a user, I want "open Claude" to pick the install I actually use when Windows lists two, so that the right one opens.
17. As a user, I want ties broken by what I open by voice most, then what Windows saw me use, then the Store version, so that guesses improve over time.
18. As a user, I want my own apps (LocalFlow, AgentKanban) to open by voice with their real icons, so that my tools feel first-class.
19. As a user, I want setup to add LocalFlow to the Start menu, so that it has a name and icon Windows (and Commands) can find.
20. As a user, I want "close Spotify" to close it politely like clicking X, so that apps with unsaved work can still ask me to save.
21. As a user, I want "minimise Chrome" and "minimise everything", so that I can clear my screen by voice.
22. As a user, I want "Couldn't open / Spotify" when an app fails to launch, with details in the log, so that I know it failed without alarm.

### Media and volume
23. As a user, I want "pause", "play", "resume", "next", "skip", "previous" to control whatever the Windows media pop-up shows, so that it works with any player.
24. As a user, I want "pause Spotify" to target Spotify specifically, so that I can pick when several players are open.
25. As a user, I want "volume 30", "volume up", "volume down", "mute", "unmute", so that I can control sound hands-free.
26. As a Spotify Free user, I want media control to work without Premium or the internet, so that it's free and offline.

### Places and search
27. As a user, I want "open Downloads/Documents/Desktop/Pictures folder", so that I reach common folders fast.
28. As a user, I want "open This PC", "open C drive", "open D drive", so that I can browse drives.
29. As a user, I want "open Bluetooth settings" (and other common settings pages) to open that page, so that I skip clicking through Settings.
30. As a user, I want "open YouTube" and other saved websites to open in my default browser, so that sites are Places too.
31. As a user, I want "search Spotify for lo-fi" to open Spotify's search, so that I can find music by voice.
32. As a user, I want "search YouTube for …" and "Google …" / "search the web for …" to open results in my default browser, so that I can look things up hands-free.

### Command card and feedback
33. As a user, I want the pill's waveform to turn ice blue (no red dot) after the Wake word, so that I can tell a Command from Dictation.
34. As a user, I want a card under the pill with the app's real icon, a muted verb and the object ("Opening" / "Spotify"), so that I see what happened at a glance.
35. As a user, I want real Windows icons for folders, drives and settings, so that it looks native.
36. As a user, I want the card to slide down and fade in, then leave quickly, and to stay while I point at it, so that it feels smooth and I can read it.
37. As a user, I want success to hold ~1.6 s and No match ~2.4 s, so that misses get a bit more reading time.
38. As a user, I want a soft tick on success and a low tone on No match after the wake chime, so that I know the outcome without looking.
39. As a user with Windows animation effects off, I want the card to appear and disappear instantly, so that motion respects my setting.
40. As a user, I want Commands kept out of History, "Paste last" and the stats, so that "open Spotify" is never pasted or counted as words.

### Confirmation
41. As a user, I want any Command that would close 2+ apps to ask "Close 6 apps?" first, so that I don't lose work by accident.
42. As a user, I want the card to show the icons of the apps it will close (6 max, "+N" after), so that I see what's affected.
43. As a user, I want an app with several windows to show a count, and hovering its icon to list the window titles (tab, folder or file name), so that I know exactly what will close.
44. As a user, I want to answer "yes" / "yeah" / "do it" / "close them" or "no" / "cancel" / "stop" without the Wake word within 6 s, so that I can stay hands-free.
45. As a user, I want Close and Cancel buttons too, so that I can answer with the mouse.
46. As a user, I want silence to cancel, so that the safe outcome is the default.
47. As a user, I want the card to change to "Closed / 6 apps" or "Kept open / 6 apps", so that I know what happened.
48. As a user, I want LocalFlow itself never to be closed by a Command, so that the assistant stays available.

### Aliases, Places and Routines (settings)
49. As a user, I want a "Commands" page in settings, so that I can manage everything in one place.
50. As a user, I want to give any app, folder or website a spoken name (Alias), so that "music" opens Spotify.
51. As a user, I want "Add name" to open a search picker with tabs Apps / Folders / Website and real icons, so that finding one of 193 apps is easy.
52. As a user, I want to add any .exe, .bat or shortcut as an app, so that my own projects can be opened by voice.
53. As a user, I want Suggested Aliases (codex → ChatGPT, antigravity → Antigravity, explorer/files → File Explorer, music → Spotify) active immediately with a muted "Suggested" tag, so that it works out of the box.
54. As a user, I want editing a Suggested item to make it mine (tag removed) and ✕ to remove it, so that I stay in control.
55. As a user, I want project folders added only by me ("Add folder"), so that the list stays short.
56. As a user, I want folder Aliases spoken as "<name> folder", so that they don't clash with apps of the same name.
57. As a user, I want Routines: one phrase running several steps, so that "work mode" sets up my desk.
58. As a user, I want Suggested Routines "Work mode" (open Claude + Chrome), "Break time" (open YouTube in the default browser) and "Wrap up" (close all apps except File Explorer), all editable, so that I start with useful ones.
59. As a user, I want a Routine sub-page to rename it, add, edit and remove steps, and delete the Routine, so that I can tailor it.
60. As a user, I want Routine steps limited to: open app, open Place or website, close app, close all except…, minimise all, media action, so that a Routine can't do damage.
61. As a user, I want "Close all except" to show which apps it keeps, so that I trust what Wrap up will do.
62. As a user, I want a read-only "What you can say" list, so that I can discover Commands.
63. As a user, I want Suggested apps to start from Windows' usage data and improve from the apps I open by voice, so that the suggestions fit me.

### Docs
64. As a reader of the README, I want LocalFlow pitched as the offline replacement for "Hey Cortana" (with a nod to Jarvis), so that the nostalgia is clear.
65. As a user, I want the existing "Voice commands" switch ("new line") renamed to "Spoken formatting", so that it isn't confused with Commands.

## Implementation Decisions

### Modules
- **Commands module (new, separate file from the main app).** Pure logic, no tkinter,
  mic or model imports, so it's importable by tests. Owns: deciding the outcome of a
  turn, matching Targets, Routines, Confirmation flow, the command log, and suggestions.
  Main interface (the one test seam):
  `handle(heard_text, context) -> Outcome`, where `context` carries the Catalog, user
  Aliases/Routines, the Actions object, and `source` (hands-free or hold-to-talk with
  no text field). `Outcome` is one of: `Dictation(text)`, `Done(card)`, `NoMatch(card)`,
  `Failed(card)`, `NeedsConfirmation(apps, on_yes, on_no)`. A `card` is data only
  (icon ref, verb, object, kind) for the overlay to draw.
  Also: `answer_confirmation(heard_text) -> yes | no | unclear`, and
  `is_complete_command(partial_text) -> bool` for the early-end check.
- **Catalog** (inside the Commands module): the list of Targets. Built from Windows'
  Start apps (name + launch ID, Store apps included), user-added apps, Windows known
  folders, drives, a fixed list of common settings pages, and saved websites. Duplicate
  names collapse to one entry with a ranked preference (voice-use count, then Windows
  usage, then Store app). Built at startup on a background thread and refreshed on an
  interval or when settings change; injected so tests use a fake.
- **Actions** (interface the Commands module calls; real implementation in a Windows
  adapter module): `launch(target)`, `switch_to(target) -> bool`, `close(app)`,
  `minimise(app)`, `minimise_all()`, `open_place(place)`, `open_url(url)`,
  `spotify_search(q)`, `media(action, app=None)`, `set_volume(n)`, `volume_step(±)`,
  `mute(bool)`, `running_apps() -> [app with window titles]`, `icon_for(target) -> image`.
  Real adapter uses: Start-app launch IDs / shortcuts for launching; window enumeration
  + polite close message for close; Windows' global media session controls for media
  (works with Spotify Free, offline); Windows audio endpoint API for volume; shell icons
  for app, folder, drive and settings icons (extracted at runtime, never bundled);
  `spotify:search:` links for Spotify search; default browser for web/YouTube search.
- **Main app changes:**
  - Turn finish path: after transcription and before paste, call `handle`. Dictation →
    existing paste path. Other outcomes → overlay card + sound, no paste, no History,
    no stats, no "Paste last".
  - Hands-free turn early end: on a ~0.7 s pause, transcribe what's heard so far; if
    `is_complete_command` is true, end the turn and handle it; otherwise keep listening
    to the existing 2 s end. One extra transcription per turn at most.
  - Hold-to-talk: at key release, check via UI Automation whether the focused element
    is an editable text field. Editable or unknown → Dictation. Clearly not editable →
    handle as a Command turn.
  - Confirmation: when `NeedsConfirmation`, show the confirmation card, reopen the mic
    without the Wake word for 6 s, transcribe the answer, call `answer_confirmation`.
    Silence or unclear → no. Buttons call the same callbacks.
  - Overlay: new states for command listening (ice-blue wave), command card (normal /
    no match / couldn't open), confirmation card (icon row, count badges, window-title
    tips), all per design/DESIGN.md and tokens. Real icons drawn anti-aliased.
  - Settings: new "Commands" page (switch, Routines, Names, What you can say) with
    sub-pages "Routine" and "Add a name", per design/DESIGN.md.
  - Rename the General page's "Voice commands" label to "Spoken formatting" (config key
    unchanged).
- **Matching rules (no AI):** normalise text (lowercase, strip punctuation and leading
  fillers). A turn is a Command candidate only if it is ≤ 6 words and starts with a
  command verb (open/launch/start/switch to/go to, close/quit, minimise/hide,
  play/pause/resume/next/skip/previous, volume/mute/unmute, search/google), or equals
  an Alias or Routine name. Targets match by Alias first, then fuzzy name similarity
  with a strong threshold; below threshold → No match (if a command verb was heard) or
  Dictation (if not). Ties → ranked preference as in the Catalog.
- **Config schema (local config file, user data, never committed):**
  `commands_enabled: bool` (default true), `aliases: [{say, target_id, kind, suggested}]`,
  `routines: [{name, steps: [{type, target_id?, keep?: [target_id], action?}], suggested}]`,
  `user_apps: [{name, path}]`, `suggestions_dismissed: [id]`.
- **Command log:** a separate local file (gitignored) recording command, target and
  time; used only for ranking and suggestions. Not shown in v1.
- **Suggested items** are generated on first run (and when new top apps appear):
  Aliases listed in User Story 53, the three Routines in 58, top apps from Windows
  usage data + the user's named list (Chrome, Spotify, Claude, ChatGPT/Codex,
  Antigravity, File Explorer, LocalFlow, AgentKanban). Removing one records it as
  dismissed so it doesn't return.
- **Sounds:** existing wake chime; add a soft success tick and a low No-match tone
  (short, quiet, no melody), played with the existing beep mechanism unless a better
  tone is chosen during build.
- **LocalFlow is never a close target** (excluded from close and close-all).
- Setup adds a Start menu shortcut for LocalFlow with its icon.

## Testing Decisions

- Good tests check behaviour through the public seam (heard text in → outcome and
  Actions calls out), never internal helpers or matching scores. Test names read as
  user behaviour ("open spotfy is a no match and pastes nothing").
- **Unit seam (primary): the Commands module's `handle`**, with a fake Catalog (a few
  apps incl. duplicates, folders, drives, settings pages, websites) and a recording fake
  Actions. Cover: dictation vs command vs no match, long "open the report…" dictation,
  aliases, folder "<name> folder", switch-vs-open, duplicate ranking, media with and
  without a named app, volume parsing, search phrases, close one vs close many
  (Confirmation), confirmation answers (yes/no/silence/unclear), LocalFlow never closed,
  routines (each step type), launch failure → Failed card, `is_complete_command`,
  suggestions + dismissal, hold-to-talk source.
- **Windows integration tests (opt-in, marked `windows`, run on this PC only):** use
  the real Actions adapter against safe built-in apps: launch Notepad, switch to it,
  minimise it, close it politely; open a temp folder in Explorer and close it; read the
  catalog and find File Explorer; extract an icon for Notepad and a folder; read the
  current volume and set it back. Skipped by default and in any non-Windows run.
- Test runner: pytest, installed as a dev requirement; tests live in a top-level tests
  folder. No prior art in this repo (no tests exist yet); this spec introduces them.
- UI (overlay states, settings pages) is verified by hand against design/system.html.

## Out of Scope

- File search ("find report.pdf"); research kept in docs/research/file-search.md.
- AI fallback for loosely worded requests (local Ollama) and its "thinking" state.
- Shell commands in Routines.
- Playing a specific song/playlist via the Spotify Web API (needs Premium + internet).
- Screen-reading agents or clicking inside apps.
- Languages other than English; Mac/Linux.
- Showing the command log in the UI.
- Suggesting project folders automatically.

## Further Notes

- Glossary terms used: Dictation, Hold-to-talk, Wake word, Hands-free turn, Command,
  Target, Place, Alias, Routine, Suggested, Confirmation, No match.
- "Cortana" is a Microsoft trademark: never ship it as a default name, logo or asset.
- Performance: idle CPU must stay ~0 (CLAUDE.md). Catalog and icon work happens on a
  background thread; icons are cached.
- Open design questions remain in design/DESIGN.md (card above the pill when the pill
  is low on screen; exact tones).

## Progress

- [ ] 1. Test setup + Commands module skeleton + "open/switch to <app>" end to end via
      Wake word (Catalog from Start apps, real Actions launch/switch, plain text card)
- [ ] 2. Command card visuals: ice-blue listening wave, real icons, slide/fade, hold
      timings, hover-to-keep, success/No match sounds, No match and Couldn't open
- [ ] 3. Early end on ~0.7 s pause for complete Commands
- [ ] 4. Media (any player + named app) and volume Commands
- [ ] 5. Places (known folders, This PC, drives, settings pages, websites) and search
      (Spotify, YouTube, web)
- [ ] 6. Close / minimise + Confirmation card (icon row, counts, window-title tips,
      voice yes/no, buttons, silence cancels)
- [ ] 7. Hold-to-talk with no text field runs Commands
- [ ] 8. Command log, duplicate ranking, Suggested Aliases and top apps, user-added apps
- [ ] 9. Commands settings page: switch, Names list, "Add a name" sub-page
- [ ] 10. Routines: storage, the three Suggested Routines, Routine sub-page editor,
      "What you can say"
- [ ] 11. Polish & docs: Start menu shortcut in setup, rename "Voice commands" →
      "Spoken formatting", README "Hey Cortana" pitch, user guide, Windows integration
      tests pass

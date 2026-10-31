# LocalFlow

Offline voice input for Windows: turns speech into typed text, and (with the wake word)
into actions on the computer.

## Language

### Input modes

**Dictation**:
Speech that ends up as text pasted at the cursor.
_Avoid_: Transcription (that's the internal step), typing

**Hold-to-talk**:
Dictation started by holding the hotkey; pasted, unless no text field has focus, in which case it is handled like a Hands-free turn.
_Avoid_: Push-to-talk, Ctrl mode

**Wake word**:
The spoken phrase ("Hey Jarvis" by default) that starts a hands-free turn.
_Avoid_: Hotword, trigger word, Cortana

**Hands-free turn**:
Everything said after the wake word until a pause; becomes a Command if it matches one, otherwise Dictation. Speech that sounds like a Command but fits no Target is a No match, never Dictation.
_Avoid_: Wake session, ambient dictation

### Commands

**Command**:
A short spoken instruction that LocalFlow carries out instead of pasting ("open Spotify", "pause", "volume 30").
_Avoid_: Action, intent, skill

**Target**:
The thing a Command acts on: an installed app, a folder, a settings page, or the media player.

**Alias**:
A user-chosen spoken name for a Target ("music" means Spotify).
_Avoid_: Nickname, shortcut

**Routine**:
A user-named list of Commands run together by one phrase ("work mode").
_Avoid_: Macro, workflow, scene

**Place**:
A Target that is a location rather than an app: a folder, a settings page, or a website.
_Avoid_: Link, location, shortcut

**Suggested**:
An Alias or Routine LocalFlow proposes from the user's most-used apps, which the user can keep, edit or remove.
_Avoid_: Recommended, default

**Confirmation**:
A yes/no question the Command card asks before a Command that closes several apps at once.
_Avoid_: Prompt, dialog, are-you-sure

**No match**:
The outcome when a Hands-free turn looks like a Command but no Target fits.
_Avoid_: Error, failure

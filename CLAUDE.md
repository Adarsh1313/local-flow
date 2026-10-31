# LocalFlow

Offline, free hold-to-talk dictation for Windows 11 on modest hardware
(Ryzen 5 3550H, GTX 1050 3 GB). Python 3.12, tkinter UI, faster-whisper / onnx-asr.

## Commands (run from localflow/)
- Setup: `setup.bat` (creates .venv, installs requirements.txt)
- Run: `run.bat` (background, tray icon) · `debug.bat` (with console)
- Tests: none yet
- Design showcase preview: launch config `design` in .claude/launch.json (port 8765)

## Folder map
- `localflow/localflow.py` — the whole app (single file, ~3.7k lines)
- `design/` — DESIGN.md, tokens.css, system.html ("Graphite Capsule")
- `docs/specs/` — feature specs · `docs/research/` — research notes
- `docs/user-guide.md`, `docs/screenshots/` — user docs

## Project rules
- Everything stays on the machine: no cloud calls, accounts or telemetry.
  Optional local Ollama only (`localhost:11434`).
- Must stay fast on the hardware above: idle CPU ~0, no animation running while idle.
- Never commit user data files listed in .gitignore (config, history, dictionary, recordings).
- tkinter draws from tokens: mirror any token change in `design/tokens.css` and the
  constants block in localflow.py ("Look and feel" section).
- Search localflow.py with grep for the class/function you need; don't read it whole.

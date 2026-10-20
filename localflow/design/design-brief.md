# LocalFlow — Design Brief

## What this is
A private, offline dictation tool for one person on Windows 11. Mode: **Operate**:
people open settings to change one thing and leave; the pill and hover bar must
stay out of the way. Speed of finding a setting beats visual flair.

## Direction chosen
**1 · Fluent Graphite.** Betting on: it should feel like it belongs in Windows 11
Settings. Neutral graphite surfaces, a left sidebar for the four areas (General,
Microphone, Dictionary, History), settings grouped under plain headings, each row =
title + one-line description on the left, control on the right.

## Voice & tone
- Sentence case everywhere; no all-caps labels.
- Titles say what the setting is ("Remove filler words"), descriptions say what it
  does in under ~8 words ("Drops "um" and "uh"").
- Numbers over adjectives ("adds 1–3 s", not "slightly slower").
- No exclamation marks, no "seamlessly", no "Get started".

## Motion philosophy
Static. Hover and press only change colour. The recording pill is the one place
with motion (waveform, pulsing recording dot), because it carries live state.

## Component conventions
- One primary (accent) button per view at most (e.g. "Add", "Paste" on a card).
- Accent is reserved for: ON switches, the primary button, the selected-nav marker,
  the selected microphone tick. Never for plain text or decoration.
- Groups are single-level: a group never contains another card.
- Row dividers are the window background colour, not lighter lines.
- Every interactive control is reachable with Tab and shows a white focus ring;
  Space/Enter activates.
- Popups (recent transcripts, microphone, scratchpad) use the same surface and
  radius-window; settings is the only large window.

## Explicit anti-references
- "Old Windows" look: grey 3D checkboxes, radio dots, default tk.OptionMenu.
- Default dark-mode purple (the previous #7c8cff accent).
- Letter-spaced all-caps section labels (the previous "DICTATION", "APP").
- Side-tab border as the only selected state: the selected nav item also gets a
  filled background.

## Open questions / extend here
- Light theme: not planned; follow up if Windows is switched to light mode.

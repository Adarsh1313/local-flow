# LocalFlow — Design Brief

## What this is
A private, offline dictation and voice-command tool for one person on Windows 11.
Mode: **Operate**: change one thing and leave; the pill and hover bar stay out of
the way. Finding a setting beats flair, but details should feel used-by-millions.

## Direction chosen
**2 · Graphite Capsule** (Oct 2026). *A quiet, smoky graphite tool where white means
"active" and everything you can touch is a capsule.* References: a smoky-glass kanban,
a glass settings sidebar (lit edges, fading dividers), a capsule side-nav with a white
circle on the selected icon, a dark dashboard (numbers with a thin colour bar).

- **Signature element: the hover bar.** A capsule that grows out of the idle pill;
  a white circle slides under whichever icon you point at and the icon turns dark.
- **Settings:** a darker sidebar where a filled capsule selection slides between
  items; cards with a 1 px lit top edge; stats corner at the
  bottom of the sidebar (big number, small label, thin colour bar).
- **White is the selection colour** (ON switches, selected capsule, primary button).
  The muted ice-blue accent is a supporting signal only.

## Voice & tone
- Sentence case everywhere; no all-caps labels.
- Titles say what the setting is ("Remove filler words"), descriptions say what it
  does in under ~8 words ("Drops "um" and "uh"").
- Numbers over adjectives ("adds 1–3 s", not "slightly slower").
- No exclamation marks, no "seamlessly", no "Get started".

## Motion philosophy
Motion confirms that something happened or shows where something went. It never
decorates. Every animation is short, eases out, can be interrupted midway (it
retargets from where it is, it doesn't restart), and stops completely when idle so
nothing burns CPU during dictation.

| Moment | What moves | Token |
|---|---|---|
| Hover / press on any control | colour fades | `--duration-hover` |
| Switch toggled | knob glides, track fades white | `--duration-move` |
| Nav item chosen | the capsule slides to it | `--duration-move` |
| Hover-bar icon pointed at | the white circle slides under it | `--duration-move` |
| Pill hovered | hover bar grows out of the pill | `--duration-enter` |
| Popup / settings opened | fades in and rises `--rise-distance` | `--duration-enter` |
| "Copy" clicked | label becomes a green check + "Copied", then back | `--duration-confirm` |
| Recording | waveform + pulsing dot (unchanged: live state) | — |
| Command listening | waveform in ice blue, no red dot (live state) | `--color-command` |
| Command thinking (AI fallback only) | one ice-blue dot breathes slowly | `--duration-breathe` |
| Command result | card slides down `--rise-distance` from under the pill + fades in | `--duration-enter` |
| Command card leaves | fades out, rising back toward the pill | `--duration-exit` |
| Confirmation answered | card content cross-fades to the result, size eases | `--duration-move` |
| Settings sub-page opened / back | slides in from the right + fades; back reverses | `--duration-enter` |

When Windows' "Animation effects" is off (Settings › Accessibility › Visual
effects), every duration is 0: things jump to their end state.

Not animated: page content when switching settings tabs (it just swaps, fast),
scrolling, text, anything during dictation except the pill.

## Command mode ("Hey Jarvis")
A new state of the pill, not a new system: same colours, type and radii. It brings
back the "Hey Cortana" feeling: say it, see it happen, no chat window.

1. **Wake word heard:** existing chime; the pill's waveform turns `--color-command`
   (ice blue), no red dot, so it reads as "command". No card yet.
2. **Thinking** (v2 AI fallback only, 1–3 s): one ice-blue dot breathing at
   `--duration-breathe`. Never a spinner.
3. **Result card** below the pill: surface, radius-card, lit top edge, `--shadow-float`
   (it floats). Width `--command-card-min` to `--command-card-max`, fits its text.
   - Left: the app's real icon at `--size-command-icon`; no app → a Segoe Fluent
     glyph on a `--color-control` tile, `--radius-control`.
   - Right: verb in caption, muted ("Opening"); object in display semibold
     `--text-command` ("Spotify", "Downloads", "30%").
4. **No match:** glyph E9CE + "No app called" / heard word ("Spotfy"). Nothing is
   pasted. Text never turns red: a miss isn't an error.
5. **Timing:** card holds `--duration-command-hold` on success,
   `--duration-command-miss` on no match, and stays while the pointer is over it.
6. **Sound:** wake chime, then a soft tick on success and a low tone on no match.

7. **Couldn't open:** like No match, with the warning glyph (E7BA): "Couldn't open" / "Spotify".
8. **Confirmation** (a Command that closes 2+ apps): title "Close 6 apps?", a row of
   app icons at `--size-confirm-icon` (6 max, then a "+N" chip), Cancel + white Close,
   right-aligned. An app with several windows gets a count badge; hovering its icon
   shows a tip listing the window titles (tab, folder or file name; 4 max, "+N more").
   The pill listens (blue wave) for yes/no; no countdown. Silence for
   `--duration-confirm-wait` cancels. The card then swaps in place to "Closed" or
   "Kept open" / "6 apps" and leaves on the normal hold.

Copy rules: verb + object only. "Opening Spotify", never "Sure! Opening Spotify for
you". No ellipses on finished actions.

## Commands settings page
Sidebar item "Commands" (glyph E765). Groups, top to bottom: the "Run commands with
the wake word" switch · Routines · Names · What you can say.
- **Routine row:** name, its step icons at `--size-row-icon`, chevron. Opens a sub-page.
- **Name row:** target icon at `--size-row-icon`, spoken name → target, a muted
  "Suggested" text tag (gone once edited), ✕. "Add name" button under the list.
- **Sub-pages** ("← Wrap up", "← Add a name") replace the page content and slide in
  from the right by `--rise-distance` + fade; back reverses.
  - Routine: name field, step rows (icon, label, ✕; "Close all except" shows its
    keep-open icons), "Add step", "Delete routine" (danger text button) at the bottom.
  - Add a name: search field, segmented Apps / Folders / Website, results with real
    icons (selected = white capsule), "Say it as" field, white Add button.
- **What you can say:** read-only card; each row is a phrase in body text plus a
  muted note ("Open Spotify" · switches if it's running).
- Icons are the real Windows ones (apps, folders, drives, Settings), taken at runtime.

## Component conventions
- One primary (white) button per view at most ("Add", "Paste" on a card).
- White fill is reserved for: ON switches, the selected nav capsule, the hover-bar
  circle, the primary button, the selected segment. Never for decoration.
- Accent (ice blue) is reserved for: input focus edge, the selected mic tick, the
  wake-word listening dot, the first stat bar. Never for text.
- Cards: radius-card, surface fill, 1 px lit top edge that fades out at both ends.
  No drop shadows on cards. Groups are single-level: never a card inside a card.
- Row dividers are 1 px `--color-divider` that fade out toward both ends, inset
  from the card edge.
- Everything interactive that stands alone is a capsule (switch, segmented control,
  nav selection, hover bar, pill). Buttons are radius-control, not capsules, so
  they read as buttons next to capsule toggles.
- Smooth shapes are drawn anti-aliased (rendered images), never tk's jagged polygons.
- Every interactive control is reachable with Tab and shows a white focus ring;
  Space/Enter activates.
- Icons: Segoe Fluent Icons only (one set, native, matches Windows). No emoji.

## Explicit anti-references
- "Old Windows" look: grey 3D checkboxes, radio dots, default tk.OptionMenu.
- Default dark-mode purple, and the neon purple/blue gradients from the glass
  sidebar reference: we keep its edges and dividers, not its colours.
- Glassmorphism by default: real frosted backgrounds are an optional experiment,
  never required for the design to work.
- Letter-spaced all-caps section labels.
- Side-tab border as the selected state: selection is a filled capsule.
- Drop shadows on everything: only the floating pill and hover bar get one.
- Bouncy springs: motion overshoots never; it eases out and lands.
- Siri's rainbow glow or any gradient edge around the screen or pill.
- Cortana branding: no ring logo, no blue circle, no "Cortana" name. The nostalgia
  is in the behaviour, not the look.
- Chatbot replies: no speech bubbles, no "How can I help?", no typing dots.

## Anti-slop watchlist for this direction
- Near-black + one accent is a known default: the guard is that white, not the
  accent, carries selection, and the accent stays rare.
- Don't round everything to the same radius: chips 6, controls 8, cards 12, capsules full.
- Don't animate for its own sake: if a motion isn't in the table above, it needs a reason.

## Open questions / extend here
- Command card above the pill when the pill sits low on screen? Decide when building.
- Success / no-match tones: pick or make two (short, quiet, no melody).
- The General page's "Voice commands" switch ("new line") clashes with Commands:
  rename it, e.g. "Spoken formatting".
- Light theme: not planned. Real acrylic: tested Oct 2026, washes cards out; not used.

The app is tkinter: tokens.css is the source of truth, mirrored in the "Look and
feel" constants of localflow.py. Change both together.

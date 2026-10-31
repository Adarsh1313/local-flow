# LocalFlow — Design Brief

## What this is
A private, offline dictation tool for one person on Windows 11. Mode: **Operate**:
people open settings to change one thing and leave; the pill and hover bar must
stay out of the way. Speed of finding a setting still beats visual flair, but the
details should show care: this should feel like a product used by millions.

## Direction chosen
**2 · Graphite Capsule** (replaces 1 · Fluent Graphite, Oct 2026). Betting on:
*a quiet, smoky graphite tool where white means "active" and everything you can
touch is a capsule.* References the person picked: a smoky-glass kanban (layout,
white primary button), a glass settings sidebar (lit edges, dividers that fade out
at the ends), a capsule side-nav with a white circle on the selected icon (the hover
bar), and a dark leads dashboard (rounded cards, numbers with a thin colour bar).

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

When Windows' "Animation effects" is off (Settings › Accessibility › Visual
effects), every duration is 0: things jump to their end state.

Not animated: page content when switching settings tabs (it just swaps, fast),
scrolling, text, anything during dictation except the pill.

## Command mode ("Hey Jarvis")
A new state of the pill, not a new system: same colours, type and radii. It brings
back the "Hey Cortana" feeling: say it, see it happen, no chat window.

1. **Wake word heard:** existing chime. The pill shows the waveform in
   `--color-command` (ice blue) with no red dot, so it reads as "command", not
   "dictation". No card yet.
2. **Thinking** (only when the local AI fallback runs, 1–3 s): the waveform settles
   into one ice-blue dot breathing at `--duration-breathe`. Never a spinner.
3. **Result card** drops below the pill: `--color-surface`, `--radius-card`, lit top
   edge, `--shadow-float` (the card floats, so it joins the pill and hover bar as the
   only shadowed things). Width fits its text, `--command-card-min` to `--command-card-max`.
   - Left: the app's real icon at `--size-command-icon` (from its shortcut/exe).
     No app (folder, setting, volume, media): a Segoe Fluent glyph centred in a
     `--size-command-icon` square, `--color-control` fill, `--radius-control`.
   - Right, two lines: verb in caption, muted ("Opening", "Paused", "Volume");
     object in display semibold `--text-command` ("Spotify", "Downloads", "30%").
4. **No match:** neutral glyph (E9CE, "unknown") + "No app called" / heard word
   ("Spotfy"). Nothing is pasted. Text never turns red: a miss isn't an error.
5. **Timing:** card holds `--duration-command-hold` on success,
   `--duration-command-miss` on no match, and stays while the pointer is over it.
6. **Sound:** wake chime, then a soft tick on success and a low tone on no match.

Copy rules: verb + object only. "Opening Spotify", never "Sure! Opening Spotify for
you". No ellipses on finished actions.

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
- Command card position when the pill sits near the top of the screen: card above
  instead of below? Decide when building.
- Sounds for success / no match: pick or make the two tones (short, quiet, no melody).
- Light theme: not planned; follow up if Windows is switched to light mode.
- Real acrylic behind popups: tested Oct 2026. The official DWM backdrop works but
  washes out to pale grey, and any colour tk paints over it turns translucent (cards
  lose their colour), so it only suits a window with no cards. Not used.

# Accuracy and polish

Findings: docs/research/accuracy-and-polish.md. Terms: GLOSSARY.md.

## Problem Statement

After daily use of LocalFlow, a handful of rough edges make it feel worse than Wispr Flow:

- **Square corners.** Over full-screen apps the pill and the Command card show a dark
  fringe and look rectangular instead of rounded.
- **"Hey Jarvis" pickup.** I have to strain my voice before it hears the wake word.
- **Spoken lists.** Saying "one … two …" types the word "one" instead of a list. When I
  carry on a list with "then" after a pause, no new point starts.
- **Numbers.** Numbers come out as words, or garbled: "twenty twenty six" becomes "2. 0".
- **The Dictionary.** It doesn't learn the Fixes that matter. Correcting "cloud" to
  "Claude" is silently dropped, several learned Fixes are stored but never applied, and
  I never see whether a Fix was learned.
- **New words.** Terms like ChatGPT and Codex are misheard unless I over-pronounce them.
  I'd also like my own usage to make recognition better over time, ideally by
  fine-tuning later.

## Solution

**Corners**
- The pill, the hover bar and the Command card draw with real transparency, so their
  edges are smooth over any app.

**Wake word**
- "Hey Jarvis" is heard by a dedicated offline wake-word model at normal speaking volume.
- The Microphone page gets a sensitivity setting and a choice of wake-word mic.

**Dictation formatting**
- "one … two …" becomes a numbered list, even without punctuation.
- "then" after a pause adds a point to a list that's already open.
- Numbers become digits the way people write them.

**Dictionary**
- Fixes to names and brands are learned at once. A Rewording is learned the second time.
- A card confirms each Fix ("Added to dictionary: Claude"), or says why it wasn't added.
- Built-in Starter words cover new tech terms, apps and brands, startup terms, Indian
  names and places, and spoken shorthand.

**Later work**
- Saved training recordings now show their size and can be deleted, so a dataset can
  build up for fine-tuning on Colab later.
- A measured spike decides whether hotword boosting is worth adopting.

## User Stories

**Corners**
1. As a user watching a full-screen video, I want the pill to look rounded, so that it looks polished over any app.
2. As a user, I want the Command card's corners and shadow to blend with whatever is behind them, so that no dark box appears around it.
3. As a user, I want the hover bar to look equally smooth, so that all floating surfaces match.
4. As a user on a modest laptop, I want the smoother drawing to cost nothing while idle, so that LocalFlow stays light.

**Wake word**
5. As a user, I want "Hey Jarvis" to be heard at my normal speaking volume, so that I don't have to strain my voice.
6. As a user in a noisy room, I want a sensitivity setting (Low / Normal / High), so that I can trade missed wakes against false wakes.
7. As a user with a headset, I want to choose which mic listens for the wake word, with the laptop mic as the default, so that my Bluetooth headset isn't forced into low-quality call mode.
8. As a user who changed the wake phrase, I want my custom phrase to keep working with the current method, so that customising isn't broken.
9. As a user, I want LocalFlow to keep working if the wake-word model is missing, falling back to the current method, so that one missing file doesn't break the wake word.
10. As a user, I want missed and rejected wake attempts to be logged, so that misses can be diagnosed.

**Spoken lists**
11. As a user, I want "one buy milk two call the bank" to become a numbered list even when the speech model adds no punctuation, so that lists work the way I speak.
12. As a user, I want "I have one question and two concerns" to stay a sentence, so that ordinary counting isn't turned into a list.
13. As a user, I want "then", said after a pause while a list is open, to start a new point, so that I can carry on a list naturally.
14. As a user, I want "then I went home", with no list open, to stay prose, so that storytelling isn't broken up.
15. As a user, I want existing triggers ("first… second…", "bullet point", "point one is…") to keep working, so that nothing I rely on regresses.

**Numbers**
16. As a user, I want "twenty twenty six" to become 2026, so that years read correctly.
17. As a user, I want amounts, percentages and times ("five dollars", "fifty percent", "three thirty") written as $5, 50% and 3:30, so that they read naturally.
18. As a user, I want numbers of 10 and above written as digits, so that "twenty five people" becomes "25 people".
19. As a user, I want one to nine to stay words in prose ("one question"), so that sentences follow normal writing style.
20. As a user, I want numbers never to be mistaken for list markers ("2. 0"), so that converting numbers doesn't garble the text.

**Dictionary**
21. As a user, I want a Fix from "cloud" to "Claude" to be learned straight away, so that "Claude" is spelled right next time.
22. As a user, I want a Fix to any capitalised name or brand to be learned on the first Fix, so that names stick quickly.
23. As a user, I want a Rewording ("Thursday" to "Friday") learned only when I make the same Fix twice, so that changes of mind don't pollute the Dictionary.
24. As a user, I want a small card saying "Added to dictionary: Claude" after a Fix, so that I know it worked.
25. As a user, I want a card saying why a Fix wasn't added ("Not added: looks like a rewording"), so that I understand what happened.
26. As a user, I want my existing switched-off Fixes re-checked against the new rules, so that past corrections such as "patch" to "batch" start working.
27. As a user, I want the Fixes that still aren't applied listed under "Not applied", each with a switch, so that I can turn any of them on myself.
28. As a user, I want my own Dictionary to win over Starter words when both match, so that my choices come first.

**Starter words**
29. As a user, I want built-in Starter words for current tech and AI terms (ChatGPT, Codex, Claude, Cursor…), so that they're spelled right without setup.
30. As a user, I want Starter words for popular apps and brands (WhatsApp, LinkedIn, Zomato…), so that everyday names come out right.
31. As a user, I want Starter words for startup and product terms (ICP, MNC, GTM, PRD, SaaS…), so that work jargon is written correctly.
32. As a user, I want Starter words for common Indian names and places (Bengaluru, Gurugram…), so that they aren't anglicised wrongly.
33. As a user, I want spoken shorthand ("LGTM", "FYI", "e.g.") written in its usual form, so that messages read naturally.
34. As a user, I want each Starter words group to have its own switch on the Dictionary page, so that I can turn off groups I don't want.
35. As a user, I want Starter words kept apart from my own words, so that they don't clutter my list or get changed by learning.

**Training recordings and hotwords**
36. As a user, I want the "Keep recordings for training" switch to show how much space recordings use, so that I can keep an eye on disk use.
37. As a user, I want a "Delete all" button for training recordings, so that I can clear them at any time.
38. As a user, I want each saved recording paired with the final text after my Fixes, so that the dataset is ready for fine-tuning later.
39. As a user, I want hotword boosting adopted only if a measurement shows it helps at a similar speed, so that accuracy work doesn't slow dictation.

## Implementation Decisions

### Rendering
- A pure renderer produces the pill, hover bar and Command card as RGBA images.
- A small Windows adapter shows each image with per-pixel alpha (`UpdateLayeredWindow`)
  in place of the colour-key transparency.
- Rendering happens only while a surface is visible or animating. Idle stays at zero work.
- The look is unchanged: tokens, sizes and motion stay as in design/DESIGN.md.

### Wake word
- A `WakeDetector` has one job: feed it audio frames and it returns whether the wake word
  was heard. It holds no mic and no threads. There are two implementations:
  - the openWakeWord "hey jarvis" model, used when the wake phrase is "Hey Jarvis";
  - the current transcribe-and-fuzzy-match method, used for any other phrase or when the
    model can't be loaded.
- `AmbientListener` keeps the mic and the thread. The sensitivity setting maps to the
  model threshold, and the mic choice lives here too.
- The openWakeWord model is downloaded once at setup and used offline. Its licence is
  non-commercial; this is personal use.
- Rejected wake attempts are logged with what was heard and the score.

### Text processing module
- `postprocess` moves into a pure module, together with list formatting, filler
  removal, number conversion and the swap engine. The module has no tkinter, keyboard
  or audio imports, so tests can use it directly.
- `postprocess` takes:
  - a `Transcript`: a list of parts plus the pause, in seconds, before each part (a bare
    string means no pauses);
  - small `Options` (fillers, lists, numbers, voice commands) instead of the whole config;
  - an ordered list of swap sources: the user's Dictionary first, then Starter words.
- The engine already splits speech into parts at pauses. That join now also returns the
  pause lengths, so no word-level timestamps are needed.
- Order of steps:
  1. fillers
  2. swaps
  3. voice commands
  4. numbers
  5. lists
- List markers must not be confused with converted numbers (the "2. 0" bug).
- Number rules:
  - digits for 10 and above, years, money, percentages and times;
  - one to nine stay words in prose.
  - Use `text2num` (alpha2digit) if it passes the behaviour tests; otherwise write own rules.
- Spoken lists:
  - "one … two …" in sequence makes a list without punctuation, unless the number
    counts a noun ("one question").
  - "then" after a pause of at least 0.6 s adds a point only when a list is already open.

### Dictionary
- `Dictionary` moves into its own pure module.
- `learn` returns an outcome: **Learned**, **Waiting** (a Rewording seen once) or
  **Refused** with a reason.
- A pure `describe(outcome)` gives the card text.
- Learning rules:
  - A Fix whose wanted word is capitalised, or a known brand, is learned at once,
    whatever the word frequency.
  - A Rewording is learned on the second identical Fix. Pending Rewordings are stored
    in the dictionary file.
  - On first load, existing `off` entries are re-checked against these rules. Those
    that still fail stay `off` and show under "Not applied".
- One shared swap function applies both the Dictionary and Starter words.
- The Fix feedback card reuses the Command card (icon, verb and object, about 1.6 s hold).

### Starter words
- Starter words live in a separate module: about 300–400 entries in five groups, each
  with known mishearings.
- The five groups are tech and AI, apps and brands, startup terms, Indian names and
  places, and shorthand.
- Each group has its own setting, all on by default. Learning never changes Starter words.
- The Dictionary page shows Starter words as their own section, with a switch per group.

### Training recordings
- Saving already exists (the `save_training_data` setting writes audio plus final
  corrected text). The saving code moves into a small module.
- The switch shows the total size and gets a "Delete all" action with a confirmation.

### Hotword boosting spike
- Run Parakeet through sherpa-onnx (`nemo_transducer`, int8) with the Dictionary and
  Starter words as hotwords, using `modified_beam_search`.
- Measure accuracy on a few recorded sentences containing those terms, and measure
  speed, against the current onnx-asr greedy decoding.
- Adopt it only if accuracy clearly improves at a similar speed. Record the result in
  the research note either way.
- Risk: hotwords may not apply to TDT models. If so, record that and drop it.

### Design
- New UI covers:
  - the sensitivity control and wake-word mic picker;
  - "Not applied" and the Starter words groups;
  - the training-recordings size and "Delete all";
  - the Fix card states.
- These follow design/DESIGN.md patterns. Any new token is mirrored in tokens.css and
  the "Look and feel" constants.

## Testing Decisions

- Test external behaviour through the seam, never internals. For example, check
  `learn` followed by `apply`, not the shape of `entries`.
- **Text processing** (pure, plain pytest): `postprocess` with a `Transcript` or string
  plus `Options`. Cases:
  - "one buy milk two call the bank" becomes a list;
  - "one question and two concerns" stays prose;
  - "three apples" is not a list;
  - 2026, $5, 50% and 3:30 come out as digits;
  - numbers and lists together do not produce "2. 0";
  - "then" after a pause continues an open list, and stays prose otherwise;
  - existing list triggers still work;
  - a Starter words group switch changes the output ("chat gpt" becomes "ChatGPT");
  - the Dictionary wins over Starter words.
- **Dictionary** (pure, temporary file): `learn` then `apply`, plus `describe` text. Cases:
  - "cloud" to "Claude" applies at once;
  - "Thursday" to "Friday" is Waiting, then Learned on the second Fix;
  - old `off` entries are re-checked on load;
  - a Refused outcome has a reason.
- **Wake detector**: pure tests for the fuzzy fallback (`wake_score`). An opt-in
  `-m windows` test feeds a few recorded WAV clips (normal, soft and non-wake speech)
  to the openWakeWord detector and reports scores against the threshold.
- **Rendering**: the pure renderer's pill and card images have fully transparent corner
  pixels. The layered-window call is checked by eye only.
- **Training recordings**: on a temporary folder, a saved clip and its final text land
  together, the size is reported, and "Delete all" empties the folder.
- **Prior art**: tests/test_commands.py (pure behaviour tests), tests/test_focus.py
  (pure rule), tests/test_winactions.py (opt-in desktop tests).

## Out of Scope

- Fine-tuning Parakeet itself. Planned for later on Google Colab with the saved
  recordings.
- Training a custom wake-word model for phrases other than "Hey Jarvis".
- Word-level timestamps, and pauses inside a single part.
- An automatically refreshed Starter words list from online sources. It's curated by hand.
- Moving the remaining UI code out of localflow.py, beyond the modules above.

## Further Notes

- Everything stays offline. The openWakeWord model and any sherpa-onnx model are
  downloaded once at setup.
- Idle CPU must stay near zero. The wake detector runs on the existing mic stream, and
  rendering stops when nothing is visible.
- Update README and docs/user-guide.md for the wake sensitivity, Starter words and
  training recordings.

## Progress

- [x] 1. Move `postprocess` and list formatting into a pure text module with `Options`; tests pin current behaviour
- [x] 2. Numbers to digits (before lists, no "2. 0")
- [x] 3. Spoken lists without punctuation, and "then" after a pause, via `Transcript` pauses
- [x] 4. Move `Dictionary` into a pure module with learn outcomes and the new rules; re-check `off` entries
- [x] 5. Fix feedback card, and "Not applied" on the Dictionary page
- [x] 6. Starter words module, five groups, group switches on the Dictionary page
- [ ] 7. Real-transparency rendering for the pill, hover bar and Command card
- [ ] 8. `WakeDetector` with openWakeWord "hey jarvis", fallback, sensitivity and wake-word mic picker
- [ ] 9. Training recordings: size display, "Delete all", clips module and test
- [ ] 10. Hotword boosting spike with sherpa-onnx; record the result
- [ ] 11. README and user guide updates

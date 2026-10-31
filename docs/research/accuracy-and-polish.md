# Accuracy and polish: findings (2026-10-31)

Starting point for the next feature. Brain dump: pill corners, "Hey Jarvis" pickup,
spoken lists, numbers, the dictionary, fine-tuning on my voice, public word lists.

## What the code does today, and why each issue happens

### 1. Pill and card corners look square over full-screen apps
- The pill and command card are tk windows with a colour key (`KEY = #010203`).
  Only pixels of exactly that colour become see-through.
- Shapes are antialiased RGBA images, but tk blends their soft edges (and the soft
  shadow) against the near-black key. Those blended pixels stay visible.
- Over the dark taskbar you can't see them. Over a bright full-screen app you see a
  dark fringe/halo around the capsule, which reads as a rectangle.
- Fix: draw the pill and card as one RGBA image per frame and show it with
  `UpdateLayeredWindow` (real per-pixel alpha). Edges then blend with whatever is
  behind. Costs a PIL render per frame while visible; zero when idle.

### 2. "Hey Jarvis" needs a strained voice
`AmbientListener` (localflow.py ~line 366):
- A burst only counts as speech when it is louder than 3x the learned room noise
  (minimum 0.006 RMS). Normal or soft speech can fail to open a burst at all.
- It always listens on the laptop's built-in mic, even if a headset is in use.
- Every burst of 0.35 to 3 s is fully transcribed by Parakeet, then fuzzy-matched.
  It works, but it is heavy and only as good as the energy gate in front of it.
- Rejected attempts aren't logged, so misses can't be diagnosed yet.
- Better: openWakeWord ships a pretrained, offline **"hey_jarvis"** model
  (Apache-2.0, ~1 MB, a few % of one CPU core). It scores every 80 ms frame,
  so there is no loudness gate and no full transcription per burst. Keep the
  Parakeet check as an optional second opinion to cut false wakes.

### 3. Spoken lists
`format_lists` (~line 785):
- A bare "one"/"two" only counts right after `. ! ? : ; ,`. Parakeet often writes
  "one buy milk two call the bank" with no comma, so nothing matches and you get
  the word "one".
- "then" lists need a "first" to start and three steps. "Then" after a pause, with
  no "first", never starts a new point.
- Wanted: "one … two …" without punctuation, plus "then" + pause continuing an
  existing list. Parakeet gives word timestamps, which can reveal pauses.

### 4. Numbers come out as words ("twenty twenty six")
- There is no inverse text normalisation (words to digits) step at all.
- "2. 0" looks like the list formatter catching a digit followed by a full stop.
- Fix: run an offline words-to-digits pass before list formatting
  (`text2num`'s `alpha2digit`, pip wheel, English, no cloud). Years, money,
  percentages and times. Keep "one" as a word inside normal sentences
  ("one question").

### 5. Dictionary doesn't learn the fixes that matter
`Dictionary.learn` (~line 1020) refuses any fix where **both** words are everyday
words, treating it as a change of mind:
- "cloud" (zipf 4.46) to "Claude" (3.76): both count as everyday, so it is
  **silently dropped**. This is the Claude problem.
- Many learned fixes are stored as `off` and never applied: patch to batch,
  body to Boardy, MC to MNC, man to manan, Backing to backend, New to Neu.
- There's no feedback when a fix is learned or refused, so it feels broken.
- Parakeet takes no hints. The dictionary only rewrites text after recognition.
  The `vocabulary` setting reaches Whisper only.

Fix ideas:
- Treat proper nouns and brand names (capitalised, or known product names) as
  rare, whatever their word frequency.
- Learn on the second identical correction, even between common words.
- Show "Added to dictionary" / "Not added: looks like a rewording" on the card.
- Move `off` entries to "needs review", with one tap to turn them on.

## Fine-tuning Parakeet on my voice

**How it works:**
1. Collect pairs of (audio clip, correct text). LocalFlow keeps only
   `last_recording.wav`, so it would first need an opt-in clip archive. Each
   dictation's audio would be saved next to its final, corrected text.
2. Train with NVIDIA NeMo, starting from `nvidia/parakeet-tdt-0.6b-v2`. Use
   adapters (LoRA-style, a few MB) rather than retraining all 600 M weights, so
   it can't forget general English.
3. Export to ONNX int8 and load it in place of the stock model.

**Benefit:**
- Speaker adaptation typically cuts errors 10 to 30% relative for accents and
  personal vocabulary, given 1 to 5 hours of your corrected audio. Less data
  helps less and risks overfitting.
- It is the only way the model itself learns how *you* say "Claude".

**Limits:**
- Training needs about 8 to 16 GB of GPU memory. The GTX 1050 (3 GB) can't do it.
- Training in the cloud (Colab/Kaggle) means uploading your voice, which breaks
  the "everything stays on the machine" rule. That's your call.
- It's a weekend project with real risk of a worse model. It isn't a quick win.

**Do this first** (most of the gain, no training):
- **Hotword boosting.** sherpa-onnx runs the same Parakeet model and accepts a
  hotword list, so the decoder favours "Claude", "Codex" and "ChatGPT" while it
  listens instead of being fixed afterwards. Feed it the dictionary plus a
  starter list. To verify: hotwords support for TDT models in sherpa-onnx.
- The dictionary fixes above.
- Then, if still needed, the opt-in clip archive. It builds the fine-tuning
  dataset for free while you use the app.

## Public lists of new words

- Wispr Flow's list isn't public. It relies on cloud models plus your personal
  dictionary.
- No maintained open "new tech words for speech" list exists. Useful sources:
  - Hugging Face model and org names
  - GitHub trending repo names
  - Wikidata software and product entities
- Practical approach: ship a curated **starter list** of about 200 terms with
  their usual mishearings (ChatGPT, Codex, Claude, Gemini, Copilot, Cursor,
  Antigravity, Ollama, Vercel, Supabase…). Use it for hotword boosting and the
  dictionary, and refresh it by hand now and then.
- To teach the model pronunciations: synthesize sentences containing those terms
  with a local TTS (Piper or Kokoro) and add them to the fine-tuning data.
  Synthetic text-to-audio adaptation is an established technique, and it all
  stays offline.

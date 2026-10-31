# Architectural Specification: Clause-Locked Acoustic-Valley Subtitle Synchronization & BGM Git Tracking Fix

## 1. Forensic Audit of Live Short `tKTHruFRWsw` (`run-41158662000`, "Iron Age Snail")

### 1.1 Root Cause of Missing Background Music in GitHub Actions
- **Symptom:** Live Short `https://www.youtube.com/shorts/tKTHruFRWsw` played voiceover-only without background music, despite `run_history.json` logging `"music_track": "dark_space_abyss.mp3"`.
- **Root Cause:**
  1. `.gitignore` line 15 contained a blanket `*.mp3` ignore rule. Consequently, the 15 modern `.mp3` tracks downloaded locally into `music/space/`, `music/tech/`, and `music/history/` were never tracked in Git (only 2 older tracks in `music/history/` and 3 broken `.webm`/`.webm.part` files existed on `origin/main`).
  2. When GitHub Actions Run #264 executed for `"Deep Sea & Prehistoric Survivors"` (`music_subfolder: "space"`), `Path("music/space")` existed (due to `temp_dark_neoclassical_cello.webm.part`), `list(target_dir.glob("*.mp3"))` returned `[]`, and the fallback `list(music_dir.glob("*.mp3"))` only searched the top-level `music/` folder rather than `music_dir.rglob("*.mp3")`.
  3. `LAST_SELECTED_MUSIC_TRACK` remained at its hardcoded default `"dark_space_abyss.mp3"` from module initialization.

### 1.2 Root Causes of Mid-Video Subtitle Desynchronization & Visual Artifacts
Frame-by-frame (`30 fps`) and acoustic waveform inspection of `tKTHruFRWsw` (`32.798s` duration) identified four compounding bugs:

1. **Monolithic Linear Token Division Drift (+1.0s to +2.40s Lag in Middle of Video):**
   - `kokoro-onnx` (`Kokoro.create()`) does not emit word-boundary timestamps. Previous 3.8 model's `calculate_kokoro_native_phoneme_timestamps()` synthesized the entire 97-word paragraph in one monolithic `kokoro.create(clean_text)` call and divided `total_duration / total_tokens` linearly across all words.
   - Inside `kokoro_onnx`, `Kokoro._split_phonemes()` split the 692-phoneme script into Batch 0 (`498` tokens, `0.00s–24.61s`) and Batch 1 (`193` tokens, `24.61s–32.77s`). Because `Kokoro._create_audio()` selects its style vector via `voice = voice[len(tokens)]`, Batch 0 spoke ~25% faster per phoneme than Batch 1, and rapid number runs (`"two thousand four hundred to two thousand nine hundred meters down"`) plus unstressed function words (`to`, `in`, `the`, `of`) were spoken much faster than isolated citation-form phoneme token counts predicted.
   - Resulting measured lag between actual audio pauses in `temp_inspect_audio.wav` and rendered ASS subtitles:
     - `"into its skeleton,"`: audio ends at `7.73s` vs. subtitle `8.22s–9.22s` (**+1.00s late**).
     - `"armored foot sclerites."`: audio ends at `10.95s` vs. subtitle `11.27s–12.01s` (**+1.06s late**).
     - `"down in the Indian Ocean,"`: audio ends at `16.14s` vs. subtitle `17.86s–18.81s` (**+2.40s late**).
     - `"Earth's primordial past."`: audio ends at `19.09s` vs. subtitle `20.12s–21.02s` (**+1.93s late**).
     - `"feeding this living relic."`: audio ends at `24.61s` vs. subtitle `25.23s–26.24s` (**+1.26s late**).
2. **Punctuation Stripping Causing Cross-Sentence Phrase Merging:**
   - `calculate_kokoro_native_phoneme_timestamps()` stripped trailing punctuation (`word.upper()` without `punct`).
   - Consequently, `generate_ass_file()`'s boundary check `w_clean.endswith(('.', '?', '!', ',', ';', ':', '—', '–'))` never triggered, merging words across sentence and clause pauses (`OUR OCEANS MEET`, `SKELETON BOTH IN`, `INDIAN OCEAN ITS`, `LIVING RELIC ITS`, `BIZARRE ITS`).
   - `sanitize_script_for_tts()` also stripped curly apostrophes (`\u2019`), turning `"It’s"` into `"ITS"`.
3. **29-Character Single-Line Compound Overflow (`SYMBIOTIC GAMMAPROTEOBACTERIA`):**
   - `generate_ass_file()` required `len(current_chunk) >= 2` before enforcing `current_chars + len(w_clean) > 18`, allowing 1-word `SYMBIOTIC` (9 chars) + `GAMMAPROTEOBACTERIA` (20 chars) to merge into a 29-character single-line caption frozen for `1.90s`.
4. **MoviePy EOF Black Transition Frames (`t=23.400s–23.600s`):**
   - 7 frames (`0.233s`) at the end of B-roll clip #6 rendered with a pitch-black background (`mean=2.9`) behind `SYMBIOTIC GAMMAPROTEOBACTERIA` because MoviePy's `FFMPEG_VideoReader` returns a zeroed black numpy array (`mean < 3.5, std < 2.0`) rather than `None` when an MP4 container's header duration slightly exceeds its last decodable packet.

---

## 2. Technical Architecture of the Fix

### 2.1 Clause-Locked Kokoro Synthesis + Acoustic RMS Valley Alignment (`main.py`)
- Split `clean_text` into punctuation-delimited clauses (`re.findall(r'[^.,!?;:—–]+[.,!?;:—–]*', clean_text)`).
- Synthesize each clause individually with `kokoro.create(clause, voice=voice_name, speed=1.10, lang="en-us", trim=True)`:
  - Every clause start and end timestamp is **mathematically locked to the exact sample count** (`cursor_samples / sample_rate`), reducing cumulative inter-clause drift across the entire video to **`0.000s`**.
  - Insert deterministic natural acoustic pauses between clauses (`0.24s` after `. ! ?` and `0.12s` after `, ; : — –`).
- Inside each clause's clean waveform `c_samples`:
  - Weight each word using Kokoro phoneme token count with **Klatt's polysyllabic shortening exponent** (`token_count ** 0.78`) and **connected-speech function-word reduction** (`0.62x` for unstressed function words).
  - Snap internal word boundaries to the nearest **local minimum (acoustic valley)** in `c_samples`'s 5ms RMS amplitude envelope within a `±65ms` search window.
  - Preserve trailing clause/sentence punctuation on the final word of each clause (`f"{w}{p}".upper()`) so `generate_ass_file()` respects every punctuation boundary.

### 2.2 Clause-Aware Balanced Phrase Chunking (`generate_ass_file` in `main.py`)
- Group `subs_list` words into clauses bounded by trailing punctuation `(.,!?;:—–)` so words from two different clauses or sentences are **never** merged into the same subtitle cue.
- Enforce `current_chars + len(w_disp) > 18` even when `len(current_chunk) == 1` so long scientific terms (`GAMMAPROTEOBACTERIA`, `OESOPHAGEAL`, `THREE-LAYERED`) never combine into >18-char lines.
- Rebalance trailing 1-word orphans (`<= 10` chars) at the end of a clause (`[3 words] + [1 word] -> [2 words] + [2 words]`).
- Scale ultra-long individual words (`>= 16` chars) to `{\fscx85\fscy85}` in `format_styled_word()` and upgrade `Default` style outline/shadow (`Outline=4.5, Shadow=2.0`) for crisp legibility over bright backgrounds.

### 2.3 MoviePy EOF Black-Frame Guard & BGM Repository Tracking
- In `assemble_video()`, trim `0.15s` off raw B-roll container durations before looping/slicing and guard `create_zoom_filter` against near-zero EOF black frames (`mean < 3.5 and std < 2.0`) by falling back to `last_valid_frame[0]`.
- Add `!music/**/*.mp3` to `.gitignore`, remove leftover `.webm`/`.part` files, trim oversized `.mp3` tracks (`> 8 MB`) to compact 90-second 192kbps loops, and use `music_dir.rglob("*.mp3")` as the fallback in `assemble_video()`.

# Walkthrough: Subtitle Alignment, Strict TTS Speed Preservation & Visual Filtering

## Overview
This walkthrough documents the implementation of two essential synchronization and visual quality rules in `main.py` to ensure 100% natural neural voiceover pacing, exact word-boundary ASS subtitle alignment, strict audio container duration anchoring, and zero corporate/office stock footage in historical or space Shorts clips.

---

## Key Changes Implemented

### 1. Task 1: Subtitle Alignment & Strict TTS Speed Preservation (No Audio Stretching)
- **Natural Speed Preservation:** Set Kokoro TTS synthesis `speed=1.0` in `synthesize_kokoro_audio_and_timestamps()`, prohibiting any time-stretching or dynamic slowing at the tail end of voiceover generation.
- **Phoneme Token Subtitle Alignment:** Bound ASS word-level subtitle display durations directly to Kokoro's native phoneme token allocation boundaries (`calculate_kokoro_native_phoneme_timestamps()`).
- **Audio-Anchored Container Duration:** Strictly anchored the final video container duration to `audio_duration` in `assemble_video()` (`bg_clip = bg_clip.set_duration(audio_duration)`), guaranteeing that audio drives video length.

### 2. Task 2: Visual Context Filtering (Ban Modern Corporate / Office Clips)
- **Prompt Directive Updated:** Updated Directive 4 in `generate_content()` for YouTube Shorts to explicitly ban modern corporate and office environments (`office`, `corporate`, `meeting`, `voting`, `ballot`, `business suit`, `conference room`, `boardroom`, `cubicle`) for historical and space categories.
- **Sanitizer Query Rewrites:** Updated `sanitize_search_query()` to automatically translate corporate/office terms into atmospheric outdoor or cinematic historical equivalents (`vintage map`, `old archive room`, `foggy coastline`, `historical document`, `ancient ruins`, `strategy table`).
- **Abstract/Corporate Word Filter:** Added corporate terms to the strict exclusion list in `sanitize_search_query()`.

---

## Verification & Definition of Done (DoD) Results

### 1. Python Syntax Compilation Check
Command:
```powershell
python -m py_compile main.py bot_agent.py self_heal.py test_pipeline.py
```
Output:
```text
The command completed successfully with exit code 0.
```

### 2. Unit Test Suite Execution
Command:
```powershell
python -m unittest test_pipeline.py
```
Output:
```text
.....
----------------------------------------------------------------------
Ran 5 tests in 1.916s

OK
```

### 3. Git Commit Details
- **Commit Hash:** `d40583ac528537acb183bca1d4460a4a67450fef`
- **Commit Message:** `feat(sync): preserve 100% natural TTS speed, bind word timestamps, anchor video container duration, and filter corporate B-roll`
- **Branch:** `main` (synced to remote `origin/main`).

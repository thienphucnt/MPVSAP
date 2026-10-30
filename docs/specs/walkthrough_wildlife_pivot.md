# MPVSAP 3.0 "WildApex Shorts" (Extreme Wildlife & Bizarre Biology) — Refactoring & Channel Clean-Slate Walkthrough

**Date:** 2026-10-30  
**Architecture Spec:** [`docs/specs/audit_wildlife_pivot.md`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/docs/specs/audit_wildlife_pivot.md)  
**Target Brand Identity:** `WildApex Shorts` (`@WildApexShorts`) — YouTube Category ID `15` (`Pets & Animals`)

---

## 1. Summary of Architectural Changes Implemented

### Task 1: Single-Niche Wildlife & Bizarre Biology Taxonomy (`main.py`)
- Replaced the fragmented 3-way `CATEGORIES` dictionary (`Space`, `History`, `Tech` under Category ID `28`) with 4 sub-pillars under a single **Extreme Wildlife & Bizarre Biology** umbrella, all unified under **YouTube Category ID `15` (`Pets & Animals`)**:
  1. `Bizarre Biological Superpowers` (`db_key: "superpowers"`)
  2. `Apex Predators & Deadly Matchups` (`db_key: "predators"`)
  3. `Mind-Control Parasites & Venom` (`db_key: "parasites"`)
  4. `Deep Sea & Prehistoric Survivors` (`db_key: "deep_sea"`)
- Added `LEGACY_CATEGORY_ALIASES`, `resolve_category_name()`, and `get_category_info()` so legacy CLI arguments (`--category space|history|tech`) and unit tests continue to resolve seamlessly.
- Replaced the 7-day cross-genre lock in `get_rotating_category()` with a daily rotating sub-pillar schedule across the 4 Wildlife pillars.
- Updated `CATEGORY_ANGLE_POOLS`, `is_power_word()`, `_TRENDING_KEYWORDS`, and `sanitize_metadata()` with wildlife-specific terminology and hashtags (`#shorts`, `#wildlife`, `#animals`, `#nature`).

### Task 2: Curated Species Seed Bank & Anti-Hallucination Guardrails (`main.py`)
- Added `_CURATED_SPECIES_SEED_BANK` containing 128 verified real-world species and biological phenomena across all 4 sub-pillars (`Peacock mantis shrimp`, `Pistol shrimp`, `Tardigrade`, `Immortal jellyfish`, `Ophiocordyceps unilateralis`, `Emerald cockroach wasp`, `Honey badger`, `Orca`, `Saltwater crocodile`, `Goblin shark`, `Giant squid`, `Barreleye`, etc.).
- Refactored `fetch_wikipedia_source_text()` and `fetch_playwright_scraped_source_text()` to select unused species from `_CURATED_SPECIES_SEED_BANK` first (fetching exact species extracts via `prop=extracts&explaintext=True&redirects=1`), with secondary fallback to Wikipedia biological categories (`Category:Venomous_animals`, `Category:Parasites`, `Category:Deep_sea_fish`, `Category:Predators`, `Category:Extremophiles`).
- Added Criterion #6 (`6. Factual Scientific Accuracy & Clean Opening Grammar`) to `evaluate_tournament_variants()` to penalize hallucinated sci-fi fiction or broken lowercase opening fragments.

### Task 3: 32–38s Pacing, 4-Beat Casual Geographic Arc & Opening Grammar Sanitizer (`main.py`)
- Updated the Shorts generation prompt in `generate_content()` to target **80 to 95 words** (`~30 to 35 seconds` at `speed=1.08`) using the **4-Beat Casual Geographic / Zack D. Films Structure**:
  1. **Beat 1 (0–3s):** Visceral Biological Shock Hook.
  2. **Beat 2 (3–15s):** The Anatomical Mechanism.
  3. **Beat 3 (15–30s):** The Visceral Payoff / Matchup Outcome.
  4. **Beat 4 (30–35s):** Seamless Loop Bridge.
- Added `sanitize_script_opening()` to strip leading punctuation, ellipses, or lowercase relative conjunctions (`"that "`, `"which "`, `"and "`) and capitalize the first alphabetical character of Sentence 1.
- Filtered few-shot script injection in `generate_content()` strictly to the 4 Wildlife Biology pillars so the 100 legacy Space/History/Tech runs in `run_history.json` do not contaminate new prompts.

### Task 4: Visual Pacing, Safe-Zone Typography, Unified Narrator & Compliance (`main.py`)
- **Clip Density:** Increased `VideoFormatConfig("short").clip_count` from `6` to `8` clips (`~3.8s–4.5s` per visual cut).
- **Safe-Zone Typography & Phrase Chunking:**
  - Updated `VideoFormatConfig("short")` to `sub_fontsize = 74` and `sub_position = ('center', 1120)` (`MarginV = 800`, upper-middle safe zone clear of YouTube's bottom metadata overlay).
  - Updated `generate_ass_file()` to group Shorts captions into **2-to-3 word high-impact phrase chunks** instead of single-word strobe flashing, while positioning `@WildApexShorts` at `y = 1651` (`MarginV = 268`) and the final 3.5s CTA banner at `y = 1459` (`int(1920 * 0.76)`).
- **Unified Narrator Identity:** Standardized Kokoro-82M ONNX voice synthesis onto `"am_fenrir"` at `speed=1.08` across all categories.
- **Altered Content Flag Fix:** Set `"containsSyntheticMedia": False` in `upload_to_youtube()` (real stock wildlife footage + standard TTS voiceover does not require YouTube's synthetic/altered media penalty label).

### Task 5 & 6: Live Analytics Feedback Loop, Legacy Channel Privatization & Twice-Daily Cron
- **Live YouTube Statistics Sync (`maintenance_sync.py`):** Added `sync_youtube_video_statistics()` to batch-query `youtube.videos().list(part="statistics,status")` (50 video IDs per request) and update `entry["youtube_stats"]` (`views`, `likes`, `comments`) in `dashboard/app/data/run_history.json`.
- **Hybrid View + QA Few-Shot Scoring (`main.py`):** Added top-level `get_run_score(item)` that prioritizes `float(views) * 100.0 + qa_score` when `views > 0` and falls back to `winning_script["score"]` when `views == 0` or `None`.
- **Channel Clean-Slate Sanitization (`scripts/privatize_low_view_legacy.py`):** Created and executed `scripts/privatize_low_view_legacy.py --all`, syncing live view statistics for 89 historical entries into `run_history.json` and privatizing **201 of 213** legacy uploaded videos (exhausting the daily 10,000-unit YouTube Data API v3 quota; the remaining 12 oldest videos can be privatized with a single run after daily quota reset at 07:00 UTC). Reset `past_topics.json` to `[]`.
- **Twice-Daily Upload Schedule (`.github/workflows/main.yml`):** Updated `schedule.cron` to `'0 16 * * *'` (12:00 PM EST) and `'0 23 * * *'` (7:00 PM EST).

---

## 2. Verification & Definition of Done (DoD) Terminal Outputs

### 2.1 Syntax Compilation (`py_compile`) & Unit Test Suite (`test_pipeline.py`)
```text
$ python -m py_compile main.py bot_agent.py self_heal.py maintenance_sync.py test_pipeline.py scripts/privatize_low_view_legacy.py
PY_COMPILE_SUCCESS

$ python -m unittest test_pipeline.py
......
----------------------------------------------------------------------
Ran 6 tests in 10.983s

OK

=== STARTING CHUNKED LONG-FORM RENDERING (2 SEGMENTS) ===
SUCCESS: Test 2 Passed: test_ffmpeg_concat_logic successfully verified segments.txt formatting and FFmpeg stream copy command.
Trimmed trailing silence: reduced audio duration by 0.450s (padding: 50.0ms).
SUCCESS: Test 5 Passed: test_seamless_looping_logic successfully verified TTS silence trimming and 30fps frame quantization.
SUCCESS: Test 3 Passed: test_top_level_comment_posting correctly inserted topLevelComment via YouTube Data API.
SUCCESS: Test 4 Passed: test_tournament_head_to_head_judging correctly evaluated variants side-by-side and cleaned prefixes.
Fetching raw Wikipedia biological source text for category 'Bizarre Biological Superpowers'...
Successfully ingested curated Wikipedia species: 'Peacock mantis shrimp' (94 words)
Generating ASS subtitles & watermark file: C:\Users\Admin\AppData\Local\Temp\test_wildapex_38144.ass...
ASS file written successfully.
SUCCESS: Test 6 Passed: test_wildlife_species_ingestion_and_few_shot_scoring verified WildApex 3.0 architecture.
SUCCESS: Test 1 Passed: test_youtube_preflight_fail correctly caught invalid_grant and raised AuthError.
```

### 2.2 Legacy Channel Privatization Execution (`scripts/privatize_low_view_legacy.py --all`)
```text
Connected to YouTube Channel: 'NicheFactsShorts' (Uploads Playlist: UUnqrNnMWE_4RYsqKPHgqaVA)
Found 213 total videos in channel uploads playlist.
Synced live YouTube statistics into dashboard\app\data\run_history.json (89 total entries updated across Pass 1 & Pass 2).

Pass 1 Privatized: 106 / 213 videos
Pass 2 Privatized:  95 / 107 remaining videos (201 / 213 total videos now PRIVATE; final 12 hit daily 10,000-unit YouTube API quota limit)
Execution Complete: {"total_inspected": 213, "already_private": 106, "candidates": 107, "privatized": 95, "failed": 12}
```

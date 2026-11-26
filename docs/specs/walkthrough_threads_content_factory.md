# Walkthrough: `@libknowsai` AI Content Factory 3-Phase Upgrade

## 1. Summary of Changes Implemented

Following the audit in [`docs/specs/audit_threads_content_factory_plan.md`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/docs/specs/audit_threads_content_factory_plan.md), all 3 phases have been implemented across [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py), [`maintenance_sync.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py), [`logger.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/logger.py), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml), and [`test_pipeline.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/test_pipeline.py):

### Phase 1: Research, Comment Mining & Visual Fallback Hardening
* **Multi-Source Scientific Fact Synthesis (`LearningCircuit/local-deep-research` adaptation):**
  * Added [`prioritize_biological_extract_sections()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L836-L876) to preserve the lead species overview while prioritizing high-density anatomical, venom, bite-force, and predatory sentences when Wikipedia articles exceed 1,200 words.
  * Added [`fetch_europepmc_scientific_facts()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L879-L911) to query the zero-auth Europe PMC REST API in parallel for peer-reviewed zoological abstracts and append quantitative scientific extracts to [`fetch_wikipedia_source_text()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L914-L970).
* **Viewer Comment Mining & Outlier Multiplier (`ScrapeCreators/social-media-research-skills` adaptation):**
  * Added [`mine_youtube_viewer_comments()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py#L61-L115) in [`maintenance_sync.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py) to harvest high-signal viewer questions (`?`) and species/matchup requests into `dashboard/app/data/viewer_signals.json`, injected into [`generate_content()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1436-L1449).
  * Upgraded [`sync_youtube_video_statistics()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py#L118-L216) and [`get_run_score()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1094-L1109) to compute and weight each video's channel `outlier_multiplier` (`views / median_views`).
* **5-Result Wikimedia Loop, Wikipedia `pageimages` Priority & Species Thumbnail (`FLUX.2` adaptation):**
  * Fixed [`search_wikimedia_image()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2236-L2329) so it iterates across all 5 Wikimedia Commons search results in relevance order (instead of aborting when `results[0]` is an `.svg`/`.tif`) and falls back to Wikipedia's `prop=pageimages&piprop=original` lead species photograph.
  * Upgraded [`generate_thumbnail()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3492-L3615) to query the winning species/topic (with Wikimedia fallback) and render category badges using [`get_theme_colors()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L328-L336).

### Phase 2: Saliency Video Cropping, Kinetic Subtitles, Mood BGM & Dual-Voice Option
* **OpenCV Saliency-Tracked Aspect-Preserving Crop (`Anil-matcha/AI-Youtube-Shorts-Generator` adaptation):**
  * Added [`find_video_salience_center()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2919-L2959) and [`prepare_aspect_cropped_clip()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2962-L2996) using OpenCV Sobel gradient energy to crop non-matching aspect ratios around the animal focal center `(cx, cy)` without stretching, and track `(cx, cy)` smoothly inside [`create_zoom_filter()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3076-L3133).
* **Kinetic Pop-In ASS Subtitles (`YILS-LIN/short-video-factory` adaptation):**
  * Added the 75ms pop-in transform tag `{\fscx114\fscy114\t(0,75,\fscx100\fscy100)}` to Short phrase cues in [`generate_ass_file()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2850-L2852).
* **Acoustic Mood-Matched BGM Selection (`ACE-Step 1.5` adaptation):**
  * Added [`select_mood_matched_music()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2999-L3036) to match script intensity/keywords (`combat`, `abyss`, `thriller`) to the corresponding `.mp3` tracks in `music/`.
* **Dual-Voice Contrast Hook (`Podcastfy` adaptation) & `long_form.yml` Cache Sync:**
  * Updated [`synthesize_kokoro_audio_and_timestamps()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2037-L2120) and [`generate_audio_and_subtitles()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2144-L2182) with `--voice-mode {solo,duo}` support (`af_heart` hook + `am_fenrir` breakdown with `0.000s` clause-locked sample drift).
  * Synced the Kokoro ONNX cache key (`kokoro-onnx-v1.0-v4`) and pre-download step in [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L52-L67).

### Phase 3: Multi-Language YouTube Localization & Social Distribution Bundle
* **Multi-Language YouTube Metadata Localization (`krillinai/OpenCreator` adaptation):**
  * Added [`generate_youtube_localizations()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3879-L3923) and integrated it into [`upload_to_youtube()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3956-L3999) to translate titles and descriptions into 7 global languages (`es`, `pt`, `hi`, `de`, `fr`, `ja`, `ko`) via YouTube Data API `localizations`.
* **Social Distribution Bundle (`langchain-ai/social-media-agent` adaptation):**
  * Added [`generate_social_distribution_posts()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3926-L3953) and persisted companion X, Threads, and YouTube Community Poll payloads via [`log_pipeline_run()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/logger.py#L28-L92).

---

## 2. Raw Terminal Verification Output (`py_compile` & `unittest`)

```text
> python -m py_compile main.py maintenance_sync.py logger.py test_pipeline.py; if ($?) { python -m unittest -v test_pipeline.py }

test_ffmpeg_concat_logic (test_pipeline.TestPipeline.test_ffmpeg_concat_logic)
Test 2: Verify long-form chunked rendering generates a properly formatted segments.txt ... ok
test_seamless_looping_logic (test_pipeline.TestPipeline.test_seamless_looping_logic)
Test 5: Verify seamless looping utilities: ... ok
test_threads_content_factory_enhancements (test_pipeline.TestPipeline.test_threads_content_factory_enhancements)
Test 7: Verify all 3 Phases of the @libknowsai AI Content Factory Upgrade: ... ok
test_top_level_comment_posting (test_pipeline.TestPipeline.test_top_level_comment_posting)
Test 3: Verify post_top_level_engagement_comment generates a question via Gemini ... ok
test_tournament_head_to_head_judging (test_pipeline.TestPipeline.test_tournament_head_to_head_judging)
Test 4: Verify evaluate_tournament_variants conducts a side-by-side head-to-head comparison ... ok
test_wildlife_species_ingestion_and_few_shot_scoring (test_pipeline.TestPipeline.test_wildlife_species_ingestion_and_few_shot_scoring)
Test 6: Verify MPVSAP 3.0 WildApex Shorts Wildlife & Bizarre Biology Refactoring: ... ok
test_youtube_preflight_fail (test_pipeline.TestPipeline.test_youtube_preflight_fail)
Test 1: Verify YouTube Auth Pre-flight Check fails fast on invalid_grant. ... ok

----------------------------------------------------------------------
Ran 7 tests in 7.285s

OK
```

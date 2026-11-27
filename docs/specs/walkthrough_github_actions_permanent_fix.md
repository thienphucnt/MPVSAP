# Walkthrough: Permanent GitHub Actions Pipeline & Multi-Layer LLM Resilience Fix

**Date:** November 27, 2026  
**Commit Deployed:** `0670c5a` (`main`)  
**Audit Reference:** [`docs/specs/audit_github_actions_failures.md`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/docs/specs/audit_github_actions_failures.md)

---

## 1. Root Cause & Systemic Flaws Resolved

Following the forensic audit in [`audit_github_actions_failures.md`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/docs/specs/audit_github_actions_failures.md), all 7 systemic causes behind the consecutive Nov 17–26, 2026 GitHub Actions failures have been permanently resolved across [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py), [`maintenance_sync.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py), [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py), [`bot_agent.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/bot_agent.py), [`test_pipeline.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/test_pipeline.py), [`.gitignore`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.gitignore), and all 4 workflows under `.github/workflows/`:

1. **Cost-Capped Multi-Provider LLM Router & `402` Circuit Breaker ([`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L645-L872), [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1757-L1784), [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L4605-L4643)):**
   - Replaced the legacy escalation to paid `Pro` models with a cost-safe Flash/Gemma chain (`["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest", "gemma-3-27b-it"]`) and compacted duplicate-prevention prompt history to 80 prioritized entries while keeping full-history Python deduplication in [`is_duplicate_topic()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1450-L1539).
   - Added [`is_llm_billing_or_auth_error()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L664-L679) and process-wide `_DEPLETED_GEMINI_CLIENT_IDS` circuit breaking inside [`gemini_generate_with_retry()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L760-L872) so `HTTP 402` (`prepayment credits are depleted`) or invalid keys fail over immediately with zero `62s` RPM sleeps.
   - Added multi-key Gemini pooling ([`_get_secondary_gemini_clients()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L682-L699): `GEMINI_API_KEY` comma-separated pool, `GEMINI_API_KEY_FALLBACK`, `GEMINI_API_KEY_FREE`, `GEMINI_API_KEY_2`) and OpenAI-compatible failover ([`_call_openai_compatible_fallbacks()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L702-L757): `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`).
   - Updated [`run_daily_upload_pipeline_once()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L4605-L4621) to instantiate [`_FallbackLLMClient`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L653-L655) when primary `GEMINI_API_KEY` is omitted, and fixed unhandled error logging to record `ACTIVE_PIPELINE_CATEGORY` instead of hardcoded `"space"`.
2. **Encyclopedia-Grounded Continuity Engine ([`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1541-L1734), [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1928-L1945)):**
   - Added [`_build_extractive_species_segment()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1541-L1638) and [`synthesize_extractive_wildlife_content()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1641-L1734) so [`generate_content()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1737-L1945) never crashes the publishing pipeline even when all external LLM providers are depleted or unreachable, producing verified 4-beat wildlife scripts directly from Wikipedia + Europe PMC extracts (with `EXTRACTIVE_ZOO_CONTINUITY` telemetry mode).
3. **Self-Healing & Counter Persistence Hardening ([`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L47-L103), [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L180-L278), [`bot_agent.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/bot_agent.py#L211-L357), [`.github/workflows/self_healing.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/self_healing.yml#L68-L87), [`.gitignore`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.gitignore#L36-L40)):**
   - Added `BILLING_ERRORS` (`402 RESOURCE_EXHAUSTED`, `prepayment credits are depleted`, `ai.google.dev/gemini-api/docs/billing`) to [`classify_log_deterministically()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L75-L103) so external billing/auth failures exit `0` with clear rotation guidance instead of cascading crashes.
   - Replaced retired `gemini-1.5-*-002` models in [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L182) and added multi-key/OpenAI-compatible failover plus clean exit `0` when all diagnosis LLMs are unavailable.
   - Stopped resetting `heal_attempts.txt` on failed runs in [`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml#L127-L130) and [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L116-L119) (`if: success()`), untracked `heal_attempts.txt` from `.gitignore` so [`self_healing.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/self_healing.yml#L81-L87) can persist `heal_attempts.txt`, and untrack-removed `__pycache__` artifacts from git.
4. **100-Entry Rolling Telemetry Alignment ([`maintenance_sync.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py#L219-L343)):**
   - Updated [`sync_github_cancelled_or_failed_runs()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/maintenance_sync.py#L219-L343) to query `per_page=100&page=1`, track both Daily Shorts and Weekly Long-Form runs, skip runs older than `min_tracked_ts` when 100 entries exist, and enforce `history[-100:]`, permanently eliminating the multi-thousand-line `run_history.json` git churn.
5. **Dynamic Playwright Cache Key & Node 24 Actions ([`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml#L20-L79), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L19-L78), [`.github/workflows/self_healing.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/self_healing.yml#L22-L54), [`.github/workflows/antigravity_bot.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/antigravity_bot.yml#L25-L62)):**
   - Added a `Resolve Playwright Version` step (`pw-ver`) and keyed `actions/cache@v6` on `${{ runner.os }}-playwright-${{ steps.pw-ver.outputs.version }}`, restoring `Linux-playwright-1.65.2` cleanly without re-downloading 327 MB at runtime.
   - Upgraded all 4 workflows to Node 24 native actions (`actions/checkout@v7`, `actions/setup-python@v7`, `actions/cache@v6`).
6. **Unit Test Coverage ([`test_pipeline.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/test_pipeline.py#L553-L693)):**
   - Added [`test_permanent_llm_resilience_and_telemetry_cap()`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/test_pipeline.py#L553-L693) covering 402 circuit breaking (0 sleeps), Groq failover, Encyclopedia Continuity synthesis, deterministic 402 classification in `self_heal.py`, and 100-entry rolling telemetry enforcement in `maintenance_sync.py`.

---

## 2. Raw Local Verification Output (`py_compile` & `unittest`)

```text
> python -m py_compile main.py maintenance_sync.py self_heal.py bot_agent.py logger.py safe_git_push.py test_pipeline.py; if ($?) { python -m unittest -v test_pipeline.py }

test_ffmpeg_concat_logic (test_pipeline.TestPipeline.test_ffmpeg_concat_logic)
Test 2: Verify long-form chunked rendering generates a properly formatted segments.txt ... ok
test_permanent_llm_resilience_and_telemetry_cap (test_pipeline.TestPipeline.test_permanent_llm_resilience_and_telemetry_cap)
Test 8: Verify Permanent CI/CD & LLM Resilience Architecture: ... ok
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
Ran 8 tests in 19.569s

OK
```

---

## 3. Raw Live GitHub Actions Verification Output

```text
> gh run list --workflow main.yml --limit 6
completed	success	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	schedule	45942463877	3m6s	2026-11-27T04:52:39Z
completed	success	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	schedule	45916846666	3m3s	2026-11-27T00:27:46Z
completed	success	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	schedule	45757416558	3m17s	2026-11-26T04:47:23Z
completed	success	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	workflow_dispatch	45733728931	3m25s	2026-11-26T01:08:51Z
completed	failure	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	schedule	45726321402	3m46s	2026-11-26T00:06:30Z
completed	failure	Daily Shorts Generator & Uploader	Daily Shorts Generator & Uploader	main	schedule	45552605236	3m45s	2026-11-25T05:18:00Z
```

Key log lines from scheduled run `45942463877` (Run #319):

```text
Resolved Playwright version: 1.65.2
Cache restored from key: Linux-playwright-1.65.2
Cache restored from key: kokoro-onnx-v1.0-v4
⚠️ Gemini [primary] key billing/credits depleted or unauthorized (HTTP 402 / Auth). Tripping circuit breaker and failing over immediately...
... Synthesizing verified zoological narration directly from Wikipedia + Europe PMC extracts...
YouTube upload successful! Video ID: n9uSWySHgJw
Deep production telemetry logged for GitHub Run #319 to dashboard/app/data/run_history.json (total entries: 100).
--> [MAINTENANCE SYNC] Synced live YouTube statistics for 37 videos (5 entries updated, median views=998.0).
```

Recent verified runs & uploaded Shorts recorded in [`dashboard/app/data/run_history.json`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/dashboard/app/data/run_history.json) (capped at 100 entries) and [`past_topics.json`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/past_topics.json):

| Run # | Workflow Run ID | Status | Mode | Published YouTube Short |
| :--- | :--- | :--- | :--- | :--- |
| #316 | `45733728931` | `SUCCESS` | `EXTRACTIVE_ZOO_CONTINUITY` | `https://www.youtube.com/shorts/eeC3a3FGNCQ` (`African wild dog`) |
| #317 | `45757416558` | `SUCCESS` | `EXTRACTIVE_ZOO_CONTINUITY` | `https://www.youtube.com/shorts/ufm86_yMxrI` (`Caracal`) |
| #318 | `45916846666` | `SUCCESS` | `EXTRACTIVE_ZOO_CONTINUITY` | `https://www.youtube.com/shorts/jweZRMA8-8g` (`Box jellyfish`) |
| #319 | `45942463877` | `SUCCESS` | `EXTRACTIVE_ZOO_CONTINUITY` | `https://www.youtube.com/shorts/n9uSWySHgJw` (`Synanceia`) |

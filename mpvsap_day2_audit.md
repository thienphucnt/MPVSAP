# Day 2 Optimization & Architecture Audit Report

**Date:** July 30, 2026  
**Auditor:** Principal Systems Engineer  
**Target Repository:** `thienphucnt/MPVSAP`

---

## 1. Git Telemetry & Checkout Bloat

- **Status:** `Missing`
- **File Paths:** [`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml#L21), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L21), [`.github/workflows/self_healing.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/self_healing.yml#L21), [`.github/workflows/antigravity_bot.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/antigravity_bot.yml#L26), [`logger.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/logger.py#L90-L102)
- **Summary:** None of the 4 GitHub Actions workflow files use `fetch-depth: 1` under `actions/checkout@v4`, forcing every CI runner to download the complete git commit history on every run. Additionally, `logger.py` loads and appends every run entry to `logs/run_history.json` and `dashboard/app/data/run_history.json` without any max-entry rotation cap, causing `run_history.json` to grow infinitely inside the repository commit tree (currently over 6,500 lines).

---

## 2. Multi-Platform Syndication

- **Status:** `Partially Implemented`
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2781-L2910), [`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml#L150-L157), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L74-L81)
- **Summary:** Direct posting logic for TikTok (`upload_to_tiktok`), Facebook Reels (`upload_to_facebook`), and Instagram Reels (`upload_to_instagram`) is fully written in `main.py` using raw REST requests. However, in workflow `.yml` files, TikTok and Meta credentials are indiscriminately injected into jobs like `long_form.yml` where social syndication is completely bypassed (`if config.is_short:` checks). Furthermore, Instagram Reels API requires a publicly accessible video URL which fails on isolated CI/local runners unless media is pre-hosted.

---

## 3. Pexels API Fallbacks

- **Status:** `Partially Implemented`
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1708-L1780)
- **Summary:** `download_pexels_videos()` attempts Pexels HD video queries per keyword, falls back to searching Wikimedia Commons for static images to render synthetic zoom clips, and then retries category default Pexels keywords. However, if all remote API calls encounter a 429 rate limit, network timeout, or quota exhaustion, it raises `Exception("All Pexels downloads failed.")` and crashes the pipeline instead of drawing from a local offline generic B-roll directory (e.g. `assets/fallback_broll/`).

---

## 4. Workflow Security (Least Privilege)

- **Status:** `Missing`
- **File Paths:** [`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml#L134-L157), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml#L58-L81), [`.github/workflows/antigravity_bot.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/antigravity_bot.yml#L87-L111)
- **Summary:** Workflow files violate the principle of least privilege by blindly dumping all repository secrets (`GEMINI_API_KEY`, `PEXELS_API_KEY`, `YOUTUBE_*`, `TIKTOK_*`, `META_*`, `IG_*`, `FB_*`) into step environment variables across every job. For example, `long_form.yml` injects TikTok and Meta access tokens even though long-form compilations only upload to YouTube, and `antigravity_bot.yml` exposes all social publishing tokens to the autonomous coder agent loop.

---

## 5. Other Observations

1. **Automated Heartbeat Commit Noise:** `safe_git_push.py` commits `heartbeat.txt` directly to `main` on every single run. Automated heartbeat commits account for over 70% of the repository's entire commit history.
2. **Duplicate Telemetry File Storage:** Telemetry records are written to both `logs/run_history.json` and `dashboard/app/data/run_history.json`, requiring custom `.gitattributes` merge strategies (`merge=ours`) to avoid merge conflicts.
3. **Duplicated Kokoro Validation Logic:** Inline Python validation scripts for Kokoro ONNX model weights are copy-pasted across `main.yml` and `long_form.yml` instead of being centralized in a helper module.

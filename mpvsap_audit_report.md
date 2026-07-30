# Architectural Audit Report: MPVSAP Codebase

**Date:** July 30, 2026  
**Auditor:** Principal Systems Engineer  
**Target Repository:** `thienphucnt/MPVSAP`

---

## 1. Gemini Quota Exhaustion (429 Errors)

- **Status:** `Implemented`
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L461-L516)
- **Summary:** All Gemini API calls (both script generation and auto-QA tournament evaluation) are wrapped in `gemini_generate_with_retry()`, which implements a multi-model fallback chain (`gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-flash-latest`, `gemini-pro-latest`) with exponential backoff for transient errors. It includes intelligent rate-limit handling that fast-switches models on long 429 delays and executes up to 3 outer passes with automatic 60–90s sleep pauses to wait for 1-minute RPM rate limit window resets.

---

## 2. YouTube Refresh Token Management

- **Status:** `Missing`
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2549-L2560), [`.github/workflows/main.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/main.yml), [`.github/workflows/long_form.yml`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/.github/workflows/long_form.yml)
- **Summary:** There is currently no pre-flight validation check at the start of workflow execution or main script startup to verify YouTube OAuth credentials. Refresh token instantiation and API authorization occur only inside `upload_to_youtube()` after full script generation, stock media downloads, and video rendering have already finished, causing `invalid_grant` errors to be caught late after heavy CPU rendering.

---

## 3. Long-Form Compilation Timeouts

- **Status:** `Partially Implemented`
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L3085-L3140)
- **Summary:** Segment audio synthesis, subtitle timestamp calculation, and Pexels stock video fetching are performed segment-by-segment in a loop to manage memory efficiently. However, the final video rendering step passes all raw B-roll clips, concatenated master audio, and full subtitle timelines into `assemble_video()`, rendering the entire 10-part compilation as a single monolithic pass rather than compiling pre-rendered video chunks (`segment_0.mp4`, `segment_1.mp4`) and stitching them at the end via FFmpeg stream concatenation.

---

## 4. Self-Healing Diagnostic Logic

- **Status:** `Implemented`
- **File Paths:** [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L88-L108), [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L152-L189)
- **Summary:** `self_heal.py` explicitly instructs the Gemini diagnostic engine to categorize failure logs into two distinct statuses: `STATUS: TRANSIENT` (for 429 rate limits, 503 service outages, expired tokens, or network timeouts) versus `STATUS: FIXED` (for actual code/syntax bugs). If classified as `TRANSIENT`, the script logs the explanation and exits without modifying any source files; if `FIXED`, it validates line counts and applies a minimal unified diff patch to `main.py`.

---

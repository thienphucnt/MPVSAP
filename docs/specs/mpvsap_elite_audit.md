# MPVSAP Elite Engineering Audit Report

**Date:** July 30, 2026  
**Auditor:** Principal Systems Architecture & AI Engineer  
**Governance:** Operating under Permanent Agent Constitution (`.agyrules`)  
**Target Repository:** `thienphucnt/MPVSAP`

---

## Executive Summary Table

| Audit Area | Component Evaluated | Status | Target Files / Locations | Core Recommendation |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Repository Hygiene & Context Bloat** | **`Needs Refactoring`** | Root Dir, `CHAT_HISTORY.md`, `auth_provider_a.py`, `delete_video.py` | Relocate specs/history to `docs/`, move legacy scripts to `scripts/legacy/`, `.gitignore` ephemeral scratchpads. |
| **2** | **Autonomous Agent Test Shielding** | **`Flawed`** | [`bot_agent.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/bot_agent.py#L230-L265), `.github/workflows/antigravity_bot.yml` | Wire post-edit automated unit test validation (`test_pipeline.py`) into agent execution loop with auto-retry self-correction. |
| **3** | **Broadcast-Grade Audio Engineering** | **`Needs Refactoring`** | [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2433-L2442) | Implement FFmpeg `sidechaincompress` filtergraph for dynamic music ducking (-18dB to -22dB during speech) + EBU R128 `loudnorm`. |
| **4** | **Deterministic Self-Healing** | **`Flawed`** | [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L46-L108) | Add deterministic pre-flight error classifier to instantly catch non-code env errors (`invalid_grant`, `429`, `ENOSPC`) before invoking LLM. |

---

## 1. Repository Hygiene & Context Bloat

### Audit Findings
- **Context Window Contamination:** `CHAT_HISTORY.md` in the root repository consumes ~23% of total token context when workspace files are loaded into LLM context windows.
- **Legacy & Ephemeral Clutter:** Legacy standalone utility scripts (`auth_provider_a.py`, `delete_video.py`) sit directly in the root directory. Ephemeral bot artifacts (`bot_comment.md`, `issue_context.json`, `failed_logs.txt`) are created during runner execution without strict `.gitignore` containment.
- **Violation of AGY Directive 2 (SPEC-IN-REPO):** Documentation and audit reports were historically created in root rather than isolated under `docs/specs/`.

### FAANG-Grade Architectural Solution
1. **Context Slimming:** Move `CHAT_HISTORY.md` to `docs/history/CHAT_HISTORY_archive.md` or rely on git commit logs to free up ~25,000+ context tokens for LLM context windows.
2. **Directory Restructuring:**
   - Move all architecture plans and audit reports to `docs/specs/`.
   - Move standalone utility scripts to `scripts/legacy/`.
3. **Ephemeral Containment:** Update `.gitignore` to strictly exclude:
   ```gitignore
   bot_comment.md
   issue_context.json
   failed_logs.txt
   segments.txt
   *.ass
   temp_no_subs_*.mp4
   ```

---

## 2. Autonomous Agent Test Shielding (`bot_agent.py` & `antigravity_bot.yml`)

### Audit Findings
- **File Paths:** [`bot_agent.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/bot_agent.py#L230-L265)
- **Current Behavior:** `bot_agent.py` processes Gemini function calls (read/write files, run commands) and terminates as soon as Gemini finishes generating text.
- **Flaw:** The agent does NOT automatically run `test_pipeline.py` or `py_compile` as a mandatory validation gate after code edits. If Gemini generates buggy code or breaking changes, the bot commits or outputs `bot_comment.md` without discovering test breakages.

### FAANG-Grade Architectural Solution
Implement a **Post-Edit Test Shielding Gate** inside `bot_agent.py`:
1. When Gemini finishes its function call iterations, `bot_agent.py` automatically executes:
   ```python
   test_result = subprocess.run([sys.executable, "-m", "unittest", "test_pipeline.py"], capture_output=True, text=True)
   ```
2. If `test_result.returncode != 0`, `bot_agent.py` automatically appends the unit test failure traceback to the Gemini chat session:
   `"CRITICAL TEST FAILURE: Unit tests failed after your edits. Please fix the error: <stderr_output>"`
3. The agent loop continues up to 3 self-correction iterations until `test_pipeline.py` returns `OK` before finalizing `bot_comment.md`.

---

## 3. Broadcast-Grade Audio Engineering

### Audit Findings
- **File Paths:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L2433-L2442)
- **Current Code:**
  ```python
  cmd = [
      "ffmpeg", "-y",
      "-i", audio_path,
      "-i", music_temp_path,
      "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-14:TP=-1.0:LRA=11",
      "-c:a", "pcm_s16le",
      mixed_audio_path
  ]
  ```
- **Flaw:** `amix` performs a static linear blend of voiceover and background music. When speech is present, the music volume does NOT automatically duck down, creating audio masking and reducing voice intelligibility.

### FAANG-Grade Architectural Solution
Implement **Sidechain Dynamic Ducking** with EBU R128 Loudness Normalization. FFmpeg uses the spoken voiceover signal (`[0:a]`) to dynamically compress background music (`[1:a]`) by -18dB to -22dB during speech, restoring music volume during pauses:

```bash
ffmpeg -y -i voiceover.wav -i music.mp3 -filter_complex \
"[1:a][0:a]sidechaincompress=threshold=0.08:ratio=10:attack=10:release=150[ducked]; \
 [0:a][ducked]amix=inputs=2:duration=first:weights=1.0 0.25[mixed]; \
 [mixed]loudnorm=I=-16:TP=-1.5:LRA=11[out]" \
-map "[out]" -c:a aac -b:a 192k final_audio.mp4
```

---

## 4. Deterministic Self-Healing (`self_heal.py`)

### Audit Findings
- **File Paths:** [`self_heal.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/self_heal.py#L46-L108)
- **Current Behavior:** `self_heal.py` reads `failed_logs.txt` and immediately sends the log extract to Gemini LLM for diagnosis.
- **Flaw:** When a workflow fails due to an environmental or authentication issue (e.g. YouTube OAuth `invalid_grant: Token expired or revoked` or `429 RESOURCE_EXHAUSTED`), `self_heal.py` still invokes Gemini across multiple fallback models, wasting API quota and attempting impossible code fixes for expired tokens.

### FAANG-Grade Architectural Solution
Implement a **Deterministic Pre-Flight Classifier** in `self_heal.py` *before* contacting Gemini LLM:

```python
AUTHENTICATION_ERRORS = [
    r"invalid_grant",
    r"Token expired or revoked",
    r"YouTube OAuth Pre-flight Check FAILED",
    r"google.auth.exceptions.RefreshError"
]

ENVIRONMENT_ERRORS = [
    r"429 RESOURCE_EXHAUSTED",
    r"Quota exceeded",
    r"No space left on device",
    r"ENOSPC"
]

def classify_log_deterministically(log_text: str) -> Optional[str]:
    for pattern in AUTHENTICATION_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return "STATUS: ENVIRONMENT_AUTH_EXPIRED - YouTube OAuth refresh token expired. Manual token refresh required."
    for pattern in ENVIRONMENT_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return "STATUS: TRANSIENT_INFRASTRUCTURE - Resource quota or disk space exhausted. No code fix applicable."
    return None
```

If a deterministic match is found, `self_heal.py` immediately prints the status and exits with code 0 without calling the Gemini API.

---

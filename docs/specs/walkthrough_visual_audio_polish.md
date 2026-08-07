# Walkthrough: Visual & Audio Polish (Pexels Atmospheric B-Roll & Phonetic Expansion)

## Overview
This walkthrough documents the implementation of two essential prompt engineering and pipeline sanitization rules in `main.py` to prevent Pexels stock footage retrieval failures and neural TTS pronunciation errors.

---

## Key Changes Implemented

### 1. Task 1: The Pexels Limitation Rule (Atmospheric B-Roll Translation)
- **Directive Updated:** In `generate_content()` prompt directives for YouTube Shorts, added strict guidance informing the LLM that Pexels is a modern lifestyle stock video library lacking archival historical footage, specific military vehicles (e.g. *Panzer tanks*), or period-accurate soldiers.
- **Rule Enforced:** The LLM MUST translate specific historical nouns into generic, moody, timeless cinematic visual descriptors.
- **Banned Examples:** `French soldiers`, `German Panzer tank`, `Maginot Line fortress`, `Roman legionaries`.
- **Required Examples:** `barbed wire fence in fog`, `abandoned concrete bunker`, `dark moody forest`, `vintage paper map`, `heavy military boots walking`.
- **Pipeline Guardrail:** Updated `sanitize_search_query()` in `main.py` to automatically rewrite specific historical terms into generic cinematic search queries before sending requests to the Pexels API.

### 2. Task 2: Audio-Optimized Pronunciation Guardrail (Phonetic Expansion)
- **Directive Updated:** In `generate_content()` prompt directives for YouTube Shorts, enforced a mandatory **Phonetic Expansion Rule**.
- **Rule Enforced:** The LLM MUST write out all acronyms, historical abbreviations, numbers, and symbols phonetically exactly as spoken.
- **Banned Examples:** `WWI`, `WWII`, `WW1`, `WW2`, `US`, `UK`, `$5M`.
- **Required Examples:** `World War One`, `World War Two`, `United States`, `United Kingdom`, `five million dollars`.
- **Pipeline Guardrail:** Added regex expansion fallbacks in `sanitize_script_for_tts()` in `main.py` (e.g., `\bWWI\b` $\rightarrow$ `World War One`, `\bWWII\b` $\rightarrow$ `World War Two`, `\bUS\b` $\rightarrow$ `United States`, `\bUK\b` $\rightarrow$ `United Kingdom`).

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
Ran 5 tests in 1.770s

OK
```

### 3. Git Commit Details
- **Commit Hash:** `9858494d4482270dd2353aa86e9c5db0d358140b`
- **Commit Message:** `feat(prompt): add Pexels atmospheric b-roll translation and TTS phonetic expansion rules to main.py`
- **Branch:** `main` (synced to remote `origin/main`).

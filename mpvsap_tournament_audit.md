# Auto-QA Tournament Engine Audit Report

**Date:** July 30, 2026  
**Auditor:** Principal Systems Engineer & AI Prompt Engineer  
**Target Repository:** `thienphucnt/MPVSAP`

---

## 1. Variant Script & Title Generation Logic

- **Status:** `Needs Refactoring`
- **File Paths & Lines:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L985-L1080)
- **Summary:** In `generate_content()`, Gemini is prompted to generate 5 candidate variants in a single JSON response. However, the system prompt lacks explicit constraints prohibiting shared title prefixes or repetitive title templates. As a result, Gemini frequently produces near-identical title structures across variants. Furthermore, telemetry backfilling logic previously generated titles using rigid string prepending (`f"{angle}: {clean_title}"`), causing Variant 2 through Variant 5 to display repetitive prefixed titles (e.g. `Scientific Breakthrough: Bridgwater Canal's Hidden Financial War`) in the dashboard UI.

---

## 2. Auto-QA Evaluation Prompt & Scoring Criteria

- **Status:** `Flawed`
- **File Paths & Lines:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L736-L820), [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L1094-L1114)
- **Summary:** In `generate_content()`, tournament evaluation is executed via an isolated loop where `evaluate_script_quality()` is called sequentially for each variant (`for idx, candidate in enumerate(parsed_variants)`). Evaluating each variant in a vacuum without presenting all 5 candidates in a single head-to-head comparative prompt context prevents Gemini from performing relative ranking. This leads to score clustering, positional bias towards Variant 1, and penalization of prepended titles under `title_synergy` and `absence_of_cliches` criteria.

---

## 3. Variant Diversity & Selection Pipeline

- **Status:** `Needs Refactoring`
- **File Paths & Lines:** [`main.py`](file:///C:/Users/Admin/Documents/antigravity/vibrant-hawking/main.py#L998)
- **Summary:** The 5 tournament narrative angles are hardcoded in `main.py` line 998 (`1-Suspenseful Mystery, 2-Scientific Breakthrough, 3-Dramatic Conflict, 4-Existential Wonder, 5-Action Mystery`). These exact same 5 angles are used statically for every daily run regardless of category (`space`, `history`, `tech`). There is currently no category-specific angle pool, no angle rotation mechanism, and no dynamic randomization to ensure narrative variety across different topics.

---

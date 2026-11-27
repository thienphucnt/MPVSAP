import os
import re
import sys
import time
import random
import difflib
from pathlib import Path
from google import genai
from google.genai import types


def apply_unified_diff(original_lines, diff_text):
    """Apply a unified diff to a list of lines, returning the patched lines."""
    patched = list(original_lines)
    hunk_pattern = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', re.MULTILINE)
    diff_lines = diff_text.splitlines()

    if not list(hunk_pattern.finditer(diff_text)):
        return None  # Not a valid diff

    changes = []
    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        m = hunk_pattern.match(line)
        if m:
            src_start = int(m.group(1)) - 1
            src_len = int(m.group(2) if m.group(2) else "1")
            added = []
            i += 1
            while i < len(diff_lines) and not diff_lines[i].startswith('@@'):
                dl = diff_lines[i]
                if dl.startswith('+'):
                    added.append(dl[1:] + '\n')
                i += 1
            changes.append((src_start, src_len, added))
        else:
            i += 1

    # Apply changes in reverse order to preserve line numbers
    for src_start, src_len, added in reversed(changes):
        patched[src_start:src_start + src_len] = added

    return patched


AUTHENTICATION_ERRORS = [
    r"invalid_grant",
    r"Token expired or revoked",
    r"YouTube OAuth Pre-flight Check FAILED",
    r"google\.auth\.exceptions\.RefreshError",
    r"AuthError",
    r"API_KEY_INVALID",
    r"API key not valid",
]

BILLING_ERRORS = [
    r"402 RESOURCE_EXHAUSTED",
    r"'code':\s*402",
    r'"code":\s*402',
    r"prepayment credits are depleted",
    r"ai\.google\.dev/gemini-api/docs/billing",
]

ENVIRONMENT_ERRORS = [
    r"429 RESOURCE_EXHAUSTED",
    r"All configured LLM providers exhausted",
    r"Quota exceeded",
    r"No space left on device",
    r"ENOSPC",
    r"503 UNAVAILABLE",
]


def classify_log_deterministically(log_text: str):
    """
    Pre-flight deterministic log classifier to instantly detect non-code environment,
    billing, and authentication errors without calling LLM models or burning API quota.
    """
    for pattern in BILLING_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return (
                "STATUS: ENVIRONMENT_BILLING_DEPLETED\n"
                "EXPLANATION: Google AI Studio prepaid credits on GEMINI_API_KEY are depleted (HTTP 402). "
                "Generate a free-tier API key in a new unbilled AI Studio project (https://aistudio.google.com/apikey) "
                "or top up billing at https://ai.studio/projects, then update GEMINI_API_KEY in GitHub Secrets. "
                "No code modification can resolve external API billing depletion."
            )
    for pattern in AUTHENTICATION_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return (
                "STATUS: ENVIRONMENT_AUTH_EXPIRED\n"
                "EXPLANATION: OAuth or API credential is expired, invalid, or revoked. "
                "Manual credential rotation is required. No code modification can fix expired credentials."
            )
    for pattern in ENVIRONMENT_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return (
                "STATUS: TRANSIENT_INFRASTRUCTURE\n"
                "EXPLANATION: Runner resource quota, upstream API rate limit, or disk space is exhausted. "
                "No code modification can resolve transient infrastructure or quota limits."
            )
    return None


def main():
    print("Starting AI Self-Healing Diagnostic script...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    log_path = Path("failed_logs.txt")
    code_path = Path("main.py")

    if not log_path.exists():
        print(f"Error: Log file '{log_path}' not found. Nothing to diagnose.")
        sys.exit(1)

    if not code_path.exists():
        print(f"Error: Source file '{code_path}' not found.")
        sys.exit(1)

    # Read log and code content
    log_content = log_path.read_text(encoding="utf-8", errors="ignore")
    code_content = code_path.read_text(encoding="utf-8", errors="ignore")
    original_line_count = len(code_content.splitlines())
    # Safety guard: never accept a file with fewer than 90% of original lines or fewer than 2800
    MIN_ACCEPTABLE_LINES = max(2800, int(original_line_count * 0.90))
    print(f"Original main.py: {original_line_count} lines. Min acceptable after fix: {MIN_ACCEPTABLE_LINES} lines.")

    # Deterministic Pre-Flight Classifier
    deterministic_result = classify_log_deterministically(log_content)
    if deterministic_result:
        print("\n--- DETERMINISTIC PRE-FLIGHT DIAGNOSIS ---")
        print(deterministic_result)
        print("\nSkipping LLM code modification loop as error is non-code environmental/auth.")
        sys.exit(0)

    # Trim log to last 200 lines to keep prompts compact

    # Trim log to last 200 lines to keep prompts compact
    log_lines = log_content.splitlines()
    if len(log_lines) > 200:
        log_content = "\n".join(log_lines[-200:])
        print("Trimmed log content to last 200 lines.")

    client = genai.Client(api_key=api_key)

    prompt = (
        "You are an expert self-healing software engineer fixing a failing automated video pipeline.\n\n"
        "Here is the FAILED run log (last 200 lines):\n"
        "==================================================\n"
        f"{log_content}\n"
        "==================================================\n\n"
        "Instructions:\n"
        "1. Analyze the logs to determine the EXACT cause of the failure.\n"
        "2. Classify the error into one of two statuses:\n"
        "   - 'STATUS: TRANSIENT' - The failure was caused by a temporary network timeout, a 503 "
        "Service Unavailable, a 429 Rate Limit, a temporary third-party API outage, or any issue "
        "that does not require code changes to fix. In this case, do NOT provide any code.\n"
        "   - 'STATUS: FIXED' - The failure was caused by a code bug. You MUST output ONLY a "
        "minimal unified diff patch targeting the specific lines that need changing. Do NOT output "
        "the entire file. Outputting the full file causes catastrophic truncation.\n"
        "3. The diff must be in standard unified diff format:\n"
        "   --- a/main.py\n"
        "   +++ b/main.py\n"
        "   @@ -LINE,COUNT +LINE,COUNT @@\n"
        "   -removed lines\n"
        "   +added lines\n"
        "4. Output format:\n\n"
        "STATUS: <TRANSIENT or FIXED>\n"
        "EXPLANATION: <Short explanation of what went wrong and how you solved it>\n"
        "DIFF:\n"
        "```diff\n"
        "# Include ONLY if STATUS is FIXED. Minimal targeted diff only.\n"
        "```"
    )

    print("Sending diagnosis request to LLM...")

    model_fallback_chain = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemma-4-31b-it",
    ]
    max_retries = 3
    response = None
    last_error = None

    candidate_keys = [k.strip() for k in (api_key or "").split(",") if k.strip()]
    for extra_env in ("GEMINI_API_KEY_FALLBACK", "GEMINI_API_KEY_FREE"):
        ev = os.environ.get(extra_env, "").strip()
        if ev and ev not in candidate_keys:
            candidate_keys.append(ev)

    for key_idx, active_key in enumerate(candidate_keys):
        active_client = genai.Client(api_key=active_key) if key_idx > 0 else client
        key_depleted = False
        for current_model in model_fallback_chain:
            success = False
            for attempt in range(max_retries):
                try:
                    print(f"Attempting diagnosis using model: {current_model} (key #{key_idx + 1})...")
                    gen_config = types.GenerateContentConfig(automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
                    response = active_client.models.generate_content(
                        model=current_model,
                        contents=prompt,
                        config=gen_config
                    )
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    err_s = str(e)
                    err_u = err_s.upper()
                    if "402" in err_s or "PREPAYMENT CREDITS" in err_u or "API_KEY_INVALID" in err_u:
                        print(f"Gemini key #{key_idx + 1} billing depleted or invalid (402/Auth). Skipping remaining models on this key...")
                        key_depleted = True
                        break
                    if "404" in err_s or "NOT_FOUND" in err_u:
                        print(f"Model {current_model} unavailable (404). Trying next model...")
                        break

                    is_quota_or_rate_limit = any(err in err_u for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA"])
                    is_transient = any(err in err_u for err in ["503", "UNAVAILABLE", "HIGH DEMAND"])

                    if is_quota_or_rate_limit:
                        print(f"Model {current_model} quota exceeded. Trying next fallback...")
                        break

                    if is_transient and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        print(f"Gemini API busy on {current_model} (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time:.2f}s: {e}")
                        time.sleep(wait_time)
                    else:
                        break
            if success or key_depleted:
                break
        if response is not None:
            break

    # Optional OpenAI-compatible fallback (Groq / OpenRouter / OpenAI)
    if response is None:
        import json as _json
        import urllib.request as _urlreq
        for prov_name, env_var, endpoint, m_id in [
            ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
            ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "meta-llama/llama-3.3-70b-instruct:free"),
            ("OpenAI", "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
        ]:
            pkey = os.environ.get(env_var, "").strip()
            if not pkey:
                continue
            try:
                req_body = _json.dumps({
                    "model": m_id,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                }).encode("utf-8")
                req = _urlreq.Request(
                    endpoint,
                    data=req_body,
                    headers={"Authorization": f"Bearer {pkey}", "Content-Type": "application/json"},
                    method="POST",
                )
                with _urlreq.urlopen(req, timeout=30) as r:
                    payload_resp = _json.loads(r.read().decode("utf-8"))
                    txt = payload_resp["choices"][0]["message"]["content"]
                    response = type("_Resp", (), {"text": txt})()
                    print(f"Diagnosis completed via {prov_name} ({m_id}).")
                    break
            except Exception as fb_e:
                last_error = fb_e

    if response is None:
        print(
            f"Notice: AI Self-Healing skipped LLM code patching because all configured LLM APIs are currently unavailable "
            f"(Last error: {last_error}). Exiting cleanly to avoid cascading false-failure alerts."
        )
        sys.exit(0)

    analysis = response.text.strip()
    print("Received diagnosis from Gemini.")

    status_match = re.search(r'^STATUS:\s*(TRANSIENT|FIXED)', analysis, re.MULTILINE | re.IGNORECASE)
    explanation_match = re.search(r'^EXPLANATION:\s*(.+)$', analysis, re.MULTILINE | re.IGNORECASE)

    if not status_match:
        print("Error: Could not parse STATUS from Gemini response.")
        print("Gemini response was:\n", analysis)
        sys.exit(1)

    status = status_match.group(1).upper()
    explanation = explanation_match.group(1) if explanation_match else "No explanation provided."

    print(f"Parsed Status: {status}")
    print(f"Explanation: {explanation}")

    if status == "FIXED":
        diff_block_match = re.search(r'```diff\s*(.*?)\s*```', analysis, re.DOTALL | re.IGNORECASE)
        python_block_match = re.search(r'```python\s*(.*?)\s*```', analysis, re.DOTALL | re.IGNORECASE)

        if diff_block_match:
            # Preferred path: apply minimal diff patch
            diff_text = diff_block_match.group(1).strip()
            original_lines = code_content.splitlines(keepends=True)
            patched = apply_unified_diff(original_lines, diff_text)

            if patched is None:
                print("SAFETY ABORT: Diff parsing failed (no valid @@ hunks found). No changes applied.")
                sys.exit(0)

            patched_line_count = len(patched)
            if patched_line_count < MIN_ACCEPTABLE_LINES:
                print(
                    f"SAFETY ABORT: Diff application resulted in only {patched_line_count} lines "
                    f"(minimum required: {MIN_ACCEPTABLE_LINES}). Refusing to apply patch."
                )
                sys.exit(0)

            code_path.write_text("".join(patched), encoding="utf-8")
            print(f"Applied diff patch to main.py. New line count: {patched_line_count}")
            sys.exit(0)

        elif python_block_match:
            # Legacy full-file mode — strict safety guard
            fixed_code = python_block_match.group(1).strip()
            fixed_line_count = len(fixed_code.splitlines())
            print(f"WARNING: Gemini returned a full python code block ({fixed_line_count} lines).")

            if fixed_line_count < MIN_ACCEPTABLE_LINES:
                print(
                    f"SAFETY ABORT: Generated code has only {fixed_line_count} lines "
                    f"(minimum required: {MIN_ACCEPTABLE_LINES}). "
                    "This is almost certainly a truncated/incomplete file. Refusing to overwrite main.py. "
                    "Manual investigation required."
                )
                # Exit 0 so self-healer does not endlessly re-trigger
                sys.exit(0)

            code_path.write_text(fixed_code, encoding="utf-8")
            print(f"Overwrote main.py with Gemini-provided full code ({fixed_line_count} lines).")
            sys.exit(0)

        else:
            print("Error: STATUS was FIXED but no ```diff or ```python code block found in Gemini response.")
            sys.exit(1)

    elif status == "TRANSIENT":
        print("No code changes needed. Transient error handled successfully.")
        sys.exit(0)

    else:
        print(f"Error: Unknown status '{status}' returned by Gemini.")
        sys.exit(1)


if __name__ == "__main__":
    main()

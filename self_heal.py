import os
import re
import sys
import time
import random
import difflib
from pathlib import Path
from google import genai


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
    r"AuthError"
]

ENVIRONMENT_ERRORS = [
    r"429 RESOURCE_EXHAUSTED",
    r"Quota exceeded",
    r"No space left on device",
    r"ENOSPC"
]


def classify_log_deterministically(log_text: str):
    """
    Pre-flight deterministic log classifier to instantly detect non-code environment
    and authentication errors without calling LLM models or burning API quota.
    """
    for pattern in AUTHENTICATION_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return (
                "STATUS: ENVIRONMENT_AUTH_EXPIRED\n"
                "EXPLANATION: YouTube OAuth refresh token is expired or revoked. "
                "Manual token re-authentication is required. No code modification can fix expired OAuth credentials."
            )
    for pattern in ENVIRONMENT_ERRORS:
        if re.search(pattern, log_text, re.IGNORECASE):
            return (
                "STATUS: TRANSIENT_INFRASTRUCTURE\n"
                "EXPLANATION: Runner resource quota or disk space is exhausted. "
                "No code modification can resolve infrastructure or quota limits."
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

    print("Sending diagnosis request to Gemini...")

    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro-002", "gemini-1.5-flash-002"]
    max_retries = 3
    response = None
    last_error = None

    for current_model in model_fallback_chain:
        success = False
        for attempt in range(max_retries):
            try:
                print(f"Attempting diagnosis using model: {current_model}...")
                response = client.models.generate_content(
                    model=current_model,
                    contents=prompt
                )
                success = True
                break
            except Exception as e:
                last_error = e
                is_quota_or_rate_limit = any(err in str(e).upper() for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA"])
                is_transient = any(err in str(e) or err in str(e).upper() for err in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"])

                if is_quota_or_rate_limit:
                    print(f"Model {current_model} quota exceeded. Trying next fallback...")
                    break

                if is_transient and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Gemini API busy on {current_model} (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time:.2f}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise
        if success:
            break

    if response is None:
        raise Exception(f"AI Self-Healing failed to contact any Gemini model. Last error: {last_error}")

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

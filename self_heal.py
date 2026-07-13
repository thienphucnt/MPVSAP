import os
import re
import sys
import time
import random
from pathlib import Path
from google import genai

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

    # Clean log output slightly to keep it compact (take last 200 lines if too long)
    log_lines = log_content.splitlines()
    if len(log_lines) > 200:
        log_content = "\n".join(log_lines[-200:])
        print("Trimmed log content to last 200 lines.")

    client = genai.Client(api_key=api_key)

    prompt = (
        "You are an expert self-healing software engineer in charge of fixing an automated short-form video generation pipeline.\n\n"
        "Here is the source code of the pipeline ('main.py'):\n"
        "==================================================\n"
        f"{code_content}\n"
        "==================================================\n\n"
        "Here is the console output/logs of the failed workflow run ('failed_logs.txt'):\n"
        "==================================================\n"
        f"{log_content}\n"
        "==================================================\n\n"
        "Instructions:\n"
        "1. Analyze the logs to determine the cause of the failure.\n"
        "2. Classify the error into one of two statuses:\n"
        "   - 'STATUS: TRANSIENT' - The failure was caused by a temporary network timeout, a 503 Service Unavailable, a 429 Rate Limit, a temporary third-party API outage, or any issue that does not require code changes to fix. In this case, do NOT provide any code.\n"
        "   - 'STATUS: FIXED' - The failure was caused by a syntax error, logic bug, type error, import error, or something that CAN and SHOULD be fixed by modifying the Python source code. You must provide the entire, fully corrected 'main.py' file inside a single python markdown block (```python ... ```).\n"
        "3. Keep all comments, existing robust functions, API timeouts, retry loops, and typewriter styles intact unless they are the direct cause of the bug.\n"
        "4. Your output must follow this format:\n\n"
        "STATUS: <TRANSIENT or FIXED>\n"
        "EXPLANATION: <Short explanation of what went wrong and how you solved it (or if it's transient)>\n"
        "CODE:\n"
        "```python\n"
        "# (Include the entire corrected main.py code here, only if STATUS is FIXED)\n"
        "```"
    )

    print("Sending diagnosis request to Gemini...")
    
    # Robust fallback model chain for diagnostic run
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
        # Extract code block
        code_block_match = re.search(r'```python\s*(.*?)\s*```', analysis, re.DOTALL | re.IGNORECASE)
        if not code_block_match:
            print("Error: STATUS was FIXED but no python code block (```python ... ```) was found in Gemini's response.")
            sys.exit(1)

        fixed_code = code_block_match.group(1).strip()
        if len(fixed_code) < 100:
            print("Error: The generated code block is too short to be the full main.py. Aborting safety overwrite.")
            sys.exit(1)

        # Overwrite main.py
        code_path.write_text(fixed_code, encoding="utf-8")
        print("Successfully overwrote 'main.py' with the code fix.")
        sys.exit(0) # Exit code 0 to indicate a successful fix/transient handle

    elif status == "TRANSIENT":
        print("No code changes needed. Transient error handled successfully.")
        sys.exit(0)

    else:
        print(f"Error: Unknown status '{status}' returned by Gemini.")
        sys.exit(1)

if __name__ == "__main__":
    main()

import os
import re
import sys
import json
import random
from pathlib import Path
from google import genai

def main():
    print("Starting Antigravity GitHub Bot Agent...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        sys.exit(1)

    prompt_text = os.environ.get("BOT_PROMPT")
    if not prompt_text:
        print("Error: BOT_PROMPT environment variable is empty.")
        sys.exit(1)

    print(f"Received Prompt: {prompt_text}")

    # Load main.py as context
    main_path = Path("main.py")
    main_content = main_path.read_text(encoding="utf-8", errors="ignore") if main_path.exists() else ""

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are Antigravity, an expert agentic AI software developer. "
        "Your task is to analyze the user's prompt request, inspect the codebase, and write the necessary code changes. "
        "Return your response ONLY as a valid JSON object matching the format below. Do not include markdown code block tags (like ```json), quotes, or extra text.\n"
        "JSON Schema:\n"
        "{\n"
        '  "explanation": "<explain what you did>",\n'
        '  "files": [\n'
        "    {\n"
        '      "path": "relative/path/to/file.py",\n'
        '      "content": "<full file content including modifications>"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_prompt = (
        f"User Prompt Request:\n"
        f"==================================================\n"
        f"{prompt_text}\n"
        f"==================================================\n\n"
        f"Current 'main.py' codebase:\n"
        f"==================================================\n"
        f"{main_content}\n"
        f"==================================================\n"
    )

    # Use robust model chain for code updates
    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro-002", "gemini-1.5-flash-002"]
    response = None
    
    for model in model_fallback_chain:
        try:
            print(f"Calling Gemini using model: {model}...")
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config={"system_instruction": system_instruction}
            )
            break
        except Exception as e:
            print(f"Error calling {model}: {e}. Trying next model...")

    if not response or not response.text:
        print("Error: Failed to get response from Gemini.")
        sys.exit(1)

    text = response.text.strip()
    
    # Strip markdown block formatting if present
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except Exception as e:
        print(f"ERROR: Could not parse response as JSON. Raw text was:\n{text}")
        sys.exit(1)

    explanation = data.get("explanation", "No explanation provided.")
    files_to_update = data.get("files", [])

    print(f"\nAI Explanation of changes:\n{explanation}\n")

    for file_info in files_to_update:
        rel_path = file_info.get("path")
        content = file_info.get("content")
        if not rel_path or not content:
            continue

        target_path = Path(rel_path)
        print(f"Writing updates to {target_path}...")
        # Create directories if they do not exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        print(f"Successfully wrote {target_path}")

    print("Checking if codebase compiles clean...")
    import py_compile
    for file_info in files_to_update:
        rel_path = file_info.get("path")
        if rel_path and rel_path.endswith(".py"):
            try:
                py_compile.compile(rel_path, doraise=True)
                print(f"  {rel_path} compiled successfully!")
            except Exception as e:
                print(f"  ERROR: {rel_path} has syntax errors: {e}")
                sys.exit(1)

    print("AI Bot changes applied successfully.")

if __name__ == "__main__":
    main()

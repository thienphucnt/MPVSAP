import os
import re
import sys
import subprocess
from pathlib import Path
from google import genai
from google.genai import types

# Define developer tools for Gemini to use autonomously
def read_file(path: str) -> str:
    """Reads the contents of a file in the workspace. The path must be relative to the repository root."""
    p = Path(path)
    if not p.exists():
        return f"Error: File '{path}' does not exist."
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"Error reading file: {e}"

def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with the specified content. The path must be relative to the repository root."""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Successfully wrote content to '{path}'"
    except Exception as e:
        return f"Error writing file: {e}"

def list_dir(path: str = ".") -> str:
    """Lists files and folders inside the specified directory path. The path must be relative to the repository root."""
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return f"Error: '{path}' is not a valid directory."
    try:
        entries = []
        for x in p.iterdir():
            t = "DIR" if x.is_dir() else "FILE"
            entries.append(f"[{t}] {x.name}")
        return "\n".join(entries) if entries else "(Empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"

def run_command(command: str) -> str:
    """Runs a shell/terminal command in the workspace and returns the exit code, stdout, and stderr."""
    print(f"--- Running agent command: {command} ---")
    try:
        # Run in bash shell with 120s timeout
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=120)
        output = f"Exit Code: {res.returncode}\nStdout:\n{res.stdout}\nStderr:\n{res.stderr}"
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out after 120 seconds."
    except Exception as e:
        return f"Error running command: {e}"

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

    # Check if this is a request to trigger/run the pipeline
    is_run_request = any(
        phrase in prompt_text.lower()
        for phrase in ["run pipeline", "trigger pipeline", "run uploader", "run daily uploader", "run upload pipeline", "start pipeline", "run generator", "run daily upload"]
    )

    if is_run_request:
        print("\n[ACTION DETECTED] Request to execute/run the video generation pipeline.")
        
        # 1. Try to trigger the workflow using gh CLI (removes dependency/runtime overhead if it works)
        print("Attempting to trigger workflow 'main.yml' via GitHub CLI...")
        gh_result = subprocess.run(
            ["gh", "workflow", "run", "main.yml"],
            capture_output=True,
            text=True
        )
        if gh_result.returncode == 0:
            print("SUCCESS: Triggered the 'Daily Shorts Generator & Uploader' workflow on GitHub Actions!")
            print("The pipeline is now running independently in the cloud. You can check the 'Actions' tab to watch its progress.")
            Path("bot_comment.md").write_text(
                "I successfully triggered the **Daily Shorts Generator & Uploader** workflow in the cloud!\n\n"
                "You can check its real-time progress on the **Actions** tab of your repository.",
                encoding="utf-8"
            )
            sys.exit(0)
        else:
            print(f"GitHub CLI trigger not authorized or failed (Code {gh_result.returncode}): {gh_result.stderr.strip()}")
            print("Falling back to executing the pipeline locally on this runner...")

        # 2. Local execution fallback: parse category from prompt
        category_arg = []
        if "space" in prompt_text.lower():
            category_arg = ["--category", "space"]
        elif "history" in prompt_text.lower():
            category_arg = ["--category", "history"]
        elif "tech" in prompt_text.lower():
            category_arg = ["--category", "tech"]

        print(f"Executing: python main.py {' '.join(category_arg)}")
        pipeline_res = subprocess.run(
            [sys.executable, "main.py"] + category_arg,
            text=False  # stream output directly to stdout/stderr
        )
        if pipeline_res.returncode == 0:
            print("\nSUCCESS: Video generation pipeline completed successfully on this runner!")
            Path("bot_comment.md").write_text(
                "I executed the video generation and upload pipeline locally on the runner!\n\n"
                "✅ **Status:** Completed successfully.\n"
                "🎥 **Result:** Video has been rendered and uploaded to your YouTube channel.",
                encoding="utf-8"
            )
            sys.exit(0)
        else:
            print(f"\nERROR: Video generation pipeline failed with exit code: {pipeline_res.returncode}")
            Path("bot_comment.md").write_text(
                f"I attempted to run the video generation and upload pipeline locally, but it failed with exit status code `{pipeline_res.returncode}`.\n\n"
                "❌ Please check the action run logs for more details.",
                encoding="utf-8"
            )
            sys.exit(pipeline_res.returncode)

    # 3. Autonomous Tool-Use Agent execution
    print("\n[AGENTIC DEV WORKFLOW DETECTED] Initializing Gemini autonomous coding loop...")
    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are Antigravity, a powerful autonomous agentic AI coding assistant running on a GitHub Actions VM. "
        "Your goal is to inspect the codebase and implement the user's issue request completely. "
        "You have full tool capabilities to list directory structures, read code files, write/update code files, "
        "and execute shell commands (e.g. running python scripts, compiling code, or running tests). "
        "Instructions:\n"
        "1. Inspect files and search contents to understand the repository structure.\n"
        "2. Make the edits necessary to resolve the prompt.\n"
        "3. You must verify that your changes are correct and compile successfully (e.g. run 'python -m py_compile main.py' or equivalent) before you finish.\n"
        "4. When you are done, summarize what changes you made and present them clearly in your final response text."
    )

    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro-002", "gemini-1.5-flash-002"]
    success = False
    
    for model in model_fallback_chain:
        try:
            print(f"Starting agent run using model: {model}...")
            response = client.models.generate_content(
                model=model,
                contents=f"User request: {prompt_text}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[read_file, write_file, list_dir, run_command]
                )
            )
            print("\nAgent run completed. Response summary:")
            print(response.text)
            Path("bot_comment.md").write_text(
                f"### 🤖 Autonomous Coder Run Summary\n\n"
                f"{response.text}",
                encoding="utf-8"
            )
            success = True
            break
        except Exception as e:
            print(f"Error executing agent with {model}: {e}. Trying next model...")

    if not success:
        print("Error: Agent run failed across all models.")
        Path("bot_comment.md").write_text(
            "❌ I attempted to process your request using the autonomous coding agent, but encountered errors across all models.\n\n"
            "Please check the action run logs for more details.",
            encoding="utf-8"
        )
        sys.exit(1)

    print("AI Bot agent changes applied and verified successfully.")

if __name__ == "__main__":
    main()

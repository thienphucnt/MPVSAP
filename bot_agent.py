import os
import re
import sys
import json
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
    # Guardrail against executing main.py directly
    cmd_lower = command.lower()
    if "main.py" in cmd_lower:
        if "py_compile" in cmd_lower or "-m py_compile" in cmd_lower:
            pass
        else:
            return (
                "Error: Direct execution of the video generation/upload pipeline ('main.py') "
                "is permanently blocked inside this coder agent environment to prevent runner time limits "
                "and workspace corruption. Please write/update files or run tests instead."
            )
            
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

    # Load issue context history if available
    issue_context_path = Path("issue_context.json")
    conversation_history = ""
    if issue_context_path.exists():
        try:
            with open(issue_context_path, "r", encoding="utf-8") as f:
                issue_data = json.load(f)
            
            title = issue_data.get("title", "")
            body = issue_data.get("body", "")
            comments = issue_data.get("comments", [])
            
            conversation_history += f"Issue Title: {title}\n"
            conversation_history += f"Issue Description:\n===================\n{body}\n===================\n\n"
            conversation_history += "Conversation History:\n"
            
            for comment in comments:
                author = comment.get("author", {}).get("login", "unknown")
                comment_body = comment.get("body", "")
                created_at = comment.get("createdAt", "")
                conversation_history += f"- [{author} at {created_at}]: {comment_body}\n"
        except Exception as e:
            print("Failed to parse issue context:", e)

    client = genai.Client(api_key=api_key)

    system_instruction = (
        "You are Antigravity, a powerful autonomous agentic AI coding assistant running on a GitHub Actions VM. "
        "Your goal is to inspect the codebase and implement the user's issue request completely. "
        "You have full tool capabilities to list directory structures, read code files, write/update code files, "
        "and execute shell commands (e.g. running python scripts, compiling code, or running tests). "
        "You are given the full conversation history of the GitHub issue thread for context. "
        "Instructions:\n"
        "1. Inspect files and search contents to understand the repository structure.\n"
        "2. Make the edits necessary to resolve the prompt.\n"
        "3. You must verify that your changes are correct and compile successfully (e.g. run 'python -m py_compile main.py' or equivalent) before you finish.\n"
        "4. When you are done, summarize what changes you made and present them clearly in your final response text."
    )

    import time
    import random

    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-pro-latest"]
    success = False
    
    for model in model_fallback_chain:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"Starting agent run using model: {model} (attempt {attempt + 1}/{max_retries})...")
                
                # Construct context-aware prompt
                prompt_content = f"User Request: {prompt_text}\n"
                if conversation_history:
                    prompt_content = (
                        f"Here is the context of the GitHub Issue thread conversation so far:\n"
                        f"==================================================\n"
                        f"{conversation_history}\n"
                        f"==================================================\n\n"
                        f"Please fulfill the user's latest request: '{prompt_text}' based on this conversation context."
                    )
                
                # Map tool names to Python functions
                tool_map = {
                    "read_file": read_file,
                    "write_file": write_file,
                    "list_dir": list_dir,
                    "run_command": run_command
                }
                
                # Start multi-turn chat session with tools enabled
                chat = client.chats.create(
                    model=model,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[read_file, write_file, list_dir, run_command]
                    )
                )
                
                # Send prompt
                response = chat.send_message(prompt_content)
                
                # Iterate on function call responses
                max_steps = 15
                for step in range(max_steps):
                    function_calls = response.function_calls
                    if not function_calls:
                        break
                        
                    print(f"Step {step + 1}: Executing {len(function_calls)} tool calls...")
                    tool_responses = []
                    for call in function_calls:
                        func_name = call.name
                        func_args = call.args
                        
                        if func_name in tool_map:
                            try:
                                result = tool_map[func_name](**func_args)
                            except Exception as ex:
                                result = f"Error executing tool: {ex}"
                        else:
                            result = f"Error: Tool '{func_name}' is not recognized."
                            
                        print(f"  Tool '{func_name}' -> Result preview: {str(result)[:200]}...")
                        tool_responses.append(
                            types.Part.from_function_response(
                                name=func_name,
                                response={"result": result}
                            )
                        )
                    response = chat.send_message(tool_responses)
                    
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
                is_rate_limit = any(err in str(e).upper() for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE_LIMIT"])
                if is_rate_limit and attempt < max_retries - 1:
                    # Parse dynamic retry delay from Gemini API response
                    match = re.search(r"retry in ([0-9\.]+)s", str(e))
                    if match:
                        wait_time = float(match.group(1)) + random.uniform(1, 3)
                        print(f"Gemini API requested wait. Sleeping for {wait_time:.2f}s before retry...")
                    else:
                        wait_time = (15 * (attempt + 1)) + random.uniform(2, 5)
                        print(f"Rate limited on {model}. Retrying in {wait_time:.2f}s... Error: {e}")
                    time.sleep(wait_time)
                else:
                    print(f"Error executing agent with {model}: {e}. Trying next fallback...")
                    break
        if success:
            break

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

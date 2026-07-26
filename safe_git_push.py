import os
import sys
import json
import subprocess
import time
from pathlib import Path

def run_cmd(cmd: str, check: bool = False, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    return subprocess.run(cmd, shell=True, check=check, capture_output=capture_output, text=True)

def merge_json_lists(local_file: Path, remote_file_content: str) -> list:
    """Intelligently merge two JSON lists/dicts (local vs remote) preserving union of all unique entries."""
    try:
        local_data = json.loads(local_file.read_text(encoding="utf-8")) if local_file.exists() else []
    except Exception:
        local_data = []

    try:
        remote_data = json.loads(remote_file_content)
    except Exception:
        remote_data = []

    if isinstance(local_data, list) and isinstance(remote_data, list):
        # Union by 'id', 'github_run_id', 'youtube_video_id', or 'topic'
        seen_keys = set()
        merged = []
        for item in local_data + remote_data:
            if isinstance(item, dict):
                key = item.get("id") or item.get("github_run_id") or item.get("youtube_video_id") or item.get("topic") or str(item)
            else:
                key = str(item)
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(item)
        return merged
    elif isinstance(local_data, dict) and isinstance(remote_data, dict):
        merged = dict(remote_data)
        merged.update(local_data)
        return merged
    return local_data if local_data else remote_data

def resolve_git_conflicts():
    """Detect and auto-resolve any git merge/rebase conflicts on state files."""
    status_proc = run_cmd("git status --porcelain")
    if not status_proc.stdout:
        return

    conflicted_files = []
    for line in status_proc.stdout.splitlines():
        if line.startswith("UU ") or line.startswith("AA ") or line.startswith("UD ") or line.startswith("DU "):
            conflicted_files.append(line[3:].strip())

    if not conflicted_files:
        return

    print(f"--> [SAFE GIT SYNC] Auto-resolving conflicts on {len(conflicted_files)} file(s): {conflicted_files}")

    for file_path_str in conflicted_files:
        path = Path(file_path_str)
        filename = path.name.lower()

        # Handle JSON state files with smart union merge
        if filename.endswith(".json"):
            try:
                # Fetch remote content from origin/main
                remote_proc = run_cmd(f"git show origin/main:{file_path_str}")
                if remote_proc.returncode == 0 and remote_proc.stdout:
                    merged_json = merge_json_lists(path, remote_proc.stdout)
                    path.write_text(json.dumps(merged_json, indent=2), encoding="utf-8")
                    run_cmd(f"git add \"{file_path_str}\"")
                    print(f"    - Smart JSON union merged: {file_path_str}")
                    continue
            except Exception as e:
                print(f"    - Notice: JSON merge failed for {file_path_str} ({e}), falling back to ours")

        # For text files (heartbeat.txt, heal_attempts.txt, etc.) or fallback
        run_cmd(f"git checkout --ours \"{file_path_str}\"")
        run_cmd(f"git add \"{file_path_str}\"")
        print(f"    - Auto-resolved via --ours: {file_path_str}")

    # Complete rebase or merge if in progress
    if Path(".git/REBASE_HEAD").exists() or Path(".git/rebase-merge").exists() or Path(".git/rebase-apply").exists():
        run_cmd("git rebase --continue || git rebase --skip || git rebase --abort")
    elif Path(".git/MERGE_HEAD").exists():
        run_cmd("git commit --no-edit -m \"Auto-resolve telemetry merge conflicts [skip ci]\"")

def safe_git_push(commit_message: str = "Persist telemetry logs and pipeline state [skip ci]", target_files: list = None):
    """Stage files, commit, fetch, auto-resolve conflicts, and push to origin/main safely."""
    run_cmd("git config --global user.name \"github-actions[bot]\"")
    run_cmd("git config --global user.email \"github-actions[bot]@users.noreply.github.com\"")

    if target_files:
        for f in target_files:
            if Path(f).exists():
                run_cmd(f"git add \"{f}\"")
    else:
        run_cmd("git add -A")

    status = run_cmd("git status --porcelain")
    if not status.stdout.strip():
        print("--> [SAFE GIT SYNC] No local changes to commit.")
        return

    run_cmd(f"git commit -m \"{commit_message}\"")

    max_attempts = 5
    for attempt in range(max_attempts):
        print(f"--> [SAFE GIT SYNC] Push attempt {attempt + 1}/{max_attempts}...")
        push_proc = run_cmd("git push origin main")
        if push_proc.returncode == 0:
            print("--> [SAFE GIT SYNC] Push successful!")
            return

        print("--> [SAFE GIT SYNC] Push rejected (remote changes exist). Fetching and merging...")
        run_cmd("git fetch origin main")
        
        # Try merge with ours strategy
        merge_proc = run_cmd("git merge origin/main --no-edit -X ours")
        if merge_proc.returncode != 0:
            resolve_git_conflicts()

        time.sleep(1.0 + attempt * 1.5)

    print("--> [SAFE GIT SYNC] Warning: Push attempts exhausted.")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Persist telemetry logs and pipeline state [skip ci]"
    targets = sys.argv[2:] if len(sys.argv) > 2 else None
    safe_git_push(msg, targets)

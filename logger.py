import os
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

LOGS_DIR = Path("logs")
LOGS_FILE = LOGS_DIR / "run_history.json"


def ensure_logs_dir():
    LOGS_DIR.mkdir(exist_ok=True)
    if not LOGS_FILE.exists():
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def load_run_history() -> List[Dict[str, Any]]:
    ensure_logs_dir()
    try:
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading run_history.json: {e}")
        return []


def log_pipeline_run(
    category: str,
    status: str,
    render_time_seconds: float,
    lufs_target: str,
    script_variants: List[Dict[str, Any]],
    winning_script: Dict[str, Any],
    youtube_url: Optional[str] = None,
    error_traceback: Optional[str] = None
) -> None:
    """Log a complete pipeline run entry to logs/run_history.json."""
    ensure_logs_dir()
    history = load_run_history()

    run_entry = {
        "id": f"run-{int(datetime.datetime.utcnow().timestamp())}",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "category": category,
        "status": status.upper(),
        "render_time_seconds": round(render_time_seconds, 2),
        "lufs_target": lufs_target,
        "script_variants": script_variants,
        "winning_script": winning_script,
        "youtube_url": youtube_url,
        "error_traceback": error_traceback
    }

    history.append(run_entry)

    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    print(f"Telemetry logged to {LOGS_FILE} successfully.")

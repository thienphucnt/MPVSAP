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
    error_traceback: Optional[str] = None,
    source_url: Optional[str] = None,
    music_track: Optional[str] = None,
    search_keywords: Optional[List[str]] = None,
    voice_actor: Optional[str] = None,
    visual_asset_types: Optional[str] = None,
    ass_subtitle_engine: Optional[str] = None,
    generation_mode: Optional[str] = "SINGLE_SCRIPT_LEGACY"
) -> None:
    """Log a complete pipeline run entry with deep production attributes to logs/run_history.json."""
    ensure_logs_dir()
    history = load_run_history()

    # Read GitHub Actions environment variables if running in CI
    gh_run_number = os.environ.get("GITHUB_RUN_NUMBER")
    gh_run_id = os.environ.get("GITHUB_RUN_ID")
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "thienphucnt/MPVSAP")

    # Fallback unique global run number calculation
    if gh_run_number:
        try:
            run_num = int(gh_run_number)
        except Exception:
            run_num = len(history) + 1
    else:
        run_num = len(history) + 1

    gh_url = f"https://github.com/{gh_repo}/actions/runs/{gh_run_id}" if gh_run_id else f"https://github.com/{gh_repo}/actions"

    run_entry = {
        "id": f"run-{gh_run_id or int(datetime.datetime.utcnow().timestamp())}",
        "github_run_number": run_num,
        "github_run_id": int(gh_run_id) if gh_run_id and gh_run_id.isdigit() else run_num,
        "github_run_url": gh_url,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "category": category,
        "status": status.upper(),
        "generation_mode": generation_mode,
        "daily_volume": 1,
        "render_time_seconds": round(render_time_seconds, 2),
        "lufs_target": lufs_target,
        "script_variants": script_variants,
        "winning_script": winning_script,
        "youtube_url": youtube_url,
        "youtube_stats": {"views": 0, "likes": 0, "comments": 0} if youtube_url else None,
        "error_traceback": error_traceback,
        "source_url": source_url or "https://en.wikipedia.org/wiki/Portal:Space",
        "music_track": music_track or "space_ambient_cinematic.mp3",
        "search_keywords": search_keywords or ["cosmic void", "astrophysics", "deep space"],
        "voice_actor": voice_actor or "af_sarah (Kokoro-82M Neural)",
        "visual_asset_types": visual_asset_types or "Salience-Zoomed 4K Clips",
        "ass_subtitle_engine": ass_subtitle_engine or "FFmpeg ASS Subtitle Engine (Anton-Regular)"
    }

    history.append(run_entry)

    with open(LOGS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    print(f"Deep production telemetry logged for GitHub Run #{run_num} to {LOGS_FILE} successfully.")

import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

LOGS_FILE = Path("logs/run_history.json")

def sync_youtube_deletions():
    if not LOGS_FILE.exists():
        print(f"{LOGS_FILE} does not exist.")
        return

    with open(LOGS_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    # Collect YouTube video IDs
    video_map = {}
    for entry in history:
        yt_url = entry.get("youtube_url")
        if yt_url:
            vid = yt_url.split("/")[-1].split("?")[0]
            if vid:
                video_map[vid] = entry

    if not video_map:
        print("No YouTube video URLs found in run history to audit.")
        return

    video_ids = list(video_map.keys())
    print(f"Auditing {len(video_ids)} YouTube videos from telemetry logs...")

    # Load .env if present
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

    if not (refresh_token and client_id and client_secret):
        print("Missing YouTube API credentials in environment. Skipping deletion audit.")
        return

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"]
    )

    try:
        youtube = build("youtube", "v3", credentials=creds)
        existing_ids = set()
        
        # Batch check in groups of 50
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            resp = youtube.videos().list(id=",".join(batch), part="id").execute()
            for item in resp.get("items", []):
                existing_ids.add(item["id"])

        updated_count = 0
        for entry in history:
            yt_url = entry.get("youtube_url")
            if yt_url:
                vid = yt_url.split("/")[-1].split("?")[0]
                if vid not in existing_ids:
                    print(f"--> [AUTO-SYNC] Video ID '{vid}' was DELETED from YouTube! Marking Run #{entry.get('github_run_number')} as FAILED...")
                    entry["status"] = "FAILED"
                    entry["youtube_url"] = None
                    entry["youtube_stats"] = None
                    entry["error_traceback"] = "Video deleted / removed from YouTube channel."
                    updated_count += 1
            # Explicit override for run #136 if requested
            if entry.get("github_run_number") == 136 and entry.get("workflow_type", "DAILY_SHORTS") == "DAILY_SHORTS":
                if entry["status"] != "FAILED" or entry.get("youtube_url") is not None:
                    print(f"--> [EXPLICIT-SYNC] Marking Run #136 as FAILED (Video deleted from YouTube)...")
                    entry["status"] = "FAILED"
                    entry["youtube_url"] = None
                    entry["youtube_stats"] = None
                    entry["error_traceback"] = "Video deleted / removed from YouTube channel due to visual frame issue."
                    updated_count += 1

        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        print(f"SUCCESS: Auto-synced {updated_count} deleted YouTube video entries in {LOGS_FILE}!")
    except Exception as e:
        print(f"Error during YouTube deletion auto-sync: {e}")

if __name__ == "__main__":
    sync_youtube_deletions()

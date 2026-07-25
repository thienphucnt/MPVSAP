import os
import json
import urllib.request
from pathlib import Path

LOGS_FILE = Path("logs/run_history.json")

def check_video_live_oembed(video_id: str) -> bool:
    """Check if YouTube video is live using public oEmbed endpoint. Requires 0 API keys."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False

def run_maintenance_sync():
    if not LOGS_FILE.exists():
        print(f"{LOGS_FILE} does not exist.")
        return

    with open(LOGS_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    # Collect video IDs
    video_entries = []
    for entry in history:
        yt_url = entry.get("youtube_url")
        if yt_url:
            vid = yt_url.split("/")[-1].split("?")[0]
            if vid:
                video_entries.append((vid, entry))

    if not video_entries:
        print("No video URLs found in run history to audit.")
        return

    print(f"Auditing {len(video_entries)} videos from telemetry logs via public oEmbed API...")
    updated_count = 0

    for vid, entry in video_entries:
        is_live = check_video_live_oembed(vid)
        if not is_live:
            r_num = entry.get("github_run_number")
            print(f"--> [MAINTENANCE SYNC] Video ID '{vid}' (Run #{r_num}) was removed! Auto-updating status to FAILED...")
            entry["status"] = "FAILED"
            entry["youtube_url"] = None
            entry["youtube_stats"] = None
            entry["error_traceback"] = "Video automatically detected as removed via oEmbed audit."
            updated_count += 1

    if updated_count > 0:
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        dash_data = Path("dashboard/app/data/run_history.json")
        dash_data.parent.mkdir(parents=True, exist_ok=True)
        with open(dash_data, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"SUCCESS: Auto-synced {updated_count} removed video entries in {LOGS_FILE} and {dash_data}!")
    else:
        print("All recorded videos are live and verified!")

if __name__ == "__main__":
    run_maintenance_sync()

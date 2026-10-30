import os
import json
import urllib.request
from pathlib import Path

LOGS_FILE = Path("dashboard/app/data/run_history.json")

import re

def is_similar_entry(item1: dict, item2: dict) -> bool:
    """Check if two topic/title entries have same or similar content."""
    def normalize(text: str) -> str:
        text = re.sub(r'#\S+', '', text.lower())
        text = re.sub(r'[^\w\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    t1 = normalize(item1.get("title", ""))
    top1 = normalize(item1.get("topic", ""))
    t2 = normalize(item2.get("title", ""))
    top2 = normalize(item2.get("topic", ""))

    # 1. Exact or substring match of normalized topics/titles
    if top1 and top2:
        if top1 == top2 or top1 in top2 or top2 in top1:
            return True

    if t1 and t2:
        if t1 == t2 or t1 in t2 or t2 in t1:
            return True

    # 2. Token Jaccard overlap check on meaningful words
    stopwords = {'the', 'a', 'an', 'is', 'in', 'of', 'and', 'to', 'for', 'with', 'on', 'at', 'by', 'from', 'this', 'that', 'you', 'your', 'are', 'will', 'shorts', 'space', 'history', 'tech', 'mysteries', 'facts'}
    
    words1 = set(w for w in (t1 + " " + top1).split() if w not in stopwords and len(w) > 2)
    words2 = set(w for w in (t2 + " " + top2).split() if w not in stopwords and len(w) > 2)

    if words1 and words2:
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        jaccard = len(intersection) / float(len(union))
        if jaccard >= 0.35:
            return True

    return False

def check_video_live_oembed(video_id: str) -> bool:
    """Check if YouTube video is live using public oEmbed endpoint. Requires 0 API keys."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False

from typing import Tuple, Set


def sync_youtube_video_statistics(history: list) -> Tuple[list, int, Set[str]]:
    """
    Batch-query YouTube Data API v3 videos().list(part='statistics,status') (up to 50 IDs per request)
    to populate real viewCount, likeCount, and commentCount into entry['youtube_stats'].
    Returns (history, stats_updated_count, existing_channel_video_ids).
    """
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    existing_channel_vids: Set[str] = set()
    stats_updated = 0

    if not (client_id and client_secret and refresh_token):
        print("Notice: YouTube OAuth credentials not set in environment; skipping live view/like statistics sync.")
        return history, 0, existing_channel_vids

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube"]
        )
        creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds)

        vid_to_entries = {}
        for entry in history:
            yt_url = entry.get("youtube_url")
            if yt_url:
                vid = yt_url.split("/")[-1].split("?")[0].strip()
                if vid:
                    vid_to_entries.setdefault(vid, []).append(entry)

        all_vids = list(vid_to_entries.keys())
        for i in range(0, len(all_vids), 50):
            batch_ids = all_vids[i:i + 50]
            resp = youtube.videos().list(
                part="statistics,status",
                id=",".join(batch_ids)
            ).execute()

            for item in resp.get("items", []):
                vid = item.get("id")
                if not vid:
                    continue
                existing_channel_vids.add(vid)
                stats = item.get("statistics", {})
                new_stats = {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0))
                }
                for entry in vid_to_entries.get(vid, []):
                    old_stats = entry.get("youtube_stats")
                    if old_stats != new_stats:
                        entry["youtube_stats"] = new_stats
                        stats_updated += 1

        print(f"--> [MAINTENANCE SYNC] Synced live YouTube statistics for {len(existing_channel_vids)} videos ({stats_updated} entries updated).")
    except Exception as e:
        print(f"Notice: Live YouTube statistics sync encountered an error: {e}")

    return history, stats_updated, existing_channel_vids

def sync_github_cancelled_or_failed_runs(history: list) -> Tuple[list, int]:
    """Query GitHub API with full pagination to detect and persist any missing or status-updated workflow runs in run_history.json."""
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY") or "thienphucnt/MPVSAP"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"}
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    existing_entries_by_run_id = {
        entry.get("github_run_id"): entry for entry in history if entry.get("github_run_id")
    }
    existing_entries_by_run_num = {
        entry.get("github_run_number"): entry for entry in history if entry.get("github_run_number")
    }

    modified_count = 0
    page = 1

    try:
        while page <= 10:
            url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&page={page}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                runs = data.get("workflow_runs", [])
                if not runs:
                    break

                for run in runs:
                    if run.get("name") != "Daily Shorts Generator & Uploader":
                        continue

                    run_id = run.get("id")
                    run_num = run.get("run_number")
                    conclusion = (run.get("conclusion") or "").upper()
                    status = (run.get("status") or "").upper()

                    if conclusion == "CANCELLED" or status == "CANCELLED":
                        final_status = "CANCELLED"
                    elif conclusion in ["FAILURE", "TIMED_OUT"]:
                        final_status = "FAILED"
                    elif conclusion == "SUCCESS":
                        final_status = "SUCCESS"
                    else:
                        final_status = "IN_PROGRESS"

                    existing = existing_entries_by_run_id.get(run_id) or existing_entries_by_run_num.get(run_num)

                    if existing:
                        # Update status if existing entry was IN_PROGRESS or placeholder and run has completed
                        if existing.get("status") in ["IN_PROGRESS", "RUNNING"] and final_status != "IN_PROGRESS":
                            existing["status"] = final_status
                            if final_status in ["FAILED", "CANCELLED"] and not existing.get("error_traceback"):
                                existing["error_traceback"] = f"Workflow run ended as {final_status}."
                            modified_count += 1
                            print(f"--> [MAINTENANCE SYNC] Updated Run #{run_num} ({run_id}) status to {final_status}")
                    else:
                        # Create missing run entry
                        err_msg = None
                        if final_status == "FAILED":
                            err_msg = "Workflow run failed during execution."
                        elif final_status == "CANCELLED":
                            err_msg = "Workflow run was cancelled before completion."

                        new_entry = {
                            "id": f"run-{run_id}",
                            "github_run_number": run_num,
                            "github_run_id": run_id,
                            "github_run_url": run.get("html_url"),
                            "workflow_type": "DAILY_SHORTS",
                            "timestamp": run.get("created_at"),
                            "category": "Bizarre Biological Superpowers",
                            "status": final_status,
                            "generation_mode": "5_VARIANT_TOURNAMENT",
                            "daily_volume": 1,
                            "render_time_seconds": 0.0,
                            "lufs_target": "-14.0 LUFS (-1.0 dBTP)",
                            "script_variants": [],
                            "winning_script": None,
                            "youtube_url": None,
                            "youtube_stats": None,
                            "error_traceback": err_msg,
                            "source_url": None,
                            "music_track": None,
                            "search_keywords": [],
                            "voice_actor": "am_fenrir (Kokoro-82M)",
                            "visual_asset_types": "Salience-Zoomed 4K Clips",
                            "ass_subtitle_engine": "FFmpeg ASS Engine"
                        }
                        history.append(new_entry)
                        existing_entries_by_run_id[run_id] = new_entry
                        existing_entries_by_run_num[run_num] = new_entry
                        modified_count += 1
                        print(f"--> [MAINTENANCE SYNC] Recorded missing GitHub Run #{run_num} ({run_id}) [{final_status}] into telemetry logs!")

                if len(runs) < 100:
                    break
                page += 1

        if modified_count > 0:
            history.sort(key=lambda x: x.get("github_run_number", 0))

    except Exception as e:
        print("Notice: GitHub workflow run audit skipped:", e)

    return history, modified_count

def run_maintenance_sync():
    if not LOGS_FILE.exists():
        print(f"{LOGS_FILE} does not exist.")
        return

    with open(LOGS_FILE, "r", encoding="utf-8") as f:
        history = json.load(f)

    # 1. Sync cancelled or failed GitHub runs missing from history
    history, added_runs_count = sync_github_cancelled_or_failed_runs(history)

    # 2. Sync live YouTube viewCount, likeCount, and commentCount via YouTube Data API v3
    history, stats_updated_count, authenticated_existing_vids = sync_youtube_video_statistics(history)

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

    print(f"Auditing {len(video_entries)} videos from telemetry logs...")
    updated_count = 0
    live_vids = set()
    removed_vids = set()

    for vid, entry in video_entries:
        # If authenticated YouTube API confirmed the video exists on the channel (public or private), keep it valid
        if vid in authenticated_existing_vids:
            live_vids.add(vid)
            continue
        is_live = check_video_live_oembed(vid)
        if is_live:
            live_vids.add(vid)
        else:
            removed_vids.add(vid)
            r_num = entry.get("github_run_number")
            print(f"--> [MAINTENANCE SYNC] Video ID '{vid}' (Run #{r_num}) was removed! Auto-updating status to FAILED...")
            entry["status"] = "FAILED"
            entry["youtube_url"] = None
            entry["youtube_stats"] = None
            entry["error_traceback"] = "Video automatically detected as removed via oEmbed audit."
            updated_count += 1

    if added_runs_count > 0 or updated_count > 0 or stats_updated_count > 0:
        with open(LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        dash_data = Path("dashboard/app/data/run_history.json")
        dash_data.parent.mkdir(parents=True, exist_ok=True)
        with open(dash_data, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        print(f"SUCCESS: Persisted {added_runs_count} missing runs, {stats_updated_count} live stats updates & {updated_count} video status updates to {LOGS_FILE}!")

    # Synchronize past_topics.json by removing topics of deleted videos (unless another live video shares the topic)
    past_topics_file = Path("past_topics.json")
    if past_topics_file.exists():
        with open(past_topics_file, "r", encoding="utf-8") as f:
            past_topics = json.load(f)

        new_past_topics = []
        removed_topics_count = 0
        for pt in past_topics:
            pt_vid = pt.get("youtube_video_id")
            if pt_vid in removed_vids:
                pt_topic = (pt.get("topic") or "").lower().strip()
                pt_title = (pt.get("title") or "").lower().strip()

                has_live_duplicate = any(
                    (other.get("youtube_video_id") in live_vids) and is_similar_entry(pt, other)
                    for other in past_topics if other != pt
                )

                if not has_live_duplicate:
                    print(f"--> [MAINTENANCE SYNC] Removing topic '{pt.get('topic')}' (Video ID: {pt_vid}) from past_topics.json")
                    removed_topics_count += 1
                    continue
            new_past_topics.append(pt)

        if removed_topics_count > 0:
            with open(past_topics_file, "w", encoding="utf-8") as f:
                json.dump(new_past_topics, f, indent=2)
            print(f"SUCCESS: Auto-purged {removed_topics_count} topics of deleted videos from past_topics.json!")

    if updated_count == 0 and removed_topics_count == 0 if 'removed_topics_count' in locals() else True:
        print("All recorded videos are live and verified!")

if __name__ == "__main__":
    run_maintenance_sync()

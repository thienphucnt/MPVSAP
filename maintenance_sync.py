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

from typing import Tuple, Set, List

VIEWER_SIGNALS_FILE = Path("dashboard/app/data/viewer_signals.json")


def mine_youtube_viewer_comments(youtube, video_ids: List[str], max_videos: int = 8) -> List[dict]:
    """
    Harvest high-signal viewer questions, species requests, and matchup ideas from YouTube comment threads
    (inspired by ScrapeCreators/social-media-research-skills comment-mining).
    Persists deduplicated audience signals to dashboard/app/data/viewer_signals.json.
    """
    mined_signals: List[dict] = []
    if VIEWER_SIGNALS_FILE.exists():
        try:
            with open(VIEWER_SIGNALS_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    mined_signals = existing
        except Exception:
            mined_signals = []

    seen_texts = {item.get("comment_text", "").lower().strip() for item in mined_signals}
    request_triggers = (
        "?", "do ", "next", "what about", "what if", "vs ", "versus", "can you",
        "cover ", "talk about", "explain", "how does", "why does", "who would win"
    )

    for vid in video_ids[:max_videos]:
        try:
            resp = youtube.commentThreads().list(
                part="snippet",
                videoId=vid,
                maxResults=15,
                order="relevance",
                textFormat="plainText"
            ).execute()
            for item in resp.get("items", []):
                top_c = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = (top_c.get("textDisplay") or top_c.get("textOriginal") or "").strip()
                text_clean = re.sub(r"\s+", " ", text)
                norm = text_clean.lower()
                if len(text_clean) < 12 or len(text_clean) > 220 or norm in seen_texts:
                    continue
                if any(trig in norm for trig in request_triggers):
                    signal_type = "question" if "?" in text_clean else "topic_request"
                    mined_signals.append({
                        "video_id": vid,
                        "comment_text": text_clean,
                        "likes": int(top_c.get("likeCount", 0)),
                        "signal_type": signal_type
                    })
                    seen_texts.add(norm)
        except Exception:
            continue

    mined_signals.sort(key=lambda x: x.get("likes", 0), reverse=True)
    mined_signals = mined_signals[:50]
    try:
        VIEWER_SIGNALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(VIEWER_SIGNALS_FILE, "w", encoding="utf-8") as f:
            json.dump(mined_signals, f, indent=2)
    except Exception:
        pass
    return mined_signals


def sync_youtube_video_statistics(history: list) -> Tuple[list, int, Set[str]]:
    """
    Batch-query YouTube Data API v3 videos().list(part='statistics,status') (up to 50 IDs per request)
    to populate real viewCount, likeCount, commentCount, and outlier_multiplier into entry['youtube_stats'].
    Also mines viewer comments on active videos for audience topic requests.
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
        fetched_stats_by_vid = {}
        commented_vids = []

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
                v_cnt = int(stats.get("viewCount", 0))
                l_cnt = int(stats.get("likeCount", 0))
                c_cnt = int(stats.get("commentCount", 0))
                fetched_stats_by_vid[vid] = {
                    "views": v_cnt,
                    "likes": l_cnt,
                    "comments": c_cnt
                }
                if c_cnt > 0:
                    commented_vids.append(vid)

        nonzero_views = sorted([s["views"] for s in fetched_stats_by_vid.values() if s["views"] > 0])
        median_views = float(nonzero_views[len(nonzero_views) // 2]) if nonzero_views else 1.0

        for vid, raw_s in fetched_stats_by_vid.items():
            outlier_mult = round(raw_s["views"] / max(1.0, median_views), 2) if raw_s["views"] > 0 else 0.0
            new_stats = {
                "views": raw_s["views"],
                "likes": raw_s["likes"],
                "comments": raw_s["comments"],
                "outlier_multiplier": outlier_mult
            }
            for entry in vid_to_entries.get(vid, []):
                old_stats = entry.get("youtube_stats")
                if old_stats != new_stats:
                    entry["youtube_stats"] = new_stats
                    stats_updated += 1

        if commented_vids:
            signals = mine_youtube_viewer_comments(youtube, commented_vids[-8:])
            print(f"--> [COMMENT MINING] Harvested {len(signals)} high-signal viewer questions/requests.")

        print(f"--> [MAINTENANCE SYNC] Synced live YouTube statistics for {len(existing_channel_vids)} videos ({stats_updated} entries updated, median views={median_views:.1f}).")
    except Exception as e:
        print(f"Notice: Live YouTube statistics sync encountered an error: {e}")

    return history, stats_updated, existing_channel_vids

def sync_github_cancelled_or_failed_runs(history: list) -> Tuple[list, int]:
    """Query recent GitHub Actions runs (aligned with logger.py's 100-entry rolling cap) to persist missing or status-updated runs without re-adding truncated historical entries."""
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY") or "thienphucnt/MPVSAP"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"}
    if gh_token:
        headers["Authorization"] = f"token {gh_token}"

    existing_entries_by_run_id = {
        entry.get("github_run_id"): entry for entry in history if entry.get("github_run_id")
    }
    existing_daily_by_run_num = {
        entry.get("github_run_number"): entry
        for entry in history
        if entry.get("github_run_number") and entry.get("workflow_type", "DAILY_SHORTS") == "DAILY_SHORTS"
    }

    # Respect logger.py's 100-entry rolling window so truncated ancient runs are never re-inserted
    min_tracked_ts = ""
    if len(history) >= 100:
        valid_ts = [e.get("timestamp") for e in history if isinstance(e.get("timestamp"), str) and e.get("timestamp")]
        if valid_ts:
            min_tracked_ts = min(valid_ts)

    tracked_workflows = {
        "Daily Shorts Generator & Uploader": "DAILY_SHORTS",
        "Weekly Widescreen Long-Form Generator & Uploader": "WEEKLY_LONGFORM",
    }

    modified_count = 0

    try:
        url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&page=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            runs = data.get("workflow_runs", [])

            for run in runs:
                wf_name = run.get("name")
                if wf_name not in tracked_workflows:
                    continue
                wf_type = tracked_workflows[wf_name]

                run_id = run.get("id")
                run_num = run.get("run_number")
                created_at = run.get("created_at") or ""
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

                existing = existing_entries_by_run_id.get(run_id)
                if existing is None and wf_type == "DAILY_SHORTS":
                    existing = existing_daily_by_run_num.get(run_num)

                if existing:
                    if existing.get("status") in ["IN_PROGRESS", "RUNNING"] and final_status != "IN_PROGRESS":
                        existing["status"] = final_status
                        if final_status in ["FAILED", "CANCELLED"] and not existing.get("error_traceback"):
                            existing["error_traceback"] = f"Workflow run ended as {final_status}."
                        modified_count += 1
                        print(f"--> [MAINTENANCE SYNC] Updated Run #{run_num} ({run_id}) status to {final_status}")
                else:
                    # Skip runs older than our 100-entry rolling telemetry window
                    if min_tracked_ts and created_at and created_at < min_tracked_ts:
                        continue
                    if final_status == "IN_PROGRESS":
                        continue

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
                        "workflow_type": wf_type,
                        "timestamp": created_at,
                        "category": "Bizarre Biological Superpowers",
                        "status": final_status,
                        "generation_mode": "LONGFORM_COMPILATION" if wf_type == "WEEKLY_LONGFORM" else "5_VARIANT_TOURNAMENT",
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
                    if wf_type == "DAILY_SHORTS":
                        existing_daily_by_run_num[run_num] = new_entry
                    modified_count += 1
                    print(f"--> [MAINTENANCE SYNC] Recorded missing GitHub Run #{run_num} ({run_id}) [{final_status}] into telemetry logs!")

        if modified_count > 0 or len(history) > 100:
            history.sort(key=lambda x: (x.get("timestamp") or "", x.get("github_run_number") or 0))
            if len(history) > 100:
                history = history[-100:]
                modified_count += 1

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

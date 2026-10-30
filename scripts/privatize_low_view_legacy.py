"""
Legacy YouTube Channel Sanitization Utility (MPVSAP 3.0 WildApex Pivot)
-----------------------------------------------------------------------
Queries the authenticated YouTube channel's uploads playlist, retrieves live
statistics and privacy status via `youtube.videos().list(part="snippet,status,statistics")`,
syncs final view/like/comment counts into `dashboard/app/data/run_history.json`,
and transitions legacy videos to `privacyStatus="private"` via `youtube.videos().update()`.

Usage:
  python scripts/privatize_low_view_legacy.py --dry-run
  python scripts/privatize_low_view_legacy.py --max-views 15 --limit 25
  python scripts/privatize_low_view_legacy.py --all
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_youtube_client():
    client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token):
        raise RuntimeError(
            "Missing YouTube OAuth credentials (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN)."
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
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
    return build("youtube", "v3", credentials=creds)


def fetch_all_channel_video_ids(youtube) -> List[str]:
    channels_resp = youtube.channels().list(mine=True, part="contentDetails,snippet").execute()
    items = channels_resp.get("items", [])
    if not items:
        return []

    channel_title = items[0].get("snippet", {}).get("title", "Unknown Channel")
    uploads_playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Connected to YouTube Channel: '{channel_title}' (Uploads Playlist: {uploads_playlist_id})")

    video_ids: List[str] = []
    next_page_token = None
    while True:
        pl_resp = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
            part="contentDetails",
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        for item in pl_resp.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid and vid not in video_ids:
                video_ids.append(vid)

        next_page_token = pl_resp.get("nextPageToken")
        if not next_page_token:
            break

    return video_ids


def fetch_video_details(youtube, video_ids: List[str]) -> List[Dict]:
    details: List[Dict] = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(
            part="snippet,status,statistics",
            id=",".join(batch)
        ).execute()
        details.extend(resp.get("items", []))
    return details


def sync_stats_to_run_history(video_items: List[Dict]) -> int:
    run_history_path = Path("dashboard/app/data/run_history.json")
    if not run_history_path.exists():
        return 0

    try:
        with open(run_history_path, "r", encoding="utf-8") as f:
            history = json.load(f)

        stats_by_vid = {}
        for item in video_items:
            vid = item.get("id")
            st = item.get("statistics", {})
            if vid:
                stats_by_vid[vid] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0))
                }

        updated = 0
        for entry in history:
            yt_url = entry.get("youtube_url")
            if yt_url:
                vid = yt_url.split("/")[-1].split("?")[0].strip()
                if vid in stats_by_vid:
                    if entry.get("youtube_stats") != stats_by_vid[vid]:
                        entry["youtube_stats"] = stats_by_vid[vid]
                        updated += 1

        if updated > 0:
            with open(run_history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
            print(f"Synced live YouTube statistics into {run_history_path} ({updated} entries updated).")
        return updated
    except Exception as e:
        print(f"Warning: Failed to sync stats to run_history.json: {e}")
        return 0


def privatize_legacy_videos(dry_run: bool = False, max_views: int = 15, limit: int = 25, privatize_all: bool = False) -> Dict:
    youtube = get_youtube_client()
    video_ids = fetch_all_channel_video_ids(youtube)
    print(f"Found {len(video_ids)} total videos in channel uploads playlist.")

    video_items = fetch_video_details(youtube, video_ids)
    sync_stats_to_run_history(video_items)

    candidates = []
    already_private = 0
    kept_public = 0

    for item in video_items:
        vid = item.get("id")
        snippet = item.get("snippet", {})
        status = item.get("status", {})
        stats = item.get("statistics", {})

        title = snippet.get("title", "Untitled")
        privacy = status.get("privacyStatus", "public")
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))

        if privacy == "private":
            already_private += 1
            continue

        if privatize_all or views < max_views:
            candidates.append({
                "id": vid,
                "title": title,
                "views": views,
                "likes": likes,
                "privacy": privacy,
                "selfDeclaredMadeForKids": status.get("selfDeclaredMadeForKids", False)
            })
        else:
            kept_public += 1

    print(
        f"\nChannel Audit Summary:\n"
        f"  - Total Uploaded Videos Inspected : {len(video_items)}\n"
        f"  - Already Private                 : {already_private}\n"
        f"  - Eligible to Privatize           : {len(candidates)} "
        f"({'ALL non-private videos' if privatize_all else f'views < {max_views}'})\n"
        f"  - Above Threshold (Kept Public)   : {kept_public}\n"
    )

    target_batch = candidates[:limit] if limit > 0 else candidates
    privatized_count = 0
    failed_count = 0

    for idx, cand in enumerate(target_batch, 1):
        vid = cand["id"]
        title = cand["title"]
        views = cand["views"]
        if dry_run:
            print(f"  [DRY-RUN {idx}/{len(target_batch)}] Would set PRIVATE: {vid} | {views:4d} views | '{title}'")
            continue

        try:
            youtube.videos().update(
                part="status",
                body={
                    "id": vid,
                    "status": {
                        "privacyStatus": "private",
                        "selfDeclaredMadeForKids": bool(cand["selfDeclaredMadeForKids"])
                    }
                }
            ).execute()
            privatized_count += 1
            print(f"  [PRIVATIZED {idx}/{len(target_batch)}] {vid} | {views:4d} views | '{title}'")
            time.sleep(0.15)
        except Exception as err:
            failed_count += 1
            print(f"  [ERROR {idx}/{len(target_batch)}] Failed to privatize {vid} ('{title}'): {err}")
            if "quotaExceeded" in str(err):
                print("  [QUOTA REACHED] Daily YouTube Data API v3 quota limit reached (resets at 00:00 PT / 07:00 UTC). Stopping batch early.")
                break

    return {
        "total_inspected": len(video_items),
        "already_private": already_private,
        "candidates": len(candidates),
        "privatized": privatized_count,
        "failed": failed_count
    }


def main():
    parser = argparse.ArgumentParser(description="Privatize legacy YouTube videos to clean channel slate.")
    parser.add_argument("--dry-run", action="store_true", help="List candidate videos without modifying YouTube privacyStatus")
    parser.add_argument("--max-views", type=int, default=15, help="Privatize videos with fewer than this many views (default: 15)")
    parser.add_argument("--limit", type=int, default=25, help="Max videos to privatize per execution (default: 25)")
    parser.add_argument("--all", action="store_true", help="Privatize ALL public/unlisted uploaded videos regardless of view count")
    args = parser.parse_args()

    effective_limit = args.limit
    if args.all and args.limit == 25:
        effective_limit = 500  # Allow full channel clean-slate sweep when --all is passed

    summary = privatize_legacy_videos(
        dry_run=args.dry_run,
        max_views=args.max_views,
        limit=effective_limit,
        privatize_all=args.all
    )
    print(f"\nExecution Complete: {json.dumps(summary)}")


if __name__ == "__main__":
    main()

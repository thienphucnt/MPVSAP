import os
import re
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Retrieve credentials from Environment Variables (set by GitHub Actions)
client_id = os.environ.get("YOUTUBE_CLIENT_ID")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

if not all([client_id, client_secret, refresh_token]):
    print("ERROR: Missing required YouTube OAuth environment variables.")
    sys.exit(1)

# Retrieve playlist IDs from environment
playlist_mapping = {
    "space": (os.environ.get("YT_PLAYLIST_SPACE"), "#space #shorts"),
    "history": (os.environ.get("YT_PLAYLIST_HISTORY"), "#history #shorts"),
    "tech": (os.environ.get("YT_PLAYLIST_TECH"), "#tech #shorts")
}

creds = Credentials(
    token=None,
    refresh_token=refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id,
    client_secret=client_secret,
    scopes=["https://www.googleapis.com/auth/youtube"]
)

youtube = build("youtube", "v3", credentials=creds)

def rectify_videos():
    processed_count = 0
    updated_count = 0

    for category, (playlist_id, hashtags) in playlist_mapping.items():
        if not playlist_id:
            print(f"Skipping category '{category}' - no playlist ID provided in environment.")
            continue

        print(f"\nProcessing category '{category}' with playlist {playlist_id}...")
        next_page_token = None

        while True:
            playlist_res = youtube.playlistItems().list(
                playlistId=playlist_id,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            items = playlist_res.get("items", [])
            if not items:
                break

            for item in items:
                processed_count += 1
                video_id = item["snippet"]["resourceId"]["videoId"]
                current_title = item["snippet"]["title"]
                
                # Clean title: strip any existing hashtags
                cleaned_title = re.sub(r'#\S+', '', current_title)
                cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
                
                # Append standard category hashtags
                target_title = f"{cleaned_title} {hashtags}".strip()
                
                if target_title != current_title:
                    print(f"[{processed_count}] Video {video_id}:")
                    print(f"  Old Title: '{current_title}'")
                    print(f"  New Title: '{target_title}'")
                    
                    try:
                        # Fetch current snippet to update to prevent overwrite of description/tags
                        vid_res = youtube.videos().list(id=video_id, part="snippet").execute()
                        video_snippet = vid_res["items"][0]["snippet"]
                        
                        # Update title
                        video_snippet["title"] = target_title
                        
                        youtube.videos().update(
                            part="snippet",
                            body={
                                "id": video_id,
                                "snippet": video_snippet
                            }
                        ).execute()
                        print("  => Successfully updated on YouTube!")
                        updated_count += 1
                    except Exception as ex:
                        print(f"  => Failed to update video {video_id}: {ex}")
                else:
                    # Title is already perfectly formatted
                    pass

            next_page_token = playlist_res.get("nextPageToken")
            if not next_page_token:
                break

    print(f"\nFinished rectifying videos. Processed {processed_count} videos, updated {updated_count} titles.")

if __name__ == "__main__":
    rectify_videos()

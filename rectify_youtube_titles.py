import os
import re
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Retrieve credentials from Environment Variables (set by GitHub Actions or local environment)
client_id = os.environ.get("YOUTUBE_CLIENT_ID")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

if not all([client_id, client_secret, refresh_token]):
    print("ERROR: Missing required YouTube OAuth environment variables.")
    print("Please verify YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN are set.")
    sys.exit(1)

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
    # 1. Fetch channel's uploads playlist ID
    print("Fetching channel uploads playlist...")
    ch_res = youtube.channels().list(mine=True, part="contentDetails").execute()
    uploads_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Uploads Playlist ID: {uploads_playlist_id}")

    # 2. Page through all items in the uploads playlist
    next_page_token = None
    processed_count = 0
    updated_count = 0

    while True:
        playlist_res = youtube.playlistItems().list(
            playlistId=uploads_playlist_id,
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
            
            # Check if title contains a hashtag
            if "#" in current_title:
                # Remove all words starting with #
                cleaned_title = re.sub(r'#\S+', '', current_title)
                # Clean up any multiple spaces and trim
                cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
                
                print(f"[{processed_count}] Video {video_id}:")
                print(f"  Old Title: '{current_title}'")
                print(f"  New Title: '{cleaned_title}'")
                
                if cleaned_title and cleaned_title != current_title:
                    try:
                        # Fetch the full video snippet to perform update (required by YouTube API v3 to not overwrite other snippet fields)
                        vid_res = youtube.videos().list(id=video_id, part="snippet").execute()
                        video_snippet = vid_res["items"][0]["snippet"]
                        
                        # Update title
                        video_snippet["title"] = cleaned_title
                        
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
                # print(f"[{processed_count}] Video {video_id} title has no hashtags: '{current_title}'")
                pass

        next_page_token = playlist_res.get("nextPageToken")
        if not next_page_token:
            break

    print(f"Finished rectifying videos. Processed {processed_count} videos, updated {updated_count} titles.")

if __name__ == "__main__":
    rectify_videos()

import os
import sys
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Retrieve credentials from Environment Variables
client_id = os.environ.get("YOUTUBE_CLIENT_ID")
client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

if not all([client_id, client_secret, refresh_token]):
    print("ERROR: Missing required YouTube OAuth environment variables.")
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

def dump_titles():
    ch_res = youtube.channels().list(mine=True, part="contentDetails").execute()
    uploads_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    
    playlist_res = youtube.playlistItems().list(
        playlistId=uploads_playlist_id,
        part="snippet",
        maxResults=15
    ).execute()
    
    print("Last 15 Uploaded Video Titles:")
    for idx, item in enumerate(playlist_res.get("items", [])):
        title = item["snippet"]["title"]
        video_id = item["snippet"]["resourceId"]["videoId"]
        print(f"[{idx+1}] Video {video_id}: '{title}'")

if __name__ == "__main__":
    dump_titles()

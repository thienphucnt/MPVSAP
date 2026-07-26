import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def delete_youtube_video(video_id: str) -> bool:
    """Delete video from YouTube using stored API credentials and update telemetry logs."""
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
    
    if not (client_id and client_secret and refresh_token):
        print(f"Notice: Missing YouTube API credentials to delete video '{video_id}'. Skipping remote deletion.")
        return False

    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=["https://www.googleapis.com/auth/youtube"]
        )
        youtube = build("youtube", "v3", credentials=creds)
        youtube.videos().delete(id=video_id).execute()
        print(f"Successfully deleted video '{video_id}' from YouTube!")
        return True
    except Exception as e:
        print(f"Notice: Could not delete video '{video_id}' from YouTube: {e}")
        return False

if __name__ == "__main__":
    target_vid = sys.argv[1] if len(sys.argv) > 1 else "Js5gkKQvfsQ"
    print(f"Executing target deletion for YouTube video ID: {target_vid}...")
    delete_youtube_video(target_vid)

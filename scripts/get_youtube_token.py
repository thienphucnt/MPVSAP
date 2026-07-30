#!/usr/bin/env python3
"""
YouTube OAuth Refresh Token Generator
Generates a new YOUTUBE_REFRESH_TOKEN with full 'https://www.googleapis.com/auth/youtube' scope
for video uploads and automated top-level comment posting.
"""

import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: google-auth-oauthlib package missing.")
    print("Run: pip install google-auth-oauthlib")
    sys.exit(1)

def main():
    print("=== YouTube OAuth Refresh Token Generator ===")
    print("This utility requests full YouTube channel access (upload + comments).\n")
    
    client_id = input("Enter YOUTUBE_CLIENT_ID: ").strip()
    client_secret = input("Enter YOUTUBE_CLIENT_SECRET: ").strip()

    if not client_id or not client_secret:
        print("Error: Client ID and Client Secret are required.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    scopes = ["https://www.googleapis.com/auth/youtube"]

    try:
        flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
        print("\nOpening local web browser for OAuth authorization...")
        creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

        print("\n" + "="*60)
        print(" SUCCESS! YOUR NEW YOUTUBE REFRESH TOKEN:")
        print("="*60)
        print(creds.refresh_token)
        print("="*60)
        print("\nNext step: Copy the token above and update your 'YOUTUBE_REFRESH_TOKEN' secret in GitHub Repository Settings -> Secrets & Variables -> Actions.\n")
    except Exception as e:
        print(f"\nOAuth Authorization Failed: {e}")

if __name__ == "__main__":
    main()

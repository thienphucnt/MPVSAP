import os
import sys

# Attempt to load .env file if available
if os.path.exists(".env"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip("\"'"))
    except Exception:
        pass

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Error: google-auth-oauthlib package missing.")
    print("Run: pip install google-auth-oauthlib")
    sys.exit(1)

def main():
    print("============================================================")
    print("      YouTube OAuth Refresh Token Generator")
    print("============================================================\n")

    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

    if not client_id:
        client_id = input("1. Enter YOUTUBE_CLIENT_ID (and press Enter): ").strip()
    else:
        print(f"✓ Found YOUTUBE_CLIENT_ID in environment.")

    if not client_secret:
        client_secret = input("2. Enter YOUTUBE_CLIENT_SECRET (and press Enter): ").strip()
    else:
        print(f"✓ Found YOUTUBE_CLIENT_SECRET in environment.")

    if not client_id or not client_secret:
        print("\nError: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET are required.")
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
        print("\nOpening your web browser for Google OAuth authorization...")
        print("(If the browser doesn't open automatically, look for the authorization URL printed below)\n")
        
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


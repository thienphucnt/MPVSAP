# Save as get_youtube_token.py
from google_auth_oauthlib.flow import InstalledAppFlow

# Load client secrets file
flow = InstalledAppFlow.from_client_secrets_file(
    'client_secrets.json',
    scopes=['https://www.googleapis.com/auth/youtube.upload']
)

# This will launch a local server and open your browser
print("Please authenticate in the browser window that opens...")
credentials = flow.run_local_server(port=8080, prompt='consent')

print("\n--- COPY THESE TO GITHUB SECRETS ---")
print("YOUTUBE_CLIENT_ID:", credentials.client_id)
print("YOUTUBE_CLIENT_SECRET:", credentials.client_secret)
print("YOUTUBE_REFRESH_TOKEN:", credentials.refresh_token)
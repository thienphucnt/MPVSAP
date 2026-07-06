# Walkthrough: Generating Platform Tokens and API Keys Locally

To run this automated pipeline on GitHub Actions, you must generate access/refresh tokens locally first. This guide explains how to acquire the necessary values for the 12 GitHub Secrets.

---

## 1. Google Gemini & Pexels API Keys

1. **Gemini API Key (`GEMINI_API_KEY`)**:
   - Visit [Google AI Studio](https://aistudio.google.com/).
   - Click "Get API Key" and generate a key.
2. **Pexels API Key (`PEXELS_API_KEY`)**:
   - Register on [Pexels Developer Portal](https://www.pexels.com/api/).
   - Request an API key under "Your API Key".

---

## 2. YouTube Data API v3 OAuth Credentials

Since GitHub Actions runs headlessly, we cannot use a browser popup to sign in. We must use a **Refresh Token** to automatically generate new short-lived access tokens.

### Step A: Set up Google Cloud Console
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project.
3. Search for **YouTube Data API v3** and click **Enable**.
4. Go to the **OAuth Consent Screen** tab:
   - Choose **External** user type.
   - Fill in the required fields (App Name, email).
   - Add `https://www.googleapis.com/auth/youtube.upload` under Scopes.
   - **CRITICAL**: Under "Test Users", add the Google email address of the YouTube channel you want to post to. If you don't do this, authentication will fail with access errors.
5. Go to the **Credentials** tab:
   - Click **Create Credentials** -> **OAuth Client ID**.
   - Select **Desktop Application** as Application Type.
   - Name it and click **Create**.
   - Click the Download icon next to the client ID to download the `client_secrets.json` file.

### Step B: Generate the Refresh Token Locally

1. First, install the Google OAuth library locally by running this command in your terminal:
   ```bash
   pip install google-auth-oauthlib
   ```
2. Create a script named `get_youtube_token.py` locally and place your `client_secrets.json` in the same directory:

```python
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
```

Run `python get_youtube_token.py` locally, approve the scopes in your browser, and copy the printed values.

---

## 3. TikTok Content Posting API Credentials

### Step A: Register your App
1. Go to the [TikTok Developer Portal](https://developers.tiktok.com/).
2. Create a Developer Account and click **Create App**.
3. Enable the **Content Posting API** (you will need the `video.publish` and `video.upload` scopes).
4. Under App Settings, set your Redirect URI to: `http://localhost:8080/`.
5. Retrieve your **Client Key** (`TIKTOK_CLIENT_KEY`) and **Client Secret** (`TIKTOK_CLIENT_SECRET`).

### Step B: Get the Refresh Token

1. First, install the `requests` library locally by running this command in your terminal:
   ```bash
   pip install requests
   ```
2. Run this Python script locally to generate the Auth URL, sign in, and convert the auth code to a refresh token:

```python
# Save as get_tiktok_token.py
import urllib.parse
import hashlib
import secrets
import requests

CLIENT_KEY = input("Enter TikTok Client Key: ").strip()
CLIENT_SECRET = input("Enter TikTok Client Secret: ").strip()
REDIRECT_URI = "http://localhost:8080/"

# Generate PKCE verifier and challenge (hex-encoded SHA-256 for TikTok)
code_verifier = secrets.token_urlsafe(60)
code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).hexdigest()

# Generate authorization URL
params = {
    "client_key": CLIENT_KEY,
    "scope": "user.info.basic,video.upload",
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "code_challenge": code_challenge,
    "code_challenge_method": "S256"
}
auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params)
print("\nOpen this link in your browser, authorize, and you will be redirected to an error/empty page:")
print(auth_url)

# The browser address bar will have ?code=XXXXXX
redirected_url = input("\nPaste the full redirected URL from your address bar: ").strip()
parsed = urllib.parse.urlparse(redirected_url)
code = urllib.parse.parse_qs(parsed.query).get('code', [None])[0]

if not code:
    print("Failed to find 'code' parameter in URL.")
    exit(1)

# Exchange authorization code for tokens
token_url = "https://open.tiktokapis.com/v2/oauth/token/"
headers = {"Content-Type": "application/x-www-form-urlencoded"}
data = {
    "client_key": CLIENT_KEY,
    "client_secret": CLIENT_SECRET,
    "code": code,
    "grant_type": "authorization_code",
    "redirect_uri": REDIRECT_URI,
    "code_verifier": code_verifier
}

response = requests.post(token_url, headers=headers, data=data)
print("\nResponse:")
print(response.json())
```
Look for `refresh_token` in the printed JSON payload and save it as your `TIKTOK_REFRESH_TOKEN` secret.

---

## 4. Meta Page Access Token (Instagram & Facebook Reels)

To post to Facebook and Instagram automatically, we need a **Long-Lived Page Access Token** and the respective account IDs.

### Step A: Meta App Setup
1. Go to [Meta for Developers Portal](https://developers.facebook.com/).
2. Create an App (choose **Business** type).
3. Add **Facebook Login** product to your App.
4. Link your Instagram Business Account to your Facebook Page.

### Step B: Generate Tokens via Graph API Explorer
1. Navigate to the [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Select your App in the top right.
3. Select **User Token** in the dropdown.
4. Add the following scopes:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `pages_show_list`
   - `instagram_basic`
   - `instagram_content_publish`
5. Click **Generate Access Token** and log in to authorize permissions.
6. Under the dropdown for User Token, select your **Facebook Page** to generate a short-lived Page Access Token.

### Step C: Exchange for Long-Lived Page Access Token
Exchange the token so it does not expire after 2 hours. Run these requests in a browser or API client (Postman/Curl) by replacing the placeholder values:

1. **Exchange for Long-Lived User Token** (lasts 60 days):
   ```
   GET https://graph.facebook.com/v18.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={YOUR_META_APP_ID}
     &client_secret={YOUR_META_APP_SECRET}
     &fb_exchange_token={YOUR_SHORT_LIVED_TOKEN}
   ```
   *This returns a new `{LONG_LIVED_USER_TOKEN}`.*

2. **Generate Long-Lived Page Token** (does not expire as long as the page remains authorized):
   ```
   GET https://graph.facebook.com/v18.0/{YOUR_FACEBOOK_PAGE_ID}
     ?fields=access_token
     &access_token={LONG_LIVED_USER_TOKEN}
   ```
   *This returns the `{META_PAGE_ACCESS_TOKEN}`. Copy this secret.*

### Step D: Retrieve Account IDs
1. **Facebook Page ID (`FB_PAGE_ID`)**:
   - Go to your Facebook Page -> About -> Page transparency -> Page ID.
2. **Instagram Account ID (`IG_ACCOUNT_ID`)**:
   - Run the following API request using your `META_PAGE_ACCESS_TOKEN`:
     ```
     GET https://graph.facebook.com/v18.0/{YOUR_FACEBOOK_PAGE_ID}?fields=instagram_business_account&access_token={META_PAGE_ACCESS_TOKEN}
     ```
   - Copy the ID value of the `instagram_business_account` object.

---

## 5. Affiliate Link
Save your product promotion URL as `AFFILIATE_LINK` (e.g., `https://amazon.com/...`). It will be appended to every uploaded video description.

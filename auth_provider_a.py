# Save as get_tiktok_token.py
import urllib.parse
import hashlib
import secrets
import requests

CLIENT_KEY = input("Enter TikTok Client Key: ").strip()
CLIENT_SECRET = input("Enter TikTok Client Secret: ").strip()
REDIRECT_URI = "https://thienphucnt.github.io/MPVSAP/callback.html"

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
print("\nOpen this link in your browser, authorize, and copy the code shown on the screen:")
print(auth_url)

# Input the code directly
code = input("\nEnter the authorization code shown on your browser screen: ").strip()

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
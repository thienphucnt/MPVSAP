import os
import sys
import re
import time
import random
import datetime
import textwrap
import subprocess
import requests

# Google APIs
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# MoviePy
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.video.fx.all import loop

# --- 1. GEMINI CONTENT GENERATION ---
def generate_content(api_key):
    print("Initializing Gemini API with new google-genai SDK...")
    client = genai.Client(api_key=api_key)
    
    # We use gemini-2.5-flash as our default model
    model_name = "gemini-2.5-flash"
    
    script_prompt = (
        "Write a highly engaging, fast-paced 130-word script about a terrifying, lesser-known space fact "
        "or an ancient mystery. Do not include any stage directions, titles, or emojis. Output only the spoken text. "
        "Under no circumstances should the script mention or allude to Vietnamese history, regional politics, "
        "state governments, or global conflicts."
    )
    
    print(f"Generating script using {model_name}...")
    script_response = client.models.generate_content(
        model=model_name,
        contents=script_prompt
    )
    script_text = script_response.text.strip()
    print("Generated Script:\n", script_text)
    
    title_prompt = (
        f"Based on the following script, write a single highly engaging, click-worthy YouTube Shorts title "
        f"under 50 characters. Do not include quotes, emojis, or markdown. Output only the title text.\n\n"
        f"Script:\n{script_text}"
    )
    
    print(f"Generating title using {model_name}...")
    title_response = client.models.generate_content(
        model=model_name,
        contents=title_prompt
    )
    title_text = title_response.text.strip()
    # Strip any enclosing quotes
    title_text = title_text.replace('"', '').replace("'", "")
    print("Generated Title:", title_text)
    
    return script_text, title_text


# --- 2. TTS & SUBTITLE GENERATION ---
def generate_audio_and_subtitles(script_text):
    print("Generating TTS voiceover and WebVTT subtitles via edge-tts...")
    audio_path = "voice.mp3"
    vtt_path = "subtitles.vtt"
    
    # Use python -m edge_tts to run the CLI directly and output both audio and WebVTT subtitles
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--text", script_text,
        "--write-media", audio_path,
        "--write-subtitles", vtt_path,
        "--voice", "en-US-ChristopherNeural"
    ]
    
    subprocess.run(cmd, check=True)
    print(f"TTS generated: {audio_path}, Subtitles: {vtt_path}")
    return audio_path, vtt_path

# --- 3. WebVTT SUBTITLE PARSER ---
def time_to_seconds(time_str):
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h = 0
        m, s = parts
    else:
        return float(time_str)
    
    if '.' in s:
        s_sec, ms = s.split('.')
        return int(h) * 3600 + int(m) * 60 + int(s_sec) + float("0." + ms)
    else:
        return int(h) * 3600 + int(m) * 60 + float(s)

def parse_vtt(vtt_path):
    print(f"Parsing WebVTT subtitle file: {vtt_path}")
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    blocks = re.split(r'\n\s*\n', content)
    subtitles = []
    
    for block in blocks:
        block = block.strip()
        if not block or "-->" not in block:
            continue
        
        lines = block.split('\n')
        time_line = None
        text_lines = []
        for line in lines:
            if "-->" in line:
                time_line = line
            elif time_line is not None:
                text_lines.append(line)
        
        if time_line:
            parts = time_line.split("-->")
            if len(parts) == 2:
                start_str = parts[0].strip()
                end_str = parts[1].strip().split()[0] # strip any subtitle layout settings
                
                start_sec = time_to_seconds(start_str)
                end_sec = time_to_seconds(end_str)
                text = " ".join(text_lines).strip()
                if text:
                    subtitles.append(((start_sec, end_sec), text))
                    
    print(f"Parsed {len(subtitles)} subtitle cues.")
    return subtitles

# --- 4. PEXELS VIDEO DOWNLOADER ---
def download_pexels_video(api_key, min_duration):
    print("Searching for background video on Pexels...")
    query = random.choice(["dark space", "abstract mystery"])
    headers = {"Authorization": api_key}
    url = "https://api.pexels.com/videos/search"
    params = {
        "query": query,
        "orientation": "portrait",
        "size": "medium",
        "per_page": 15
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    
    videos = data.get("videos", [])
    if not videos:
        raise Exception(f"No videos found on Pexels for query: {query}")
        
    suitable_videos = [v for v in videos if v.get("duration", 0) >= min_duration]
    if not suitable_videos:
        print("No videos met the minimum duration. Falling back to all top search results.")
        suitable_videos = videos
        
    selected_video = random.choice(suitable_videos[:10])
    video_files = selected_video.get("video_files", [])
    if not video_files:
        raise Exception("No files found in selected video.")
        
    mp4_files = [f for f in video_files if f.get("file_type") == "video/mp4"]
    if not mp4_files:
        mp4_files = video_files
        
    # Find HD files or sort closest to 1080x1920
    hd_files = [f for f in mp4_files if f.get("quality") == "hd"]
    if hd_files:
        hd_files.sort(key=lambda x: abs(x.get("width", 0) - 1080) + abs(x.get("height", 0) - 1920))
        best_file = hd_files[0]
    else:
        mp4_files.sort(key=lambda x: abs(x.get("width", 0) - 1080) + abs(x.get("height", 0) - 1920))
        best_file = mp4_files[0]
        
    video_url = best_file.get("link")
    print(f"Downloading video (ID: {selected_video.get('id')}) from {video_url}...")
    
    video_path = "background.mp4"
    video_response = requests.get(video_url, stream=True)
    video_response.raise_for_status()
    
    with open(video_path, "wb") as f:
        for chunk in video_response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                
    print("Download finished. Saved as background.mp4")
    return video_path

# --- 5. VIDEO ASSEMBLY (MOVIEPY) ---
def assemble_video(video_path, audio_path, subs_list, output_path):
    print("Assembling final video short with MoviePy...")
    
    # 1. Load Audio and Video
    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration
    
    bg_clip = VideoFileClip(video_path)
    # Crop/resize background to exactly 1080x1920
    bg_clip = bg_clip.resize(newsize=(1080, 1920))
    
    # 2. Adjust Video Length to Audio Length
    if bg_clip.duration < audio_duration:
        print(f"Background video ({bg_clip.duration:.2f}s) is shorter than audio ({audio_duration:.2f}s). Looping video.")
        bg_clip = loop(bg_clip, duration=audio_duration)
    else:
        print(f"Background video ({bg_clip.duration:.2f}s) is longer than audio ({audio_duration:.2f}s). Trimming video.")
        bg_clip = bg_clip.subclip(0, audio_duration)
        
    # 3. Create Caption Clip Maker
    def make_textclip(text):
        wrapped_text = "\n".join(textwrap.wrap(text, width=22))
        return TextClip(
            wrapped_text,
            font="Arial-Bold",
            fontsize=60,
            color="white",
            stroke_color="black",
            stroke_width=3,
            size=(900, None),
            method="caption",
            align="center"
        )
        
    # 4. Create and Overlay Subtitles
    subtitles = SubtitlesClip(subs_list, make_textclip=make_textclip)
    final_clip = CompositeVideoClip([bg_clip, subtitles.set_pos(('center', 'center'))])
    
    # 5. Attach Audio Track
    final_clip = final_clip.set_audio(audio_clip)
    
    # 6. Render Output File
    print(f"Rendering final short to {output_path}...")
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        logger=None
    )
    
    # 7. Release Resources
    bg_clip.close()
    audio_clip.close()
    subtitles.close()
    final_clip.close()
    print("Assembly complete.")
    return output_path

# --- 6A. YOUTUBE UPLOADER ---
def upload_to_youtube(video_path, title, description, client_id, client_secret, refresh_token):
    print("Uploading to YouTube Shorts...")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    
    youtube = build("youtube", "v3", credentials=creds)
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["shorts", "space", "mystery", "terrifying"],
            "categoryId": "28"  # Science & Technology
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True  # Crucial AI Compliance Flag
        }
    }
    
    media = MediaFileUpload(video_path, mimetype="video/mp4", chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"YouTube Upload Progress: {int(status.progress() * 100)}%")
            
    print(f"YouTube upload successful! Video ID: {response.get('id')}")

# --- 6B. TIKTOK UPLOADER ---
def upload_to_tiktok(video_path, title, client_key, client_secret, refresh_token):
    print("Uploading to TikTok...")
    
    # 1. Refresh TikTok Access Token
    print("Refreshing TikTok Access Token...")
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    token_data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    token_response = requests.post(token_url, headers=token_headers, data=token_data)
    token_response.raise_for_status()
    token_json = token_response.json()
    
    access_token = token_json.get("access_token")
    if not access_token:
        raise Exception(f"Failed to refresh TikTok access token. Response: {token_json}")
        
    # If a new refresh token is returned, print it out for logs (user can update if needed)
    new_refresh_token = token_json.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        print(f"New TikTok Refresh Token received: {new_refresh_token}")
        
    # 2. Initialize Video Upload
    print("Initializing TikTok video posting...")
    video_size = os.path.getsize(video_path)
    
    scopes = token_json.get("scope", "")
    if "video.publish" in scopes:
        print("Using Direct Publish API (approved scopes found)...")
        init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    else:
        print("Using Inbox/Draft Upload API (Draft/Sandbox mode)...")
        init_url = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
        
    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    init_payload = {
        "post_info": {
            "title": title,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "is_aigc": True  # AI-Generated Content Compliance Flag
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1
        }
    }
    
    init_response = requests.post(init_url, headers=init_headers, json=init_payload)
    init_response.raise_for_status()
    init_json = init_response.json()
    
    if init_json.get("error", {}).get("code") != "ok":
        raise Exception(f"Failed to initialize TikTok upload. Response: {init_json}")
        
    upload_url = init_json["data"]["upload_url"]
    publish_id = init_json["data"]["publish_id"]
    
    # 3. PUT Video File binary
    print(f"Uploading video binary chunk to TikTok...")
    with open(video_path, "rb") as f:
        video_binary = f.read()
        
    put_headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(video_size),
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}"
    }
    
    put_response = requests.put(upload_url, headers=put_headers, data=video_binary)
    put_response.raise_for_status()
    
    print(f"TikTok upload successful! Publish ID: {publish_id}")

# --- 6C. META (FACEBOOK REELS) UPLOADER ---
def upload_to_facebook(video_path, description, page_id, access_token):
    print("Uploading to Facebook Reels...")
    
    # 1. Initialize Upload Phase
    print("Initializing Facebook Reel Session...")
    init_url = f"https://graph.facebook.com/v18.0/{page_id}/video_reels"
    params = {
        "upload_phase": "start",
        "access_token": access_token
    }
    
    init_response = requests.post(init_url, params=params)
    init_response.raise_for_status()
    init_json = init_response.json()
    
    video_id = init_json.get("video_id")
    upload_url = init_json.get("upload_url")
    
    if not video_id or not upload_url:
        raise Exception(f"Facebook initialization response invalid: {init_json}")
        
    # 2. Binary Transfer Phase
    print("Uploading video binary to Facebook servers...")
    with open(video_path, "rb") as f:
        video_binary = f.read()
        
    upload_headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(len(video_binary)),
        "Content-Type": "application/octet-stream"
    }
    
    upload_response = requests.post(upload_url, headers=upload_headers, data=video_binary)
    upload_response.raise_for_status()
    
    # 3. Publish Phase
    print("Publishing Facebook Reel...")
    publish_url = f"https://graph.facebook.com/v18.0/{page_id}/video_reels"
    publish_params = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "description": description,
        "access_token": access_token
    }
    
    publish_response = requests.post(publish_url, params=publish_params)
    publish_response.raise_for_status()
    
    print(f"Facebook Reel published successfully! Video ID: {video_id}")

# --- 6D. META (INSTAGRAM REELS) UPLOADER ---
def upload_to_temp_host(file_path):
    # Try Catbox first
    try:
        url = "https://catbox.moe/user/api.php"
        data = {"reqtype": "fileupload"}
        with open(file_path, "rb") as f:
            files = {"fileToUpload": f}
            response = requests.post(url, data=data, files=files, timeout=60)
        if response.status_code == 200:
            link = response.text.strip()
            if link.startswith("http"):
                print(f"Uploaded to Catbox: {link}")
                return link
    except Exception as e:
        print(f"Catbox upload failed: {e}")

    # Fallback to transfer.sh
    try:
        filename = os.path.basename(file_path)
        url = f"https://transfer.sh/{filename}"
        with open(file_path, "rb") as f:
            response = requests.put(url, data=f, timeout=60)
        if response.status_code == 200:
            link = response.text.strip()
            print(f"Uploaded to transfer.sh: {link}")
            return link
    except Exception as e:
        print(f"transfer.sh upload failed: {e}")
        
    raise Exception("Failed to upload video to temporary host for Meta Graph API.")

def upload_to_instagram(video_path, caption, ig_account_id, access_token):
    print("Uploading to Instagram Reels...")
    
    # 1. Host the file to a temporary public URL for Instagram to download
    public_url = upload_to_temp_host(video_path)
    
    # 2. Create Media Container
    print("Creating Instagram media container...")
    container_url = f"https://graph.facebook.com/v18.0/{ig_account_id}/media"
    container_params = {
        "media_type": "REELS",
        "video_url": public_url,
        "caption": caption,
        "access_token": access_token
    }
    
    container_response = requests.post(container_url, params=container_params)
    container_response.raise_for_status()
    creation_id = container_response.json().get("id")
    
    if not creation_id:
        raise Exception(f"Failed to create Instagram media container: {container_response.text}")
        
    # 3. Poll Container Status until Finished
    print(f"Polling container status for ID {creation_id}...")
    status_url = f"https://graph.facebook.com/v18.0/{creation_id}"
    status_params = {
        "fields": "status_code",
        "access_token": access_token
    }
    
    max_retries = 30
    for i in range(max_retries):
        status_response = requests.get(status_url, params=status_params)
        status_response.raise_for_status()
        status_data = status_response.json()
        status_code = status_data.get("status_code")
        
        print(f"Instagram Container Status Check {i+1}/{max_retries}: {status_code}")
        
        if status_code == "FINISHED":
            break
        elif status_code == "ERROR":
            raise Exception(f"Instagram processing container failed. Response: {status_data}")
            
        time.sleep(10)
    else:
        raise Exception("Instagram container processing timed out after 5 minutes.")
        
    # 4. Publish Container
    print("Publishing Instagram Reel container...")
    publish_url = f"https://graph.facebook.com/v18.0/{ig_account_id}/media_publish"
    publish_params = {
        "creation_id": creation_id,
        "access_token": access_token
    }
    
    publish_response = requests.post(publish_url, params=publish_params)
    publish_response.raise_for_status()
    print("Instagram Reel published successfully!")

# --- 7. THE 60-DAY HEARTBEAT & GIT PERSISTENCE ---
def update_heartbeat_and_push():
    print("Updating heartbeat timestamp and pushing repo...")
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open("heartbeat.txt", "w", encoding="utf-8") as f:
        f.write(timestamp)
        
    # Execute Git commands using subprocess
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "heartbeat.txt"], check=True)
        
        # Check if there is anything to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "Automated heartbeat update [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Heartbeat pushed successfully.")
        else:
            print("No changes to commit for heartbeat.")
    except Exception as e:
        print("Git heartbeat commit/push failed:", e)

# --- MAIN CONTROLLER ---
def main():
    print("Starting automated short-form video generation pipeline...")
    
    # 1. Read required Environment Variables
    gemini_key = os.environ.get("GEMINI_API_KEY")
    pexels_key = os.environ.get("PEXELS_API_KEY")
    affiliate_link = os.environ.get("AFFILIATE_LINK", "http://example.com/affiliate")
    
    # Platform variables
    youtube_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    youtube_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    
    tiktok_client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    tiktok_client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    tiktok_refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN")
    
    meta_access_token = os.environ.get("META_PAGE_ACCESS_TOKEN")
    ig_account_id = os.environ.get("IG_ACCOUNT_ID")
    fb_page_id = os.environ.get("FB_PAGE_ID")
    
    # Validate core keys
    if not gemini_key or not pexels_key:
        print("CRITICAL: GEMINI_API_KEY and PEXELS_API_KEY are required to run the pipeline.")
        sys.exit(1)
        
    # 2. Content Generation
    script_text, title = generate_content(gemini_key)
    
    # Description layout
    description = f"{script_text}\n\nRecommended tool: {affiliate_link}"
    
    # 3. Audio (TTS) & Subtitles
    audio_path, vtt_path = generate_audio_and_subtitles(script_text)
    
    # 4. Parse Subtitles
    subs_list = parse_vtt(vtt_path)
    
    # Get audio length to find matching background length
    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration
    audio_clip.close()
    
    # 5. Background video
    video_path = download_pexels_video(pexels_key, audio_duration)
    
    # 6. Assembly
    output_path = "final_short.mp4"
    assemble_video(video_path, audio_path, subs_list, output_path)
    
    # 7. Upload to Platforms with isolated try/except blocks
    
    # YouTube Upload
    if youtube_client_id and youtube_client_secret and youtube_refresh_token:
        try:
            upload_to_youtube(
                output_path, title, description,
                youtube_client_id, youtube_client_secret, youtube_refresh_token
            )
        except Exception as e:
            print("ERROR uploading to YouTube:", e)
    else:
        print("YouTube credentials missing, skipping YouTube upload.")
        
    # TikTok Upload
    if tiktok_client_key and tiktok_client_secret and tiktok_refresh_token:
        try:
            upload_to_tiktok(output_path, title, tiktok_client_key, tiktok_client_secret, tiktok_refresh_token)
        except Exception as e:
            print("ERROR uploading to TikTok:", e)
    else:
        print("TikTok credentials missing, skipping TikTok upload.")
        
    # Facebook Reels Upload
    if fb_page_id and meta_access_token:
        try:
            upload_to_facebook(output_path, description, fb_page_id, meta_access_token)
        except Exception as e:
            print("ERROR uploading to Facebook Reels:", e)
    else:
        print("Facebook credentials missing, skipping Facebook Reels upload.")
        
    # Instagram Reels Upload
    if ig_account_id and meta_access_token:
        try:
            upload_to_instagram(output_path, description, ig_account_id, meta_access_token)
        except Exception as e:
            print("ERROR uploading to Instagram Reels:", e)
    else:
        print("Instagram credentials missing, skipping Instagram Reels upload.")
        
    # 8. Update Heartbeat for repository persistence
    update_heartbeat_and_push()
    
    print("Pipeline execution complete.")

if __name__ == "__main__":
    main()

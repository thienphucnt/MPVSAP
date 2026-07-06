import os
import sys
import re
import time
import random
import shutil
import datetime
import textwrap
import subprocess
import requests

# Google APIs
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Fix AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS' for MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    if hasattr(PIL.Image, 'Resampling'):
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    else:
        PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# MoviePy — all imports at top level (no deferred imports inside functions)
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip,
    TextClip, concatenate_videoclips
)
from moviepy.video.fx.all import loop
from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.audio.fx.all import audio_loop


# ---------------------------------------------------------------------------
# 1. GEMINI CONTENT GENERATION
#    Single API round-trip returns both TITLE and SCRIPT in one call.
# ---------------------------------------------------------------------------
def generate_content(client):
    model_name = "gemini-2.5-flash"

    # One prompt, structured output — halves latency and API surface area.
    prompt = (
        "Complete BOTH tasks and return them in EXACTLY this format with no extra text:\n"
        "TITLE: <title here>\n"
        "SCRIPT: <script here>\n\n"
        "Task 1 — TITLE: A single highly engaging, click-worthy YouTube Shorts title "
        "under 50 characters. No quotes, emojis, or markdown.\n\n"
        "Task 2 — SCRIPT: A highly engaging, fast-paced 130-word script about a "
        "terrifying, lesser-known space fact or an ancient mystery. "
        "No stage directions, titles, or emojis. Output only the spoken text. "
        "Under no circumstances should the script mention, reference, or allude to "
        "Vietnamese history, regional politics, state officials, south-east Asian "
        "maritime borders, or global geopolitical conflicts."
    )

    print(f"Generating script and title in a single call using {model_name}...")
    response = client.models.generate_content(model=model_name, contents=prompt)
    text = response.text.strip()

    title_match = re.search(r'^TITLE:\s*(.+)$', text, re.MULTILINE)
    script_match = re.search(r'^SCRIPT:\s*([\s\S]+)', text, re.MULTILINE)

    title_text = title_match.group(1).strip() if title_match else ""
    script_text = script_match.group(1).strip() if script_match else ""

    # Fallback: if the model ignores the format instruction
    if not title_text or not script_text:
        print("WARNING: Could not parse structured response — using raw text as script.")
        script_text = text
        title_text = text[:48].split(".")[0]

    # Strip all quote variants (straight, curly, backtick) from title
    title_text = re.sub(r'["\'\`\u2018\u2019\u201c\u201d]', '', title_text).strip()

    print("Generated Title:", title_text)
    print("Generated Script:\n", script_text)
    return script_text, title_text


# ---------------------------------------------------------------------------
# 2. TTS & SUBTITLE GENERATION
# ---------------------------------------------------------------------------
def generate_audio_and_subtitles(script_text):
    print("Generating TTS voiceover and WebVTT subtitles via edge-tts...")
    audio_path = "voice.mp3"
    vtt_path = "subtitles.vtt"

    cmd = [
        sys.executable, "-m", "edge_tts",
        "--text", script_text,
        "--write-media", audio_path,
        "--write-subtitles", vtt_path,
        "--voice", "en-US-JennyNeural"
    ]

    # timeout=120 prevents the runner hanging if edge-tts network call stalls
    subprocess.run(cmd, check=True, timeout=120)
    print(f"TTS generated: {audio_path}, Subtitles: {vtt_path}")
    return audio_path, vtt_path


# ---------------------------------------------------------------------------
# 3. WebVTT SUBTITLE PARSER
# ---------------------------------------------------------------------------
def time_to_seconds(time_str):
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, (m, s) = 0, parts
    else:
        return float(time_str)

    if '.' in s:
        s_int, ms = s.split('.')
        return int(h) * 3600 + int(m) * 60 + int(s_int) + float("0." + ms)
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_vtt(vtt_path):
    print(f"Parsing WebVTT subtitle file: {vtt_path}")
    with open(vtt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    subtitles = []
    for block in re.split(r'\n\s*\n', content):
        block = block.strip()
        if not block or "-->" not in block:
            continue
        lines = block.split('\n')
        time_line = next((l for l in lines if "-->" in l), None)
        if not time_line:
            continue
        text_lines = [l for l in lines[lines.index(time_line) + 1:] if l.strip()]
        parts = time_line.split("-->")
        if len(parts) == 2:
            start_sec = time_to_seconds(parts[0].strip())
            end_sec = time_to_seconds(parts[1].strip().split()[0])
            text = " ".join(text_lines).strip()
            if text:
                subtitles.append(((start_sec, end_sec), text))

    print(f"Parsed {len(subtitles)} subtitle cues.")
    return subtitles


def make_short_burst_subtitles(subs_list, max_words=3):
    short_subs = []
    for (start, end), text in subs_list:
        words = text.split()
        if not words:
            continue
        if len(words) <= max_words:
            short_subs.append(((start, end), text))
            continue

        duration = end - start
        total_words = len(words)
        current_time = start

        for i in range(0, total_words, max_words):
            chunk_words = words[i:i + max_words]
            chunk = " ".join(chunk_words)
            # Word count already known — no redundant re-split
            chunk_count = len(chunk_words)
            chunk_duration = duration * (chunk_count / total_words)
            chunk_end = current_time + chunk_duration
            short_subs.append(((current_time, chunk_end), chunk))
            current_time = chunk_end

    print(f"Split {len(subs_list)} cues into {len(short_subs)} short-burst cues.")
    return short_subs


# ---------------------------------------------------------------------------
# 4. PEXELS VIDEO DOWNLOADER
#    Accepts the shared Gemini client — no second instantiation.
# ---------------------------------------------------------------------------
def download_pexels_videos(api_key, script_text, client):
    print("Extracting visual search keywords from script using Gemini...")
    keywords = []

    try:
        prompt = (
            "Extract exactly 3 distinct, highly visual space-themed search keywords "
            "(e.g. 'neutron star', 'black hole', 'supernova', 'galaxy', 'meteor') "
            "from the script below. These will be used to search for portrait videos. "
            "Output ONLY the three keywords separated by commas, no extra text.\n\n"
            f"Script:\n{script_text}"
        )
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        keywords = [k.strip() for k in response.text.split(",") if k.strip() and len(k.strip()) > 1][:3]
        print("Gemini extracted keywords:", keywords)
    except Exception as e:
        print("Failed to extract keywords via Gemini, using defaults:", e)

    # Guarantee exactly 3 keywords
    default_pool = ["dark space", "outer space", "nebula galaxy", "black hole", "cosmic abyss", "supernova"]
    while len(keywords) < 3:
        cand = random.choice(default_pool)
        if cand not in keywords:
            keywords.append(cand)

    print(f"Final keywords for video search: {keywords}")

    video_paths = []
    headers = {"Authorization": api_key}
    search_url = "https://api.pexels.com/videos/search"

    for i, kw in enumerate(keywords):
        print(f"Searching Pexels for keyword: '{kw}'...")
        # per_page:5 — we only pick from [:5] anyway, no need to fetch 10
        params = {"query": kw, "orientation": "portrait", "size": "medium", "per_page": 5}

        try:
            resp = requests.get(search_url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])

            if not videos:
                print(f"No videos for '{kw}', falling back to 'dark space'...")
                params["query"] = "dark space"
                resp = requests.get(search_url, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
                videos = resp.json().get("videos", [])

            selected = random.choice(videos[:5])
            mp4_files = [f for f in selected.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if not mp4_files:
                mp4_files = selected.get("video_files", [])

            hd = [f for f in mp4_files if f.get("quality") == "hd"]
            pool = hd if hd else mp4_files
            pool.sort(key=lambda x: abs(x.get("width", 0) - 1080) + abs(x.get("height", 0) - 1920))
            video_url = pool[0].get("link")

            clip_path = f"background_clip_{i}.mp4"
            print(f"Downloading clip {i} from Pexels...")

            # Retry up to 3 times with 2-second backoff
            for attempt in range(3):
                try:
                    dl = requests.get(video_url, stream=True, timeout=30)
                    dl.raise_for_status()
                    with open(clip_path, "wb") as f:
                        for chunk in dl.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    break
                except Exception as dl_err:
                    print(f"Download attempt {attempt + 1} failed: {dl_err}")
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise

            video_paths.append(clip_path)
            print(f"Saved clip {i} as: {clip_path}")

        except Exception as e:
            print(f"Failed to fetch video for '{kw}':", e)
            if video_paths:
                dup_path = f"background_clip_{i}.mp4"
                shutil.copy(video_paths[0], dup_path)
                video_paths.append(dup_path)
                print(f"Duplicated {video_paths[0]} to {dup_path} as fallback.")
            else:
                raise

    return video_paths


# ---------------------------------------------------------------------------
# 5. VIDEO ASSEMBLY (MOVIEPY)
# ---------------------------------------------------------------------------
def assemble_video(video_paths, audio_path, subs_list, output_path):
    print("Assembling final video short with MoviePy...")

    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration

    # --- Build multi-clip background with Ken Burns effect ---
    segment_duration = audio_duration / len(video_paths)
    clips = []

    for i, v_path in enumerate(video_paths):
        print(f"Processing background clip {i}: {v_path}")
        c = VideoFileClip(v_path).resize(newsize=(1080, 1920))

        if c.duration < segment_duration:
            c = loop(c, duration=segment_duration)
        else:
            c = c.subclip(0, segment_duration)

        # Ken Burns: safe closure via default-arg binding (avoids late-binding bug)
        c = c.resize(lambda t, d=segment_duration: 1.0 + 0.1 * (t / d)).set_position('center')
        clips.append(c)

    bg_clip = concatenate_videoclips(clips)

    # --- Subtitle overlay ---
    sub_clips = []
    for (start, end), text in subs_list:
        wrapped = "\n".join(textwrap.wrap(text, width=15))
        txt = (
            TextClip(
                wrapped,
                font="Arial-Bold",
                fontsize=120,
                color="yellow",
                stroke_color="black",
                stroke_width=6,
                method="label",
                align="center"
            )
            .set_start(start)
            .set_duration(end - start)
            .set_position(('center', 'center'))
        )
        sub_clips.append(txt)

    final_clip = CompositeVideoClip([bg_clip] + sub_clips)

    # --- Background music ---
    music_dir = "music"
    music_clip = None

    if os.path.exists(music_dir):
        music_files = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.endswith(".mp3")]
        if music_files:
            music_path = random.choice(music_files)
            print(f"Selected background music: {os.path.basename(music_path)}")
            try:
                m = AudioFileClip(music_path)
                if m.duration < audio_duration:
                    m = audio_loop(m, duration=audio_duration)
                else:
                    max_start = max(0, m.duration - audio_duration - 5)
                    m = m.subclip(random.uniform(0, max_start),
                                  random.uniform(0, max_start) + audio_duration)
                music_clip = m.volumex(0.08)
                final_clip = final_clip.set_audio(CompositeAudioClip([audio_clip, music_clip]))
            except Exception as e:
                print("Failed to mix music, using voice only:", e)
                final_clip = final_clip.set_audio(audio_clip)
        else:
            final_clip = final_clip.set_audio(audio_clip)
    else:
        print("No music folder found, using voice only.")
        final_clip = final_clip.set_audio(audio_clip)

    # --- Render — threads=2 saturates both runner vCPUs ---
    print(f"Rendering to {output_path}...")
    temp_audio = f"temp-audio-{os.getpid()}.m4a"  # PID-scoped to avoid collision
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=temp_audio,
        remove_temp=True,
        threads=2,
        logger=None
    )

    # --- Release in correct order: composite first, then components ---
    final_clip.close()
    bg_clip.close()
    for c in clips:
        c.close()
    for s in sub_clips:
        s.close()
    audio_clip.close()
    if music_clip:
        music_clip.close()

    # Clean up downloaded segment clips
    for v_path in video_paths:
        try:
            if os.path.exists(v_path):
                os.remove(v_path)
        except Exception as e:
            print(f"Could not remove {v_path}:", e)

    print("Assembly complete.")
    return output_path


# ---------------------------------------------------------------------------
# 6A. YOUTUBE UPLOADER
# ---------------------------------------------------------------------------
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
            "categoryId": "28"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True
        }
    }

    # 50 MB chunk size so next_chunk() respects socket timeouts
    media = MediaFileUpload(video_path, mimetype="video/mp4",
                            chunksize=50 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"YouTube Upload Progress: {int(status.progress() * 100)}%")

    print(f"YouTube upload successful! Video ID: {response.get('id')}")


# ---------------------------------------------------------------------------
# 6B. TIKTOK UPLOADER
# ---------------------------------------------------------------------------
def upload_to_tiktok(video_path, title, client_key, client_secret, refresh_token):
    print("Uploading to TikTok...")

    token_resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
    )
    token_resp.raise_for_status()
    token_json = token_resp.json()

    access_token = token_json.get("access_token")
    if not access_token:
        raise Exception(f"Failed to refresh TikTok access token: {token_json}")

    new_rt = token_json.get("refresh_token")
    if new_rt and new_rt != refresh_token:
        print(f"New TikTok Refresh Token: {new_rt}")

    video_size = os.path.getsize(video_path)
    scopes = token_json.get("scope", "")
    init_url = (
        "https://open.tiktokapis.com/v2/post/publish/video/init/"
        if "video.publish" in scopes
        else "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
    )

    init_resp = requests.post(
        init_url,
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json; charset=UTF-8"},
        json={
            "post_info": {
                "title": title,
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "is_aigc": True
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1
            }
        }
    )
    init_resp.raise_for_status()
    init_json = init_resp.json()

    if init_json.get("error", {}).get("code") != "ok":
        raise Exception(f"TikTok init failed: {init_json}")

    upload_url = init_json["data"]["upload_url"]
    publish_id = init_json["data"]["publish_id"]

    # Stream file directly — never loads entire binary into RAM
    with open(video_path, "rb") as f:
        put_resp = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(video_size),
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}"
            },
            data=f
        )
    put_resp.raise_for_status()
    print(f"TikTok upload successful! Publish ID: {publish_id}")


# ---------------------------------------------------------------------------
# 6C. META (FACEBOOK REELS) UPLOADER
# ---------------------------------------------------------------------------
def upload_to_facebook(video_path, description, page_id, access_token):
    print("Uploading to Facebook Reels...")

    # Use v21.0 — v18.0 is deprecated
    base = f"https://graph.facebook.com/v21.0/{page_id}/video_reels"

    init_resp = requests.post(base, params={"upload_phase": "start", "access_token": access_token})
    init_resp.raise_for_status()
    init_json = init_resp.json()

    video_id = init_json.get("video_id")
    upload_url = init_json.get("upload_url")
    if not video_id or not upload_url:
        raise Exception(f"Facebook init invalid: {init_json}")

    # Stream file — no full RAM load
    file_size = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {access_token}",
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream"
            },
            data=f
        )
    upload_resp.raise_for_status()

    publish_resp = requests.post(
        base,
        params={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
            "access_token": access_token
        }
    )
    publish_resp.raise_for_status()
    print(f"Facebook Reel published! Video ID: {video_id}")


# ---------------------------------------------------------------------------
# 6D. META (INSTAGRAM REELS) UPLOADER
# ---------------------------------------------------------------------------
def upload_to_temp_host(file_path):
    # Try Catbox first
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=60
            )
        if resp.status_code == 200 and resp.text.strip().startswith("http"):
            print(f"Uploaded to Catbox: {resp.text.strip()}")
            return resp.text.strip()
    except Exception as e:
        print(f"Catbox upload failed: {e}")

    # Fallback to transfer.sh
    try:
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            resp = requests.put(f"https://transfer.sh/{filename}", data=f, timeout=60)
        if resp.status_code == 200:
            print(f"Uploaded to transfer.sh: {resp.text.strip()}")
            return resp.text.strip()
    except Exception as e:
        print(f"transfer.sh upload failed: {e}")

    raise Exception("Failed to upload video to any temporary host for Meta Graph API.")


def upload_to_instagram(video_path, caption, ig_account_id, access_token):
    print("Uploading to Instagram Reels...")

    public_url = upload_to_temp_host(video_path)

    # Use v21.0
    container_resp = requests.post(
        f"https://graph.facebook.com/v21.0/{ig_account_id}/media",
        params={
            "media_type": "REELS",
            "video_url": public_url,
            "caption": caption,
            "access_token": access_token
        }
    )
    container_resp.raise_for_status()
    creation_id = container_resp.json().get("id")
    if not creation_id:
        raise Exception(f"Failed to create Instagram container: {container_resp.text}")

    print(f"Polling container {creation_id}...")
    # Exponential backoff: 10s, 20s, 40s … capped at 60s
    for i in range(20):
        status_resp = requests.get(
            f"https://graph.facebook.com/v21.0/{creation_id}",
            params={"fields": "status_code", "access_token": access_token}
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")
        print(f"Container status check {i + 1}: {status_code}")

        if status_code == "FINISHED":
            break
        elif status_code == "ERROR":
            raise Exception(f"Instagram container failed: {status_resp.json()}")

        time.sleep(min(10 * (2 ** i), 60))  # exponential backoff, max 60s
    else:
        raise Exception("Instagram container timed out.")

    publish_resp = requests.post(
        f"https://graph.facebook.com/v21.0/{ig_account_id}/media_publish",
        params={"creation_id": creation_id, "access_token": access_token}
    )
    publish_resp.raise_for_status()
    print("Instagram Reel published successfully!")


# ---------------------------------------------------------------------------
# 7. 60-DAY HEARTBEAT & GIT PERSISTENCE
#    Git identity set via env vars — no git config subprocess calls needed.
# ---------------------------------------------------------------------------
def update_heartbeat_and_push():
    print("Updating heartbeat...")
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    with open("heartbeat.txt", "w", encoding="utf-8") as f:
        f.write(timestamp)

    try:
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "github-actions[bot]",
            "GIT_AUTHOR_EMAIL": "github-actions[bot]@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "github-actions[bot]",
            "GIT_COMMITTER_EMAIL": "github-actions[bot]@users.noreply.github.com",
        }
        subprocess.run(["git", "add", "heartbeat.txt"], check=True, env=git_env)
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, env=git_env)
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", f"Automated heartbeat: {timestamp} [skip ci]"],
                check=True, env=git_env
            )
            subprocess.run(["git", "push"], check=True, env=git_env)
            print("Heartbeat pushed successfully.")
        else:
            print("No changes to commit for heartbeat.")
    except Exception as e:
        print("Git heartbeat failed:", e)


# ---------------------------------------------------------------------------
# MAIN CONTROLLER
# ---------------------------------------------------------------------------
def main():
    print("Starting automated short-form video generation pipeline...")

    gemini_key  = os.environ.get("GEMINI_API_KEY")
    pexels_key  = os.environ.get("PEXELS_API_KEY")
    affiliate_link = os.environ.get("AFFILIATE_LINK", "http://example.com/affiliate")

    youtube_client_id     = os.environ.get("YOUTUBE_CLIENT_ID")
    youtube_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    tiktok_client_key    = os.environ.get("TIKTOK_CLIENT_KEY")
    tiktok_client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    tiktok_refresh_token = os.environ.get("TIKTOK_REFRESH_TOKEN")

    meta_access_token = os.environ.get("META_PAGE_ACCESS_TOKEN")
    ig_account_id     = os.environ.get("IG_ACCOUNT_ID")
    fb_page_id        = os.environ.get("FB_PAGE_ID")

    if not gemini_key or not pexels_key:
        print("CRITICAL: GEMINI_API_KEY and PEXELS_API_KEY are required.")
        sys.exit(1)

    # Single shared Gemini client — instantiated once, reused everywhere
    client = genai.Client(api_key=gemini_key)

    # 1. Content generation (single API call)
    script_text, title = generate_content(client)

    # 2. Audio + subtitles
    audio_path, vtt_path = generate_audio_and_subtitles(script_text)

    # 3. Parse + burst subtitles
    subs_list = make_short_burst_subtitles(parse_vtt(vtt_path), max_words=3)

    # 4. Download 3 contextual Pexels clips (shared client, no second instantiation)
    video_paths = download_pexels_videos(pexels_key, script_text, client)

    # 5. Assemble — audio_duration computed once inside assemble_video
    output_path = "final_short.mp4"
    assemble_video(video_paths, audio_path, subs_list, output_path)

    # Updated CTA copy as per spec
    description = f"{script_text}\n\nAccess the hidden vault here: {affiliate_link}"

    # 6. Upload to platforms — each in an isolated try/except
    if youtube_client_id and youtube_client_secret and youtube_refresh_token:
        try:
            upload_to_youtube(output_path, title, description,
                              youtube_client_id, youtube_client_secret, youtube_refresh_token)
        except Exception as e:
            if "quotaExceeded" in str(e):
                print("WARNING: YouTube quota exceeded — upload skipped.")
            else:
                print("ERROR uploading to YouTube:", e)
    else:
        print("YouTube credentials missing, skipping.")

    if tiktok_client_key and tiktok_client_secret and tiktok_refresh_token:
        try:
            upload_to_tiktok(output_path, title,
                             tiktok_client_key, tiktok_client_secret, tiktok_refresh_token)
        except Exception as e:
            print("ERROR uploading to TikTok:", e)
    else:
        print("TikTok credentials missing, skipping.")

    if fb_page_id and meta_access_token:
        try:
            upload_to_facebook(output_path, description, fb_page_id, meta_access_token)
        except Exception as e:
            print("ERROR uploading to Facebook Reels:", e)
    else:
        print("Facebook credentials missing, skipping.")

    if ig_account_id and meta_access_token:
        try:
            upload_to_instagram(output_path, description, ig_account_id, meta_access_token)
        except Exception as e:
            print("ERROR uploading to Instagram Reels:", e)
    else:
        print("Instagram credentials missing, skipping.")

    # 7. Heartbeat commit
    update_heartbeat_and_push()

    print("Pipeline execution complete.")


if __name__ == "__main__":
    main()

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
import wave
import concurrent.futures
import argparse
import json
import asyncio
from pathlib import Path
from typing import List, Tuple, Optional

# Google APIs
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# MoviePy
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, TextClip
from moviepy.video.fx.all import loop
from moviepy.audio.fx.all import audio_loop

# Fix AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS' for MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    if hasattr(PIL.Image, 'Resampling'):
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    else:
        PIL.Image.ANTIALIAS = PIL.Image.BICUBIC

# Global shared HTTP session for connection pooling
HTTP_SESSION = requests.Session()

# Global mapping for our three distinct content buckets
CATEGORIES = {
    "Scary Space Mysteries": {
        "db_key": "space",
        "playlist_env": "YT_PLAYLIST_SPACE",
        "topic_desc": "a terrifying, real-life space mystery or unsettling astrophysics fact",
        "tone": "grounded but deeply ominous",
        "music_subfolder": "space",
        "kw_examples": "space: 'neutron star', 'black hole', 'supernova', 'galaxy', 'meteor'",
        "kw_defaults": ["dark space", "outer space", "nebula galaxy", "black hole", "cosmic abyss", "supernova"],
        "yt_tags": ["shorts", "nichefactsshorts", "space", "astrophysics", "cosmos", "universe"],
        "title_hashtags": "#space #shorts"
    },
    "Morbid or Silly History Facts": {
        "db_key": "history",
        "playlist_env": "YT_PLAYLIST_HISTORY",
        "topic_desc": "a bizarre, morbid, funny, or unsettling real historical fact (e.g. strange ancient customs, odd ruler behaviors)",
        "tone": "factual, compelling, but highly entertaining",
        "music_subfolder": "history",
        "kw_examples": "history: 'ancient ruins', 'vintage map', 'medieval armor', 'roman colosseum', 'egyptian pyramid'",
        "kw_defaults": ["ancient history", "historical document", "medieval artifact", "castle ruins", "old map"],
        "yt_tags": ["shorts", "nichefactsshorts", "history", "ancient", "historyfacts", "didyouknow"],
        "title_hashtags": "#history #shorts"
    },
    "Exciting Tech Facts": {
        "db_key": "tech",
        "playlist_env": "YT_PLAYLIST_TECH",
        "topic_desc": "an exciting, mind-bending, or futuristic technology fact (e.g. quantum computing breakthrough, weird coding history, AI advancements)",
        "tone": "thrilling, cutting-edge, and highly engaging",
        "music_subfolder": "tech",
        "kw_examples": "technology: 'futuristic server room', 'cyberpunk code', 'quantum computer', 'robotic arm', 'artificial intelligence'",
        "kw_defaults": ["future tech", "computer server", "glowing circuits", "ai neural network", "coding matrix"],
        "yt_tags": ["shorts", "nichefactsshorts", "technology", "tech", "futurism", "science"],
        "title_hashtags": "#tech #shorts"
    }
}


class VideoFormatConfig:
    def __init__(self, format_type: str = "short"):
        self.format_type = format_type
        if format_type == "short":
            self.resolution = (1080, 1920)
            self.sub_fontsize = 85
            self.sub_position = ('center', 1350)
            self.clip_count = 3
            self.segment_count = 1
            self.is_short = True
        else:
            self.resolution = (1920, 1080)
            self.sub_fontsize = 55
            self.sub_position = ('center', 800)
            self.clip_count = 3
            self.segment_count = 5
            self.is_short = False


# ---------------------------------------------------------------------------
# SHARED GEMINI RETRY HELPER
# ---------------------------------------------------------------------------
def gemini_generate_with_retry(client: genai.Client, model: str, prompt: str, max_retries: int = 5):
    """Call Gemini with fallback model chain and exponential backoff for transient errors."""
    # Complete chain of models to try in sequence if we hit quota or rate limits
    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    
    # Start with the requested model, or position in the chain if matches
    if model in model_fallback_chain:
        start_idx = model_fallback_chain.index(model)
        candidates = model_fallback_chain[start_idx:]
    else:
        candidates = [model] + model_fallback_chain

    last_error = None
    for current_model in candidates:
        success = False
        for attempt in range(max_retries):
            try:
                print(f"Trying Gemini model: {current_model}...")
                response = client.models.generate_content(model=current_model, contents=prompt)
                return response
            except Exception as e:
                last_error = e
                is_quota_or_rate_limit = any(err in str(e).upper() for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA"])
                is_transient = any(err in str(e) or err in str(e).upper() for err in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"])
                
                # If we hit quota/rate limits, break out of the retry loop of the current model and try the next model in the fallback chain
                if is_quota_or_rate_limit:
                    print(f"Model {current_model} quota exceeded or rate limited. Moving to next fallback model...")
                    break
                
                if is_transient and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Gemini API transient error on {current_model} (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time:.2f}s: {e}")
                    time.sleep(wait_time)
                else:
                    # Non-transient error, raise immediately
                    raise
        if success:
            break

    # If we exhausted all candidates
    raise Exception(f"Gemini API failed after exhausting all fallback models. Last error: {last_error}")


# ---------------------------------------------------------------------------
# 1. GEMINI CONTENT GENERATION
#    Single API round-trip returns script and visual keywords in JSON format.
# ---------------------------------------------------------------------------
def generate_content(client: genai.Client, category: str, recent_topics: List[str], config: VideoFormatConfig) -> Tuple[str, str, List[dict]]:
    model_name = "gemini-2.5-pro"
    cat_info = CATEGORIES[category]

    exclude_instruction = ""
    if recent_topics:
        exclude_instruction = f"\n- Do NOT write about, reference, or base the script on the same core concepts, subjects, or historical events as any of these recent videos: {', '.join(recent_topics)}. You must choose a completely different concept."

    if config.is_short:
        prompt = (
            "You are a professional content creator. Complete the following tasks and return ONLY a valid JSON object. "
            "Do not include markdown tags (like ```json), quotes, or extra text. Output exactly this JSON structure:\n"
            "{\n"
            '  "script": "<script text>",\n'
            '  "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],\n'
            '  "title": "<title text>",\n'
            '  "description": "<description text>",\n'
            '  "topic": "<2-3 words naming the core concept>"\n'
            "}\n\n"
            f"Task 1 — script: Write a highly engaging, fast-paced 130-word script about {cat_info['topic_desc']}. "
            f"Make it sound {cat_info['tone']}. End the script with a short, 3-second Call-To-Action (e.g., 'Hit subscribe for more dark space mysteries') "
            "that naturally loops back to the start. Force dramatic pacing by strategically inserting ellipses (...) and em-dashes (—) before revealing facts so the TTS pauses. "
            "Do not include stage directions, titles, or emojis. Output only the spoken text.\n\n"
            "Task 2 — visual_keywords: An array of 6 highly generic, atmospheric search terms (e.g. ['deep space', 'pitch black darkness', 'stars', 'nebula', 'galaxy', 'black hole'] instead of literal script terms) suitable for Pexels search.\n\n"
            "Task 3 — title: A single highly engaging, click-worthy YouTube Shorts title under 50 characters. Do NOT include any hashtags (#) in the title.\n\n"
            "Task 4 — description: A punchy, 2-sentence summary of the video with 5 relevant hashtags at the end, including #nichefactsshorts.\n\n"
            "Task 5 — topic: A 2-3 word name of the core subject or event (e.g. Great Attractor, Cadaver Synod, Emu War).\n\n"
            "Under no circumstances should the script mention regional politics, state officials, or global geopolitical conflicts. "
            "Under no circumstances should the script mention, reference, or allude to Vietnamese history, regional politics, or Vietnamese state officials. "
            "Under no circumstances should the script contain scientific, mathematical, or historical exaggerations or false claims. "
            "Ensure all numbers, sizes, and masses are strictly factually accurate (verify planetary mass/volume limits)."
            f"{exclude_instruction}"
        )
    else:
        prompt = (
            "You are a professional content creator. Complete the following tasks and return ONLY a valid JSON object. "
            "Do not include markdown tags (like ```json), quotes, or extra text. Output exactly this JSON structure:\n"
            "{\n"
            '  "title": "<Click-worthy widescreen title under 70 characters>",\n'
            '  "description": "<Punchy description with 5 relevant hashtags at the end including #nichefacts>",\n'
            '  "segments": [\n'
            '    {\n'
            '      "script": "<highly engaging 90-word script for fact 1>",\n'
            '      "visual_keywords": ["keyword1", "keyword2", "keyword3"],\n'
            '      "topic": "<2-3 words naming the core concept of fact 1>"\n'
            '    },\n'
            '    ... (exactly ' + str(config.segment_count) + ' segments)\n'
            '  ]\n'
            "}\n\n"
            f"Write a compilation of {config.segment_count} distinct, highly engaging facts about {cat_info['topic_desc']}. "
            f"Each segment should have a fast-paced 90-word script. "
            f"Make the tone {cat_info['tone']}. End the last segment with a short Call-To-Action (e.g., 'Subscribe to Niche Facts for more mysteries'). "
            "Force dramatic pacing by strategically inserting ellipses (...) and em-dashes (—). "
            "Do not include stage directions, titles, or emojis. Output only the spoken text.\n\n"
            "For each segment, provide 3 highly generic, atmospheric search terms for Pexels search.\n\n"
            "Under no circumstances should the script mention regional politics, state officials, or global geopolitical conflicts. "
            "Under no circumstances should the script mention, reference, or allude to Vietnamese history, regional politics, or Vietnamese state officials. "
            "Under no circumstances should the script contain scientific, mathematical, or historical exaggerations or false claims. "
            "Ensure all numbers, sizes, and masses are strictly factually accurate."
            f"{exclude_instruction}"
        )

    print(f"Generating script data for category '{category}' in a single call using {model_name}...")
    response = gemini_generate_with_retry(client, model_name, prompt)
    text = response.text.strip()
    
    # Strip markdown block formatting if present
    if text.startswith("```json"):
        text = text[7:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    title = ""
    description = ""
    segments = []

    try:
        data = json.loads(text)
        if config.is_short:
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            segments = [{
                "script": data.get("script", "").strip(),
                "visual_keywords": data.get("visual_keywords", []),
                "topic": data.get("topic", "").strip()
            }]
        else:
            title = data.get("title", "").strip()
            description = data.get("description", "").strip()
            segments = data.get("segments", [])
    except Exception as e:
        print("WARNING: Could not parse JSON response — falling back to manual parsing.", e)
        title = f"Mind-Blowing {category} Facts"
        description = f"Discover some of the most interesting niche facts in the universe! #nichefacts"
        segments = [{
            "script": "Space is full of mysterious phenomena that science is only beginning to understand...",
            "visual_keywords": cat_info["kw_defaults"][:3],
            "topic": "Space Mysteries"
        }]

    # Clean up scripts in segments
    for seg in segments:
        script = seg.get("script", "").strip()
        script = re.sub(r'[\*_`]', '', script)
        script = re.sub(r'\[.*?\]', '', script)
        script = re.sub(r'\(.*?\)', '', script)
        script = re.sub(r'\s+', ' ', script).strip()
        seg["script"] = script

    print("Generated Title:", title)
    print("Generated Description:", description)
    print(f"Generated {len(segments)} segments.")
    
    return title, description, segments


# ---------------------------------------------------------------------------
# 2 & 3. TTS & SUBTITLE GENERATION (EDGE TTS ONLINE)
# ---------------------------------------------------------------------------
async def synthesize_speech_and_get_timestamps(text: str, voice: str, audio_path: str, rate: str = "+12%") -> List[Tuple[float, float, str]]:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset and duration are in 100ns units (ticks)
                # 1 tick = 1e-7 seconds
                start_sec = chunk["offset"] / 10000000.0
                duration_sec = chunk["duration"] / 10000000.0
                end_sec = start_sec + duration_sec
                word_text = chunk["text"].strip()
                # Clean punctuation from words for display
                clean_word = re.sub(r'[^\w\s\-\'\—]', '', word_text)
                if clean_word:
                    words.append((start_sec, end_sec, clean_word))
                    
    return words


def generate_audio_and_subtitles(script_text: str, category: str, topic: str = "") -> Tuple[str, List[Tuple[Tuple[float, float], str]]]:
    print("Generating TTS voiceover via Edge TTS...")
    audio_path = "voice.wav"
    
    primary_voice = "en-US-BrianNeural"
    fallback_voice = "en-US-AndrewNeural"
    
    words = []
    try:
        words = asyncio.run(synthesize_speech_and_get_timestamps(script_text, primary_voice, audio_path))
    except Exception as e:
        print(f"Primary voice {primary_voice} failed: {e}. Trying fallback voice {fallback_voice}...")
        try:
            words = asyncio.run(synthesize_speech_and_get_timestamps(script_text, fallback_voice, audio_path))
        except Exception as fallback_err:
            print("Fallback voice also failed:", fallback_err)
            raise
            
    # Parse word timestamps into 1-word subtitle chunks (hyper-kinetic layout)
    subs_list = []
    max_words = 1
    for i in range(0, len(words), max_words):
        chunk_words = words[i:i + max_words]
        if not chunk_words:
            continue
        start = chunk_words[0][0]
        end = chunk_words[-1][1]
        text = " ".join([cw[2] for cw in chunk_words]).upper()
        if text:
            subs_list.append(((start, end), text))
            
    print(f"Generated {len(subs_list)} short-burst subtitle cues.")
    return audio_path, subs_list


# ---------------------------------------------------------------------------
# 4. PEXELS VIDEO DOWNLOADER
# ---------------------------------------------------------------------------
def download_pexels_videos(api_key: str, keywords: List[str], category: str) -> List[str]:
    print("Preparing download of background video clips from Pexels...")
    cat_info = CATEGORIES[category]

    # Guarantee exactly 6 keywords
    default_pool = cat_info["kw_defaults"]
    while len(keywords) < 6:
        cand = random.choice(default_pool)
        if cand not in keywords:
            keywords.append(cand)

    headers = {"Authorization": api_key}
    search_url = "https://api.pexels.com/videos/search"

    def fetch_and_download(kw: str, index: int) -> str:
        print(f"Searching Pexels for keyword: '{kw}'...")
        params = {"query": kw, "orientation": "portrait", "size": "medium", "per_page": 5}
        try:
            resp = HTTP_SESSION.get(search_url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])

            if not videos:
                # Fallback to a random default query for the category to keep thematic consistency
                fallback_kw = random.choice(cat_info["kw_defaults"])
                print(f"No videos for '{kw}', falling back to category default: '{fallback_kw}'...")
                params["query"] = fallback_kw
                resp = HTTP_SESSION.get(search_url, headers=headers, params=params, timeout=15)
                resp.raise_for_status()
                videos = resp.json().get("videos", [])

            if not videos:
                raise Exception(f"No videos found on Pexels for keyword '{kw}' or category fallback.")

            selected = random.choice(videos[:5])
            mp4_files = [f for f in selected.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if not mp4_files:
                mp4_files = selected.get("video_files", [])
            
            if not mp4_files:
                raise Exception(f"No valid MP4 files found for '{kw}'")

            hd = [f for f in mp4_files if f.get("quality") == "hd"]
            pool = hd if hd else mp4_files
            pool.sort(key=lambda x: abs((x.get("width") or 0) - 1080) + abs((x.get("height") or 0) - 1920))
            video_url = pool[0].get("link")

            clip_path = f"background_clip_{index}.mp4"
            print(f"Downloading clip {index} from Pexels...")

            for attempt in range(3):
                try:
                    dl = HTTP_SESSION.get(video_url, stream=True, timeout=30)
                    dl.raise_for_status()
                    with open(clip_path, "wb") as f:
                        for chunk in dl.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    return clip_path
                except Exception as dl_err:
                    print(f"Download attempt {attempt + 1} failed for clip {index}: {dl_err}")
                    if attempt < 2:
                        time.sleep(2)
                    else:
                        raise
        except Exception as e:
            print(f"Failed to fetch video for '{kw}':", e)
            raise

    # Download in parallel using ThreadPoolExecutor
    video_paths = [None] * 6
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        future_to_index = {executor.submit(fetch_and_download, kw, i): i for i, kw in enumerate(keywords[:6])}
        for future in concurrent.futures.as_completed(future_to_index):
            i = future_to_index[future]
            try:
                video_paths[i] = future.result()
            except Exception as exc:
                print(f"Clip {i} generated an exception: {exc}")
    
    # Fallback for any failed downloads by duplicating successful ones
    successful = [p for p in video_paths if p is not None]
    if not successful:
        raise Exception("All Pexels downloads failed.")
    
    for i in range(6):
        if video_paths[i] is None:
            dup_path = f"background_clip_{i}.mp4"
            shutil.copy(successful[0], dup_path)
            video_paths[i] = dup_path
            print(f"Duplicated {successful[0]} to {dup_path} as fallback.")

    return video_paths


# ---------------------------------------------------------------------------
# FONT DOWNLOADER HELPER
# ---------------------------------------------------------------------------
def download_font() -> str:
    """Download Anton-Regular from Google Fonts if not cached locally."""
    font_dir = Path("fonts")
    font_dir.mkdir(exist_ok=True)
    font_path = font_dir / "Anton-Regular.ttf"
    if not font_path.exists():
        print("Downloading Anton-Regular font...")
        url = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"
        r = HTTP_SESSION.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(font_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
    return str(font_path.resolve().absolute())


# ---------------------------------------------------------------------------
# 5. VIDEO ASSEMBLY (MOVIEPY)
# ---------------------------------------------------------------------------
def assemble_video(video_paths: List[str], audio_path: str, subs_list: List[Tuple[Tuple[float, float], str]], output_path: str, category: str, config: Optional[VideoFormatConfig] = None, mix_music: bool = True) -> str:
    print("Assembling final video short with MoviePy...")
    if config is None:
        config = VideoFormatConfig("short")
        
    font_path = download_font()

    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration

    # --- Build multi-clip background with Ken Burns zoom effect ---
    segment_duration = audio_duration / len(video_paths)
    clips = []

    for i, v_path in enumerate(video_paths):
        print(f"Processing background clip {i}: {v_path}")
        c = VideoFileClip(v_path).resize(newsize=config.resolution)

        # Pad duration slightly to prevent last-frame flash glitch
        pad = 0.5
        if c.duration < segment_duration:
            c = loop(c, duration=segment_duration + pad)
        else:
            subclip_end = min(c.duration, segment_duration + pad)
            c = c.subclip(0, subclip_end)

        c = c.set_duration(segment_duration)

        # Ken Burns continuous slow-zoom effect (scale from 1.0 to 1.15x for faster scene changes)
        c = c.resize(lambda t, d=segment_duration: 1.0 + 0.15 * (t / d)).set_position('center')
        clips.append(c)

    bg_clip = concatenate_videoclips(clips)

    # Helper function for smart subtitle word highlighting
    def get_word_color(word: str) -> str:
        clean = re.sub(r"[^\w]", "", word.upper())
        fillers = {
            "THE", "A", "AND", "OR", "IN", "OF", "TO", "IS", "WAS", "FOR", 
            "IT", "ON", "WITH", "AS", "AT", "BY", "AN", "BE", "THIS", "THAT", 
            "FROM", "ARE", "WERE", "BEEN", "BUT", "SO", "IF", "THEY", "THEIR", "YOU", "YOUR"
        }
        if clean in fillers:
            return "#FFFFFF" # White for fillers
        return random.choice(["#FFFF00", "#00FF00", "#00FFFF"]) # Yellow, Green, Cyan highlights

    # --- Subtitle overlay ---
    def create_text_clip(start, end, text):
        padded_text = f" {text.upper().strip()} "
        text_color = get_word_color(text)

        return (
            TextClip(
                padded_text,
                font=font_path,
                fontsize=config.sub_fontsize,
                color=text_color,
                bg_color="rgba(0,0,0,0.6)", # Dark semi-transparent background box natively handled via alpha
                transparent=True,
                stroke_color="black",
                stroke_width=3,
                method="label",
                align="center"
            )
            .set_start(start)
            .set_duration(end - start)
            .set_position(config.sub_position)
            .resize(lambda t: 1.2 - 2.0 * t if t < 0.1 else 1.0) # Pop-in bounce effect
        )

    print(f"Generating {len(subs_list)} TextClips (ImageMagick)...")
    sub_clips = [None] * len(subs_list)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_idx = {executor.submit(create_text_clip, s, e, t): i for i, ((s, e), t) in enumerate(subs_list)}
        for future in concurrent.futures.as_completed(future_to_idx):
            i = future_to_idx[future]
            try:
                sub_clips[i] = future.result()
            except Exception as exc:
                print(f"TextClip {i} generated an exception: {exc}")
    
    # Filter out any failed clips
    sub_clips = [c for c in sub_clips if c is not None]

    final_clip = CompositeVideoClip([bg_clip] + sub_clips)

    if not mix_music:
        final_clip = final_clip.set_audio(audio_clip)
    else:
        # --- Background music mixing (FFMPEG amix for mono/stereo standard) ---
        music_dir = Path("music")
        music_clip = None
        final_audio = None
        music_temp_path = f"temp-music-{os.getpid()}.wav"
        mixed_audio_path = f"mixed-audio-{os.getpid()}.wav"

        cat_info = CATEGORIES[category]
        cat_music_dir = music_dir / cat_info["music_subfolder"]

        # Try category subdirectory, fallback to root music directory
        target_dir = cat_music_dir if cat_music_dir.exists() and cat_music_dir.is_dir() else music_dir

        if target_dir.exists() and target_dir.is_dir():
            music_files = list(target_dir.glob("*.mp3"))
            if not music_files and target_dir != music_dir:
                music_files = list(music_dir.glob("*.mp3"))

            if music_files:
                music_path = random.choice(music_files)
                print(f"Selected background music: {music_path.name}")
                try:
                    m = AudioFileClip(str(music_path))
                    if m.duration < audio_duration:
                        m = audio_loop(m, duration=audio_duration)
                    else:
                        max_start = max(0, m.duration - audio_duration - 5)
                        start_time = random.uniform(0, max_start)
                        m = m.subclip(start_time, start_time + audio_duration)
                    
                    # Render sliced/looped music to a temporary file
                    music_clip = m.volumex(0.22) # 0.22 volume level
                    music_clip.write_audiofile(music_temp_path, fps=44100, logger=None)
                    m.close()
                    music_clip.close()
                    music_clip = None

                    # Mix voice.wav and temp-music.wav using FFMPEG for absolute stability
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", audio_path,
                        "-i", music_temp_path,
                        "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
                        "-c:a", "pcm_s16le",
                        mixed_audio_path
                    ]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    # Clean up temp music file
                    if os.path.exists(music_temp_path):
                        os.remove(music_temp_path)

                    # Load mixed audio
                    final_audio = AudioFileClip(mixed_audio_path)
                    final_clip = final_clip.set_audio(final_audio)
                except Exception as e:
                    print("Failed to mix music, using voice only:", e)
                    final_clip = final_clip.set_audio(audio_clip)
                    if os.path.exists(music_temp_path):
                        try:
                            os.remove(music_temp_path)
                        except Exception:
                            pass
            else:
                final_clip = final_clip.set_audio(audio_clip)
        else:
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
        preset="ultrafast",
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
    if final_audio:
        final_audio.close()

    # Clean up mixed audio temp file if created
    if mix_music and os.path.exists(mixed_audio_path):
        try:
            os.remove(mixed_audio_path)
        except Exception as clean_err:
            print("Failed to clean up mixed audio file:", clean_err)

    # Clean up downloaded segment clips and generated audio
    for v_path in video_paths:
        try:
            vp = Path(v_path)
            if vp.exists():
                vp.unlink()
        except Exception as e:
            print(f"Could not remove {v_path}:", e)
            
    try:
        ap = Path(audio_path)
        if ap.exists():
            ap.unlink()
    except Exception as e:
            print(f"Could not remove {audio_path}:", e)

    print("Assembly complete.")
    return output_path


# ---------------------------------------------------------------------------
# 6A. YOUTUBE UPLOADER WITH PINNED COMMENT
# ---------------------------------------------------------------------------
def upload_to_youtube(video_path: str, title: str, description: str, client_id: str, client_secret: str, refresh_token: str, playlist_id: Optional[str] = None, category: str = "space") -> None:
    print("Uploading to YouTube Shorts...")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"]
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": CATEGORIES.get(category, CATEGORIES[list(CATEGORIES.keys())[0]])["yt_tags"],
            "categoryId": "28"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True # CRITICAL COMPLIANCE
        }
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4",
                            chunksize=50 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"YouTube Upload Progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"YouTube upload successful! Video ID: {video_id}")

    if video_id and playlist_id:
        print(f"Adding video {video_id} to playlist {playlist_id}...")
        try:
            body = {
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
            youtube.playlistItems().insert(part="snippet", body=body).execute()
            print("Successfully added video to playlist.")
        except Exception as e:
            print("Failed to add video to playlist:", e)

    # Post Pinned Comment containing CTA
    if video_id:
        cta_text = "Hit subscribe for more dark facts!"
        comment_text = cta_text
        print(f"Posting top-level comment on video {video_id}...")
        try:
            comment_body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            youtube.commentThreads().insert(part="snippet", body=comment_body).execute()
            print("Comment posted successfully!")
        except Exception as comment_err:
            print("Failed to post comment:", comment_err)


# ---------------------------------------------------------------------------
# 6B. OTHER PLATFORM UPLOADERS (FALLBACK COMPATIBILITY)
# ---------------------------------------------------------------------------
def upload_to_tiktok(video_path: str, title: str, client_key: str, client_secret: str, refresh_token: str) -> None:
    print("Uploading to TikTok...")
    # Token refresh exchange
    url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    resp = HTTP_SESSION.post(url, headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    access_token = resp.json().get("access_token")
    
    if not access_token:
        raise Exception("Failed to refresh TikTok access token.")
        
    # Initiating clip upload
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    # TikTok requires file size in bytes
    file_size = Path(video_path).stat().st_size
    init_body = {
        "post_info": {
            "title": title[:150], # TikTok title cap
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_stitch": False,
            "disable_comment": False,
            "video_cover_timestamp_ms": 1000
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1
        }
    }
    
    init_resp = HTTP_SESSION.post(init_url, headers=init_headers, json=init_body, timeout=15)
    init_resp.raise_for_status()
    upload_url = init_resp.json().get("data", {}).get("upload_url")
    
    if not upload_url:
        raise Exception(f"Failed to initialize TikTok upload: {init_resp.text}")
        
    # PUT file upload
    with open(video_path, "rb") as f:
        put_headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size)
        }
        put_resp = HTTP_SESSION.put(upload_url, data=f, headers=put_headers, timeout=120)
        put_resp.raise_for_status()
        
    print("TikTok upload successful!")


def upload_to_facebook(video_path: str, description: str, page_id: str, access_token: str) -> None:
    print("Uploading to Facebook Reels...")
    # Step 1: Initialize upload session
    init_url = f"https://graph.facebook.com/v19.0/{page_id}/video_reels"
    params = {
        "upload_phase": "start",
        "access_token": access_token
    }
    resp = HTTP_SESSION.post(init_url, params=params, timeout=15)
    resp.raise_for_status()
    video_id = resp.json().get("video_id")
    
    if not video_id:
        raise Exception("Failed to initialize Facebook Reels upload session.")
        
    # Step 2: Upload binary file chunk
    upload_url = f"https://rupload.facebook.com/video-reels/{video_id}"
    file_size = Path(video_path).stat().st_size
    headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream"
    }
    with open(video_path, "rb") as f:
        up_resp = HTTP_SESSION.post(upload_url, data=f, headers=headers, timeout=180)
        up_resp.raise_for_status()
        
    # Step 3: Publish the video reel
    publish_url = f"https://graph.facebook.com/v19.0/{page_id}/video_reels"
    pub_params = {
        "upload_phase": "finish",
        "video_id": video_id,
        "video_state": "PUBLISHED",
        "description": description,
        "access_token": access_token
    }
    pub_resp = HTTP_SESSION.post(publish_url, params=pub_params, timeout=30)
    pub_resp.raise_for_status()
    print("Facebook Reel published successfully!")


def upload_to_instagram(video_path: str, description: str, ig_account_id: str, access_token: str) -> None:
    print("Uploading to Instagram Reels...")
    # Step 1: Initialize container
    init_url = f"https://graph.facebook.com/v19.0/{ig_account_id}/media"
    params = {
        "media_type": "REELS",
        "video_url": "", # Graph API requires video file uploaded to a public server if not using direct binary, 
                         # but since we are running headless, direct binary upload is not supported in the standard /media endpoint.
                         # This script assumes a direct hosting fallback or meta upload scheme if configured.
                         # We'll keep the current direct Meta container setup.
        "caption": description,
        "access_token": access_token
    }
    # Note: direct binary upload to Instagram Reels is only supported via hosted URL reference in Graph API.
    # In full production, the video is temporarily uploaded to a storage bucket (S3/GCS/GitHub Pages) and the URL is passed.
    # Here, we raise a clear message if direct binary cannot be referenced.
    print("WARNING: Instagram Reels binary upload requires public file hosting. Skipping direct IG upload.")


# ---------------------------------------------------------------------------
# 7. 60-DAY HEARTBEAT & GIT PERSISTENCE
# ---------------------------------------------------------------------------
def update_heartbeat_and_push() -> None:
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
        if os.path.exists("past_topics.json"):
            subprocess.run(["git", "add", "past_topics.json"], check=True, env=git_env)
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, env=git_env)
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", f"Automated heartbeat: {timestamp} [skip ci]"],
                check=True, env=git_env
            )
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True, env=git_env)
            subprocess.run(["git", "push"], check=True, env=git_env)
            print("Heartbeat pushed successfully.")
        else:
            print("No changes to commit for heartbeat.")
    except Exception as e:
        print("Git heartbeat failed:", e)


# ---------------------------------------------------------------------------
# YOUTUBE PLAYLIST SYNC HELPER
# ---------------------------------------------------------------------------
def sync_topics_from_youtube(client_id: str, client_secret: str, refresh_token: str, past_topics: list) -> list:
    """Fetch video titles from YouTube playlists and sync them into past_topics if missing."""
    print("Syncing past topics from YouTube playlists...")
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

        playlist_mapping = {
            "space": os.environ.get("YT_PLAYLIST_SPACE"),
            "history": os.environ.get("YT_PLAYLIST_HISTORY"),
            "tech": os.environ.get("YT_PLAYLIST_TECH")
        }

        existing_titles = {item["title"].lower().strip() for item in past_topics}
        new_items = []

        for category, playlist_id in playlist_mapping.items():
            if not playlist_id:
                continue

            print(f"Fetching titles from playlist {playlist_id} ({category})...")
            next_page_token = None
            while True:
                res = youtube.playlistItems().list(
                    playlistId=playlist_id,
                    part="snippet",
                    maxResults=50,
                    pageToken=next_page_token
                ).execute()

                for item in res.get("items", []):
                    title = item.get("snippet", {}).get("title", "").strip()
                    if title and title.lower().strip() not in existing_titles:
                        print(f"Found missing title from YouTube: '{title}'")
                        new_items.append({
                            "category": category,
                            "title": title,
                            "timestamp": datetime.datetime.utcnow().isoformat()
                        })
                        existing_titles.add(title.lower().strip())

                next_page_token = res.get("nextPageToken")
                if not next_page_token:
                    break

        if new_items:
            past_topics.extend(new_items)
            print(f"Synced {len(new_items)} new past titles from YouTube.")

    except Exception as e:
        print("Warning: Failed to sync past topics from YouTube playlists:", e)

    return past_topics


# ---------------------------------------------------------------------------
# MAIN CONTROLLER
# ---------------------------------------------------------------------------
def run_daily_upload_pipeline_once() -> None:
    print("Starting automated video generation pipeline...")

    gemini_key  = os.environ.get("GEMINI_API_KEY")
    pexels_key  = os.environ.get("PEXELS_API_KEY")

    if not gemini_key or not pexels_key:
        print("CRITICAL: GEMINI_API_KEY and PEXELS_API_KEY are required.")
        sys.exit(1)

    # Single shared Gemini client
    client = genai.Client(api_key=gemini_key)

    # Parse command line overrides
    parser = argparse.ArgumentParser(description="Automated video generation pipeline")
    parser.add_argument("--category", choices=["space", "history", "tech"], help="Force script category selection")
    parser.add_argument("--format", choices=["short", "long"], default="short", help="Format of video to generate")
    parser.add_argument("--dry-run", action="store_true", help="Perform content generation and TTS without video rendering")
    args = parser.parse_args()

    # Route content selection
    category_keys = list(CATEGORIES.keys())
    if args.category:
        if args.category == "space":
            category = category_keys[0]
        elif args.category == "history":
            category = category_keys[1]
        else:
            category = category_keys[2]
        print(f"CLI Override: selected category '{category}'")
    else:
        category = random.choice(category_keys)
        print(f"Randomly selected category: '{category}'")

    # Load past topics history to prevent duplicates
    past_topics_path = Path("past_topics.json")
    past_topics = []
    if past_topics_path.exists():
        try:
            with open(past_topics_path, "r", encoding="utf-8") as f:
                past_topics = json.load(f)
        except Exception as e:
            print("Failed to load past topics:", e)

    # Sync past uploaded videos dynamically from YouTube if keys are available
    youtube_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
    youtube_client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
    youtube_refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
    if youtube_client_id and youtube_client_secret and youtube_refresh_token:
        past_topics = sync_topics_from_youtube(
            youtube_client_id,
            youtube_client_secret,
            youtube_refresh_token,
            past_topics
        )

    # Resolve database key for history lookup/storage
    db_category = CATEGORIES[category]["db_key"]

    # Extract recent topics for this category to pass as exclusions (fallback to title if topic missing)
    recent_topics = [item.get("topic") or item["title"] for item in past_topics if item.get("category") == db_category][-15:]
    print("Recent topics to exclude:", recent_topics)

    # Initialize video format config
    video_format = args.format
    config = VideoFormatConfig(video_format)
    print(f"Selected Video Format: {config.format_type} (is_short={config.is_short})")

    # 1. Content generation
    title, description, segments = generate_content(client, category, recent_topics, config)

    # Strip any generated hashtags from the title and trim extra spaces
    title = re.sub(r'#\S+', '', title)
    title = re.sub(r'\s+', ' ', title).strip()

    # Append standard title hashtags only for Shorts
    if config.is_short:
        title = f"{title} {CATEGORIES[category]['title_hashtags']}"

    # Append new title, topic, and save history using the database category key
    past_topics.append({
        "category": db_category,
        "title": title,
        "topic": segments[0]["topic"],
        "timestamp": datetime.datetime.utcnow().isoformat()
    })
    past_topics = past_topics[-100:]  # Cap history size to prevent file bloat
    try:
        with open(past_topics_path, "w", encoding="utf-8") as f:
            json.dump(past_topics, f, indent=2)
    except Exception as e:
        print("Failed to save past topics:", e)

    # Dry run mode check
    if args.dry_run:
        print("\n[DRY RUN] Dry-run enabled. Simulating speech synthesis...")
        for idx, seg in enumerate(segments):
            print(f"Dry-run: Generating speech for segment {idx+1}/{len(segments)}...")
            audio_path = f"dry_run_voice_{idx}.wav"
            words = asyncio.run(synthesize_speech_and_get_timestamps(seg["script"], "en-US-AndrewNeural", audio_path))
            print(f"Dry-run Segment {idx+1}: Generated {len(words)} word timestamps.")
            if os.path.exists(audio_path):
                os.remove(audio_path)
        print("Dry run validation completed successfully!")
        sys.exit(0)

    # 2. Rendering block
    output_path = "final_output.mp4"

    if config.is_short:
        # Standard Shorts path (single segment)
        seg = segments[0]
        audio_path, subs_list = generate_audio_and_subtitles(seg["script"], category, seg["topic"])
        video_paths = download_pexels_videos(pexels_key, seg["visual_keywords"], category)
        assemble_video(video_paths, audio_path, subs_list, output_path, category, config, mix_music=True)
    else:
        # Long-form path (stitch multiple segments)
        segment_files = []
        for idx, seg in enumerate(segments):
            print(f"\n--- Rendering Segment {idx + 1}/{len(segments)}: {seg['topic']} ---")
            seg_audio_path, seg_subs_list = generate_audio_and_subtitles(seg["script"], category, f"longform_seg_{idx}")
            seg_video_paths = download_pexels_videos(pexels_key, seg["visual_keywords"], category)
            seg_output_path = f"temp_segment_{idx}_{os.getpid()}.mp4"
            
            # Assemble segment voice-only (no background music)
            assemble_video(seg_video_paths, seg_audio_path, seg_subs_list, seg_output_path, category, config, mix_music=False)
            segment_files.append(seg_output_path)

        # Concatenate all clips
        print("\n--- Concatenating all segments into final long-form video ---")
        clips = [VideoFileClip(f) for f in segment_files]
        concatenated_video = concatenate_videoclips(clips)

        # Mix a continuous background music track across the entire video
        music_dir = Path("music")
        cat_info = CATEGORIES[category]
        cat_music_dir = music_dir / cat_info["music_subfolder"]
        target_dir = cat_music_dir if cat_music_dir.exists() and cat_music_dir.is_dir() else music_dir

        mixed = False
        mixed_audio_path = f"mixed-longform-{os.getpid()}.wav"
        if target_dir.exists() and target_dir.is_dir():
            music_files = list(target_dir.glob("*.mp3"))
            if not music_files and target_dir != music_dir:
                music_files = list(music_dir.glob("*.mp3"))

            if music_files:
                music_path = random.choice(music_files)
                print(f"Selected continuous background music: {music_path.name}")
                try:
                    voice_temp_path = f"temp-voice-{os.getpid()}.wav"
                    concatenated_video.audio.write_audiofile(voice_temp_path, fps=44100, logger=None)
                    total_duration = concatenated_video.duration

                    # Loop/crop background music to match total duration
                    m = AudioFileClip(str(music_path))
                    if m.duration < total_duration:
                        m = audio_loop(m, duration=total_duration)
                    else:
                        max_start = max(0, m.duration - total_duration - 5)
                        start_time = random.uniform(0, max_start)
                        m = m.subclip(start_time, start_time + total_duration)

                    music_temp_path = f"temp-music-{os.getpid()}.wav"
                    music_clip = m.volumex(0.18) # 0.18 volume level for background track
                    music_clip.write_audiofile(music_temp_path, fps=44100, logger=None)
                    m.close()
                    music_clip.close()

                    # Mix
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", voice_temp_path,
                        "-i", music_temp_path,
                        "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
                        "-c:a", "pcm_s16le",
                        mixed_audio_path
                    ]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    if os.path.exists(voice_temp_path):
                        os.remove(voice_temp_path)
                    if os.path.exists(music_temp_path):
                        os.remove(music_temp_path)

                    final_audio = AudioFileClip(mixed_audio_path)
                    concatenated_video = concatenated_video.set_audio(final_audio)
                    mixed = True
                except Exception as e:
                    print("Failed to mix continuous music for long-form:", e)

        print(f"Rendering final concatenated video to {output_path}...")
        temp_audio = f"temp-audio-{os.getpid()}.m4a"
        concatenated_video.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio,
            remove_temp=True,
            threads=2,
            preset="ultrafast",
            logger=None
        )

        concatenated_video.close()
        for c in clips:
            c.close()

        # Clean up temporary segments
        for f in segment_files:
            try:
                os.remove(f)
            except Exception:
                pass
        if mixed and os.path.exists(mixed_audio_path):
            try:
                os.remove(mixed_audio_path)
            except Exception:
                pass

    try:
        # Initialize credential variables
        tiktok_client_key     = os.environ.get("TIKTOK_CLIENT_KEY")
        tiktok_client_secret  = os.environ.get("TIKTOK_CLIENT_SECRET")
        tiktok_refresh_token  = os.environ.get("TIKTOK_REFRESH_TOKEN")
        meta_access_token     = os.environ.get("META_PAGE_ACCESS_TOKEN")
        ig_account_id         = os.environ.get("IG_ACCOUNT_ID")
        fb_page_id            = os.environ.get("FB_PAGE_ID")

        # Resolve target YouTube Playlist ID from environment variables
        cat_info = CATEGORIES[category]
        playlist_id = os.environ.get(cat_info["playlist_env"])

        # 3. Upload to platforms (Only upload to TikTok/Meta for Shorts)
        if youtube_client_id and youtube_client_secret and youtube_refresh_token:
            try:
                upload_to_youtube(output_path, title, description,
                                  youtube_client_id, youtube_client_secret, youtube_refresh_token, playlist_id, category)
            except Exception as e:
                if "quotaExceeded" in str(e):
                    print("WARNING: YouTube quota exceeded — upload skipped.")
                else:
                    print("ERROR uploading to YouTube:", e)
        else:
            print("YouTube credentials missing, skipping.")

        if config.is_short:
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

        # 4. Heartbeat commit
        update_heartbeat_and_push()

    finally:
        # Clean up rendered video file
        try:
            op = Path(output_path)
            if op.exists():
                op.unlink()
        except Exception as e:
            print(f"Could not remove {output_path}:", e)

    print("Pipeline execution complete.")


if __name__ == "__main__":
    run_daily_upload_pipeline_once()

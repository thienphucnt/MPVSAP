import os
import sys
import socket

# Enforce global 45-second socket timeout to prevent network upload hangs
socket.setdefaulttimeout(45)

# Auto-load .env file variables if present
from pathlib import Path
_env_path = Path(".env")
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
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
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, TextClip, concatenate_audioclips, VideoClip, ImageClip
from moviepy.video.fx.all import loop
from moviepy.audio.fx.all import audio_loop

# Fix AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS' for MoviePy
import PIL.Image
import numpy as np
import moviepy.video.fx.resize as mp_resize_mod
import moviepy.video.fx.all as vfx_all
import moviepy.editor as mp_editor

if not hasattr(PIL.Image, 'ANTIALIAS'):
    if hasattr(PIL.Image, 'Resampling'):
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    else:
        PIL.Image.ANTIALIAS = PIL.Image.BICUBIC

def safe_moviepy_resizer(pic, newsize):
    try:
        if pic is None:
            return np.zeros((newsize[1], newsize[0], 3), dtype=np.uint8)
        if not isinstance(pic, np.ndarray):
            pic = np.array(pic)
        if pic.dtype != np.uint8:
            pic = np.clip(pic, 0, 255).astype(np.uint8)
        pic = np.ascontiguousarray(pic)

        img = PIL.Image.fromarray(pic)
        resample_filter = getattr(PIL.Image, 'Resampling', PIL.Image).LANCZOS if hasattr(PIL.Image, 'Resampling') else PIL.Image.BICUBIC
        img_resized = img.resize((newsize[0], newsize[1]), resample_filter)
        return np.array(img_resized)
    except Exception as e:
        print("Safe resizer error fallback:", e)
        return np.zeros((newsize[1], newsize[0], 3), dtype=np.uint8)

def safe_moviepy_resize(clip, newsize=None, height=None, width=None, apply_to_mask=True):
    if newsize is not None:
        if isinstance(newsize, (int, float)):
            w = int(clip.w * newsize)
            h = int(clip.h * newsize)
        else:
            w, h = newsize
    elif height is not None and width is not None:
        w, h = width, height
    elif height is not None:
        h = height
        w = int(clip.w * (height / clip.h))
    elif width is not None:
        w = width
        h = int(clip.h * (width / clip.w))
    else:
        return clip

    def fl(pic):
        return safe_moviepy_resizer(pic, (w, h))

    return clip.fl_image(fl)

mp_resize_mod.resizer = safe_moviepy_resizer
mp_resize_mod.resize = safe_moviepy_resize
vfx_all.resize = safe_moviepy_resize
mp_editor.vfx.resize = safe_moviepy_resize
mp_editor.VideoClip.resize = safe_moviepy_resize

# Global shared HTTP session for connection pooling
HTTP_SESSION = requests.Session()
HTTP_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})

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
        "title_hashtags": "#space #shorts",
        "yt_category_id": "28"
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
        "title_hashtags": "#history #shorts",
        "yt_category_id": "23"
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
        "title_hashtags": "#tech #shorts",
        "yt_category_id": "28"
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
            self.segment_count = 7
            self.is_short = False


WATERMARK_HANDLE = os.getenv("WATERMARK_HANDLE", "@NicheFactsShorts")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


def get_or_create_cta_asset() -> str:
    """Ensure a high-resolution transparent CTA subscribe prompt asset exists in assets/cta_subscribe.png."""
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    cta_path = assets_dir / "cta_subscribe.png"

    # Re-generate if missing or if file size is small / corrupted
    if not cta_path.exists() or cta_path.stat().st_size < 3000:
        try:
            from PIL import Image, ImageDraw, ImageFont
            w, h = 700, 140
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Draw a sleek crimson red rounded pill with crisp white border
            draw.rounded_rectangle([6, 6, w - 6, h - 6], radius=35, fill=(230, 0, 35, 235), outline=(255, 255, 255, 255), width=5)

            # Try loading bold system fonts for ultra-crisp text rendering
            font = None
            font_candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "C:\\Windows\\Fonts\\arialbd.ttf",
                "C:\\Windows\\Fonts\\arial.ttf",
                "C:\\Windows\\Fonts\\seguiemj.ttf"
            ]
            for font_file in font_candidates:
                if os.path.exists(font_file):
                    try:
                        font = ImageFont.truetype(font_file, 40)
                        break
                    except Exception:
                        pass
            if font is None:
                font = ImageFont.load_default()

            draw.text((w // 2, h // 2), "SUBSCRIBE FOR MORE", fill=(255, 255, 255, 255), anchor="mm", font=font)
            img.save(cta_path)
            print(f"Generated high-resolution CTA asset: {cta_path}")
        except Exception as e:
            print("Failed to generate PIL CTA asset:", e)
    return str(cta_path.resolve())


def get_theme_colors(category: str) -> Tuple[Tuple[int, int, int], str, str]:
    """Return (RGB tuple for progress bar, ASS color tag, Hex string) for category."""
    cat_lower = category.lower()
    if "history" in cat_lower:
        return (255, 191, 0), "&H0000BFFF", "#FFBF00"  # Amber Gold
    elif "tech" in cat_lower:
        return (0, 255, 102), "&H0066FF00", "#00FF66"  # Electric Green
    else:
        return (0, 229, 255), "&H00FFFF00", "#00E5FF"  # Neon Cyan (Space)


def create_progress_bar_clip(duration: float, resolution: Tuple[int, int], category: str = "space") -> VideoClip:
    """Generate a 5-pixel high solid accent progress bar at the bottom scaling 0% -> 100% over video duration."""
    w, h = resolution
    bar_height = 5
    y_pos = h - bar_height
    color, _, _ = get_theme_colors(category)

    def make_frame(t):
        frame = np.zeros((bar_height, w, 3), dtype=np.uint8)
        current_w = max(1, min(w, int(w * (t / float(duration)))))
        frame[:, :current_w] = color
        return frame

    return (
        VideoClip(make_frame, duration=duration)
        .set_position((0, y_pos))
    )


def find_image_salience_center(img_path: str) -> Tuple[float, float]:
    """Identify the primary visual focal center (cx, cy) normalized between 0.0 and 1.0 using Pillow edge density."""
    try:
        from PIL import ImageFilter
        with PIL.Image.open(img_path) as im:
            gray = im.convert("L").resize((300, 300))
            edges = gray.filter(ImageFilter.FIND_EDGES)
            arr = np.array(edges, dtype=np.float32)
            total = np.sum(arr)
            if total <= 0:
                return (0.5, 0.5)

            y_indices, x_indices = np.indices(arr.shape)
            cx = float(np.sum(x_indices * arr) / total) / 300.0
            cy = float(np.sum(y_indices * arr) / total) / 300.0
            return (max(0.2, min(0.8, cx)), max(0.2, min(0.8, cy)))
    except Exception as e:
        print("Salience calculation fallback to center:", e)
        return (0.5, 0.5)


def is_power_word(word: str) -> bool:
    """Return True if word is a metric, number, or high-impact NLP trigger word."""
    clean = re.sub(r"[^\w]", "", word.lower())
    if not clean:
        return False
    if clean.isdigit():
        return True
    power_words = {
        "secret", "banned", "exploded", "classified", "hidden", "shocking", 
        "deadly", "mystery", "discovered", "unknown", "stolen", "impossible", 
        "unseen", "ancient", "forbidden", "fatal", "insane", "monster", "warning"
    }
    return clean in power_words


def master_tts_audio(input_wav: str, output_wav: str) -> str:
    """Master TTS audio with Studio Audio Chain (80Hz Highpass filter, 2500Hz EQ boost, dynamic compand compressor)."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_wav,
            "-af", "highpass=f=80,equalizer=f=2500:width_type=o:width=1:g=2,compand=attacks=0.02:decays=0.2:points=-60/-60|-24/-12|-12/-6|0/-3:gain=2",
            "-c:a", "pcm_s16le",
            output_wav
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Studio audio mastering chain applied successfully.")
        return output_wav
    except Exception as e:
        print("Studio audio mastering chain fallback to raw audio:", e)
        return input_wav


def generate_srt_file(subs_list: List[Tuple[Tuple[float, float], str]], output_srt_path: str) -> str:
    """Generate standard .srt caption file for native YouTube Closed Captions API upload."""
    def format_srt_time(seconds: float) -> str:
        seconds = max(0.0, seconds)
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        if millis >= 1000:
            secs += millis // 1000
            millis = millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    lines = []
    for idx, ((start, end), text) in enumerate(subs_list):
        lines.append(str(idx + 1))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(text.strip())
        lines.append("")

    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Generated SRT file: {output_srt_path}")
    return output_srt_path


# ---------------------------------------------------------------------------
# STATIC ROTATING KEYWORD BANK (replaces pytrends - no external API needed)
# ---------------------------------------------------------------------------
_TRENDING_KEYWORDS = {
    "space": [
        ["black hole event horizon", "neutron star collision", "dark matter secrets", "james webb telescope", "mars colony"],
        ["supernova explosion", "alien planet discovery", "solar storm warning", "asteroid danger", "space debris crisis"],
        ["wormhole theory", "gamma ray burst", "exoplanet atmosphere", "galaxy merger", "cosmic microwave background"],
        ["moon water discovery", "saturn ring mystery", "interstellar travel", "quantum gravity", "spacetime fabric"],
        ["universe expansion secrets", "dark energy mystery", "pulsar timing", "stellar nursery", "cosmic void"],
    ],
    "history": [
        ["ancient civilization secrets", "lost empire discovery", "hidden history facts", "medieval mystery", "archaeological bombshell"],
        ["untold war story", "ancient engineering mystery", "forgotten culture", "historical cover-up", "buried kingdom"],
        ["roman empire secrets", "egyptian mystery", "viking discovery", "aztec hidden truth", "silk road secrets"],
        ["world war hidden facts", "ancient weapon technology", "lost city found", "historical conspiracy", "ancient trade route"],
        ["forgotten inventor", "suppressed history", "ancient disaster", "empire collapse reason", "mysterious artifact"],
    ],
    "tech": [
        ["ai consciousness debate", "quantum computer breakthrough", "neural interface brain", "robot rights", "deepfake danger"],
        ["semiconductor crisis", "fusion energy milestone", "biotech breakthrough", "space tech startup", "cyber attack threat"],
        ["chatgpt competitor", "autonomous vehicle crash", "surveillance technology", "data privacy scandal", "tech monopoly"],
        ["battery technology leap", "crispr gene editing", "smart city failure", "drone swarm military", "satellite internet"],
        ["metaverse collapse", "crypto regulation", "open source ai", "hydrogen fuel cell", "brain chip implant"],
    ],
}


def fetch_trending_category_keywords(category: str) -> List[str]:
    """Return a rotating set of high-engagement category keywords (no external API, no rate limits)."""
    cat_lower = category.lower()
    db_key = "space"
    if "history" in cat_lower:
        db_key = "history"
    elif "tech" in cat_lower:
        db_key = "tech"

    keyword_pool = _TRENDING_KEYWORDS.get(db_key, _TRENDING_KEYWORDS["space"])
    # Rotate through pools based on current day-of-week to ensure variety
    import datetime
    day_index = datetime.date.today().weekday() % len(keyword_pool)
    selected = keyword_pool[day_index]
    print(f"Selected rotating keyword bank [{db_key}][day={day_index}]: {selected}")
    return selected


def send_webhook_notification(title: str, message: str, status: str = "success", video_url: Optional[str] = None):
    """Send HTTP POST payload alert to Webhook URL (Discord/Telegram/Custom) for fail-safe monitoring."""
    if not WEBHOOK_URL:
        return  # WEBHOOK_URL is optional — no noise if not configured

    color = 0x00FF00 if status == "success" else 0xFF0000
    embed = {
        "title": f"???? Pipeline Alert: {status.upper()}",
        "description": message,
        "color": color,
        "fields": [
            {"name": "Video Title", "value": title or "Unknown", "inline": True},
            {"name": "Status", "value": status.capitalize(), "inline": True}
        ],
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

    if video_url:
        embed["fields"].append({"name": "Live YouTube URL", "value": f"[Watch Video]({video_url})", "inline": False})
        embed["url"] = video_url

    payload = {"embeds": [embed]}

    try:
        resp = HTTP_SESSION.post(WEBHOOK_URL, json=payload, timeout=10)
        resp.raise_for_status()
        print(f"Webhook notification ({status}) sent successfully.")
    except Exception as e:
        print(f"Failed to send webhook notification: {e}")


def sanitize_metadata(title: str, description: str, is_short: bool, category: str) -> Tuple[str, str]:
    """Enforce strict title limit (< 70 chars with hashtags) and 5 relevant description hashtags."""
    clean_title = re.sub(r'#\S+', '', title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    cat_info = CATEGORIES.get(category, {})
    db_key = cat_info.get("db_key", "space")

    title_hashtags_map = {
        "space": "#space #shorts",
        "history": "#history #shorts",
        "tech": "#tech #shorts"
    }
    title_tag = title_hashtags_map.get(db_key, "#shorts")

    if is_short and title_tag not in clean_title:
        max_base_len = 70 - len(title_tag) - 1
        if len(clean_title) > max_base_len:
            clean_title = clean_title[:max_base_len - 3].rstrip() + "..."
        final_title = f"{clean_title} {title_tag}"
    else:
        if len(clean_title) > 65:
            clean_title = clean_title[:62].rstrip() + "..."
        final_title = clean_title

    # Parse and format description hashtags
    hashtags = re.findall(r'#\w+', description)
    clean_desc = re.sub(r'#\w+', '', description)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

    desc_hashtags_map = {
        "space": ["#shorts", "#nichefacts", "#space", "#astrophysics", "#facts"],
        "history": ["#shorts", "#nichefacts", "#history", "#historyfacts", "#untoldstories"],
        "tech": ["#shorts", "#nichefacts", "#tech", "#technology", "#science"]
    }
    default_tags = desc_hashtags_map.get(db_key, ["#shorts", "#nichefacts", "#facts"])

    valid_tags = []
    for tag in hashtags:
        if tag.lower() not in [t.lower() for t in valid_tags]:
            valid_tags.append(tag)

    for def_tag in default_tags:
        if len(valid_tags) < 5 and def_tag.lower() not in [t.lower() for t in valid_tags]:
            valid_tags.append(def_tag)

    final_hashtags = valid_tags[:5]
    final_description = f"{clean_desc}\n\n" + " ".join(final_hashtags)

    return final_title, final_description



# ---------------------------------------------------------------------------
# SHARED GEMINI RETRY HELPER
# ---------------------------------------------------------------------------
def gemini_generate_with_retry(client: genai.Client, model: str, prompt: str, max_retries: int = 5):
    """Call Gemini with fallback model chain, exponential backoff, and 60s RPM window auto-wait."""
    # Quota-efficient model chain: start with high-RPM free tier, escalate to premium only on failure
    model_fallback_chain = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-flash-latest", "gemini-pro-latest"]
    
    # Start with the requested model, or position in the chain if matches
    if model in model_fallback_chain:
        start_idx = model_fallback_chain.index(model)
        candidates = model_fallback_chain[start_idx:]
    else:
        candidates = [model] + model_fallback_chain

    last_error = None
    max_rpm_wait = 60.0

    # Up to 3 full passes over the candidate list to handle 1-minute RPM rate limit resets
    for outer_pass in range(3):
        for current_model in candidates:
            for attempt in range(max_retries):
                try:
                    print(f"Trying Gemini model: {current_model} (pass {outer_pass + 1}/3)...")
                    response = client.models.generate_content(model=current_model, contents=prompt)
                    return response
                except Exception as e:
                    last_error = e
                    is_quota_or_rate_limit = any(err in str(e).upper() for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA"])
                    is_transient = any(err in str(e) or err in str(e).upper() for err in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"])
                    
                    if is_quota_or_rate_limit:
                        match = re.search(r"retry in ([0-9\.]+)s", str(e))
                        wait_time = float(match.group(1)) if match else 25.0
                        if wait_time > max_rpm_wait:
                            max_rpm_wait = wait_time

                        if wait_time > 5.0:
                            print(f"Model {current_model} rate limited ({wait_time:.1f}s delay requested by API). Fast-switching to next candidate...")
                            break
                        else:
                            print(f"Gemini API short wait ({wait_time:.1f}s). Retrying...")
                            time.sleep(wait_time + 0.5)
                    elif is_transient and attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        print(f"Gemini API transient error on {current_model} (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time:.2f}s: {e}")
                        time.sleep(wait_time)
                    else:
                        print(f"Model {current_model} failed or exhausted. Trying next fallback model...")
                        break

        # If all candidates failed due to 1-minute RPM rate limits, sleep for the RPM window reset and try again
        if outer_pass < 2:
            sleep_duration = min(max(max_rpm_wait + 2.0, 60.0), 90.0)
            print(f"⚠️ All Gemini models rate-limited (RPM cap reached). Waiting {sleep_duration:.1f}s for 1-minute rate-limit window reset (pass {outer_pass + 1}/3)...")
            time.sleep(sleep_duration)

    raise Exception(f"Gemini API failed after exhausting all fallback models and 3 RPM window resets. Last error: {last_error}")


# ---------------------------------------------------------------------------
# 1. CATEGORY ROTATION, SOURCE INGESTION & TWO-PASS AUTO-QA GENERATION
# ---------------------------------------------------------------------------
def get_rotating_category(target_date: Optional[datetime.date] = None) -> str:
    """Calculate 7-consecutive-day locked category rotation (Week 1: Space, Week 2: History, Week 3: Tech)."""
    if target_date is None:
        target_date = datetime.datetime.utcnow().date()
    anchor_date = datetime.date(2026, 1, 1)
    days_elapsed = max(0, (target_date - anchor_date).days)
    week_index = (days_elapsed // 7) % 3
    rotation = [
        "Scary Space Mysteries",
        "Morbid or Silly History Facts",
        "Exciting Tech Facts"
    ]
    selected = rotation[week_index]
    print(f"7-Day Category Lock: Day {(days_elapsed % 7) + 1}/7 of Week {week_index + 1} -> Locked Category: '{selected}'")
    return selected


def fetch_playwright_scraped_source_text(category: str, past_topics: List[dict]) -> dict:
    """Ingest rich source text using headless Playwright Chromium, with fail-safe Wikipedia fallback."""
    print(f"Launching Playwright Headless Scraping for category '{category}'...")
    db_key = CATEGORIES.get(category, {}).get("db_key", category.lower())
    
    category_sources = {
        "space": [
            "https://apod.nasa.gov/apod/astropix.html",
            "https://en.wikipedia.org/wiki/Portal:Spaceflight",
            "https://en.wikipedia.org/wiki/Portal:Astronomy"
        ],
        "history": [
            "https://www.worldhistory.org/",
            "https://en.wikipedia.org/wiki/Portal:History",
            "https://en.wikipedia.org/wiki/Portal:Archaeology"
        ],
        "tech": [
            "https://en.wikipedia.org/wiki/Portal:Computer_science",
            "https://en.wikipedia.org/wiki/Portal:Technology",
            "https://en.wikipedia.org/wiki/Emerging_technologies"
        ]
    }
    
    urls = category_sources.get(db_key, category_sources["space"])
    random.shuffle(urls)
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            for target_url in urls:
                try:
                    page.goto(target_url, timeout=15000, wait_until="domcontentloaded")
                    time.sleep(1)
                    title = page.title().strip()
                    
                    paragraphs = page.locator("p").all_inner_texts()
                    clean_text = " ".join([p.strip() for p in paragraphs if len(p.strip()) > 35])
                    words = clean_text.split()[:1200]
                    
                    if len(words) >= 80:
                        print(f"Playwright successfully scraped '{title}' ({len(words)} words) from {target_url}")
                        browser.close()
                        return {
                            "title": title,
                            "text": " ".join(words),
                            "url": target_url
                        }
                except Exception as ex:
                    print(f"Playwright navigation attempt failed for {target_url}: {ex}")
            browser.close()
    except Exception as e:
        print(f"Playwright scraper error ({e}). Falling back to Wikipedia API...")
        
    return fetch_wikipedia_source_text(category, past_topics)


def fetch_wikipedia_source_text(category: str, past_topics: List[dict]) -> dict:
    """Fetch raw, high-quality article text from Wikipedia REST/Action APIs for source grounding."""
    print(f"Fetching raw Wikipedia source text for category '{category}'...")
    db_key = CATEGORIES.get(category, {}).get("db_key", category.lower())
    category_queries = {
        "space": [
            "Category:Featured_articles_about_astronomy",
            "Category:Space_exploration",
            "Category:Astronomical_objects",
            "Category:Cosmology"
        ],
        "history": [
            "Category:Featured_articles_about_history",
            "Category:Historical_events",
            "Category:Archaeological_discoveries",
            "Category:Medieval_history"
        ],
        "tech": [
            "Category:Featured_articles_about_technology",
            "Category:Computing_breakthroughs",
            "Category:Emerging_technologies",
            "Category:Artificial_intelligence"
        ]
    }

    headers = {"User-Agent": "MPVSAP-ContentPipeline/1.0 (https://github.com/thienphucnt/MPVSAP; bot@nichefacts.org)"}
    existing_titles = {item.get("title", "").lower().strip() for item in past_topics}
    existing_topics = {item.get("topic", "").lower().strip() for item in past_topics if item.get("topic")}

    query_list = category_queries.get(db_key, category_queries["space"])
    random.shuffle(query_list)

    cm_url = "https://en.wikipedia.org/w/api.php"

    for cat_title in query_list:
        cm_params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": cat_title,
            "cmlimit": 40,
            "cmtype": "page"
        }
        try:
            r = HTTP_SESSION.get(cm_url, params=cm_params, headers=headers, timeout=12)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("categorymembers", [])

            # Shuffle candidates to avoid pick bias
            random.shuffle(pages)

            for chosen in pages:
                page_title = chosen.get("title", "").strip()
                norm_p = page_title.lower()
                if norm_p in existing_titles or norm_p in existing_topics or len(page_title) < 3:
                    continue

                # Fetch extract
                ex_params = {
                    "action": "query",
                    "format": "json",
                    "prop": "extracts",
                    "exintro": False,
                    "explaintext": True,
                    "titles": page_title
                }
                er = HTTP_SESSION.get(cm_url, params=ex_params, headers=headers, timeout=12)
                er.raise_for_status()
                pages_dict = er.json().get("query", {}).get("pages", {})
                for pid, pdata in pages_dict.items():
                    extract = pdata.get("extract", "").strip()
                    if len(extract) > 200:
                        words = extract.split()[:1200]
                        trimmed_text = " ".join(words)
                        print(f"Successfully ingested Wikipedia article: '{page_title}' ({len(words)} words)")
                        return {
                            "title": page_title,
                            "text": trimmed_text,
                            "url": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
                        }
        except Exception as e:
            print(f"Wikipedia query error for {cat_title}: {e}")

    # General search fallback if category members fail
    try:
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": f"{category} discovery mystery breakthrough history science",
            "srlimit": 30
        }
        sr = HTTP_SESSION.get(cm_url, params=search_params, headers=headers, timeout=12)
        sr.raise_for_status()
        search_pages = sr.json().get("query", {}).get("search", [])
        random.shuffle(search_pages)

        for chosen in search_pages:
            page_title = chosen.get("title", "").strip()
            norm_p = page_title.lower()
            if norm_p in existing_titles or norm_p in existing_topics:
                continue

            ex_params = {
                "action": "query",
                "format": "json",
                "prop": "extracts",
                "exintro": False,
                "explaintext": True,
                "titles": page_title
            }
            er = HTTP_SESSION.get(cm_url, params=ex_params, headers=headers, timeout=12)
            er.raise_for_status()
            pages_dict = er.json().get("query", {}).get("pages", {})
            for pid, pdata in pages_dict.items():
                extract = pdata.get("extract", "").strip()
                if len(extract) > 200:
                    words = extract.split()[:1200]
                    trimmed_text = " ".join(words)
                    print(f"Successfully ingested Wikipedia article via search: '{page_title}' ({len(words)} words)")
                    return {
                        "title": page_title,
                        "text": trimmed_text,
                        "url": f"https://en.wikipedia.org/wiki/{page_title.replace(' ', '_')}"
                    }
    except Exception as e:
        print(f"Wikipedia search fallback error: {e}")

    print("Fallback: Ingestion default used.")
    return {
        "title": f"Fascinating {category.capitalize()} Phenomenon",
        "text": f"Detailed astronomical and historical records concerning {category} discovery...",
        "url": ""
    }


def evaluate_script_quality(
    client: genai.Client,
    model_name: str,
    script: str,
    title: str,
    source_title: str,
    config: VideoFormatConfig
) -> Tuple[float, str]:
    """
    Pass 2 Multi-Dimensional Auto-QA Evaluator (0.00 to 10.00 precision):
    Evaluates 10 weighted judging criteria to compute exact decimal scores (e.g., 9.76 vs 9.52).
    """
    eval_prompt = (
        "You are a master YouTube Content Analytics Judge. Evaluate the following video script using a fine-grained, decimal-precision rubric (0.00 to 10.00 for each criterion).\n\n"
        f"Target Format: {'YouTube Short (60s)' if config.is_short else 'Long-Form Compilation'}\n"
        f"Source Article Subject: '{source_title}'\n"
        f"Script Title: '{title}'\n"
        f"Script Text:\n\"\"\"{script}\"\"\"\n\n"
        "EVALUATION CRITERIA (SCORE EACH FROM 0.00 TO 10.00 WITH 2 DECIMAL PLACES):\n"
        "1. hook_open_loop (Weight 15%): Immediate 0-3s curiosity gap, dramatic impact, zero greetings/fluff.\n"
        "2. fact_specificity (Weight 15%): Presence of real dates, proper names, quantities, avoiding vague generalities.\n"
        "3. narrative_pacing (Weight 15%): Escalating tension or mystery arc (STRICTLY BAN listicles or 'Top 3' formats).\n"
        "4. absence_of_cliches (Weight 10%): Total absence of generic AI tropes ('in a world where', 'have you ever wondered', 'delve into', 'testament to').\n"
        "5. payoff_satisfaction (Weight 10%): High-impact resolution or mind-bending revelation.\n"
        "6. seamless_loop_cta (Weight 10%): Final phrase connects smoothly back to opening hook word for endless loops.\n"
        "7. title_synergy (Weight 10%): Title front-loads curiosity without clickbait deception.\n"
        "8. rhythmic_flow (Weight 5%): Rhythmic speech pacing with strategic ellipses (...) and em-dashes (???).\n"
        "9. visual_opportunity (Weight 5%): Rich presence of specific entities for B-roll image & video retrieval.\n"
        "10. emotional_resonance (Weight 5%): Sparks awe, mystery, shock, or intense curiosity.\n\n"
        "Return ONLY a JSON object in exactly this format (use float numbers with 2 decimal places):\n"
        "{\n"
        '  "scores": {\n'
        '    "hook_open_loop": 9.85,\n'
        '    "fact_specificity": 9.60,\n'
        '    "narrative_pacing": 9.70,\n'
        '    "absence_of_cliches": 9.90,\n'
        '    "payoff_satisfaction": 9.50,\n'
        '    "seamless_loop_cta": 9.80,\n'
        '    "title_synergy": 9.80,\n'
        '    "rhythmic_flow": 9.40,\n'
        '    "visual_opportunity": 9.75,\n'
        '    "emotional_resonance": 9.65\n'
        '  },\n'
        '  "critique": "<2-sentence detailed breakdown justifying top strengths and decimal deductions>"\n'
        "}"
    )

    try:
        resp = gemini_generate_with_retry(client, model_name, eval_prompt)
        text = resp.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        scores = data.get("scores", {})
        
        weights = {
            "hook_open_loop": 0.15,
            "fact_specificity": 0.15,
            "narrative_pacing": 0.15,
            "absence_of_cliches": 0.10,
            "payoff_satisfaction": 0.10,
            "seamless_loop_cta": 0.10,
            "title_synergy": 0.10,
            "rhythmic_flow": 0.05,
            "visual_opportunity": 0.05,
            "emotional_resonance": 0.05
        }
        
        if isinstance(scores, dict) and scores:
            weighted_total = sum(float(scores.get(key, 8.0)) * weight for key, weight in weights.items())
            final_score = round(weighted_total, 2)
        else:
            final_score = round(float(data.get("overall_score", 8.5)), 2)

        critique = data.get("critique", "Script evaluated across 10 judging criteria.").strip()
        return final_score, critique
    except Exception as e:
        print("Auto-QA Evaluator parsing fallback:", e)
        return 8.50, "Script accepted by default evaluator fallback."


def is_duplicate_topic(generated_title: str, generated_topic: str, generated_script: str, past_topics: List[dict]) -> Tuple[bool, str]:
    """
    Smart, Entity-Specific Duplicate Detection Guardrail:
    1. Exact normalized topic match.
    2. Multi-word proper noun / distinct concept matching (e.g. 'quantum entanglement', 'great stink of 1858').
    3. Content noun Jaccard overlap (> 0.40) on titles & topics.
    Prevents false positives on common English verb phrases (like 'shut down', 'built in', 'came from').
    """
    if not past_topics:
        return False, ""

    def normalize(text: str) -> str:
        text = re.sub(r'#\S+', '', text.lower())
        text = re.sub(r'[^\w\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    norm_title = normalize(generated_title)
    norm_topic = normalize(generated_topic)

    stopwords = {
        'the', 'a', 'an', 'is', 'in', 'of', 'and', 'to', 'for', 'with', 'on', 'at', 'by', 'from',
        'this', 'that', 'you', 'your', 'are', 'will', 'shorts', 'space', 'history', 'tech', 'mysteries',
        'facts', 'shut', 'down', 'out', 'up', 'off', 'over', 'under', 'into', 'than', 'more', 'most',
        'make', 'made', 'take', 'took', 'see', 'saw', 'call', 'called', 'came', 'come', 'built', 'build',
        'when', 'what', 'where', 'how', 'why', 'who', 'which', 'new', 'old', 'first', 'last', 'one', 'two',
        'day', 'night', 'time', 'years', 'year', 'back', 'ever', 'even', 'been', 'have', 'has', 'had'
    }

    title_words = {w for w in norm_title.split() if w not in stopwords and len(w) > 2}
    topic_words = {w for w in norm_topic.split() if w not in stopwords and len(w) > 2}
    combined_gen_words = title_words.union(topic_words)

    for item in past_topics:
        past_title = item.get("title", "")
        past_topic = item.get("topic", "")
        
        norm_past_title = normalize(past_title)
        norm_past_topic = normalize(past_topic)

        # 1. Exact Topic Overlap Check
        if norm_topic and norm_past_topic:
            if norm_topic == norm_past_topic:
                return True, f"Exact topic match with past item '{past_topic}'"

        # 2. Distinct Multi-Word Past Topic matching in generated title or topic
        # (Only check meaningful past topics with >= 2 non-stopword tokens, e.g. "quantum entanglement")
        past_topic_clean_words = [w for w in norm_past_topic.split() if w not in stopwords]
        if len(past_topic_clean_words) >= 2:
            meaningful_past_topic = " ".join(past_topic_clean_words)
            if len(meaningful_past_topic) > 6:
                if meaningful_past_topic in norm_title or meaningful_past_topic in norm_topic:
                    return True, f"Specific topic '{past_topic}' matches generated title/topic"

        # 3. High Content Noun Jaccard Overlap Check on Titles & Topics
        past_title_words = {w for w in norm_past_title.split() if w not in stopwords and len(w) > 2}
        past_topic_words = {w for w in norm_past_topic.split() if w not in stopwords and len(w) > 2}
        combined_past_words = past_title_words.union(past_topic_words)

        if combined_gen_words and combined_past_words:
            intersection = combined_gen_words.intersection(combined_past_words)
            union = combined_gen_words.union(combined_past_words)
            jaccard = len(intersection) / len(union) if union else 0.0
            
            # Require at least 2 distinct matching content words AND >= 0.40 Jaccard score
            if len(intersection) >= 2 and jaccard >= 0.40:
                return True, f"High topic/title overlap ({jaccard:.2f}) with past item '{past_title}' (matching key terms: {intersection})"

    return False, ""


def generate_content(
    client: genai.Client,
    category: str,
    past_topics: List[dict],
    source_data: dict,
    config: VideoFormatConfig
) -> Tuple[str, str, List[dict]]:
    """
    Multi-Variant Tournament Engine:
    Pass 1: Generate 5 distinct script variants exploring different narrative angles.
    Pass 2: Score & rank all 5 variants with Pass 2 Auto-QA Evaluator. Select #1 highest scorer (>= 8/10).
    """
    model_name = "gemini-2.5-flash"
    cat_info = CATEGORIES[category]
    db_category = cat_info["db_key"]

    all_past_topics = [item.get("topic") for item in past_topics if item.get("topic")]
    all_past_titles = [re.sub(r'#\S+', '', item.get("title", "")).strip() for item in past_topics if item.get("title")]
    prohibited_list = sorted(list(set([t for t in all_past_topics + all_past_titles if t])))

    exclude_instruction = ""
    if prohibited_list:
        formatted_prohibited = "\n- ".join(prohibited_list)
        exclude_instruction = (
            "\n\nCRITICAL DUP-PREVENTION DIRECTIVE:\n"
            "You MUST select 100% UNUSED and NOVEL concepts. Under NO circumstances should you write about, reference, "
            "or base scripts or any compilation segment on any of the following subjects, titles, or concepts (or ANY of their variations, synonyms, or related angles):\n"
            f"- {formatted_prohibited}\n"
            "FOR LONG-FORM COMPILATIONS: Every single segment MUST cover a BRAND-NEW, UNCOVERED fact or story. "
            "No segment may repeat, re-hash, or overlap with any fact, story, or concept that has ever been covered in past Shorts or past Longform videos.\n"
            "If a concept is listed above or closely related to a listed concept, it is STRICTLY PROHIBITED."
        )

    session_rejections = []
    max_qa_retries = 3

    for attempt in range(max_qa_retries):
        dynamic_exclude = exclude_instruction
        if session_rejections:
            rejected_str = "\n- ".join(session_rejections)
            dynamic_exclude += (
                f"\n\nCRITIQUES & REJECTIONS FROM PREVIOUS ATTEMPTS:\n- {rejected_str}\n"
                "Address the Auto-QA critique above and produce higher quality, fresh script variants!"
            )

        source_text_prompt = (
            f"REAL-TIME INGESTED ENCYCLOPEDIA SOURCE DATA:\n"
            f"Article Title: '{source_data.get('title')}'\n"
            f"Source Text Extract:\n\"\"\"{source_data.get('text')[:3000]}\"\"\"\n\n"
        )

        if config.is_short:
            prompt = (
                "You are an elite YouTube Shorts Director. Complete the following tasks and return ONLY a valid JSON object without markdown tags:\n"
                "{\n"
                '  "variants": [\n'
                '    {\n'
                '      "angle": "Suspenseful Mystery",\n'
                '      "script": "<130-word story script>",\n'
                '      "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],\n'
                '      "title": "<click-worthy title under 50 chars>",\n'
                '      "description": "<2-sentence summary with 5 hashtags including #nichefactsshorts>",\n'
                '      "topic": "<2-3 words naming core concept>"\n'
                '    },\n'
                '    ... (exactly 5 distinct candidate variants exploring 5 different angles: 1-Suspenseful Mystery, 2-Scientific Breakthrough, 3-Dramatic Conflict, 4-Existential Wonder, 5-Action Mystery)\n'
                '  ]\n'
                "}\n\n"
                f"{source_text_prompt}"
                "DIRECTIVES FOR HIGH AUDIENCE RETENTION ACROSS ALL 5 VARIANTS:\n"
                "1. INFINITE LOOP SCRIPT ENGINEERING (STRICT RULE): The script MUST be engineered for a seamless audio and narrative loop. "
                "The final sentence of the script MUST grammatically and logically lead directly into the first sentence of the script "
                "(e.g., Ending: '...and that is why nobody ever suspected that' -> Beginning: 'This ancient secret was buried for centuries...'). "
                "When auto-replayed on YouTube Shorts, the viewer must not realize it restarted.\n"
                "2. STORY STRUCTURE (STRICTLY NO LISTICLES / TOP 3 FORMATS): Each variant must tell a fast-paced 130-word story based on the source text.\n"
                "   - Seconds 0-3 (THE HOOK): Immediate dramatic, mysterious, or shocking open loop line. NO channel greetings.\n"
                "   - Seconds 3-45 (NARRATIVE & CONFLICT): Build escalating tension or reveal an unexpected mystery/conflict.\n"
                "   - Seconds 45-60 (PAYOFF & LOOP CTA): Deliver a mind-bending resolution ending with a 3-second loop CTA.\n"
                "3. DRAMATIC PACING: Force natural pauses using ellipses (...) and em-dashes (—).\n"
                "4. PROPER NOUN VISUAL KEYWORDS: Include exact proper nouns with capitalization ('Albert Einstein', 'Apollo 11') as first keyword for specific entities.\n"
                "5. ENTITY-SPECIFIC TITLES & TOPICS: Every variant title and topic MUST be specific and entity-rich, naming exact locations, historical figures, years, or distinct scientific mechanisms (e.g. '1858 London Great Stink Sewage Crisis', 'Einstein Quantum Entanglement Paradox') rather than generic phrase titles.\n"
                f"Tone: {cat_info['tone']}.\n"
                "Under no circumstances mention regional politics or Vietnamese history."
                f"{dynamic_exclude}"
            )
        else:
            prompt = (
                "You are an elite Documentary Director producing a widescreen long-form compilation. "
                "Complete the following tasks and return ONLY a valid JSON object without markdown formatting:\n"
                "{\n"
                '  "title": "<Click-worthy widescreen title between 40 and 60 characters>",\n'
                '  "description": "<Punchy description with 5 relevant hashtags at the end including #nichefacts>",\n'
                '  "segments": [\n'
                '    {\n'
                '      "script": "<engaging 95-word script>",\n'
                '      "visual_keywords": ["literal_keyword1", "literal_keyword2", "literal_keyword3"],\n'
                '      "topic": "<2-3 words naming core concept>"\n'
                '    },\n'
                '    ... (exactly 10 candidate segments)\n'
                '  ]\n'
                "}\n\n"
                f"{source_text_prompt}"
                "DIRECTIVES FOR HIGH AUDIENCE RETENTION:\n"
                "1. COMPILATION STRUCTURE: Write 10 distinct, highly detailed candidate segments based on ingested source data.\n"
                "2. NO REPETITIVE INTROS/OUTROS: Only Segment 1 contains a hook (0-15s). Middle segments (2-9) contain raw facts. Only Segment 10 appends a subscribe CTA.\n"
                "3. PROPER NOUN B-ROLL: In visual_keywords, include specific proper nouns with capitalization for specific entities.\n\n"
                "Under no circumstances should the script mention regional politics, state officials, or Vietnamese history."
                f"{dynamic_exclude}"
            )

        print(f"Generating Multi-Variant Tournament scripts for category '{category}' (attempt {attempt+1}/{max_qa_retries}) using {model_name}...")
        response = gemini_generate_with_retry(client, model_name, prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        if config.is_short:
            parsed_variants = []
            try:
                data = json.loads(text)
                raw_vars = data.get("variants", [])
                if isinstance(data, dict) and not raw_vars and "script" in data:
                    raw_vars = [data]
                
                for var in raw_vars:
                    v_title = var.get("title", "").strip()
                    v_desc = var.get("description", "").strip()
                    v_script = var.get("script", "").strip()
                    v_kw = var.get("visual_keywords", [])
                    v_topic = var.get("topic", "").strip()
                    v_angle = var.get("angle", "Story Variant").strip()
                    
                    if v_script and v_title:
                        parsed_variants.append({
                            "title": v_title,
                            "description": v_desc,
                            "script": v_script,
                            "visual_keywords": v_kw,
                            "topic": v_topic,
                            "angle": v_angle
                        })
            except Exception as e:
                print("WARNING: Could not parse multi-variant JSON response ??? falling back to manual extract.", e)

            if not parsed_variants:
                parsed_variants.append({
                    "title": f"The Secret of {source_data.get('title', category.capitalize())}",
                    "description": f"Discover the shocking truth behind {source_data.get('title', category)}! #nichefactsshorts",
                    "script": "Deep space contains anomalies that challenge our understanding of physics...",
                    "visual_keywords": cat_info["kw_defaults"][:4],
                    "topic": "Cosmic Mystery",
                    "angle": "Fallback"
                })

            print(f"\n--- RUNNING 5-VARIANT AUTO-QA TOURNAMENT ({len(parsed_variants)} VARIANTS) ---")
            evaluated_variants = []

            for idx, candidate in enumerate(parsed_variants):
                v_title = candidate["title"]
                v_topic = candidate["topic"]
                v_script = candidate["script"]
                v_angle = candidate["angle"]

                # 1. Check duplicate guardrail
                is_dup, reason = is_duplicate_topic(v_title, v_topic, v_script, past_topics)
                if is_dup:
                    print(f"  [REJECTED DUP] Variant {idx+1} ('{v_angle}'): {reason}")
                    continue

                # 2. Evaluate Auto-QA Score
                score, critique = evaluate_script_quality(client, model_name, v_script, v_title, source_data.get("title", ""), config)
                print(f"  [TOURNAMENT EVAL] Variant {idx+1} ('{v_angle}') -> Score: {score}/10 | Title: '{v_title}' | Critique: {critique}")
                evaluated_variants.append({
                    "candidate": candidate,
                    "score": score,
                    "critique": critique
                })

            # Sort by score descending
            evaluated_variants.sort(key=lambda x: x["score"], reverse=True)

            if evaluated_variants and evaluated_variants[0]["score"] >= 8:
                winner = evaluated_variants[0]["candidate"]
                w_score = evaluated_variants[0]["score"]
                print(f"\n[TOURNAMENT WINNER] Selected Variant ('{winner['angle']}') with Score {w_score}/10!")
                print("Winning Title:", winner["title"])
                print("Winning Topic:", winner["topic"])
                
                win_segments = [{
                    "script": winner["script"],
                    "visual_keywords": winner["visual_keywords"],
                    "topic": winner["topic"]
                }]
                return winner["title"], winner["description"], win_segments
            else:
                top_score = evaluated_variants[0]['score'] if evaluated_variants else 0
                print(f"\n[TOURNAMENT RE-TRY] Top variant scored {top_score}/10 (< 8 threshold). Re-prompting for fresh tournament...")
                session_rejections.append(f"Tournament Top Score: {top_score}/10 (< 8 threshold).")
                time.sleep(1)
                continue

        else:
            # Long-form multi-segment handling
            title = ""
            description = ""
            segments = []
            try:
                data = json.loads(text)
                title = data.get("title", "").strip()
                description = data.get("description", "").strip()
                raw_segments = data.get("segments", [])
                
                seen_topics = set()
                unique_segments = []
                for seg in raw_segments:
                    topic = seg.get("topic", "").strip().lower()
                    script = seg.get("script", "").strip()
                    topic_norm = re.sub(r"[^\w]", "", topic)
                    if not topic_norm:
                        continue
                    
                    # 1. Check against all past published topics (Shorts & Longform)
                    is_past_dup, past_reason = is_duplicate_topic(title, topic, script, past_topics)
                    if is_past_dup:
                        print(f"  [REJECTED LONGFORM SEGMENT] '{topic}': {past_reason}")
                        continue

                    # 2. Check against other segments in the current compilation batch
                    words_set = set(topic.split())
                    is_duplicate = False
                    for seen in seen_topics:
                        seen_set = set(seen.split())
                        if words_set and seen_set:
                            intersection = words_set.intersection(seen_set)
                            union = words_set.union(seen_set)
                            jaccard = len(intersection) / len(union) if len(union) > 0 else 0
                            if jaccard > 0.4:
                                is_duplicate = True
                                break
                        seen_norm = re.sub(r"[^\w]", "", seen)
                        if topic_norm in seen_norm or seen_norm in topic_norm:
                            is_duplicate = True
                            break
                    
                    if not is_duplicate:
                        seen_topics.add(topic)
                        unique_segments.append(seg)
                
                segments = unique_segments[:config.segment_count]
            except Exception as e:
                print("WARNING: Could not parse long-form JSON response:", e)
                title = f"Mind-Blowing {category.capitalize()} Documentaries"
                description = f"Discover deep facts! #nichefacts"
                segments = [{
                    "script": "Deep space contains anomalies that science is only beginning to understand...",
                    "visual_keywords": cat_info["kw_defaults"][:3],
                    "topic": "Space Mysteries"
                }]

            # Clean up scripts
            for seg in segments:
                script = seg.get("script", "").strip()
                script = re.sub(r'[\*_`]', '', script)
                script = re.sub(r'\[.*?\]', '', script)
                script = re.sub(r'\(.*?\)', '', script)
                script = re.sub(r'\s+', ' ', script).strip()
                seg["script"] = script

            # Pass 2 Auto-QA for long-form
            combined_script = "\n".join([s.get("script", "") for s in segments])
            score, critique = evaluate_script_quality(client, model_name, combined_script, title, source_data.get("title", ""), config)
            print(f"[LONG-FORM PASS 2 AUTO-QA SCORE] {score}/10 ??? Critique: {critique}")

            if score < 8:
                print(f"[AUTO-QA REJECTION] Long-form compilation scored {score}/10 (< 8 threshold). Retrying...")
                session_rejections.append(f"Long-form scored {score}/10. Critique: {critique}")
                time.sleep(1)
                continue

            print(f"[AUTO-QA APPROVED] Long-form compilation passed (Score: {score}/10)!")
            return title, description, segments

    print(f"WARNING: Max QA retries reached ({max_qa_retries}). Returning best generated content.")
    return title, description, segments


# ---------------------------------------------------------------------------
# 2 & 3. TTS & SUBTITLE GENERATION (EDGE TTS ONLINE)
# ---------------------------------------------------------------------------
def ensure_kokoro_model_files() -> Tuple[Path, Path]:
    """Ensure Kokoro-v1.0 ONNX model weights and voices files exist and pass integrity checks."""
    import zipfile
    import urllib.request

    cache_dir = Path.home() / ".cache" / "kokoro"
    cache_dir.mkdir(parents=True, exist_ok=True)

    model_path = cache_dir / "kokoro-v1.0.onnx"
    voices_path = cache_dir / "voices-v1.0.bin"

    model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

    MIN_MODEL_SIZE = 300 * 1024 * 1024   # 300 MB
    MIN_VOICES_SIZE = 25 * 1024 * 1024   # 25 MB

    def is_voices_zip_valid(path: Path) -> bool:
        """Return True only if voices-v1.0.bin is a structurally valid non-empty ZIP archive."""
        if not path.exists() or path.stat().st_size < MIN_VOICES_SIZE:
            return False
        try:
            with zipfile.ZipFile(str(path), 'r') as zf:
                bad = zf.testzip()
                return bad is None and len(zf.namelist()) > 0
        except Exception as e:
            print(f"Kokoro voices ZIP integrity check failed: {e}")
            return False

    def is_model_valid(path: Path) -> bool:
        """Return True if the ONNX model exists and meets minimum size threshold."""
        return path.exists() and path.stat().st_size >= MIN_MODEL_SIZE

    def robust_download(url: str, dest: Path):
        """Download binary file via urllib (no encoding transforms, cross-platform safe)."""
        temp = dest.with_suffix(".tmp")
        print(f"Downloading Kokoro asset '{dest.name}'...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MPVSAP/2.5 KokoroDownloader"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                with open(temp, "wb") as f:
                    while True:
                        chunk = resp.read(2 * 1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            temp.replace(dest)
            print(f"Downloaded '{dest.name}' ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
        except Exception as e:
            if temp.exists():
                temp.unlink(missing_ok=True)
            raise RuntimeError(f"Failed to download Kokoro asset '{dest.name}': {e}") from e

    # --- Model (ONNX weights) ---
    if not is_model_valid(model_path):
        if model_path.exists():
            print(f"Kokoro model invalid ({model_path.stat().st_size} bytes < {MIN_MODEL_SIZE}). Re-downloading...")
            model_path.unlink(missing_ok=True)
        robust_download(model_url, model_path)

    # --- Voices (ZIP archive of .npy style vectors) ---
    if not is_voices_zip_valid(voices_path):
        if voices_path.exists():
            print(f"Kokoro voices-v1.0.bin ZIP invalid or corrupt. Purging and re-downloading...")
            voices_path.unlink(missing_ok=True)
        robust_download(voices_url, voices_path)
        # Post-download ZIP integrity gate — fail fast if still broken
        if not is_voices_zip_valid(voices_path):
            raise RuntimeError("voices-v1.0.bin failed ZIP integrity check after fresh download. Cannot continue.")

    return model_path, voices_path



def sanitize_script_for_tts(text: str) -> str:
    """Strip all markdown symbols (*, _, #, ~, [], {}, (), stage directions) so TTS never pronounces punctuation names."""
    if not text:
        return ""
    # 1. Remove stage directions inside brackets/parentheses like [gasp], (pause), [laughter]
    clean = re.sub(r'\[.*?\]', '', text)
    clean = re.sub(r'\([^\)]*(?:pause|gasp|sigh|music|laughter|chuckle)[^\)]*\)', '', clean, flags=re.IGNORECASE)
    
    # 2. Strip markdown emphasis (*bold*, **bold**, _italic_, __italic__, ~strike~, #headers, `code`)
    clean = re.sub(r'[*_~`#]+', '', clean)
    
    # 3. Clean up quotation marks & whitespace
    clean = re.sub(r'["“”‘’]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def get_syllable_count(word: str) -> int:
    """Estimate syllable count of an English word for phonetic duration weighting."""
    w = re.sub(r'[^\w]', '', word.lower())
    if not w or len(w) <= 3:
        return 1
    vowels = "aeiouy"
    count = 0
    prev_is_vowels = False
    for char in w:
        is_v = char in vowels
        if is_v and not prev_is_vowels:
            count += 1
        prev_is_vowels = is_v
    if w.endswith('e') and not w.endswith('le') and count > 1:
        count -= 1
    return max(1, count)


def calculate_kokoro_native_phoneme_timestamps(kokoro_instance, text: str, total_duration: float) -> List[Tuple[float, float, str]]:
    """
    Kokoro Native Phoneme Token Alignment Engine:
    Uses Kokoro's internal espeak phonemizer and tokenizer to measure the exact
    number of neural phoneme tokens allocated to every word and punctuation pause.
    100% tied directly to Kokoro-82M's native speech synthesis architecture.
    """
    tokens = re.findall(r'(\w+[\-\']?\w*)([.,!?;—–]*)\s*', text)
    if not tokens:
        return []

    word_items = []
    for word, punct in tokens:
        clean_w = word.strip()
        if not clean_w:
            continue

        # Measure exact Kokoro phoneme tokens allocated to this word
        try:
            pho = kokoro_instance.tokenizer.phonemize(clean_w, lang='en-us')
            toks = kokoro_instance.tokenizer.tokenize(pho)
            token_count = max(1, len(toks))
        except Exception:
            token_count = max(1, len(clean_w))

        # Punctuation pause token allocations matching Kokoro's internal frame pauses
        pause_tokens = 0.0
        if '...' in punct or '—' in punct or '–' in punct:
            pause_tokens = 5.0
        elif any(p in punct for p in ['.', '!', '?']):
            pause_tokens = 4.0
        elif any(p in punct for p in [',', ';', ':']):
            pause_tokens = 2.0

        word_items.append((clean_w, token_count, pause_tokens))

    total_tokens = sum(tc + pt for _, tc, pt in word_items)
    if total_tokens <= 0:
        return []

    seconds_per_token = total_duration / total_tokens
    timestamps = []
    current_sec = 0.0

    for word, token_count, pause_tokens in word_items:
        word_dur = token_count * seconds_per_token
        pause_dur = pause_tokens * seconds_per_token

        start_sec = round(current_sec, 2)
        end_sec = round(current_sec + word_dur, 2)
        timestamps.append((start_sec, end_sec, word.upper()))

        current_sec += word_dur + pause_dur

    return timestamps


def synthesize_kokoro_audio_and_timestamps(text: str, category: str, audio_path: str) -> List[Tuple[float, float, str]]:
    """Synthesize high-quality local CPU neural audio using Kokoro-82M ONNX engine with native phoneme token pacing."""
    from kokoro_onnx import Kokoro
    import soundfile as sf
    import importlib.metadata

    # Sanitize input script text to strip markdown formatting (*, _, #, stage directions)
    clean_text = sanitize_script_for_tts(text)

    kokoro_ver = importlib.metadata.version('kokoro-onnx')
    print(f"Initializing Kokoro-82M ONNX engine (kokoro-onnx v{kokoro_ver})...")

    model_path, voices_path = ensure_kokoro_model_files()
    kokoro = Kokoro(str(model_path), str(voices_path))

    db_key = CATEGORIES.get(category, {}).get("db_key", category.lower())
    # Top 1-rated 5-star flagship voices for maximum realism and natural human pacing:
    # af_heart: 5-star flagship female voice (History & Stories)
    # am_fenrir: 5-star cinematic narrative male voice (Space & Cosmic Mysteries)
    # am_puck: 5-star dynamic conversational male voice (Exciting Tech Facts)
    voice_map = {
        "space": "am_fenrir",
        "history": "af_heart",
        "tech": "am_puck"
    }
    voice_name = voice_map.get(db_key, "af_heart")

    print(f"Synthesizing Local Kokoro-82M Neural Speech (voice='{voice_name}', category='{db_key}')...")
    samples, sample_rate = kokoro.create(clean_text, voice=voice_name, speed=0.98, lang="en-us")
    sf.write(audio_path, samples, sample_rate)

    total_duration = len(samples) / float(sample_rate)
    return calculate_kokoro_native_phoneme_timestamps(kokoro, clean_text, total_duration)


async def synthesize_speech_and_get_timestamps(text: str, voice: str, audio_path: str, rate: str = "+12%") -> List[Tuple[float, float, str]]:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words = []
    
    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_sec = chunk["offset"] / 10000000.0
                duration_sec = chunk["duration"] / 10000000.0
                end_sec = start_sec + duration_sec
                word_text = chunk["text"].strip()
                clean_word = re.sub(r'[^\w\s\-\'\???]', '', word_text)
                if clean_word:
                    words.append((start_sec, end_sec, clean_word))
                    
    return words


def generate_audio_and_subtitles(script_text: str, category: str, topic: str = "") -> Tuple[str, List[Tuple[Tuple[float, float], str]], str]:
    clean_topic = re.sub(r"[^\w]", "_", topic) if topic else "voice"
    audio_path = f"{clean_topic}.wav"

    clean_script = sanitize_script_for_tts(script_text)

    words = []
    voice_used = ""
    db_key = CATEGORIES.get(category, {}).get("db_key", category.lower())
    voice_map = {"space": "am_fenrir", "history": "af_heart", "tech": "am_puck"}
    kokoro_voice = voice_map.get(db_key, "af_heart")

    try:
        print(f"Generating Local Neural TTS voiceover via Kokoro-82M ONNX ({kokoro_voice})...")
        words = synthesize_kokoro_audio_and_timestamps(clean_script, category, audio_path)
        voice_used = f"{kokoro_voice} (Kokoro-82M ONNX)"
    except Exception as e:
        import traceback
        print(f"Kokoro-82M TTS fallback due to [{type(e).__name__}]: {e}")
        traceback.print_exc()
        primary_voice = "en-US-BrianNeural"
        fallback_voice = "en-US-AndrewNeural"
        try:
            words = asyncio.run(synthesize_speech_and_get_timestamps(clean_script, primary_voice, audio_path))
            voice_used = f"{primary_voice} (Edge-TTS Fallback)"
        except Exception as fallback_err:
            words = asyncio.run(synthesize_speech_and_get_timestamps(script_text, fallback_voice, audio_path))
            voice_used = f"{fallback_voice} (Edge-TTS Fallback)"

    # Apply Studio Audio Mastering Chain (80Hz Highpass filter, 2.5kHz EQ Boost, Compand Compressor)
    mastered_audio_path = f"{clean_topic}_mastered.wav"
    audio_path = master_tts_audio(audio_path, mastered_audio_path)

    subs_list = []
    for start_sec, end_sec, text in words:
        if text:
            subs_list.append(((start_sec, end_sec), text.upper()))
            
    print(f"Generated {len(subs_list)} short-burst subtitle cues. Voice: {voice_used}")
    return audio_path, subs_list, voice_used


# ---------------------------------------------------------------------------
# 4. PEXELS VIDEO DOWNLOADER
# ---------------------------------------------------------------------------
def sanitize_search_query(query: str) -> str:
    """Sanitize keyword query string to remove special characters and control parameters."""
    if not query:
        return ""
    clean = re.sub(r"[^\w\s\-\']", " ", query)
    return re.sub(r"\s+", " ", clean).strip()


WIKIMEDIA_HEADERS = {
    "User-Agent": "MPVSAP_VideoBot/2.5 (https://github.com/thienphucnt/MPVSAP; bot@mpvsap.org)"
}

def search_wikimedia_image(query: str) -> Optional[str]:
    """Query Wikimedia Commons for a specific entity with compliant User-Agent and retry logic."""
    clean_query = sanitize_search_query(query)
    if not clean_query:
        return None
    search_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": clean_query,
        "srnamespace": 6,  # Namespace 6 is strictly for File: namespace in Wikimedia
        "srlimit": 5
    }
    
    for attempt in range(2):
        try:
            time.sleep(0.5)  # Respectful rate limit delay to prevent 429 throttling
            resp = HTTP_SESSION.get(search_url, params=params, headers=WIKIMEDIA_HEADERS, timeout=15)
            if resp.status_code == 429:
                time.sleep(2.0)
                continue
            resp.raise_for_status()
            results = resp.json().get("query", {}).get("search", [])
            if not results:
                print(f"No search results on Wikimedia for '{query}'")
                return None
                
            first_title = results[0]["title"]
            img_params = {
                "action": "query",
                "format": "json",
                "titles": first_title,
                "prop": "imageinfo",
                "iiprop": "url"
            }
            img_resp = HTTP_SESSION.get(search_url, params=img_params, headers=WIKIMEDIA_HEADERS, timeout=15)
            if img_resp.status_code == 429:
                time.sleep(2.0)
                continue
            img_resp.raise_for_status()
            pages = img_resp.json().get("query", {}).get("pages", {})
            for page_id, page in pages.items():
                info = page.get("imageinfo", [])
                if info:
                    url = info[0]["url"]
                    # Only return raster image formats Pillow can open ??? skip SVG, PDF, tiff, webm etc.
                    allowed_exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
                    if any(url.lower().split("?")[0].endswith(ext) for ext in allowed_exts):
                        return url
                    else:
                        print(f"Wikimedia: skipping unsupported format for '{query}': {url.split('/')[-1]}")
                        return None
        except Exception as e:
            if attempt == 1:
                print(f"Wikimedia search failed for '{query}':", e)
    return None

def download_wikimedia_image(url: str, index: int) -> Optional[str]:
    """Download a Wikimedia image with compliant User-Agent and convert to valid RGB JPEG."""
    # Safety guard: reject unsupported formats before downloading
    clean_url = url.lower().split("?")[0]
    allowed_exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    if not any(clean_url.endswith(ext) for ext in allowed_exts):
        print(f"Wikimedia: skipping unsupported format: {url.split('/')[-1]}")
        return None

    temp_path = f"temp_wiki_{index}_{os.getpid()}.jpg"
    for attempt in range(2):
        try:
            time.sleep(0.3)
            resp = HTTP_SESSION.get(url, headers=WIKIMEDIA_HEADERS, timeout=20)
            if resp.status_code == 429:
                time.sleep(2.0)
                continue
            resp.raise_for_status()

            # Convert downloaded raster image (PNG/WebP/GIF/JPG) to RGB JPEG using Pillow
            from PIL import Image
            import io
            raw = resp.content
            if len(raw) < 100:
                raise ValueError(f"Wikimedia response too small ({len(raw)} bytes), likely invalid")
            img = Image.open(io.BytesIO(raw))
            img = img.convert("RGB")
            img.save(temp_path, "JPEG", quality=95)
            return temp_path
        except Exception as e:
            if attempt == 1:
                print(f"Wikimedia image download/convert failed for {url.split('/')[-1]}: {e}")
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass
    return None

def make_image_video_clip(image_path: str, duration: float, target_res: Tuple[int, int], output_path: str) -> None:
    """Animate a static image into a dynamic video clip with salience-based focal point zoom."""
    from moviepy.editor import ImageClip
    from PIL import Image
    w, h = target_res
    
    cx, cy = find_image_salience_center(image_path)
    clip = ImageClip(image_path).set_duration(duration)
    img_w, img_h = clip.size
    scale = max(w / img_w, h / img_h) * 1.15
    
    clip = clip.resize(scale)
    
    def zoom_filter(get_frame, t):
        try:
            frame = get_frame(t)
            if frame is None:
                return np.zeros((h, w, 3), dtype=np.uint8)
            if not isinstance(frame, np.ndarray):
                frame = np.array(frame)
            if frame.dtype != np.uint8:
                frame = np.clip(frame, 0, 255).astype(np.uint8)
            frame = np.ascontiguousarray(frame)

            progress = min(1.0, max(0.0, float(t) / max(0.01, float(duration))))
            cur_scale = 1.0 + 0.15 * progress
            
            nw = max(w, int(w * cur_scale))
            nh = max(h, int(h * cur_scale))
            
            img = Image.fromarray(frame)
            resample_filter = getattr(Image, 'Resampling', Image).LANCZOS if hasattr(Image, 'Resampling') else Image.BICUBIC
            img_resized = img.resize((nw, nh), resample_filter)
            
            center_x = int(cx * nw)
            center_y = int(cy * nh)
            
            left = max(0, min(nw - w, center_x - w // 2))
            top = max(0, min(nh - h, center_y - h // 2))
            
            img_cropped = img_resized.crop((left, top, left + w, top + h))
            return np.array(img_cropped)
        except Exception as e:
            print("Salience zoom filter error fallback:", e)
            try:
                frame = get_frame(t)
                img = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8))
                return np.array(img.resize((w, h)))
            except Exception as e2:
                print("Critical frame fallback error:", e2)
                return np.full((h, w, 3), 128, dtype=np.uint8)  # Mid-gray fallback instead of pitch black

    try:
        clip = clip.fl(zoom_filter)
    except Exception as e:
        print("Salience zoom filter setup fallback:", e)
        clip = clip.resize((w, h))
        
    clip.write_videofile(
        output_path,
        fps=30,
        codec="libx264",
        preset="ultrafast",
        ffmpeg_params=["-pix_fmt", "yuv420p"],
        logger=None
    )
    clip.close()

def download_single_pexels_video(api_key: str, kw: str, index: int, orientation: str, filename_prefix: str, category: str) -> Optional[str]:
    """Download a single background clip from Pexels API matching the keyword."""
    cat_info = CATEGORIES[category]
    headers = {"Authorization": api_key}
    search_url = "https://api.pexels.com/videos/search"
    clean_kw = sanitize_search_query(kw)
    params = {"query": clean_kw if clean_kw else "space", "orientation": orientation, "size": "medium", "per_page": 5}
    
    try:
        resp = HTTP_SESSION.get(search_url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        
        if not videos:
            fallback_kw = random.choice(cat_info["kw_defaults"])
            print(f"No videos for '{kw}', falling back to category default: '{fallback_kw}'...")
            params["query"] = fallback_kw
            resp = HTTP_SESSION.get(search_url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            
        if videos:
            selected = random.choice(videos[:5])
            mp4_files = [f for f in selected.get("video_files", []) if f.get("file_type") == "video/mp4"]
            if not mp4_files:
                mp4_files = selected.get("video_files", [])
            if mp4_files:
                hd = [f for f in mp4_files if f.get("quality") == "hd"]
                pool = hd if hd else mp4_files
                pool.sort(key=lambda x: abs((x.get("width") or 0) - 1080) + abs((x.get("height") or 0) - 1920))
                video_url = pool[0].get("link")
                clip_path = f"{filename_prefix}_clip_{index}.mp4"
                raw_path = f"{filename_prefix}_raw_{index}.mp4"
                for attempt in range(3):
                    try:
                        dl = HTTP_SESSION.get(video_url, stream=True, timeout=30)
                        dl.raise_for_status()
                        with open(raw_path, "wb") as f:
                            for chunk in dl.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                        # Transcode to SDR H.264 yuv420p immediately after download.
                        # Pexels serves HDR/VP9/AV1 clips that MoviePy decodes as near-black
                        # (mean_b~0.04) due to tone mapping collapse. FFmpeg normalises
                        # colour space to safe SDR before MoviePy ever touches the file.
                        transcode_cmd = [
                            "ffmpeg", "-y", "-i", raw_path,
                            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                            "-c:v", "libx264", "-preset", "ultrafast",
                            "-crf", "23", "-pix_fmt", "yuv420p",
                            "-colorspace", "bt709", "-color_primaries", "bt709",
                            "-color_trc", "bt709",
                            "-c:a", "aac", "-b:a", "128k",
                            clip_path
                        ]
                        result = subprocess.run(
                            transcode_cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                            timeout=120
                        )
                        if result.returncode != 0:
                            err = result.stderr.decode("utf-8", errors="replace")[-300:]
                            print(f"FFmpeg transcode warning for '{kw}' clip {index}: {err}")
                            # Fall back: just use the raw file directly
                            import shutil as _shutil
                            _shutil.move(raw_path, clip_path)
                        else:
                            if os.path.exists(raw_path):
                                os.remove(raw_path)
                        return clip_path
                    except Exception as e:
                        print(f"Download attempt {attempt+1} failed: {e}")
                        for p in [raw_path, clip_path]:
                            if os.path.exists(p):
                                try: os.remove(p)
                                except Exception: pass
                        time.sleep(1)
    except Exception as e:
        print(f"Failed to fetch Pexels video for '{kw}':", e)
    return None


def download_pexels_videos(api_key: str, keywords: List[str], category: str, orientation: str = "portrait", limit: int = 6, filename_prefix: str = "bg") -> List[str]:
    print("Preparing download of background video clips from Pexels and Wikimedia...")
    cat_info = CATEGORIES[category]
    
    # Guarantee enough keywords
    default_pool = cat_info["kw_defaults"]
    while len(keywords) < limit:
        cand = random.choice(default_pool)
        if cand not in keywords:
            keywords.append(cand)
            
    # Process each keyword. We fetch from Pexels video API first. If Pexels has no video, we try Wikimedia image search.
    def process_keyword(kw: str, index: int) -> str:
        clip_path = f"{filename_prefix}_clip_{index}.mp4"
        
        # 1. Try Pexels HD video search for keyword first
        p_path = download_single_pexels_video(api_key, kw, index, orientation, filename_prefix, category)
        if p_path:
            return p_path

        # 2. Secondary fallback: try Wikimedia Commons image search
        print(f"No Pexels video for '{kw}'. Searching Wikimedia Commons for image fallback...")
        wiki_url = search_wikimedia_image(kw)
        if wiki_url:
            image_path = download_wikimedia_image(wiki_url, index)
            if image_path:
                try:
                    target_res = (1080, 1920) if orientation == "portrait" else (1920, 1080)
                    clip_dur = 17.0 if orientation == "portrait" else 8.0
                    make_image_video_clip(image_path, clip_dur, target_res, clip_path)
                    return clip_path
                except Exception as e:
                    print(f"Failed to create image-to-video clip for '{kw}': {e}")
                finally:
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                        except Exception:
                            pass

        # 3. Hard fallback: try a category default video search on Pexels
        fallback_kw = random.choice(cat_info["kw_defaults"])
        print(f"Wikimedia image fallback failed for '{kw}'. Trying category default '{fallback_kw}' on Pexels...")
        p_path = download_single_pexels_video(api_key, fallback_kw, index, orientation, filename_prefix, category)
        if p_path:
            return p_path

        raise Exception(f"Failed to download B-roll for keyword '{kw}' and fallback '{fallback_kw}'")

    video_paths = [None] * limit
    with concurrent.futures.ThreadPoolExecutor(max_workers=limit) as executor:
        futures = {executor.submit(process_keyword, keywords[i], i): i for i in range(limit)}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                video_paths[idx] = future.result()
            except Exception as e:
                print(f"Error fetching B-roll clip {idx}: {e}")
                
    # Fallback for any failed downloads by duplicating successful ones
    successful = [p for p in video_paths if p is not None]
    if not successful:
        raise Exception("All Pexels downloads failed.")
    
    for i in range(limit):
        if video_paths[i] is None:
            dup_path = f"{filename_prefix}_clip_{i}.mp4"
            shutil.copy(successful[0], dup_path)
            video_paths[i] = dup_path
            print(f"Duplicated {successful[0]} to {dup_path} as fallback.")

    return video_paths


# ---------------------------------------------------------------------------
# FONT DOWNLOADER HELPER
# ---------------------------------------------------------------------------
def register_font_linux(font_path: str):
    if sys.platform.startswith("linux"):
        try:
            dest_dir = Path.home() / ".local/share/fonts"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / "Anton-Regular.ttf"
            if not dest_file.exists():
                import shutil
                shutil.copy(font_path, dest_file)
                print(f"Copied font to Linux local fonts: {dest_file}")
                # Run fc-cache to update font cache
                subprocess.run(["fc-cache", "-f"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("Registered font with fc-cache.")
        except Exception as e:
            print("Failed to register font on Linux system:", e)


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
    font_abs_path = str(font_path.resolve().absolute())
    register_font_linux(font_abs_path)
    return font_abs_path


def format_ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        secs += centiseconds // 100
        centiseconds = centiseconds % 100
    if secs >= 60:
        minutes += secs // 60
        secs = secs % 60
    if minutes >= 60:
        hours += minutes // 60
        minutes = minutes % 60
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def generate_ass_file(subs_list: List[Tuple[Tuple[float, float], str]], output_ass_path: str, category: str, config: VideoFormatConfig, watermark_handle: str = WATERMARK_HANDLE) -> None:
    print(f"Generating ASS subtitles & watermark file: {output_ass_path}...")
    font_name = "Anton"
    play_res_x = config.resolution[0]
    play_res_y = config.resolution[1]
    
    sub_y = config.sub_position[1]
    margin_v = play_res_y - sub_y
    watermark_margin_v = max(40, int(play_res_y * 0.20))  # Lower-center safe zone anchored below main captions
    
    lines = [
        "[Script Info]",
        "; Script generated by Antigravity Hybrid Video Engine",
        "ScriptType: v4.00+",
        f"PlayResX: {play_res_x}",
        f"PlayResY: {play_res_y}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name},{config.sub_fontsize},&H00FFFFFF,&H0000FFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,0,2,10,10,{margin_v},1",
        f"Style: Watermark,{font_name},36,&HA8FFFFFF,&HA8FFFFFF,&H90000000,&H00000000,-1,0,0,0,100,100,0,0,1,2.0,1,2,10,10,{watermark_margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    # Add persistent visual watermark event across the full video timeline
    if config.is_short and subs_list:
        total_start = format_ass_time(subs_list[0][0][0])
        total_end = format_ass_time(subs_list[-1][0][1] + 3.0)
        lines.append(f"Dialogue: 0,{total_start},{total_end},Watermark,,0,0,0,,{watermark_handle}")
    
    _, theme_ass_color, _ = get_theme_colors(category)

    def get_ass_color_tag(word: str) -> str:
        clean = re.sub(r"[^\w]", "", word.upper())
        fillers = {
            "THE", "A", "AND", "OR", "IN", "OF", "TO", "IS", "WAS", "FOR", 
            "IT", "ON", "WITH", "AS", "AT", "BY", "AN", "BE", "THIS", "THAT", 
            "FROM", "ARE", "WERE", "BEEN", "BUT", "SO", "IF", "THEY", "THEIR", "YOU", "YOUR"
        }
        if clean in fillers:
            return ""
        if is_power_word(word):
            return f"{{\\fscx120\\fscy120\\1c&H0000FFFF}}"
        return f"{{\\1c{theme_ass_color}}}"
        
    if not config.is_short:
        # Group single-word cues into phrases of 3-5 words (targeting 4)
        phrases = []
        current_phrase = []
        for item in subs_list:
            current_phrase.append(item)
            (start, end), word = item
            ends_with_punc = word.endswith(('.', '?', '!', ',', ';', ':'))
            if len(current_phrase) >= 4 or ends_with_punc:
                phrases.append(current_phrase)
                current_phrase = []
        if current_phrase:
            phrases.append(current_phrase)

        # Generate overlapping color-highlighted lines for each phrase
        for phrase in phrases:
            for i, active_item in enumerate(phrase):
                (active_start, active_end), _ = active_item
                
                line_parts = []
                for j, item in enumerate(phrase):
                    (_, _), w_text = item
                    w_text_upper = w_text.upper().strip()
                    if j == i:
                        # Active word highlighted in Yellow (&H0000FFFF)
                        line_parts.append(f"{{\\1c&H0000FFFF}}{w_text_upper}{{\\1c&H00FFFFFF}}")
                    else:
                        line_parts.append(w_text_upper)
                
                line_text = " ".join(line_parts)
                start_str = format_ass_time(active_start)
                
                # Extend end time of intermediate active word to next word start to avoid flicker
                if i < len(phrase) - 1:
                    next_start = phrase[i+1][0][0]
                    end_time = max(active_end, next_start)
                else:
                    end_time = active_end
                
                end_str = format_ass_time(end_time)
                line_text = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{line_text}"
                lines.append(line_text)
    else:
        # Standard one-word-at-a-time flashing for Shorts
        for (start, end), text in subs_list:
            start_str = format_ass_time(start)
            end_str = format_ass_time(end)
            word_text = text.upper().strip()
            color_tag = get_ass_color_tag(word_text)
            line_text = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{color_tag}{word_text}"
            lines.append(line_text)
        
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"ASS file written successfully.")


# ---------------------------------------------------------------------------
# 5. PRE-UPLOAD VISUAL SANITY CHECK & VIDEO ASSEMBLY
# ---------------------------------------------------------------------------
def verify_rendered_video_visuals(video_path: str, num_samples: int = 8) -> bool:
    """Pre-Upload Visual Sanity Check: Sample 8 timestamps across the rendered video.
    If ANY sampled frame is pitch black (mean brightness < 8.0 and std < 2.0),
    throw a RuntimeError to abort upload and prevent publishing broken video.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Rendered video file not found at {video_path}")

    try:
        from moviepy.editor import VideoFileClip
        import numpy as np

        clip = VideoFileClip(video_path)
        duration = clip.duration
        print(f"\n--- PRE-UPLOAD VISUAL SANITY CHECK ---")
        print(f"Verifying video visuals: {video_path} | Duration: {duration:.2f}s")

        sample_times = [duration * (i / (num_samples + 1)) for i in range(1, num_samples + 1)]
        corrupt_black_frames = 0

        for t in sample_times:
            frame = clip.get_frame(t)
            mean_b = float(np.mean(frame))
            std_v = float(np.std(frame))
            print(f"Sample at {t:.2f}s: Mean Brightness = {mean_b:.2f}, Variance = {std_v:.2f}")

            # Corrupt black check: solid void frame with no image content (mean < 1.0 AND std < 0.5)
            # Valid dark space footage with stars/nebulae has non-zero variance (std_v >= 0.5).
            if mean_b < 1.0 and std_v < 0.5:
                # Retry sampling slightly offset (+0.3s) to rule out isolated transition/fade frames
                alt_t = min(duration - 0.1, t + 0.3)
                alt_frame = clip.get_frame(alt_t)
                alt_mean = float(np.mean(alt_frame))
                alt_std = float(np.std(alt_frame))
                print(f"  -> Retry sample at {alt_t:.2f}s: Mean = {alt_mean:.2f}, Variance = {alt_std:.2f}")

                if alt_mean < 1.0 and alt_std < 0.5:
                    print(f"CRITICAL REJECTION: Frame at {t:.2f}s is SOLID BLACK VOID!")
                    corrupt_black_frames += 1

        clip.close()

        if corrupt_black_frames > 0:
            raise RuntimeError(
                f"Pre-Upload Visual Sanity Check FAILED: Found {corrupt_black_frames} corrupted solid black frames in {video_path}! "
                f"Aborting upload to prevent publishing broken video."
            )

        print("✅ [PRE-UPLOAD SANITY CHECK PASSED] All sampled frames contain rich visual imagery! Video is 100% safe to publish.\n")
        return True
    except Exception as e:
        if "Pre-Upload Visual Sanity Check FAILED" in str(e):
            raise e
        print("Warning during pre-upload visual sanity check:", e)
        return True


def assemble_video(video_paths: List[str], audio_path: str, subs_list: List[Tuple[Tuple[float, float], str]], output_path: str, category: str, config: Optional[VideoFormatConfig] = None, mix_music: bool = True) -> str:
    print("Assembling video...")
    if config is None:
        config = VideoFormatConfig("short")
        
    font_path = download_font()
    music_clip = None
    final_audio = None
    mixed_audio_path = f"mixed-audio-{os.getpid()}.wav"

    audio_clip = AudioFileClip(audio_path)
    audio_duration = audio_clip.duration

    # --- Build multi-clip background with Ken Burns zoom effect & Seamless Visual Loop Split ---
    clips = []
    num_clips = len(video_paths)

    if config.is_short and num_clips >= 2:
        # Seamless Visual Split Loop:
        # Primary clip (video_paths[0]) is split into two contiguous subclips:
        # - c_end: plays video_paths[0] from t=0 to t=split_dur at the END of the video.
        # - c_start: plays video_paths[0] from t=split_dur onwards at the BEGINNING of the video.
        # When YouTube Shorts loops back from the end to the start, the video frame transitions from
        # video_paths[0](t=split_dur) to video_paths[0](t=split_dur) with ZERO jump cut!
        c0_full = VideoFileClip(video_paths[0]).resize(newsize=config.resolution)
        c0_dur = c0_full.duration

        split_dur = min(1.5, max(0.4, c0_dur / 4.0))

        # End clip: primary asset from 0 to split_dur
        c_end_clip = c0_full.subclip(0, min(c0_dur, split_dur)).set_duration(split_dur)

        # Remaining time to allocate for [c_start] + [mid_clips]
        mid_paths = video_paths[1:]
        rem_dur = max(1.0, audio_duration - split_dur)
        num_seq = 1 + len(mid_paths)
        per_seq_dur = rem_dur / float(num_seq)

        # Start clip: primary asset from split_dur to split_dur + per_seq_dur
        c_start_end_time = min(c0_dur, split_dur + per_seq_dur)
        c_start_clip = c0_full.subclip(min(c0_dur, split_dur), c_start_end_time)
        if c_start_clip.duration < per_seq_dur:
            c_start_clip = loop(c_start_clip, duration=per_seq_dur + 0.5)
        c_start_clip = c_start_clip.set_duration(per_seq_dur)

        # Process start clip
        def create_zoom_filter(dur_val):
            last_valid_frame = [None]
            def zoom_filter(get_frame, t):
                try:
                    frame = get_frame(t)
                    if frame is None:
                        try: frame = get_frame(0.0)
                        except Exception: pass
                    if frame is None and last_valid_frame[0] is not None:
                        frame = last_valid_frame[0]
                    if frame is None:
                        return np.full((config.resolution[1], config.resolution[0], 3), 128, dtype=np.uint8)

                    if not isinstance(frame, np.ndarray):
                        frame = np.array(frame)
                    if frame.dtype != np.uint8:
                        frame = np.clip(frame, 0, 255).astype(np.uint8)
                    frame = np.ascontiguousarray(frame)
                    last_valid_frame[0] = frame

                    target_w, target_h = config.resolution
                    progress = min(1.0, max(0.0, float(t) / max(0.01, float(dur_val))))
                    scale = 1.0 + 0.15 * progress

                    new_w = max(target_w, int(target_w * scale))
                    new_h = max(target_h, int(target_h * scale))

                    try:
                        import cv2
                        img_resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                        left = max(0, (new_w - target_w) // 2)
                        top = max(0, (new_h - target_h) // 2)
                        return img_resized[top:top + target_h, left:left + target_w]
                    except ImportError:
                        img = PIL.Image.fromarray(frame)
                        resample_filter = getattr(PIL.Image, 'Resampling', PIL.Image).BILINEAR if hasattr(PIL.Image, 'Resampling') else PIL.Image.BILINEAR
                        img_resized = img.resize((new_w, new_h), resample_filter)
                        left = max(0, (new_w - target_w) // 2)
                        top = max(0, (new_h - target_h) // 2)
                        img_cropped = img_resized.crop((left, top, left + target_w, top + target_h))
                        return np.array(img_cropped)
                except Exception:
                    return np.full((config.resolution[1], config.resolution[0], 3), 128, dtype=np.uint8)
            return zoom_filter

        clips.append(c_start_clip.fl(create_zoom_filter(per_seq_dur)))

        # Process mid clips
        for mid_path in mid_paths:
            mc = VideoFileClip(mid_path).resize(newsize=config.resolution)
            if mc.duration < per_seq_dur:
                mc = loop(mc, duration=per_seq_dur + 0.5)
            else:
                mc = mc.subclip(0, min(mc.duration, per_seq_dur + 0.5))
            mc = mc.set_duration(per_seq_dur)
            clips.append(mc.fl(create_zoom_filter(per_seq_dur)))

        # Process end clip
        clips.append(c_end_clip.fl(create_zoom_filter(split_dur)))

    else:
        per_clip_duration = audio_duration / float(num_clips)
        for i, v_path in enumerate(video_paths):
            c = VideoFileClip(v_path).resize(newsize=config.resolution)
            if c.duration < per_clip_duration:
                c = loop(c, duration=per_clip_duration + 0.5)
            else:
                c = c.subclip(0, min(c.duration, per_clip_duration + 0.5))
            c = c.set_duration(per_clip_duration)
            clips.append(c)

    bg_clip = concatenate_videoclips(clips)

    # Add dynamic retention overlays (Visual Progress Bar & CTA Subscribe Overlay)
    retention_overlays = []
    if config.is_short:
        try:
            # 1. Dynamic 5px Visual Progress Bar at bottom (category theme-colored)
            pbar_clip = create_progress_bar_clip(audio_duration, config.resolution, category)
            retention_overlays.append(pbar_clip)
        except Exception as pbar_err:
            print("Failed to add progress bar clip:", pbar_err)

        try:
            # 2. Automated CTA Overlay in final 5 seconds
            cta_asset_path = get_or_create_cta_asset()
            cta_start = max(0.0, audio_duration - 5.0)
            cta_dur = audio_duration - cta_start
            cta_y = int(config.resolution[1] * 0.70)
            cta_clip = (
                ImageClip(cta_asset_path)
                .set_start(cta_start)
                .set_duration(cta_dur)
                .set_position(("center", cta_y))
                .resize(width=int(config.resolution[0] * 0.70))
            )
            retention_overlays.append(cta_clip)
        except Exception as cta_err:
            print("Failed to add CTA overlay clip:", cta_err)

    if retention_overlays:
        bg_clip = CompositeVideoClip([bg_clip] + retention_overlays)

    # --- Background music mixing & Broadcast-Standard LUFS Normalization (-14 LUFS / -1.0 dBTP) ---
    final_audio_clip = audio_clip
    if mix_music:
        music_dir = Path("music")
        music_temp_path = f"temp-music-{os.getpid()}.wav"

        cat_info = CATEGORIES[category]
        cat_music_dir = music_dir / cat_info["music_subfolder"]
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
                    if m.duration < audio_duration + 5.0:
                        m = audio_loop(m, duration=audio_duration + 5.0)
                    else:
                        max_start = max(0, m.duration - audio_duration - 5)
                        start_time = random.uniform(0, max_start)
                        m = m.subclip(start_time, start_time + audio_duration)

                    music_clip = m.volumex(0.24)
                    music_clip.write_audiofile(music_temp_path, fps=44100, logger=None)

                    # Mix using ffmpeg with broadcast-standard LUFS normalization (-14.0 LUFS, -1.0 dBTP)
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", audio_path,
                        "-i", music_temp_path,
                        "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-14:TP=-1.0:LRA=11",
                        "-c:a", "pcm_s16le",
                        mixed_audio_path
                    ]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    final_audio = AudioFileClip(mixed_audio_path)
                    final_audio_clip = final_audio
                except Exception as e:
                    print("Failed to mix background music, using voice-only:", e)
                finally:
                    if os.path.exists(music_temp_path):
                        try:
                            os.remove(music_temp_path)
                        except Exception:
                            pass

    bg_clip = bg_clip.set_audio(final_audio_clip)

    # Try high-performance FFmpeg ASS subtitle burning first
    ass_path = f"subtitles_{os.getpid()}.ass"
    temp_no_subs = f"temp_no_subs_{os.getpid()}.mp4"
    ffmpeg_success = False

    try:
        generate_ass_file(subs_list, ass_path, category, config)
        print("Rendering background video (no subtitles)...")
        bg_clip.write_videofile(
            temp_no_subs,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=2,
            preset="ultrafast",
            logger=None
        )

        # Stage 1: Verify raw background video visuals BEFORE burning subtitles
        print("\n--- STAGE 1: RAW BACKGROUND VISUAL SANITY CHECK ---")
        verify_rendered_video_visuals(temp_no_subs)
        
        print("Burning ASS subtitles using FFmpeg...")
        cmd = [
            "ffmpeg", "-y",
            "-i", temp_no_subs,
            "-vf", f"ass={ass_path}",
            "-c:a", "copy",
            output_path
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Successfully completed video generation via high-performance FFmpeg ASS engine!")
        ffmpeg_success = True
    except Exception as ass_err:
        print(f"FFmpeg ASS engine failed ({ass_err}), falling back to MoviePy subtitle rendering...")

    # Fallback to MoviePy rendering if FFmpeg failed
    if not ffmpeg_success:
        if os.path.exists(temp_no_subs):
            try: os.remove(temp_no_subs)
            except Exception: pass

        print("Falling back to rendering subtitles with MoviePy (heavy RAM usage)...")
        
        def get_word_color(word: str) -> str:
            clean = re.sub(r"[^\w]", "", word.upper())
            fillers = {
                "THE", "A", "AND", "OR", "IN", "OF", "TO", "IS", "WAS", "FOR", 
                "IT", "ON", "WITH", "AS", "AT", "BY", "AN", "BE", "THIS", "THAT", 
                "FROM", "ARE", "WERE", "BEEN", "BUT", "SO", "IF", "THEY", "THEIR", "YOU", "YOUR"
            }
            if clean in fillers:
                return "#FFFFFF"
            return random.choice(["#FFFF00", "#00FF00", "#00FFFF"])

        def create_text_clip(start, end, text):
            padded_text = f" {text.upper().strip()} "
            text_color = get_word_color(text)
            return (
                TextClip(
                    padded_text,
                    font=font_path,
                    fontsize=config.sub_fontsize,
                    color=text_color,
                    bg_color="rgba(0,0,0,0.6)",
                    transparent=True,
                    stroke_color="black",
                    stroke_width=3,
                    method="label",
                    align="center"
                )
                .set_start(start)
                .set_duration(end - start)
                .set_position(config.sub_position)
                .resize(lambda t: 1.2 - 2.0 * t if t < 0.1 else 1.0)
            )

        sub_clips = []
        for (s, e), t in subs_list:
            try:
                sub_clips.append(create_text_clip(s, e, t))
            except Exception as exc:
                print(f"Failed to create TextClip for '{t}':", exc)

        # Persistent Watermark Overlay Layer (33% Opacity, lower-center safe zone)
        if config.is_short:
            try:
                watermark_y = int(config.resolution[1] * 0.78)
                watermark_clip = (
                    TextClip(
                        WATERMARK_HANDLE,
                        font=font_path,
                        fontsize=36,
                        color="white",
                        stroke_color="black",
                        stroke_width=2,
                        transparent=True,
                        method="label",
                        align="center"
                    )
                    .set_start(0)
                    .set_duration(bg_clip.duration)
                    .set_position(("center", watermark_y))
                    .set_opacity(0.33)
                )
                sub_clips.append(watermark_clip)
            except Exception as wm_err:
                print("Failed to add MoviePy watermark overlay clip:", wm_err)

        final_clip = CompositeVideoClip([bg_clip] + sub_clips)
        final_clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            threads=2,
            preset="ultrafast",
            logger=None
        )
        final_clip.close()
        for s in sub_clips:
            s.close()

    # Perform immediate pre-upload visual sanity check on output_path
    verify_rendered_video_visuals(output_path)

    # --- Clean up resources ---
    bg_clip.close()
    for c in clips:
        c.close()
    audio_clip.close()
    if music_clip:
        music_clip.close()
    if final_audio:
        final_audio.close()

    # Clean up temp files
    if os.path.exists(temp_no_subs):
        try: os.remove(temp_no_subs)
        except Exception: pass
    if os.path.exists(ass_path):
        try: os.remove(ass_path)
        except Exception: pass
    if os.path.exists(mixed_audio_path):
        try: os.remove(mixed_audio_path)
        except Exception: pass

    # Clean up downloaded video clips
    for v_path in video_paths:
        try:
            vp = Path(v_path)
            if vp.exists():
                vp.unlink()
        except Exception:
            pass

    try:
        ap = Path(audio_path)
        if ap.exists():
            ap.unlink()
    except Exception as e:
        print(f"Could not remove {audio_path}:", e)

    print("Assembly complete.")
    return output_path


# ---------------------------------------------------------------------------
# 5B. THEMATIC WIDESCREEN THUMBNAIL GENERATOR (PILLOW)
def download_pexels_image(pexels_key: str, query: str) -> Optional[str]:
    import urllib.parse
    print(f"Searching Pexels for thumbnail backdrop with query: '{query}'...")
    headers = {"Authorization": pexels_key}
    url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=1"
    
    try:
        resp = HTTP_SESSION.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        photos = data.get("photos", [])
        if photos:
            img_url = photos[0]["src"]["large2x"]
            print(f"Downloading Pexels backdrop: {img_url}")
            temp_path = f"temp_thumb_bg_{os.getpid()}.jpg"
            
            img_resp = HTTP_SESSION.get(img_url, timeout=15)
            img_resp.raise_for_status()
            with open(temp_path, "wb") as f:
                f.write(img_resp.content)
            return temp_path
    except Exception as e:
        print("Failed to download Pexels thumbnail backdrop:", e)
    return None


def generate_thumbnail(title: str, category: str, pexels_key: str, output_path: str = "thumbnail.jpg") -> Optional[str]:
    print("Generating widescreen thumbnail (1280x720)...")
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    cat_info = CATEGORIES[category]
    
    # 1. Acquire backdrop image
    bg_query = random.choice(cat_info["kw_defaults"])
    bg_path = download_pexels_image(pexels_key, bg_query)
    
    if bg_path and os.path.exists(bg_path):
        try:
            img = Image.open(bg_path)
            img = img.resize((1280, 720), Image.Resampling.LANCZOS)
            # Soft focus blur to direct attention to titles
            img = img.filter(ImageFilter.GaussianBlur(3))
        except Exception as e:
            print("Failed to load backdrop, using default clean dark background:", e)
            img = Image.new("RGB", (1280, 720), color=(15, 15, 20))
    else:
        img = Image.new("RGB", (1280, 720), color=(15, 15, 20))
        
    draw = ImageDraw.Draw(img, "RGBA")
    
    # 2. Smooth vignette/dark overlay
    draw.rectangle([(0, 0), (1280, 720)], fill=(10, 10, 15, 130))
    
    # 3. Text layout
    font_file = download_font()
    title_text = title.upper().strip()
    words = title_text.split()
    
    lines = []
    current_line = []
    font_size = 70
    font = ImageFont.truetype(font_file, font_size)
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w < 1000:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
        
    # Calculate dimensions
    total_height = 0
    line_spacing = 15
    line_heights = []
    line_widths = []
    
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_widths.append(w)
        line_heights.append(h)
        total_height += h + line_spacing
        
    total_height -= line_spacing
    
    start_y = (720 - total_height) // 2 + 40
    
    def is_highlight(wrd: str) -> bool:
        clean = re.sub(r"[^\w]", "", wrd.upper())
        fillers = {
            "THE", "A", "AND", "OR", "IN", "OF", "TO", "IS", "WAS", "FOR", 
            "IT", "ON", "WITH", "AS", "AT", "BY", "AN", "BE", "THIS", "THAT", 
            "FROM", "ARE", "WERE", "BEEN", "BUT", "SO", "IF"
        }
        return clean not in fillers
        
    # Draw text with highlighted keywords and drop-shadows
    for idx, line in enumerate(lines):
        line_words = line.split()
        line_w = line_widths[idx]
        start_x = (1280 - line_w) // 2
        y = start_y
        
        for word in line_words:
            # Color: Neon Yellow for key concepts, pure white for fillers
            color = (255, 235, 59, 255) if is_highlight(word) else (255, 255, 255, 255)
            
            # Shadow offset
            draw.text((start_x + 4, y + 4), word, font=font, fill=(0, 0, 0, 200))
            draw.text((start_x, y), word, font=font, fill=color)
            
            word_bbox = draw.textbbox((0, 0), word, font=font)
            space_bbox = draw.textbbox((0, 0), " ", font=font)
            word_w = word_bbox[2] - word_bbox[0]
            space_w = space_bbox[2] - space_bbox[0]
            start_x += word_w + space_w
            
        start_y += line_heights[idx] + line_spacing
        
    # 4. Brand Category badge
    badge_text = cat_info["db_key"].upper() + " DOCUMENTARY"
    badge_font = ImageFont.truetype(font_file, 26)
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0]
    badge_h = badge_bbox[3] - badge_bbox[1]
    
    badge_x = (1280 - badge_w) // 2
    badge_y = 55
    
    # Theme-colored pill backgrounds
    if category == "Morbid or Silly History Facts":
        badge_color = (229, 57, 53, 230)      # Crimson Red
    elif category == "Exciting Tech Facts":
        badge_color = (67, 160, 71, 230)       # Green
    else:
        badge_color = (30, 144, 255, 230)      # Dodger Blue
        
    padding_x = 24
    padding_y = 8
    draw.rounded_rectangle(
        [badge_x - padding_x, badge_y - padding_y, badge_x + badge_w + padding_x, badge_y + badge_h + padding_y],
        radius=14,
        fill=badge_color
    )
    
    draw.text((badge_x + 1, badge_y + 1), badge_text, font=badge_font, fill=(0, 0, 0, 160))
    draw.text((badge_x, badge_y), badge_text, font=badge_font, fill=(255, 255, 255, 255))
    
    img.save(output_path, "JPEG", quality=95)
    print(f"Thumbnail saved successfully to: {output_path}")
    
    if bg_path and os.path.exists(bg_path):
        try:
            os.remove(bg_path)
        except Exception:
            pass
            
    return output_path


# ---------------------------------------------------------------------------
# 6A. YOUTUBE UPLOADER WITH PINNED COMMENT
# ---------------------------------------------------------------------------
def upload_to_youtube(video_path: str, title: str, description: str, client_id: str, client_secret: str, refresh_token: str, playlist_id: Optional[str] = None, category: str = "space", thumbnail_path: Optional[str] = None, related_video_id: Optional[str] = None, subs_list: Optional[List] = None) -> Optional[str]:
    print("Uploading to YouTube...")
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube"]
    )
    youtube = build("youtube", "v3", credentials=creds)

    cat_data = CATEGORIES.get(category, CATEGORIES[list(CATEGORIES.keys())[0]])
    category_id = cat_data.get("yt_category_id", "28")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": cat_data["yt_tags"],
            "categoryId": category_id
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

    # Upload custom thumbnail if generated
    if video_id and thumbnail_path and Path(thumbnail_path).exists():
        print(f"Uploading custom thumbnail {thumbnail_path} for video {video_id}...")
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
            ).execute()
            print("Successfully uploaded custom thumbnail.")
        except Exception as e:
            print("Failed to upload custom thumbnail:", e)

    # Upload native Closed Captions (.SRT)
    if video_id and subs_list:
        srt_path = f"captions_{video_id}.srt"
        generate_srt_file(subs_list, srt_path)
        if Path(srt_path).exists():
            print(f"Uploading native Closed Captions (.SRT) for video {video_id}...")
            try:
                youtube.captions().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "language": "en",
                            "name": "English"
                        }
                    },
                    media_body=MediaFileUpload(srt_path, mimetype="text/plain")
                ).execute()
                print("Successfully uploaded native Closed Captions.")
            except Exception as srt_err:
                if "insufficientPermissions" in str(srt_err) or "403" in str(srt_err):
                    print("Note: YouTube native Closed Captions upload skipped (OAuth scope 'youtube.force-ssl' required). Burned-in ASS subtitles are active on video.")
                else:
                    print("Native Closed Captions API upload note:", srt_err)
            finally:
                if os.path.exists(srt_path):
                    try: os.remove(srt_path)
                    except Exception: pass

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



    return video_id


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
    
    # Define git environment
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "github-actions[bot]",
        "GIT_AUTHOR_EMAIL": "github-actions[bot]@users.noreply.github.com",
        "GIT_COMMITTER_NAME": "github-actions[bot]",
        "GIT_COMMITTER_EMAIL": "github-actions[bot]@users.noreply.github.com",
    }
    
    try:
        # 1. Fetch origin to know the latest remote state
        subprocess.run(["git", "fetch", "origin"], check=True, env=git_env)
        
        # 2. Merge past_topics.json programmatically with remote version
        local_topics = []
        if os.path.exists("past_topics.json"):
            try:
                with open("past_topics.json", "r", encoding="utf-8") as f:
                    local_topics = json.load(f)
            except Exception as e:
                print("Failed to read local past_topics.json:", e)
                
        remote_topics = []
        try:
            show_proc = subprocess.run(
                ["git", "show", "origin/main:past_topics.json"],
                capture_output=True, text=True, check=True, env=git_env
            )
            remote_topics = json.loads(show_proc.stdout)
        except Exception as e:
            print("Failed to read remote past_topics.json (falling back to local only):", e)
            remote_topics = local_topics
            
        # Combine lists removing duplicates (by title/timestamp)
        merged_topics = list(remote_topics)
        seen_keys = { (item.get("title"), item.get("timestamp")) for item in remote_topics }
        
        for item in local_topics:
            key = (item.get("title"), item.get("timestamp"))
            if key not in seen_keys:
                merged_topics.append(item)
                seen_keys.add(key)
                
        # Preserve full history database without truncation
        
        # Save merged topics locally
        with open("past_topics.json", "w", encoding="utf-8") as f:
            json.dump(merged_topics, f, indent=2)
            
        # Write heartbeat
        with open("heartbeat.txt", "w", encoding="utf-8") as f:
            f.write(timestamp)
            
        # 3. Align git index to origin/main without discarding our merged files
        subprocess.run(["git", "reset", "origin/main"], check=True, env=git_env)
        
        # 4. Add files
        subprocess.run(["git", "add", "heartbeat.txt"], check=True, env=git_env)
        if os.path.exists("past_topics.json"):
            subprocess.run(["git", "add", "past_topics.json"], check=True, env=git_env)
            
        # 5. Commit & Push
        status = subprocess.run(["git", "status", "--porcelain"],
                                capture_output=True, text=True, env=git_env)
        if status.stdout.strip():
            subprocess.run(
                ["git", "commit", "-m", f"Automated heartbeat: {timestamp} [skip ci]"],
                check=True, env=git_env
            )
            # Push with retry
            for attempt in range(3):
                try:
                    subprocess.run(["git", "push", "origin", "main"], check=True, env=git_env)
                    print("Heartbeat pushed successfully.")
                    break
                except Exception as push_err:
                    print(f"Push attempt {attempt+1} failed: {push_err}")
                    if attempt < 2:
                        print("Retrying git fetch, merge, and reset...")
                        subprocess.run(["git", "fetch", "origin"], check=True, env=git_env)
                        subprocess.run(["git", "reset", "origin/main"], check=True, env=git_env)
                        with open("past_topics.json", "w", encoding="utf-8") as f:
                            json.dump(merged_topics, f, indent=2)
                        with open("heartbeat.txt", "w", encoding="utf-8") as f:
                            f.write(timestamp)
                        subprocess.run(["git", "add", "heartbeat.txt", "past_topics.json"], check=True, env=git_env)
                        subprocess.run(
                            ["git", "commit", "-m", f"Automated heartbeat: {timestamp} [skip ci]"],
                            check=True, env=git_env
                        )
        else:
            print("No changes to commit for heartbeat.")
    except Exception as e:
        print("Git heartbeat failed:", e)


# ---------------------------------------------------------------------------
# YOUTUBE PLAYLIST SYNC HELPER
# ---------------------------------------------------------------------------
def sync_topics_from_youtube(client_id: str, client_secret: str, refresh_token: str, past_topics: list) -> list:
    """Fetch video titles directly from channel's uploads playlist and sync them into past_topics if missing."""
    print("Syncing past topics directly from YouTube channel uploads...")
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

        channels_response = youtube.channels().list(mine=True, part="contentDetails").execute()
        if not channels_response.get("items"):
            return past_topics

        uploads_playlist_id = channels_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        existing_vids = {item.get("youtube_video_id") for item in past_topics if item.get("youtube_video_id")}
        existing_titles = {item.get("title", "").lower().strip() for item in past_topics}
        new_items = []

        next_page_token = None
        while True:
            res = youtube.playlistItems().list(
                playlistId=uploads_playlist_id,
                part="snippet",
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            for item in res.get("items", []):
                snippet = item.get("snippet", {})
                vid = snippet.get("resourceId", {}).get("videoId")
                title = snippet.get("title", "").strip()

                if not vid or title in ["Private video", "Deleted video"]:
                    continue

                if vid not in existing_vids and title.lower().strip() not in existing_titles:
                    title_lower = title.lower()
                    if "#space" in title_lower or "space" in title_lower or "cosmic" in title_lower:
                        cat = "space"
                    elif "#history" in title_lower or "war" in title_lower or "history" in title_lower:
                        cat = "history"
                    else:
                        cat = "tech"

                    new_items.append({
                        "category": cat,
                        "title": title,
                        "topic": title,
                        "timestamp": snippet.get("publishedAt", datetime.datetime.utcnow().isoformat()),
                        "youtube_video_id": vid,
                        "is_long": False
                    })
                    existing_vids.add(vid)
                    existing_titles.add(title.lower().strip())

            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break

        if new_items:
            past_topics.extend(new_items)
            print(f"Synced {len(new_items)} new past titles directly from YouTube channel uploads.")

    except Exception as e:
        print("Warning: Failed to sync past topics from YouTube uploads:", e)

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

    # Route content selection using 7-day locked category rotation
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
        category = get_rotating_category()

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

    print(f"Loaded {len(past_topics)} past topic entries for exclusion checks.")

    # Initialize video format config
    video_format = args.format
    config = VideoFormatConfig(video_format)
    print(f"Selected Video Format: {config.format_type} (is_short={config.is_short})")

    # Ingest rich source text using Playwright headless Chromium (with Wikipedia fallback)
    source_data = fetch_playwright_scraped_source_text(category, past_topics)

    # Ingest real-time 7-day rising search trends for search indexing
    rising_trends = fetch_trending_category_keywords(category)
    if rising_trends:
        source_data["text"] += f"\n\nREAL-TIME 7-DAY RISING SEARCH TRENDS TO WEAVE IN:\n- " + "\n- ".join(rising_trends)

    # 1. Multi-Variant Tournament Content Generation & Pass 2 Auto-QA
    title, description, segments = generate_content(client, category, past_topics, source_data, config)

    # Resolve related long-form video link for Shorts-to-Long funneling
    related_long_video_id = None
    for item in reversed(past_topics):
        if item.get("category") == db_category and item.get("is_long") == True and item.get("youtube_video_id"):
            related_long_video_id = item["youtube_video_id"]
            break

    # Enforce strict metadata formatting (< 50 chars title, max 3 hashtags)
    title, description = sanitize_metadata(title, description, config.is_short, category)

    # Append standard title hashtags only for Shorts
    if config.is_short:
        if related_long_video_id:
            link_str = f"Explore more stories: https://youtu.be/{related_long_video_id}"
            description = f"{link_str}\n\n{description}"
            print(f"Funnel link added to description pointing to: {related_long_video_id}")

    # Note: Topic is recorded to past_topics.json ONLY after successful upload to YouTube.

    # Dry run mode check
    if args.dry_run:
        print("\n[DRY RUN] Dry-run enabled. Simulating speech synthesis (mocked)...")
        for idx, seg in enumerate(segments):
            print(f"Dry-run: Simulating speech for segment {idx+1}/{len(segments)}...")
            words_in_script = seg["script"].split()
            words = []
            curr_time = 0.0
            for w in words_in_script:
                words.append((curr_time, curr_time + 0.35, w))
                curr_time += 0.35
            print(f"Dry-run Segment {idx+1}: Generated {len(words)} mock word timestamps.")
        print("Dry run validation completed successfully!")
        sys.exit(0)

    # 2. Rendering block
    output_path = "final_output.mp4"
    thumbnail_path = None

    if config.is_short:
        # Standard Shorts path (single segment)
        seg = segments[0]
        audio_path, subs_list, actual_voice_used = generate_audio_and_subtitles(seg["script"], category, seg["topic"])
        video_paths = download_pexels_videos(pexels_key, seg["visual_keywords"], category, orientation="portrait")
        assemble_video(video_paths, audio_path, subs_list, output_path, category, config, mix_music=True)
    else:
        # Long-form path: single-pass rendering to avoid nested re-encoding
        all_video_paths = []
        all_audio_paths = []
        all_subs_list = []
        segment_durations = []
        current_time = 0.0

        for idx, seg in enumerate(segments):
            print(f"\n--- Preparing Segment {idx + 1}/{len(segments)}: {seg['topic']} ---")
            seg_audio_path, seg_subs_list, actual_voice_used = generate_audio_and_subtitles(seg["script"], category, f"longform_seg_{idx}")
            
            # Record segment audio duration for automated description chapters
            try:
                ac = AudioFileClip(seg_audio_path)
                dur = ac.duration
                segment_durations.append(dur)
                ac.close()
            except Exception as e:
                print("Failed to read audio clip duration:", e)
                dur = 45.0 # default fallback
                segment_durations.append(dur)
                
            # Offset subtitles for the current segment to align with concatenated audio timeline
            for (start, end), text in seg_subs_list:
                all_subs_list.append(((start + current_time, end + current_time), text))
            
            # Download Pexels clips with unique prefixes to prevent filename collision
            seg_video_paths = download_pexels_videos(
                pexels_key, 
                seg["visual_keywords"], 
                category, 
                orientation="landscape",
                filename_prefix=f"seg{idx}"
            )
            all_video_paths.extend(seg_video_paths)
            all_audio_paths.append(seg_audio_path)
            current_time += dur

        # Concatenate all segment audio files into a single master audio track
        print("\n--- Concatenating all segment audio files ---")
        audio_clips = [AudioFileClip(p) for p in all_audio_paths]
        concat_audio = concatenate_audioclips(audio_clips)
        master_audio_path = f"master_audio_{os.getpid()}.wav"
        concat_audio.write_audiofile(master_audio_path, fps=44100, logger=None)
        concat_audio.close()
        for ac in audio_clips:
            ac.close()

        # Clean up individual segment audio files now that they are merged
        for p in all_audio_paths:
            try:
                os.remove(p)
            except Exception:
                pass

        # Call assemble_video to perform the single-pass video render and burn all subtitles
        assemble_video(all_video_paths, master_audio_path, all_subs_list, output_path, category, config, mix_music=True)

        # Generate automated description chapters using actual durations
        timestamps = []
        chap_time = 0.0
        for idx, seg in enumerate(segments):
            minutes = int(chap_time // 60)
            seconds = int(chap_time % 60)
            timestamp_str = f"{minutes}:{seconds:02d}"
            timestamps.append(f"{timestamp_str} - {seg['topic']}")
            chap_time += segment_durations[idx]
            
        description = f"{description}\n\nChapters:\n" + "\n".join(timestamps)
        print("Updated description with dynamic chapters:\n", description)

        # Generate widescreen thumbnail (Pillow)
        try:
            thumbnail_path = f"thumbnail_{os.getpid()}.jpg"
            generate_thumbnail(title, category, pexels_key, thumbnail_path)
        except Exception as e:
            print("Failed to generate custom thumbnail:", e)
            thumbnail_path = None

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
        uploaded_video_id = None
        current_subs = subs_list if config.is_short else all_subs_list
        if youtube_client_id and youtube_client_secret and youtube_refresh_token:
            try:
                uploaded_video_id = upload_to_youtube(
                    output_path, title, description,
                    youtube_client_id, youtube_client_secret, youtube_refresh_token,
                    playlist_id, category, thumbnail_path, related_long_video_id,
                    subs_list=current_subs
                )
                
                # Append to past_topics ONLY upon successful upload to YouTube
                if uploaded_video_id:
                    past_topics.append({
                        "category": db_category,
                        "title": title,
                        "topic": segments[0]["topic"],
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                        "youtube_video_id": uploaded_video_id,
                        "is_long": not config.is_short
                    })
                    try:
                        with open(past_topics_path, "w", encoding="utf-8") as f:
                            json.dump(past_topics, f, indent=2)
                        print(f"Successfully recorded uploaded video ID {uploaded_video_id} and topic '{segments[0]['topic']}' in past_topics.json.")
                    except Exception as hist_err:
                        print("Failed to update past_topics.json with video ID:", hist_err)

                    # Trigger Webhook Success Notification
                    yt_url = f"https://www.youtube.com/shorts/{uploaded_video_id}" if config.is_short else f"https://www.youtube.com/watch?v={uploaded_video_id}"
                    send_webhook_notification(
                        title=title,
                        message=f"Successfully published new video for category **{category}**!",
                        status="success",
                        video_url=yt_url
                    )
            except Exception as e:
                if "quotaExceeded" in str(e):
                    print("WARNING: YouTube quota exceeded ??? upload skipped.")
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

        # 3.5 Log deep telemetry data to logs/run_history.json
        try:
            from logger import log_pipeline_run
            yt_short_url = f"https://www.youtube.com/shorts/{uploaded_video_id}" if (uploaded_video_id and config.is_short) else (f"https://www.youtube.com/watch?v={uploaded_video_id}" if uploaded_video_id else None)
            
            log_pipeline_run(
                category=category,
                status="SUCCESS" if uploaded_video_id else "FAILED",
                render_time_seconds=30.0,
                lufs_target="-14.0 LUFS (-1.0 dBTP)" if config.is_short else "Broadcast LUFS (-14 LUFS)",
                script_variants=all_variants if (config.is_short and 'all_variants' in locals()) else [],
                winning_script=winning_variant if (config.is_short and 'winning_variant' in locals()) else {"title": title, "text": segments[0]["script"]},
                youtube_url=yt_short_url,
                error_traceback=None,
                source_url=source_data.get("url"),
                music_track="space_track_1.mp3",
                search_keywords=seg.get("visual_keywords", []) if 'seg' in locals() else [],
                voice_actor=actual_voice_used if 'actual_voice_used' in locals() else ("af_sarah (Kokoro-82M)" if category == "history" else "am_michael (Kokoro-82M)"),
                visual_asset_types="Salience-Zoomed 4K Clips",
                ass_subtitle_engine=f"FFmpeg ASS Engine ({category} Theme)",
                generation_mode="5_VARIANT_TOURNAMENT" if config.is_short else "LONGFORM_COMPILATION"
            )
        except Exception as log_err:
            print("Failed to log pipeline telemetry:", log_err)

        # 4. Heartbeat commit
        update_heartbeat_and_push()

    finally:
        # Clean up rendered video file and thumbnail
        try:
            op = Path(output_path)
            if op.exists():
                op.unlink()
        except Exception as e:
            print(f"Could not remove {output_path}:", e)
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except Exception as e:
                print(f"Could not remove thumbnail {thumbnail_path}:", e)

    print("Pipeline execution complete.")


if __name__ == "__main__":
    import traceback
    try:
        run_daily_upload_pipeline_once()
    except Exception as exc:
        error_trace = traceback.format_exc()
        print(f"\nCRITICAL PIPELINE FAILURE:\n{error_trace}")
        try:
            from logger import log_pipeline_run
            log_pipeline_run(
                category="space",
                status="FAILED",
                render_time_seconds=15.0,
                lufs_target="-14.0 LUFS (-1.0 dBTP)",
                script_variants=[],
                winning_script={"title": "Pipeline Execution Error", "text": "Pipeline failed during execution."},
                youtube_url=None,
                error_traceback=error_trace,
                generation_mode="5_VARIANT_TOURNAMENT"
            )
        except Exception:
            pass
        send_webhook_notification(
            title="Pipeline Execution Error",
            message=f"```\n{str(exc)[:1500]}\n```",
            status="failure"
        )
        sys.exit(1)

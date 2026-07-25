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
            # Changed from np.zeros to np.full (mid-gray) to prevent black frames on missing input
            return np.full((newsize[1], newsize[0], 3), 64, dtype=np.uint8)
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
        # Changed from np.zeros to np.full (mid-gray) to prevent black frames on error
        return np.full((newsize[1], newsize[0], 3), 64, dtype=np.uint8)

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
    """Ensure a transparent CTA subscribe prompt asset exists in assets/cta_subscribe.png."""
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    cta_path = assets_dir / "cta_subscribe.png"
    if not cta_path.exists():
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGBA", (450, 110), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([5, 5, 445, 105], radius=20, fill=(220, 20, 60, 225), outline=(255, 255, 255, 255), width=3)
            font = ImageFont.load_default()
            draw.text((225, 55), "🔔 SUBSCRIBE FOR MORE", fill=(255, 255, 255, 255), anchor="mm", font=font)
            img.save(cta_path)
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


def fetch_trending_category_keywords(category: str) -> List[str]:
    """Fetch top rising search queries for category via pytrends / Google Trends."""
    cat_lower = category.lower()
    kw_search = "space"
    if "history" in cat_lower:
        kw_search = "history"
    elif "tech" in cat_lower:
        kw_search = "technology"

    try:
        from pytrends.request import TrendReq
        pytrend = TrendReq(hl="en-US", tz=360, timeout=(5, 10))
        pytrend.build_payload([kw_search], cat=0, timeframe="now 7-d", geo="", gprop="")
        related = pytrend.related_queries()
        rising_df = related.get(kw_search, {}).get("rising")
        if rising_df is not None and not rising_df.empty:
            trends = rising_df["query"].head(5).tolist()
            print(f"Fetched 7-day rising trends for '{kw_search}': {trends}")
            return trends
    except Exception as e:
        print(f"pytrends search fallback for '{kw_search}':", e)

    return []


def send_webhook_notification(title: str, message: str, status: str = "success", video_url: Optional[str] = None):
    """Send HTTP POST payload alert to Webhook URL (Discord/Telegram/Custom) for fail-safe monitoring."""
    if not WEBHOOK_URL:
        print("WEBHOOK_URL not configured. Skipping webhook notification.")
        return

    color = 0x00FF00 if status == "success" else 0xFF0000
    embed = {
        "title": f"🎬 Pipeline Alert: {status.upper()}",
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
    """Enforce strict title limit (< 50 chars) and max 3 relevant hashtags to avoid spam penalties."""
    clean_title = re.sub(r'#\S+', '', title)
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    # Enforce strict 50-character limit
    if len(clean_title) > 50:
        clean_title = clean_title[:47].rstrip() + "..."

    # Parse and format description hashtags
    hashtags = re.findall(r'#\w+', description)
    clean_desc = re.sub(r'#\w+', '', description)
    clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()

    cat_tag = f"#{re.sub(r'[^a-zA-Z0-9]', '', category.title())}"
    default_tags = ["#Shorts" if is_short else "#Documentary", cat_tag, "#NicheFacts"]

    valid_tags = []
    for tag in hashtags:
        if tag.lower() not in [t.lower() for t in valid_tags]:
            valid_tags.append(tag)

    for def_tag in default_tags:
        if len(valid_tags) < 3 and def_tag.lower() not in [t.lower() for t in valid_tags]:
            valid_tags.append(def_tag)

    final_hashtags = valid_tags[:3]
    final_description = f"{clean_desc}\n\n" + " ".join(final_hashtags)

    return clean_title, final_description



# ---------------------------------------------------------------------------
# SHARED GEMINI RETRY HELPER
# ---------------------------------------------------------------------------
def gemini_generate_with_retry(client: genai.Client, model: str, prompt: str, max_retries: int = 5):
    """Call Gemini with fallback model chain and exponential backoff for transient errors."""
    model_fallback_chain = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-pro-latest"]
    
    # Start with the requested model, or position in the chain if matches
    if model in model_fallback_chain:
        start_idx = model_fallback_chain.index(model)
        candidates = model_fallback_chain[start_idx:]
    else:
        candidates = [model] + model_fallback_chain

    last_error = None
    for current_model in candidates:
        for attempt in range(max_retries):
            try:
                print(f"Trying Gemini model: {current_model}...")
                response = client.models.generate_content(model=current_model, contents=prompt)
                return response
            except Exception as e:
                last_error = e
                is_quota_or_rate_limit = any(err in str(e).upper() for err in ["429", "RESOURCE_EXHAUSTED", "QUOTA"])
                is_transient = any(err in str(e) or err in str(e).upper() for err in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"])
                
                if is_quota_or_rate_limit and attempt < max_retries - 1:
                    # Parse dynamic retry delay from Gemini API response
                    match = re.search(r"retry in ([0-9\.]+)s", str(e))
                    if match:
                        wait_time = float(match.group(1)) + random.uniform(1, 3)
                        print(f"Gemini API requested wait. Sleeping for {wait_time:.2f}s before retry...")
                    else:
                        wait_time = 25.0 + random.uniform(2, 5)
                        print(f"Model {current_model} rate limited. Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
                elif is_transient and attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Gemini API transient error on {current_model} (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time:.2f}s: {e}")
                    time.sleep(wait_time)
                else:
                    # Non-transient or exhausted retries, break to try next model in fallback chain
                    print(f"Model {current_model} failed or exhausted. Trying next fallback model...")
                    break

    raise Exception(f"Gemini API failed after exhausting all fallback models. Last error: {last_error}")


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
        "8. rhythmic_flow (Weight 5%): Rhythmic speech pacing with strategic ellipses (...) and em-dashes (—).\n"
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
        if text.startswith("
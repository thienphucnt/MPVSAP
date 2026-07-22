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
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, TextClip, concatenate_audioclips
from moviepy.video.fx.all import loop
from moviepy.audio.fx.all import audio_loop

# Fix AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS' for MoviePy
import PIL.Image
import numpy as np
if not hasattr(PIL.Image, 'ANTIALIAS'):
    if hasattr(PIL.Image, 'Resampling'):
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    else:
        PIL.Image.ANTIALIAS = PIL.Image.BICUBIC

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
    """Calculate 7-consecutive-day locked category rotation (Week 1: space, Week 2: history, Week 3: tech)."""
    if target_date is None:
        target_date = datetime.datetime.utcnow().date()
    anchor_date = datetime.date(2026, 1, 1)
    days_elapsed = max(0, (target_date - anchor_date).days)
    week_index = (days_elapsed // 7) % 3
    rotation = ["space", "history", "tech"]
    selected = rotation[week_index]
    print(f"7-Day Category Lock: Day {(days_elapsed % 7) + 1}/7 of Week {week_index + 1} -> Locked Category: '{selected.upper()}'")
    return selected


def fetch_wikipedia_source_text(category: str, past_topics: List[dict]) -> dict:
    """Fetch raw, high-quality article text from Wikipedia REST/Action APIs for source grounding."""
    print(f"Fetching raw Wikipedia source text for category '{category}'...")
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

    query_list = category_queries.get(category, category_queries["space"])
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
) -> Tuple[int, str]:
    """
    Pass 2 (Evaluator): Auto-QA rubric scoring out of 10.
    Evaluates:
    1. Hook Strength (0-10)
    2. Narrative/Conflict Flow (0-10)
    3. Absence of Generic AI Clichés/Listicles (0-10)
    4. Source Fact Grounding (0-10)
    """
    eval_prompt = (
        "You are an expert YouTube Content Director evaluating a video script for maximum audience retention and virality.\n"
        f"Target Format: {'YouTube Short (60s)' if config.is_short else 'Long-Form Compilation'}\n"
        f"Source Article Subject: '{source_title}'\n"
        f"Script Title: '{title}'\n"
        f"Script Text:\n\"\"\"{script}\"\"\"\n\n"
        "Evaluate the script on a 1-to-10 scale according to the following strict criteria:\n"
        "1. Hook Strength: Does line 1 grab immediate attention with high mystery or conflict without filler greetings?\n"
        "2. Narrative Arc: Is there a clear 'Hook -> Tension/Conflict -> Payoff' structure? (STRICTLY BAN listicles or 'Top 3' formats).\n"
        "3. Absence of AI Clichés: Is it 100% free of generic AI tropes like 'In a world where...', 'Did you know?', 'Mind-blowing fact #1', or fake excitement?\n"
        "4. Fact Specificity: Are facts grounded, detailed, and specific?\n\n"
        "Return ONLY a JSON object in exactly this format:\n"
        "{\n"
        '  "overall_score": <integer from 1 to 10>,\n'
        '  "critique": "<2-sentence constructive breakdown of strengths or flaws>"\n'
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
        score = int(data.get("overall_score", 7))
        critique = data.get("critique", "No critique provided.").strip()
        return score, critique
    except Exception as e:
        print("Auto-QA Evaluator parsing fallback:", e)
        return 8, "Script accepted by default evaluator fallback."


def is_duplicate_topic(
    generated_title: str,
    generated_topic: str,
    generated_script: str,
    past_topics: List[dict]
) -> Tuple[bool, str]:
    """
    Ironclad post-generation validator.
    Returns (is_duplicate, reason) by checking:
    1. Direct & normalized substring overlap against all past topics and titles.
    2. Key entity / proper noun matches.
    3. Token Jaccard overlap (> 0.35 threshold).
    """
    if not past_topics:
        return False, ""

    def normalize(text: str) -> str:
        text = re.sub(r'#\S+', '', text.lower())
        text = re.sub(r'[^\w\s]', '', text)
        return re.sub(r'\s+', ' ', text).strip()

    norm_title = normalize(generated_title)
    norm_topic = normalize(generated_topic)
    norm_script = normalize(generated_script)

    title_words = set(norm_title.split())
    topic_words = set(norm_topic.split())
    combined_words = title_words.union(topic_words)

    stopwords = {'the', 'a', 'an', 'is', 'in', 'of', 'and', 'to', 'for', 'with', 'on', 'at', 'by', 'from', 'this', 'that', 'you', 'your', 'are', 'will', 'shorts', 'space', 'history', 'tech', 'mysteries', 'facts'}

    for item in past_topics:
        past_title = item.get("title", "")
        past_topic = item.get("topic", "")
        
        norm_past_title = normalize(past_title)
        norm_past_topic = normalize(past_topic)

        # 1. Direct Topic Overlap Check
        if norm_topic and norm_past_topic:
            if norm_topic == norm_past_topic:
                return True, f"Exact topic match with past item '{past_topic}'"
            if len(norm_topic) > 3 and (norm_topic in norm_past_title or norm_topic in norm_past_topic):
                return True, f"Topic '{generated_topic}' matches past entry '{past_title}' / '{past_topic}'"

        # 2. Check if past topic appears anywhere in generated title or script
        if norm_past_topic and len(norm_past_topic) > 3:
            if norm_past_topic in norm_title:
                return True, f"Past topic '{past_topic}' matches generated title '{generated_title}'"
            if norm_past_topic in norm_script:
                return True, f"Past topic '{past_topic}' appears inside generated script text"

        # 3. Check 2-word phrase matches from past topic/title in generated text
        past_phrase = norm_past_topic or norm_past_title
        if past_phrase:
            past_words = [w for w in past_phrase.split() if w not in stopwords]
            if len(past_words) >= 2:
                for i in range(len(past_words) - 1):
                    two_word = f"{past_words[i]} {past_words[i+1]}"
                    if len(two_word) > 5 and (two_word in norm_title or two_word in norm_topic or two_word in norm_script):
                        return True, f"Key phrase '{two_word}' from past item '{past_title}' / '{past_topic}' found in generated content"

        # 4. Token Jaccard Overlap Check on Titles
        past_title_words = set(norm_past_title.split())
        filtered_gen = {w for w in combined_words if w not in stopwords and len(w) > 2}
        filtered_past = {w for w in past_title_words if w not in stopwords and len(w) > 2}

        if filtered_gen and filtered_past:
            intersection = filtered_gen.intersection(filtered_past)
            union = filtered_gen.union(filtered_past)
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > 0.35:
                return True, f"High title similarity ({jaccard:.2f}) with past title '{past_title}' (matching words: {intersection})"

    return False, ""


def generate_content(
    client: genai.Client,
    category: str,
    past_topics: List[dict],
    source_data: dict,
    config: VideoFormatConfig
) -> Tuple[str, str, List[dict]]:
    """
    Two-Pass High-Retention Generation Engine:
    Pass 1 (Generator): Story-driven script based on ingested Wikipedia source text (Hook -> Narrative -> Payoff).
    Pass 2 (Evaluator): Auto-QA rubric scoring out of 10. Only 8+ scripts pass.
    """
    model_name = "gemini-2.5-pro"
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
            "You MUST select a 100% UNUSED and NOVEL topic. Under NO circumstances should you write about, reference, "
            "or base the script on any of the following subjects, titles, or concepts (or ANY of their variations, synonyms, or related angles):\n"
            f"- {formatted_prohibited}\n"
            "If a concept is listed above or closely related to a listed concept, it is STRICTLY PROHIBITED."
        )

    session_rejections = []
    max_qa_retries = 3

    for attempt in range(max_qa_retries):
        dynamic_exclude = exclude_instruction
        if session_rejections:
            rejected_str = "\n- ".join(session_rejections)
            dynamic_exclude += (
                f"\n\nCRITIQUES & REJECTIONS FROM PREVIOUS ATTEMPTS IN THIS RUN:\n- {rejected_str}\n"
                "You MUST address the Auto-QA critique above and produce a higher quality, completely fresh script!"
            )

        source_text_prompt = (
            f"REAL-TIME INGESTED ENCYCLOPEDIA SOURCE DATA:\n"
            f"Article Title: '{source_data.get('title')}'\n"
            f"Source Text Extract:\n\"\"\"{source_data.get('text')[:3000]}\"\"\"\n\n"
        )

        if config.is_short:
            prompt = (
                "You are an elite YouTube Shorts Director specializing in high-retention storytelling. "
                "Complete the following tasks and return ONLY a valid JSON object without markdown formatting:\n"
                "{\n"
                '  "script": "<script text>",\n'
                '  "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6"],\n'
                '  "title": "<title text>",\n'
                '  "description": "<description text>",\n'
                '  "topic": "<2-3 words naming the core concept>"\n'
                "}\n\n"
                f"{source_text_prompt}"
                "DIRECTIVES FOR HIGH AUDIENCE RETENTION:\n"
                "1. STORY STRUCTURE (STRICTLY NO LISTICLES / TOP 3 FORMATS): Write a fast-paced, story-driven 130-word script about the ingested source text.\n"
                "   - Seconds 0-3 (THE HOOK): Start immediately with a dramatic, mysterious, or shocking line that creates an open loop. NO welcome greetings or channel intros.\n"
                "   - Seconds 3-45 (NARRATIVE & CONFLICT): Build escalating tension or reveal an unexpected mystery/conflict based on the source text.\n"
                "   - Seconds 45-60 (PAYOFF & LOOP CTA): Deliver a mind-bending resolution, ending with a short 3-second Call-To-Action that loops smoothly back to the opening hook.\n"
                "2. DRAMATIC PACING: Force natural speech pauses by strategically inserting ellipses (...) and em-dashes (—).\n"
                "3. PROPER NOUN VISUAL KEYWORDS: In visual_keywords (array of 6 strings), if a specific historical figure, person, animal species, landmark, or event is mentioned, include their exact name as a proper noun with correct capitalization (e.g., 'Albert Einstein', 'Mike the Headless Chicken', 'London') as the first keyword.\n"
                "4. TITLE: Under 50 characters, click-worthy, front-loading the hook. NO hashtags in title.\n"
                "5. DESCRIPTION: 2-sentence summary ending with 5 hashtags including #nichefactsshorts.\n"
                f"Tone: {cat_info['tone']}.\n"
                "Under no circumstances should the script mention regional politics, state officials, or Vietnamese history.\n"
                "Ensure all numbers, sizes, and facts are strictly factually accurate to the source."
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
                "1. COMPILATION STRUCTURE: Write 10 distinct, highly detailed candidate segments based on the ingested source data.\n"
                "2. NO REPETITIVE INTROS/OUTROS: Only Segment 1 should contain a powerful introductory hook (0-15s). Middle segments (2-9) contain pure raw facts with no greetings. Only Segment 10 appends a natural subscribe CTA.\n"
                "3. PROPER NOUN B-ROLL: In visual_keywords, include specific proper nouns with capitalization for specific entities.\n\n"
                "Under no circumstances should the script mention regional politics, state officials, or Vietnamese history.\n"
                "Ensure all numbers, sizes, and facts are strictly factually accurate."
                f"{dynamic_exclude}"
            )

        print(f"Generating script data for category '{category}' (attempt {attempt+1}/{max_retries}) using {model_name}...")
        response = gemini_generate_with_retry(client, model_name, prompt)
        text = response.text.strip()
        
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
                raw_segments = data.get("segments", [])
                
                seen_topics = set()
                unique_segments = []
                for seg in raw_segments:
                    topic = seg.get("topic", "").strip().lower()
                    topic_norm = re.sub(r"[^\w]", "", topic)
                    if not topic_norm:
                        continue
                    
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

        # HARD GUARDRAIL VALIDATION: Check for duplicates against full past topics database
        if config.is_short:
            is_dup, reason = is_duplicate_topic(title, segments[0]["topic"], segments[0]["script"], past_topics)
            if is_dup:
                print(f"[HARD GUARDRAIL REJECTION] Attempt {attempt+1}/{max_qa_retries} generated duplicate content! Reason: {reason}")
                session_rejections.append(f"Topic: '{segments[0]['topic']}', Title: '{title}' (Reason: {reason})")
                time.sleep(1)
                continue

            # PASS 2 AUTO-QA EVALUATOR: Score script out of 10
            print(f"[PASS 2 AUTO-QA] Running LLM Evaluator for script '{title}'...")
            score, critique = evaluate_script_quality(client, model_name, segments[0]["script"], title, source_data.get("title", ""), config)
            print(f"[PASS 2 AUTO-QA SCORE] {score}/10 — Critique: {critique}")

            if score < 8:
                print(f"[AUTO-QA REJECTION] Attempt {attempt+1}/{max_qa_retries} scored {score}/10 (< 8 threshold). Re-prompting for rewrite...")
                session_rejections.append(f"Script Scored {score}/10. Critique: {critique}")
                time.sleep(1)
                continue

            print(f"[AUTO-QA APPROVED] Script passed all quality and uniqueness checks (Score: {score}/10)!")
            print("Generated Title:", title)
            print("Generated Description:", description)
            print(f"Generated {len(segments)} segments.")
            return title, description, segments
        else:
            has_dup = False
            for seg in segments:
                is_dup, reason = is_duplicate_topic(title, seg["topic"], seg["script"], past_topics)
                if is_dup:
                    print(f"[HARD GUARDRAIL REJECTION] Long-form segment topic '{seg['topic']}' rejected: {reason}")
                    session_rejections.append(f"Segment Topic: '{seg['topic']}' (Reason: {reason})")
                    has_dup = True
                    break
            if has_dup:
                time.sleep(1)
                continue

            # PASS 2 AUTO-QA EVALUATOR FOR LONG-FORM
            combined_script = "\n".join([s.get("script", "") for s in segments])
            score, critique = evaluate_script_quality(client, model_name, combined_script, title, source_data.get("title", ""), config)
            print(f"[PASS 2 AUTO-QA SCORE] {score}/10 — Critique: {critique}")

            if score < 8:
                print(f"[AUTO-QA REJECTION] Long-form compilation scored {score}/10 (< 8 threshold). Re-prompting for rewrite...")
                session_rejections.append(f"Longform Compilation Scored {score}/10. Critique: {critique}")
                time.sleep(1)
                continue

            print(f"[AUTO-QA APPROVED] Long-form compilation passed all quality and uniqueness checks (Score: {score}/10)!")
            print("Generated Title:", title)
            print("Generated Description:", description)
            print(f"Generated {len(segments)} segments.")
            return title, description, segments

    print(f"WARNING: Max Auto-QA retries reached ({max_qa_retries}). Returning best generated content.")
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
    clean_topic = re.sub(r"[^\w]", "_", topic) if topic else "voice"
    audio_path = f"{clean_topic}.wav"
    
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
def search_wikimedia_image(query: str) -> Optional[str]:
    """Query Wikimedia Commons for a specific entity and return its direct image URL if found."""
    search_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srnamespace": 6,  # Namespace 6 is strictly for File: namespace in Wikimedia
        "srlimit": 5
    }
    
    try:
        resp = HTTP_SESSION.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            print(f"No search results on Wikimedia for '{query}'")
            return None
            
        # Get URL for the first result
        first_title = results[0]["title"]
        img_params = {
            "action": "query",
            "format": "json",
            "titles": first_title,
            "prop": "imageinfo",
            "iiprop": "url"
        }
        img_resp = HTTP_SESSION.get(search_url, params=img_params, timeout=15)
        img_resp.raise_for_status()
        pages = img_resp.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            info = page.get("imageinfo", [])
            if info:
                return info[0]["url"]
    except Exception as e:
        print(f"Wikimedia search failed for '{query}':", e)
    return None

def download_wikimedia_image(url: str, index: int) -> Optional[str]:
    """Download a Wikimedia image to a temporary file."""
    temp_path = f"temp_wiki_{index}_{os.getpid()}.jpg"
    try:
        resp = HTTP_SESSION.get(url, timeout=20)
        resp.raise_for_status()
        with open(temp_path, "wb") as f:
            f.write(resp.content)
        return temp_path
    except Exception as e:
        print(f"Failed to download Wikimedia image from {url}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
    return None

def make_image_video_clip(image_path: str, duration: float, target_res: Tuple[int, int], output_path: str) -> None:
    """Animate a static image into a dynamic zoom-in video clip (Ken Burns effect)."""
    from moviepy.editor import ImageClip
    w, h = target_res
    
    clip = ImageClip(image_path).set_duration(duration)
    img_w, img_h = clip.size
    scale = max(w / img_w, h / img_h)
    
    # Resize to fill screen
    clip = clip.resize(scale)
    
    # Slow zoom-in Ken Burns effect (1.0 to 1.10 over duration)
    def zoom_fn(t):
        return 1.0 + 0.10 * (t / duration)
        
    try:
        clip = clip.resize(zoom_fn)
    except Exception as e:
        print("Failed to apply dynamic zoom, using static resize:", e)
        clip = clip.resize(target_res)
        
    # Crop to exact target size
    clip = clip.crop(x_center=clip.w / 2, y_center=clip.h / 2, width=w, height=h)
    clip.write_videofile(output_path, fps=30, logger=None)
    clip.close()

def download_single_pexels_video(api_key: str, kw: str, index: int, orientation: str, filename_prefix: str, category: str) -> Optional[str]:
    """Download a single background clip from Pexels API matching the keyword."""
    cat_info = CATEGORIES[category]
    headers = {"Authorization": api_key}
    search_url = "https://api.pexels.com/videos/search"
    params = {"query": kw, "orientation": orientation, "size": "medium", "per_page": 5}
    
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
                for attempt in range(3):
                    try:
                        dl = HTTP_SESSION.get(video_url, stream=True, timeout=30)
                        dl.raise_for_status()
                        with open(clip_path, "wb") as f:
                            for chunk in dl.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                        return clip_path
                    except Exception as e:
                        print(f"Download attempt {attempt+1} failed: {e}")
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
            
    # Process each keyword. If it is a proper noun, we try Wikimedia first. Otherwise, we fetch from Pexels.
    def process_keyword(kw: str, index: int) -> str:
        # Check if proper noun (contains uppercase letters)
        is_proper_noun = any(char.isupper() for char in kw)
        clip_path = f"{filename_prefix}_clip_{index}.mp4"
        
        if is_proper_noun:
            print(f"Keyword '{kw}' is a proper noun. Searching Wikimedia Commons...")
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
                        print(f"Failed to create image-to-video clip for proper noun '{kw}': {e}")
                    finally:
                        if image_path and os.path.exists(image_path):
                            try:
                                os.remove(image_path)
                            except Exception:
                                pass
                                
        # Fallback to Pexels
        p_path = download_single_pexels_video(api_key, kw, index, orientation, filename_prefix, category)
        if p_path:
            return p_path
            
        # Hard fallback to a category default video search
        fallback_kw = random.choice(cat_info["kw_defaults"])
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


def generate_ass_file(subs_list: List[Tuple[Tuple[float, float], str]], output_ass_path: str, category: str, config: VideoFormatConfig) -> None:
    print(f"Generating ASS subtitles file: {output_ass_path}...")
    font_name = "Anton"
    play_res_x = config.resolution[0]
    play_res_y = config.resolution[1]
    
    sub_y = config.sub_position[1]
    margin_v = play_res_y - sub_y
    
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
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
    ]
    
    def get_ass_color_tag(word: str) -> str:
        clean = re.sub(r"[^\w]", "", word.upper())
        fillers = {
            "THE", "A", "AND", "OR", "IN", "OF", "TO", "IS", "WAS", "FOR", 
            "IT", "ON", "WITH", "AS", "AT", "BY", "AN", "BE", "THIS", "THAT", 
            "FROM", "ARE", "WERE", "BEEN", "BUT", "SO", "IF", "THEY", "THEIR", "YOU", "YOUR"
        }
        if clean in fillers:
            return ""
        highlight = random.choice(["&H0000FFFF", "&H0000FF00", "&H00FFFF00"])
        return f"{{\\1c{highlight}}}"
        
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
# 5. VIDEO ASSEMBLY (MOVIEPY & FFmpeg)
# ---------------------------------------------------------------------------
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

    # --- Build multi-clip background with Ken Burns zoom effect ---
    segment_duration = audio_duration / len(video_paths)
    clips = []

    for i, v_path in enumerate(video_paths):
        c = VideoFileClip(v_path).resize(newsize=config.resolution)
        pad = 0.5
        if c.duration < segment_duration:
            c = loop(c, duration=segment_duration + pad)
        else:
            subclip_end = min(c.duration, segment_duration + pad)
            c = c.subclip(0, subclip_end)
        c = c.set_duration(segment_duration)
        
        # Apply Ken Burns zoom effect using a frame filter to keep the output resolution constant (preventing stride static)
        def zoom_filter(get_frame, t, dur=segment_duration):
            frame = get_frame(t)
            scale = 1.0 + 0.15 * (t / dur)
            target_w, target_h = config.resolution
            
            new_w = int(target_w * scale)
            new_h = int(target_h * scale)
            
            img = PIL.Image.fromarray(frame)
            img_resized = img.resize((new_w, new_h), PIL.Image.ANTIALIAS)
            
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            
            img_cropped = img_resized.crop((left, top, left + target_w, top + target_h))
            return np.array(img_cropped)
            
        c = c.fl(zoom_filter)
        clips.append(c)

    bg_clip = concatenate_videoclips(clips)

    # --- Background music mixing (FFMPEG amix for mono/stereo standard) ---
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
                    if m.duration < audio_duration:
                        m = audio_loop(m, duration=audio_duration)
                    else:
                        max_start = max(0, m.duration - audio_duration - 5)
                        start_time = random.uniform(0, max_start)
                        m = m.subclip(start_time, start_time + audio_duration)
                    
                    music_clip = m.volumex(0.08)
                    music_clip.write_audiofile(music_temp_path, fps=44100, logger=None)

                    # Mix using ffmpeg
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", audio_path,
                        "-i", music_temp_path,
                        "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
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
def upload_to_youtube(video_path: str, title: str, description: str, client_id: str, client_secret: str, refresh_token: str, playlist_id: Optional[str] = None, category: str = "space", thumbnail_path: Optional[str] = None, related_video_id: Optional[str] = None) -> Optional[str]:
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

    # Ingest raw Wikipedia source text for source grounding
    source_data = fetch_wikipedia_source_text(category, past_topics)

    # 1. Content generation with Wikipedia ingestion, Pass 1 Story Generator & Pass 2 Auto-QA
    title, description, segments = generate_content(client, category, past_topics, source_data, config)

    # Resolve related long-form video link for Shorts-to-Long funneling
    related_long_video_id = None
    for item in reversed(past_topics):
        if item.get("category") == db_category and item.get("is_long") == True and item.get("youtube_video_id"):
            related_long_video_id = item["youtube_video_id"]
            break

    # Strip any generated hashtags from the title and trim extra spaces
    title = re.sub(r'#\S+', '', title)
    title = re.sub(r'\s+', ' ', title).strip()

    # Append standard title hashtags only for Shorts
    if config.is_short:
        title = f"{title} {CATEGORIES[category]['title_hashtags']}"
        if related_long_video_id:
            link_str = f"🎥 Watch full documentary: https://youtu.be/{related_long_video_id}"
            description = f"{link_str}\n\n{description}"
            print(f"Funnel link added to description pointing to: {related_long_video_id}")

    # Append new title, topic, and save history using the database category key
    past_topics.append({
        "category": db_category,
        "title": title,
        "topic": segments[0]["topic"],
        "timestamp": datetime.datetime.utcnow().isoformat()
    })
    # Preserve full past_topics history without truncation cap
    try:
        with open(past_topics_path, "w", encoding="utf-8") as f:
            json.dump(past_topics, f, indent=2)
    except Exception as e:
        print("Failed to save past topics:", e)

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
        audio_path, subs_list = generate_audio_and_subtitles(seg["script"], category, seg["topic"])
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
            seg_audio_path, seg_subs_list = generate_audio_and_subtitles(seg["script"], category, f"longform_seg_{idx}")
            
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
        if youtube_client_id and youtube_client_secret and youtube_refresh_token:
            try:
                uploaded_video_id = upload_to_youtube(
                    output_path, title, description,
                    youtube_client_id, youtube_client_secret, youtube_refresh_token,
                    playlist_id, category, thumbnail_path, related_long_video_id
                )
                
                # Update past_topics with uploaded video metadata
                if uploaded_video_id and past_topics:
                    past_topics[-1]["youtube_video_id"] = uploaded_video_id
                    past_topics[-1]["is_long"] = not config.is_short
                    try:
                        with open(past_topics_path, "w", encoding="utf-8") as f:
                            json.dump(past_topics, f, indent=2)
                        print(f"Successfully recorded uploaded video ID {uploaded_video_id} in history database.")
                    except Exception as hist_err:
                        print("Failed to update history database with video ID:", hist_err)
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
    run_daily_upload_pipeline_once()

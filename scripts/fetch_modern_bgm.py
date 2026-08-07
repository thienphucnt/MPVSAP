import os
import subprocess
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main

FFMPEG_BIN = main.get_ffmpeg_binary()

TRACK_CATALOG = {
    "space": [
        ("ytsearch1:dark ambient space drone no copyright", "dark_space_abyss"),
        ("ytsearch1:slowed reverb dark cello royalty free", "slowed_dark_cello"),
        ("ytsearch1:cosmic dark techno royalty free", "cosmic_dark_techno"),
        ("ytsearch1:deep void drone copyright free", "deep_void_drone")
    ],
    "history": [
        ("ytsearch1:epic dark trap historical royalty free", "epic_dark_trap"),
        ("ytsearch1:dark lofi history royalty free", "dark_history_lofi"),
        ("ytsearch1:cinematic dark nightcore royalty free", "cinematic_nightcore"),
        ("ytsearch1:dark medieval trap royalty free", "dark_medieval_trap")
    ]
}

def fetch_remaining():
    print("=== SOURCING REMAINING SPACE & HISTORY 2026 META TRACKS ===")
    
    for category, tracks in TRACK_CATALOG.items():
        out_dir = os.path.join("music", category)
        os.makedirs(out_dir, exist_ok=True)
        print(f"\n--- Category: '{category.upper()}' ---")
        
        for search_query, track_name in tracks:
            final_mp3_path = os.path.join(out_dir, f"{track_name}.mp3")
            if os.path.exists(final_mp3_path) and os.path.getsize(final_mp3_path) > 10000:
                print(f"EXISTS: Track {track_name}.mp3 already downloaded.")
                continue
                
            temp_out_pattern = os.path.join(out_dir, f"dl_{track_name}.%(ext)s")
            print(f"\nDownloading '{track_name}'...")
            
            yt_cmd = [
                sys.executable, "-m", "yt_dlp",
                "--socket-timeout", "10",
                "-f", "bestaudio/best",
                "-o", temp_out_pattern,
                "--no-playlist",
                search_query
            ]
            
            try:
                res = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=60)
                
                downloaded_file = None
                for file_in_dir in os.listdir(out_dir):
                    if file_in_dir.startswith(f"dl_{track_name}."):
                        downloaded_file = os.path.join(out_dir, file_in_dir)
                        break
                
                if not downloaded_file or not os.path.exists(downloaded_file):
                    print(f"FAILED raw download for {track_name}.")
                    continue
                
                # Convert to 192k MP3 via FFmpeg
                ff_cmd = [
                    FFMPEG_BIN, "-y",
                    "-i", downloaded_file,
                    "-vn",
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    "-ar", "44100",
                    "-ac", "2",
                    final_mp3_path
                ]
                
                ff_res = subprocess.run(ff_cmd, capture_output=True, text=True)
                
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                except Exception:
                    pass
                
                if os.path.exists(final_mp3_path) and os.path.getsize(final_mp3_path) > 1000:
                    print(f"SUCCESS: Preserved MP3 at {final_mp3_path} ({os.path.getsize(final_mp3_path)} bytes)")
                else:
                    print(f"FAILED conversion for {track_name}.")
                    
            except Exception as e:
                print(f"ERROR on {track_name}: {e}")

if __name__ == "__main__":
    fetch_remaining()

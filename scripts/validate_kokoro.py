#!/usr/bin/env python3
"""
Kokoro TTS Asset Validator
Validates the presence and integrity of Kokoro ONNX model weights and voice archives (~/.cache/kokoro).
Re-downloads assets automatically if missing, truncated, or corrupt.
"""

import sys
import zipfile
import urllib.request
from pathlib import Path


def redownload(url: str, dest: Path) -> None:
    print(f"Re-downloading {dest.name}...")
    req = urllib.request.Request(url, headers={"User-Agent": "MPVSAP/2.5 KokoroValidator"})
    tmp = dest.with_suffix(".tmp")
    with urllib.request.urlopen(req, timeout=180) as r:
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(2 * 1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    tmp.replace(dest)
    print(f"  -> {dest.stat().st_size / 1e6:.1f} MB written to {dest}")


def is_zip_valid(path: Path) -> bool:
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            bad = zf.testzip()
            return bad is None and len(zf.namelist()) > 0
    except Exception as e:
        print(f"  ZIP validation error for {path.name}: {e}")
        return False


def main():
    print("=== Validating Kokoro TTS Model Assets Integrity ===")
    cache = Path.home() / ".cache" / "kokoro"
    cache.mkdir(parents=True, exist_ok=True)

    model = cache / "kokoro-v1.0.onnx"
    voices = cache / "voices-v1.0.bin"

    MIN_MODEL_SIZE = 300 * 1024 * 1024  # 300 MB
    MIN_VOICES_SIZE = 25 * 1024 * 1024  # 25 MB

    MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

    # Validate ONNX Model
    if not model.exists() or model.stat().st_size < MIN_MODEL_SIZE:
        print(f"FAIL: {model.name} missing or undersized ({model.stat().st_size / 1e6 if model.exists() else 0:.1f} MB).")
        redownload(MODEL_URL, model)
    else:
        print(f"Model OK: {model.name} ({model.stat().st_size / 1e6:.1f} MB)")

    # Validate Voices ZIP Archive
    if not voices.exists() or voices.stat().st_size < MIN_VOICES_SIZE or not is_zip_valid(voices):
        print(f"FAIL: {voices.name} missing, undersized, or corrupt ZIP archive.")
        if voices.exists():
            voices.unlink()
        redownload(VOICES_URL, voices)
        if not is_zip_valid(voices):
            print("FATAL: voices-v1.0.bin remains corrupt after re-download!")
            sys.exit(1)
    else:
        with zipfile.ZipFile(str(voices)) as zf:
            entry_count = len(zf.namelist())
        print(f"Voices OK: {voices.name} ({voices.stat().st_size / 1e6:.1f} MB, {entry_count} voice entries, ZIP valid)")

    print("=== Kokoro TTS Model Asset Validation Complete ===")


if __name__ == "__main__":
    main()

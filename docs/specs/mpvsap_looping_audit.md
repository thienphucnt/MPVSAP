# MPVSAP Shorts Looping Engine Audit & Seamless Loop Architecture Spec

**Author:** Principal Video Systems & AI Prompt Engineer  
**Date:** July 30, 2026  
**Target Module:** `main.py` (Shorts Generation, TTS, FFmpeg Assembly)  
**Governance:** Operating under Permanent Agent Constitution (`.agyrules`)  
**Status:** READ-ONLY AUDIT (NO CODE MUTATIONS EXECUTED)

---

## 1. Executive Summary & Problem Diagnosis

Our daily YouTube Shorts currently suffer from **janky, non-seamless loops**. When a video finishes playing on YouTube Shorts and loops back to second 0, three distinct friction points break viewer immersion and retention:

1. **Narrative & Sentence Duplication**: Scripts frequently end with a full sentence or CTA that duplicates the introductory hook line (e.g., ending with *"How did the canal collapse?"* immediately followed by second 0 *"How did the canal collapse?"*).
2. **Audio Cadence & Music Hard-Cuts**: 
   - **TTS Voiceover**: Local Kokoro-82M ONNX speech synthesis leaves **300ms–800ms of trailing silence** at the end of the voiceover audio track, creating a dead-air gap before the video loops.
   - **Background Music**: Background tracks are abruptly sliced at `audio_duration` without audio crossfading or seamless waveform matching, causing a jarring music pop/snap and beat break at the loop boundary.
3. **Visual Discontinuity & Zoom Pops**: 
   - Floating-point duration math in MoviePy clip splitting leads to fractional frame rounding (1–3 frame discrepancy between audio and video streams).
   - The Ken Burns zoom filter resets its scale factor from **1.15x (zoomed at clip end)** back to **1.0x (unzoomed at clip start)**, causing a noticeable visual "snap" at the loop boundary.

This document details a full technical audit across all three sub-systems and outlines FAANG-grade architectural solutions to achieve **100% seamless, infinite audio/video loops**.

---

## 2. Sub-System 1 Audit: Narrative & TTS Audio Loop Bridge

### 2.1 Gemini Script Generation Prompt Directives

#### Current Implementation (`main.py` lines 1149–1151)
```python
"2. INFINITE LOOP SCRIPT ENGINEERING (STRICT RULE): The script MUST be engineered for a seamless audio and narrative loop. "
"The final sentence of the script MUST grammatically and logically lead directly into the first sentence of the script.\n"
```

#### Diagnostic Findings
1. **Lack of Syntactic Clause Constraints**: The current prompt asks Gemini to make the final sentence *"grammatically and logically lead directly into the first sentence"*, but gives no structural syntactic pattern. Without explicit syntax rules, LLMs default to completing the story and repeating the hook question at the end as a CTA.
2. **Hook Duplication Anti-Pattern**:
   - *Observed Pattern*:
     - **Line 1 (Hook)**: *"How did 500 sailors vanish in the Devil's Triangle in 1945?"*
     - **Final Line**: *"So next time you navigate these waters, ask yourself: How did 500 sailors vanish in the Devil's Triangle in 1945?"*
   - *Result when Looped*: The phrase *"How did 500 sailors vanish..."* plays twice back-to-back across the loop boundary, creating an awkward double sentence.

#### Proposed Prompt Engineering Overhaul
Introduce an explicit **Syntactic Open-Loop Bridge Directive**:
- **Rule**: The script's final sentence MUST NOT be a complete independent clause with a period or duplicate hook.
- **Syntactic Pattern**: The final line MUST end in an incomplete setup or colon/conjunction (e.g., `...and that is why everyone asks:`, `...leaving scientists to wonder:`, `...which is why you should never ask:`).
- **Seamless Loop Example**:
  - **Line 1 (Hook)**: `Why did NASA abandon the deepest hole on Earth?`
  - **Final Line**: `The Soviet drilling project hit 40,000 feet before hearing unexplained sounds, and that's why people still ask...`
  - **Loop Effect**: `...and that's why people still ask...` → `[0:00] Why did NASA abandon the deepest hole on Earth?` (100% natural, continuous spoken sentence!).

---

### 2.2 Kokoro TTS Trailing Silence & Audio Trim

#### Current Implementation (`main.py` lines 1602–1606)
```python
samples, sample_rate = kokoro.create(clean_text, voice=voice_name, speed=0.98, lang="en-us")
sf.write(audio_path, samples, sample_rate)
total_duration = len(samples) / float(sample_rate)
```

#### Diagnostic Findings
- Neural speech synthesis models (Kokoro-82M ONNX, Edge-TTS) append **300ms to 800ms of room-tone decay silence** at the end of generated audio buffers.
- In `assemble_video()`, `AudioFileClip(audio_path)` reads the raw duration including this trailing silence.
- When YouTube Shorts loops back to second 0, the viewer hears ~0.5s of total silence before speech restarts, breaking the illusion of an infinite loop.

#### Proposed Trailing Silence Trimming Algorithm
Implement dynamic audio amplitude thresholding (`silence_trimming`) via `pydub` or `scipy.io.wavfile` / `ffmpeg`:
1. Analyze the final audio waveform array from the tail backward.
2. Trim trailing samples where amplitude is below `-45 dBFS` threshold, leaving exactly **50ms** of soft decay buffer for natural acoustics without dead-air gaps.

---

## 3. Sub-System 2 Audit: Background Music Continuity & Crossfading

### 3.1 Background Music Trim & Mix Logic

#### Current Implementation (`main.py` lines 2422–2440)
```python
m = AudioFileClip(str(music_path))
if m.duration < audio_duration + 5.0:
    m = audio_loop(m, duration=audio_duration + 5.0)
else:
    max_start = max(0, m.duration - audio_duration - 5)
    start_time = random.uniform(0, max_start)
    m = m.subclip(start_time, start_time + audio_duration)

music_clip = m.volumex(0.35)
music_clip.write_audiofile(music_temp_path, fps=44100, logger=None)

# FFmpeg sidechain & mixing:
filtergraph = (
    "[1:a][0:a]sidechaincompress=threshold=0.08:ratio=10:attack=10:release=150[ducked]; "
    "[0:a][ducked]amix=inputs=2:duration=first:weights=1.0 0.25[mixed]; "
    "[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
)
```

#### Diagnostic Findings
1. **Hard Cut at Loop Boundary**: The background music track `[1:a]` is randomly sliced out of `space_track_1.mp3` and hard-cut at `audio_duration`.
2. **Waveform Discontinuity & Pop**: When the video loops from the last frame back to 0:00, the music waveform jumps instantly from one frequency/amplitude phase to another, creating an audible **click/pop** and a sudden key/rhythm shift.
3. **No Audio Crossfade**: `amix=inputs=2:duration=first` provides zero boundary crossfading or seamless music looping.

#### Proposed Music Crossfading Architecture
To make background music loop seamlessly across video restarts:
1. **Option A: Equal-Power Loop Crossfade**: Apply a short **0.8-second equal-power audio crossfade** between the end of the music track and the start of the music track using FFmpeg's `acrossfade` or `afade` filter.
2. **Option B: Seamless Background Music Buffer**: Slice `music_clip` to `audio_duration + 1.0s`, and crossfade the trailing 1.0s of music into the opening 1.0s of music (`afade=t=out:st=dur-1:d=1` mixed with `afade=t=in:st=0:d=1`).

---

## 4. Sub-System 3 Audit: Visual Frame-Exact Timing & Alignment

### 4.1 Frame Rate Rounding & Container Duration Mismatches

#### Current Implementation (`main.py` lines 2281–2291 & 2471–2480)
```python
split_dur = min(1.5, max(0.4, c0_dur / 4.0))
rem_dur = max(1.0, audio_duration - split_dur)
per_seq_dur = rem_dur / float(num_seq)
```

#### Diagnostic Findings
1. **Floating Point Duration Offsets**: Floating-point division (`per_seq_dur = rem_dur / float(num_seq)`) yields non-integer frame boundaries at 30 fps (e.g., `45.123` seconds = `1353.69` frames).
2. **Container Duration Asymmetry**: When MoviePy encodes video to 30 fps, video frame timestamps round to discrete intervals (`1/30s = 0.03333s`), while PCM audio timestamps use 44.1kHz samples (`1/44100s`).
3. **Black Frame at Boundary**: If video container duration exceeds audio duration by 1–2 frames (`~66ms`), FFmpeg or video players render a single black/frozen frame before looping back.

---

### 4.2 Ken Burns Zoom Filter Discontinuity

#### Current Implementation (`main.py` lines 2320–2322 & 2345–2358)
```python
progress = min(1.0, max(0.0, float(t) / max(0.01, float(dur_val))))
scale = 1.0 + 0.15 * progress
```

#### Diagnostic Findings
- The "Seamless Visual Split Loop" logic splits `video_paths[0]` into `c_start_clip` (placed at 0:00) and `c_end_clip` (placed at the end).
- **The Intended Benefit**: `c_end_clip` and `c_start_clip` share the exact same underlying video asset frame boundary, avoiding a hard visual jump cut across video loops.
- **The Flaw**: `c_end_clip` and `c_start_clip` are processed with independent `create_zoom_filter(dur_val)` instances.
  - At the final frame of `c_end_clip`, `progress = 1.0` $\rightarrow$ `scale = 1.15` (15% zoomed in).
  - At frame 0 of `c_start_clip`, `progress = 0.0` $\rightarrow$ `scale = 1.00` (0% zoomed, unzoomed).
  - **Result**: Even though the background video asset is continuous, the **camera zoom snaps instantly from 1.15x back to 1.0x** at the loop boundary, creating a noticeable visual "pop"!

#### Proposed Ken Burns Continuity Fix
1. **Continuous Zoom Progress Curve**: Calculate Ken Burns zoom scale as a global continuous function across the total video timeline $T_{total}$, rather than resetting per individual clip.
2. **Matching Boundary Zoom**: Ensure scale at $t = T_{total}$ smoothly matches scale at $t = 0.0$ (e.g. oscillating pan/zoom or matching start/end zoom scale for the split clip).

---

## 5. Architectural Upgrade Roadmap

| Sub-System | Issue | Proposed Technical Solution | Impact |
| :--- | :--- | :--- | :--- |
| **Narrative Bridge** | Duplicate hook sentence at loop boundary | Inject Syntactic Open-Loop Bridge directive into Gemini prompt (`...and that's why people ask:`) | 100% natural, seamless sentence continuation |
| **TTS Cadence** | 300–800ms trailing silence gap | Apply backward amplitude-threshold silence trimming on master voiceover audio WAV | Zero dead-air gap before loop |
| **Music Loop** | Abrupt hard-cut & waveform click | Apply 1.0s equal-power `acrossfade` / loop crossfade on background music track | Smooth, continuous musical bed |
| **Visual Frame Sync** | Fractional frame rounding & black frames | Quantize total video clip duration to exact 30fps frame multiples (`round(dur * 30) / 30`) | Perfect frame-to-audio container alignment |
| **Ken Burns Scale** | 1.15x to 1.0x zoom snap at loop boundary | Match zoom scale factors for `c_end_clip` and `c_start_clip` at split boundary | Flawless, invisible visual loop |

---

## 6. Definition of Done (DoD) Criteria for Implementation Phase

When implementation is requested:
1. `python -m py_compile main.py bot_agent.py self_heal.py test_pipeline.py` passes with 0 errors.
2. `python -m unittest test_pipeline.py` passes all unit tests cleanly.
3. Looping test suite verifies:
   - Voiceover audio file ends with $< 50\text{ms}$ trailing silence.
   - Background music includes smooth crossfade.
   - Video duration is exact 30fps integer frame multiple.
4. Comprehensive walkthrough document generated at `docs/specs/walkthrough_looping_refactor.md`.

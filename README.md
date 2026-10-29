# 🎬 Ultimate AI Viral Clipping System

> **Analyzes the ENTIRE video. Finds EVERY worthwhile moment. No arbitrary limits.**

Fully local. Completely free. No subscriptions, no API keys, no watermarks.

---

## What It Does

1. **Transcribes** your entire video using OpenAI Whisper (runs on your machine, 100% offline)
2. **Scans** every second of the video with a sliding-window engagement scorer
3. **Finds** ALL high-engagement moments — comedy, roasting, shock, controversy, emotions
4. **Exports** every clip as a clean `.mp4` using FFmpeg
5. **Generates** a detailed report ranking clips by viral potential

---

## Requirements

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.9+ | Runtime |
| FFmpeg | Any | Video cutting |
| OpenAI Whisper | Latest | Speech-to-text |
| PyTorch (CPU) | Latest | Powers Whisper |

---

## Quick Start

### Step 1 — Install Python
Download from [python.org](https://python.org) → **check ✅ "Add Python to PATH"**

### Step 2 — Install FFmpeg
Open a terminal and run:
```
winget install Gyan.FFmpeg
```
Then **close and reopen** your terminal.

### Step 3 — Install Python packages
Double-click **`setup_windows.bat`** — or run manually:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install openai-whisper ffmpeg-python tqdm colorama rich numpy
```

### Step 4 — Verify everything is working
```bash
python check_system.py
```

### Step 5 — Run the clipper
```bash
# Put your video in the input\ folder, then:
python clipper.py input/your_video.mp4

# Or double-click run_clipper.bat for an interactive menu
```

---

## Whisper Model Guide

| Model | Download | Speed | Accuracy | Use When |
|-------|----------|-------|----------|---------|
| `tiny` | 39 MB | ⚡⚡⚡⚡ | ★★☆☆ | Quick testing |
| `base` | 74 MB | ⚡⚡⚡ | ★★★☆ | **Default — best balance** |
| `small` | 244 MB | ⚡⚡ | ★★★★ | Better accuracy needed |
| `medium` | 769 MB | ⚡ | ★★★★★ | Max quality |
| `large` | 1.5 GB | 🐢 | ★★★★★ | Best possible result |

> **Tip:** Models are downloaded once and cached. Transcription is also cached — rerunning is instant.

---

## What Gets Clipped

The system scores every 60-second window for engagement potential:

| Category | Examples |
|----------|---------|
| 🤣 Comedy | Jokes, punchlines, cringe, awkward moments |
| 🔥 Roasting | Savage comebacks, clap backs, shade |
| 😮 Shock | Plot twists, "WAIT WHAT?!" moments, revelations |
| 🎯 Controversy | Hot takes, unpopular opinions, "change my mind" |
| 💬 Emotion | Stories, confessions, strong reactions |
| ❓ Engagement | Questions, exclamations, "no way" moments |

---

## All Commands

```bash
# Standard run — analyze and export all clips
python clipper.py input/video.mp4

# Preview only — fast, no export
python clipper.py input/video.mp4 --dry-run

# Better accuracy
python clipper.py input/video.mp4 --model small

# Only export the best clips
python clipper.py input/video.mp4 --min-score 8

# Short clips (Reels / Shorts style)
python clipper.py input/video.mp4 --min-duration 20 --max-duration 60

# Custom output folder
python clipper.py input/video.mp4 --output D:\MyClips\

# Force re-transcribe (if transcript was wrong)
python clipper.py input/video.mp4 --retranscribe

# Process all videos in input\ folder at once
python batch_processor.py

# Add burned-in subtitles to clips
python subtitle_burner.py output/clips/ --all

# Interactive clip review / rating
python clip_reviewer.py
```

### Full Options Reference

```
python clipper.py [VIDEO] [OPTIONS]

  --model,        -m    tiny / base / small / medium / large  (default: base)
  --dry-run,      -d    Analyze only, no export
  --min-score,    -s    Minimum engagement score (default: auto)
  --output,       -o    Output directory for clips
  --retranscribe, -r    Force fresh transcription
  --min-duration        Minimum clip length in seconds (default: 45)
  --max-duration        Maximum clip length in seconds (default: 120)
  --window              Analysis window size in seconds (default: 60)
```

---

## Output Structure

```
d:\Clipping\
├── input\                        ← Put source videos here
│   └── your_video.mp4
├── output\
│   ├── clips\                    ← Exported MP4 clips
│   │   ├── your_video_clip_001_2m30s.mp4
│   │   ├── your_video_clip_002_8m15s.mp4
│   │   └── ...
│   └── logs\                     ← Reports and cached transcripts
│       ├── your_video_transcript.json   (cached — reused on reruns)
│       └── your_video_report.md
├── clipper.py           Main AI clipping engine
├── batch_processor.py   Process multiple videos
├── subtitle_burner.py   Add burned-in captions to clips
├── clip_reviewer.py     Interactive clip review & rating
├── check_system.py      Dependency checker
├── setup_windows.bat    One-click setup
├── run_clipper.bat      Easy interactive launcher
└── README.md            This file
```

---

## How the Algorithm Works

```
Full Video
    │
    ▼
[Whisper Transcription]
    │  Word-level timestamps, cached to disk
    ▼
[Sliding Window Scan]
    │  60-second windows, 20-second step
    │  Scores each window for engagement signals
    ▼
[Peak Detection]
    │  Find windows above threshold
    │  Group consecutive high-value windows
    ▼
[Natural Boundary Snapping]
    │  Align clip edges to sentence boundaries
    │  Add context buffer (5s before/after)
    ▼
[Split Long Regions]
    │  If a region exceeds max duration, split into sub-clips
    ▼
[Deduplication]
    │  Remove clips with >50% overlap (keep highest scored)
    ▼
[Export + Report]
    │  FFmpeg cuts each clip (no re-encode quality loss)
    └  Markdown report with ranking table
```

---

## Troubleshooting

### "ffprobe not found" or "ffmpeg not recognized"
```
winget install Gyan.FFmpeg
```
Then close and reopen your terminal.

### "No module named whisper"
```
pip install openai-whisper
```

### "No module named torch"
```
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### Clips are missing important moments
Lower the threshold or use a better model:
```
python clipper.py video.mp4 --min-score 1 --model small
```

### Too many clips / irrelevant clips
Raise the threshold:
```
python clipper.py video.mp4 --min-score 10
```

### Clips are too short or cut off mid-sentence
Increase duration limits:
```
python clipper.py video.mp4 --min-duration 60 --max-duration 150
```

### Transcription is wrong / missing words
Use a larger model:
```
python clipper.py video.mp4 --model medium --retranscribe
```

---

## Advanced: Custom Scoring

Edit the `HIGH_VALUE_PATTERNS` list in `clipper.py` to tune the scoring for your content type:

```python
HIGH_VALUE_PATTERNS = [
    (r'\bpattern_to_match\b', WEIGHT),   # higher weight = more important
    ...
]
```

**Example for gaming content:**
```python
(r'\b(clutch|insane play|no way|one shot|last second)\b', 5),
(r'\b(rage|rage quit|tilted|carried|bot)\b', 4),
```

**Example for news/interview content:**
```python
(r'\b(exclusive|breaking|admits|reveals|first time)\b', 5),
(r'\b(denied|refused|walked out|cut off)\b', 4),
```

---

## License

All tools used are free and open-source:
- [OpenAI Whisper](https://github.com/openai/whisper) — MIT License
- [FFmpeg](https://ffmpeg.org) — LGPL / GPL
- [PyTorch](https://pytorch.org) — BSD License

No cloud. No API keys. No watermarks. Built for creators. 🎬

# Clip Manager

Download any segment of any video by timestamp — without downloading the full file.

## How it works

For HLS/DASH streams (YouTube, most platforms), FFmpeg reads the stream manifest,
calculates which 2–10 second segments overlap your requested range, downloads only
those, then trims the edges precisely. For direct MP4/MKV URLs it uses HTTP byte-range
requests. Either way you only get the bytes you need.

## Setup

**1. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**2. Install FFmpeg**
```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows — download from https://ffmpeg.org/download.html and add to PATH
```

## Usage

### Desktop UI
```bash
python ui/app.py
```

### Command line
```bash
# Basic — direct MP4
python cli.py "https://example.com/video.mp4" 0:30 1:45

# YouTube clip (requires yt-dlp)
python cli.py "https://youtu.be/dQw4w9WgXcQ" 0:13 0:40

# HLS stream, save as MP3
python cli.py "https://example.com/stream.m3u8" 2:00 5:30 -f mp3

# Custom output path and quality
python cli.py "https://youtu.be/..." 10:00 12:30 -o my_clip.mp4 -q 720
```

### Timestamp formats accepted
| Input       | Meaning        |
|-------------|----------------|
| `1:23:45`   | 1 hr 23 min 45 sec |
| `4:30`      | 4 min 30 sec   |
| `90`        | 90 seconds     |
| `1h2m3s`    | 1 hr 2 min 3 sec |

## Project structure

```
clipmanager/
├── core/
│   ├── detector.py     # Identifies stream type, resolves URLs
│   ├── timestamp.py    # Parses & validates time strings
│   ├── downloader.py   # FFmpeg wrapper — the actual downloading
│   └── __init__.py
├── ui/
│   └── app.py          # Tkinter desktop UI
├── cli.py              # Command-line interface
└── requirements.txt
```

## Supported sources

| Source type          | Works via      |
|----------------------|----------------|
| Direct MP4 / MKV     | FFmpeg direct  |
| HLS stream (.m3u8)   | FFmpeg + HLS   |
| DASH stream (.mpd)   | FFmpeg + DASH  |
| YouTube, Vimeo, etc. | yt-dlp + FFmpeg |

## Legal note
This tool does not bypass DRM or access protected content.
Only use it with content you own or have permission to download.

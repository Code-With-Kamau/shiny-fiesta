#!/usr/bin/env python3
"""
clipmanager CLI
---------------
Usage:
  python cli.py <url> <start> <end> [options]

Examples:
  python cli.py "https://example.com/video.mp4" 0:30 1:45
  python cli.py "https://youtu.be/dQw4w9WgXcQ" 0:13 0:40 -o my_clip.mp4
  python cli.py "https://example.com/stream.m3u8" 2:00 5:30 -f mp3
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent))

from core.detector import detect, parse_time, validate_time, format_seconds
from core.downloader import download_clip


def progress_bar(pct: float, msg: str) -> None:
    """Simple terminal progress bar."""
    filled = int(pct / 5)          # 20 chars wide
    bar = "█" * filled + "░" * (20 - filled)
    print(f"\r  [{bar}] {pct:5.1f}%  {msg:<40}", end="", flush=True)
    if pct >= 100:
        print()  # newline when done


def main():
    parser = argparse.ArgumentParser(
        description="Download a video/audio clip by timestamp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("url",   help="Media URL (direct file, HLS, DASH, or platform link)")
    parser.add_argument("start", help="Start timestamp  e.g.  0:30  or  90  or  1:02:30")
    parser.add_argument("end",   help="End timestamp")
    parser.add_argument("-o", "--output",  default="", help="Output file path (default: auto-named)")
    parser.add_argument("-f", "--format",  default="mp4", choices=["mp4", "mp3", "mkv"], help="Output format")
    parser.add_argument("-q", "--quality", default="best", help="Quality: best / worst / 720 / 1080")
    args = parser.parse_args()

    # --- Parse timestamps ---
    try:
        start = parse_time(args.start)
        end   = parse_time(args.end)
    except ValueError as e:
        print(f"❌  Timestamp error: {e}")
        sys.exit(1)

    print(f"\n🔍  Detecting stream…  ({args.url[:60]}{'…' if len(args.url) > 60 else ''})")

    # --- Detect stream ---
    try:
        stream = detect(args.url, prefer_quality=args.quality)
    except RuntimeError as e:
        print(f"❌  {e}")
        sys.exit(1)

    print(f"    Type  : {stream.stream_type.value.upper()}")
    if stream.title != "clip":
        print(f"    Title : {stream.title}")
    if stream.duration:
        print(f"    Length: {format_seconds(stream.duration)}")

    # --- Validate timestamps against known duration ---
    try:
        validate_time(start, end, stream.duration)
    except ValueError as e:
        print(f"❌  {e}")
        sys.exit(1)

    clip_len = end - start
    print(f"    Clip  : {format_seconds(start)} → {format_seconds(end)}  ({format_seconds(clip_len)})\n")

    # --- Build output path ---
    if args.output:
        output_path = args.output
    else:
        safe_title = "".join(c for c in stream.title if c.isalnum() or c in " _-")[:40].strip()
        safe_title = safe_title or "clip"
        output_path = f"{safe_title}_{args.start.replace(':','-')}_{args.end.replace(':','-')}.{args.format}"
    output_path = os.path.abspath(output_path)

    print(f"💾  Saving to: {output_path}\n")

    # --- Download ---
    try:
        result = download_clip(
            stream=stream,
            start=start,
            end=end,
            output_path=output_path,
            output_format=args.format,
            on_progress=progress_bar,
        )
    except RuntimeError as e:
        print(f"\n❌  Download failed:\n    {e}")
        sys.exit(1)

    size_mb = Path(result).stat().st_size / 1_048_576
    print(f"\n✅  Clip saved!  {result}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

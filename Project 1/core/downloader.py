"""
Clip Downloader
---------------
Routes downloads based on StreamType:

  DIRECT / HLS / DASH  ->  FFmpeg handles it directly.
                            HLS/DASH: FFmpeg reads the manifest and fetches
                            only the segments that overlap the time range.
                            DIRECT: FFmpeg uses HTTP byte-range requests.

  PLATFORM             ->  yt-dlp --download-sections "*start-end"
                            yt-dlp handles all auth, cookies, signed URLs.
                            FFmpeg is called by yt-dlp as a post-processor.
"""

import subprocess
from pathlib import Path
from typing import Callable, Optional

from .detector import StreamInfo, StreamType


OutputFormat = str  # "mp4" | "mp3" | "mkv"


def download_clip(
    stream: StreamInfo,
    start: float,
    end: float,
    output_path: str,
    output_format: OutputFormat = "mp4",
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Download the clip [start, end] seconds and save to output_path.
    Calls on_progress(percent, message) periodically.
    Returns the final output path.
    """
    duration = end - start
    output_path = _ensure_extension(output_path, output_format)

    if on_progress:
        on_progress(0.0, "Starting download...")

    if stream.stream_type == StreamType.PLATFORM:
        _download_via_ytdlp(stream, start, end, output_path, output_format, on_progress)
    else:
        cmd = _build_ffmpeg_cmd(stream, start, end, output_path, output_format)
        _run_ffmpeg(cmd, duration, on_progress)

    if not Path(output_path).exists():
        raise RuntimeError(
            "Output file was not created.\n"
            "Check that the URL is accessible and the timestamps are valid."
        )

    if on_progress:
        on_progress(100.0, "Done!")

    return output_path


# ── yt-dlp path (platforms: YouTube, Instagram, Vimeo, etc.) ─────────────────

def _download_via_ytdlp(
    stream: StreamInfo,
    start: float,
    end: float,
    output_path: str,
    fmt: OutputFormat,
    on_progress: Optional[Callable[[float, str], None]],
) -> None:
    """
    Use yt-dlp's --download-sections to fetch only the clip range.
    yt-dlp handles authentication and calls FFmpeg internally for trimming.
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed. Run: pip install yt-dlp")

    if on_progress:
        on_progress(5.0, "Connecting to platform...")

    # Output template without extension - yt-dlp adds it
    out_stem = str(Path(output_path).with_suffix(""))

    # FFmpeg args passed to yt-dlp's post-processor
    if fmt == "mp3":
        pp_args = ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]
    elif fmt == "mp4":
        pp_args = ["-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart"]
    else:
        pp_args = ["-c", "copy"]

    class ProgressHook:
        def __call__(self, d):
            if not on_progress:
                return
            status = d.get("status", "")
            if status == "downloading":
                pct_str = d.get("_percent_str", "0%").strip().rstrip("%")
                try:
                    raw = float(pct_str)
                    pct = 5 + raw * 0.88   # scale into 5-93%
                    speed = d.get("_speed_str", "").strip()
                    eta   = d.get("_eta_str", "").strip()
                    msg   = f"Downloading... {speed}"
                    if eta:
                        msg += f"  ETA {eta}"
                    on_progress(pct, msg)
                except (ValueError, TypeError):
                    pass
            elif status == "finished":
                on_progress(94.0, "Processing clip...")

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": out_stem + ".%(ext)s",
        "download_sections": [{"start_time": start, "end_time": end}],
        "force_keyframes_at_cuts": True,
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": fmt,
            }
        ],
        "postprocessor_args": {
            "ffmpegvideoconvertor": pp_args,
        },
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [ProgressHook()],
        "noprogress": False,
    }

    url = stream.original_url or stream.url

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(
                f"Download failed: {e}\n\n"
                "For Instagram/Facebook, you may need to provide login cookies.\n"
                "See: https://github.com/yt-dlp/yt-dlp#cookies"
            )

    # yt-dlp may name the file with a different extension - find and rename it
    _find_and_rename(out_stem, fmt, output_path)


def _find_and_rename(out_stem: str, fmt: str, target: str) -> None:
    """Locate the file yt-dlp created and move it to the expected path."""
    parent = Path(out_stem).parent
    stem   = Path(out_stem).name
    known_exts = {"mp4", "mp3", "mkv", "webm", "m4a", "mov"}

    # First look for exact format match, then any video/audio file
    for ext in [fmt] + list(known_exts - {fmt}):
        candidates = list(parent.glob(f"{stem}*.{ext}"))
        if candidates:
            best = candidates[0]
            if str(best) != target:
                best.rename(target)
            return


# ── FFmpeg path (direct files, HLS, DASH) ────────────────────────────────────

def _build_ffmpeg_cmd(
    stream: StreamInfo,
    start: float,
    end: float,
    output_path: str,
    fmt: OutputFormat,
) -> list:
    """Build FFmpeg command for DIRECT / HLS / DASH streams."""

    cmd = ["ffmpeg", "-y"]

    # -user_agent must be an input option (before -i)
    cmd += ["-user_agent", "Mozilla/5.0"]

    # Seek strategy:
    #   DIRECT: seek before -i (fast, uses byte-range requests)
    #   HLS/DASH: seek after -i (must read manifest first)
    if stream.stream_type == StreamType.DIRECT:
        cmd += ["-ss", str(start), "-to", str(end)]
        cmd += ["-i", stream.url]
    else:
        cmd += ["-i", stream.url]
        cmd += ["-ss", str(start), "-to", str(end)]

    if fmt == "mp3":
        cmd += ["-vn", "-acodec", "libmp3lame", "-q:a", "2"]
    elif fmt == "mp4":
        cmd += ["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart"]
    else:
        cmd += ["-c", "copy"]

    cmd += ["-progress", "pipe:2", "-nostats"]
    cmd.append(output_path)
    return cmd


def _run_ffmpeg(
    cmd: list,
    total_duration: float,
    on_progress: Optional[Callable[[float, str], None]],
) -> None:
    """Run FFmpeg, parse progress output, raise on failure."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    current_time = 0.0
    error_lines = []

    try:
        for line in proc.stderr:
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    current_time = int(line.split("=")[1]) / 1_000_000
                except (ValueError, IndexError):
                    pass
            elif line.startswith("progress="):
                if on_progress:
                    pct = min(99.0, (current_time / total_duration) * 100) if total_duration > 0 else 0
                    if line.split("=")[1] == "end":
                        on_progress(99.0, "Finalising...")
                    else:
                        on_progress(pct, f"Downloading... {_fmt_time(current_time)} / {_fmt_time(total_duration)}")
            elif any(w in line for w in ("Error", "Invalid", "failed", "No such")):
                error_lines.append(line)
    finally:
        proc.wait()

    if proc.returncode != 0:
        details = "\n".join(error_lines) or "No details captured."
        raise RuntimeError(
            f"FFmpeg failed (exit code {proc.returncode}).\n"
            f"Details: {details}\n"
            f"Command: {' '.join(str(c) for c in cmd)}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_extension(path: str, fmt: str) -> str:
    p = Path(path)
    if p.suffix.lower().lstrip(".") != fmt:
        p = p.with_suffix(f".{fmt}")
    return str(p)


def _fmt_time(secs: float) -> str:
    secs = max(0.0, secs)
    m = int(secs // 60)
    s = secs % 60
    return f"{m}:{s:04.1f}"
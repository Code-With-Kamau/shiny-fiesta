"""
Stream Detector
---------------
Given a URL, figures out what kind of media it is and returns
a StreamInfo describing how to download it.

Decision tree:
  1. Known platform hostname                   -> StreamType.PLATFORM
  2. Direct file extension (.mp4, .mp3, etc.)  -> StreamType.DIRECT
  3. HLS manifest (.m3u8 in URL)               -> StreamType.HLS
  4. DASH manifest (.mpd in URL)               -> StreamType.DASH
  5. HEAD request sniff (Content-Type header)  -> DIRECT / HLS / DASH
  6. Anything else -> try yt-dlp               -> StreamType.PLATFORM

For PLATFORM streams the original URL is always preserved.
The downloader uses yt-dlp --download-sections directly so it
handles all auth, cookies, and CDN complexity itself.
"""

import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class StreamType(Enum):
    DIRECT   = "direct"    # Plain file URL - FFmpeg can open directly
    HLS      = "hls"       # HLS .m3u8 manifest - FFmpeg handles segments
    DASH     = "dash"      # DASH .mpd manifest - FFmpeg handles segments
    PLATFORM = "platform"  # Social/video platform - must use yt-dlp end-to-end


@dataclass
class StreamInfo:
    url: str                            # URL to use (original for PLATFORM)
    stream_type: StreamType
    original_url: str = ""              # Always the user-supplied URL
    title: str = "clip"
    duration: Optional[float] = None   # Total video length in seconds
    format_id: Optional[str] = None


# Hostnames that must go through yt-dlp
PLATFORM_HOSTNAMES = {
    "youtube.com", "youtu.be",
    "instagram.com", "instagr.am",
    "vimeo.com",
    "twitter.com", "x.com",
    "tiktok.com",
    "facebook.com", "fb.watch",
    "dailymotion.com",
    "twitch.tv",
    "reddit.com",
    "streamable.com",
    "bilibili.com",
}

DIRECT_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov",
    ".mp3", ".m4a", ".flac", ".wav", ".ogg",
}


def detect(url: str, prefer_quality: str = "best") -> StreamInfo:
    """
    Inspect a URL and return a StreamInfo.
    Raises RuntimeError if the stream cannot be identified.
    """
    url = url.strip()
    original = url

    # 1. Known platform hostname -> always use yt-dlp, no guessing
    hostname = _hostname(url)
    if any(hostname == h or hostname.endswith("." + h) for h in PLATFORM_HOSTNAMES):
        return _info_from_ytdlp(url, prefer_quality, original)

    # 2. Direct file extension (before query string)
    path = url.split("?")[0].lower()
    if any(path.endswith(ext) for ext in DIRECT_EXTENSIONS):
        return StreamInfo(url=url, stream_type=StreamType.DIRECT, original_url=original)

    # 3. HLS manifest URL
    if ".m3u8" in url.lower():
        return StreamInfo(url=url, stream_type=StreamType.HLS, original_url=original)

    # 4. DASH manifest URL
    if ".mpd" in url.lower():
        return StreamInfo(url=url, stream_type=StreamType.DASH, original_url=original)

    # 5. HEAD request - check Content-Type
    sniffed = _sniff_content_type(url, original)
    if sniffed:
        return sniffed

    # 6. Unknown - try yt-dlp as a last resort
    return _info_from_ytdlp(url, prefer_quality, original)


def _hostname(url: str) -> str:
    """Extract bare hostname, e.g. 'www.instagram.com' -> 'instagram.com'."""
    try:
        host = url.split("//", 1)[1].split("/")[0].split("?")[0].lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except IndexError:
        return ""


def _sniff_content_type(url: str, original: str) -> Optional[StreamInfo]:
    """HEAD request to map Content-Type to a StreamType."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=8) as resp:
            ct = resp.headers.get("Content-Type", "")
    except Exception:
        return None

    if "mpegurl" in ct or "m3u8" in ct:
        return StreamInfo(url=url, stream_type=StreamType.HLS, original_url=original)
    if "dash+xml" in ct or "mpd" in ct:
        return StreamInfo(url=url, stream_type=StreamType.DASH, original_url=original)
    if any(t in ct for t in ("video/", "audio/", "octet-stream")):
        return StreamInfo(url=url, stream_type=StreamType.DIRECT, original_url=original)
    return None


def _info_from_ytdlp(url: str, prefer_quality: str, original: str) -> StreamInfo:
    """
    Extract metadata only (title, duration) via yt-dlp.
    We do NOT store the CDN URL - it expires in seconds.
    The downloader will call yt-dlp again with --download-sections.
    """
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError(
            "yt-dlp is not installed.\n"
            "Run:  pip install yt-dlp\n"
            "Required for YouTube, Instagram, and other platforms."
        )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "format": "best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(
                f"Could not access this URL.\n"
                f"Reason: {e}\n\n"
                "For Instagram/Facebook, you may need to log in via cookies.\n"
                "See: https://github.com/yt-dlp/yt-dlp#cookies"
            )

    if info is None:
        raise RuntimeError("yt-dlp returned no information for this URL.")
    if "entries" in info:
        info = info["entries"][0]

    return StreamInfo(
        url=original,           # Keep original URL - CDN URLs expire
        stream_type=StreamType.PLATFORM,
        original_url=original,
        title=info.get("title", "clip"),
        duration=info.get("duration"),
        format_id=info.get("format_id"),
    )
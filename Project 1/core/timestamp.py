"""
Timestamp Utilities
-------------------
Parse human-friendly time strings into seconds (float),
and validate that a start/end pair makes sense.

Accepted formats:
  "1:23:45"   →  5025.0  (HH:MM:SS)
  "4:30"      →  270.0   (MM:SS)
  "90.5"      →  90.5    (plain seconds)
  "1h2m3s"    →  3723.0  (verbose)
"""

import re


def parse_time(ts: str) -> float:
    """
    Convert a timestamp string to a float number of seconds.
    Raises ValueError with a helpful message on bad input.
    """
    ts = ts.strip()

    if not ts:
        raise ValueError("Timestamp cannot be empty.")

    # HH:MM:SS or MM:SS (colons)
    if ":" in ts:
        parts = ts.split(":")
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        elif len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        else:
            raise ValueError(f"Unrecognised timestamp format: '{ts}'")

    # Verbose: 1h2m3s, 2m30s, 45s
    verbose = re.fullmatch(
        r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?",
        ts, re.IGNORECASE
    )
    if verbose and ts:
        h = int(verbose.group(1) or 0)
        m = int(verbose.group(2) or 0)
        s = float(verbose.group(3) or 0)
        total = h * 3600 + m * 60 + s
        if total > 0 or ts in ("0", "0s"):
            return total

    # Plain number
    try:
        return float(ts)
    except ValueError:
        pass

    raise ValueError(
        f"Cannot parse '{ts}' as a timestamp.\n"
        "Try formats like: 1:23:45 · 4:30 · 90 · 1h2m3s"
    )


def validate_time(start: float, end: float, duration: float | None = None) -> None:
    """
    Check that start < end and both are within optional total duration.
    Raises ValueError describing the problem.
    """
    if start < 0:
        raise ValueError(f"Start time ({start:.1f}s) cannot be negative.")
    if end <= start:
        raise ValueError(
            f"End time ({end:.1f}s) must be after start time ({start:.1f}s)."
        )
    if duration is not None and start >= duration:
        raise ValueError(
            f"Start time ({start:.1f}s) is past the end of the video ({duration:.1f}s)."
        )
    if duration is not None and end > duration:
        raise ValueError(
            f"End time ({end:.1f}s) exceeds video duration ({duration:.1f}s). "
            f"Set end to {duration:.1f}s or less."
        )


def format_seconds(secs: float) -> str:
    """Turn 3661.5 into '1:01:01.5' for display."""
    secs = max(0.0, secs)
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = secs % 60
    if h:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m}:{s:05.2f}"

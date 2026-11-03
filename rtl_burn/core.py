"""Core logic: make RTL subtitle lines render correctly in libass/ffmpeg.

libass lays out every subtitle line with a left-to-right base direction.
For Persian, Arabic, Urdu or Hebrew text that means sentence-final punctuation
jumps to the wrong side and mixed lines (numbers, Latin words, brackets) get
reordered. Wrapping each RTL line in RIGHT-TO-LEFT EMBEDDING (U+202B) ...
POP DIRECTIONAL FORMATTING (U+202C) forces the correct base direction.
"""

from __future__ import annotations

import re
import unicodedata

RLE = "‫"  # RIGHT-TO-LEFT EMBEDDING
LRE = "‪"  # LEFT-TO-RIGHT EMBEDDING
PDF = "‬"  # POP DIRECTIONAL FORMATTING

# Every invisible bidi control we strip before re-applying our own.
_BIDI_CONTROLS = re.compile("[‎‏‪-‮⁦-⁩]")
_ASS_TAG = re.compile(r"\{[^}]*\}")
_TIMING = re.compile(r"^\s*\d+:\d+(?::\d+)?[.,]\d+\s*-->\s*\d+:\d+(?::\d+)?[.,]\d+")

DIRECTIONS = ("auto", "rtl", "ltr")


def first_strong_direction(text: str) -> str | None:
    """Return 'rtl' or 'ltr' for the first strongly directional character, else None."""
    for ch in _ASS_TAG.sub("", text):
        bidi = unicodedata.bidirectional(ch)
        if bidi in ("R", "AL"):
            return "rtl"
        if bidi == "L":
            return "ltr"
    return None


def has_rtl(text: str) -> bool:
    """True if the text contains any right-to-left letter."""
    return any(unicodedata.bidirectional(ch) in ("R", "AL") for ch in _ASS_TAG.sub("", text))


def strip_bidi_controls(text: str) -> str:
    return _BIDI_CONTROLS.sub("", text)


def _wrap(text: str, rtl: bool) -> str:
    if not text.strip():
        return text
    start, end = (RLE, PDF) if rtl else (LRE, PDF)
    # Keep leading ASS override tags (e.g. {\an8}) outside the embedding.
    m = re.match(r"^((?:\{[^}]*\})*)(.*)$", text, re.S)
    tags, body = m.group(1), m.group(2)
    return f"{tags}{start}{body}{end}"


def fix_line(text: str, direction: str = "auto") -> str:
    """Fix one visual subtitle line.

    auto: a line that contains RTL letters gets an RTL base direction.
    rtl:  every non-empty line is forced RTL.
    ltr:  only strips stray bidi controls (useful to undo a previous fix).
    """
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}")
    clean = strip_bidi_controls(text)
    if direction == "ltr":
        return clean
    if direction == "rtl" or has_rtl(clean):
        return _wrap(clean, rtl=True)
    return clean


def fix_text_block(text: str, direction: str = "auto", newline: str = "\n") -> str:
    """Fix a cue that may span several lines (each line gets its own embedding)."""
    return newline.join(fix_line(part, direction) for part in text.split(newline))


def fix_srt(content: str, direction: str = "auto") -> str:
    """Fix every text line of an SRT (or WebVTT) document, leaving numbers/timings alone."""
    out = []
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_index = stripped.isdigit() and i + 1 < len(lines) and _TIMING.match(lines[i + 1])
        is_header = i == 0 and stripped.upper().startswith("WEBVTT")
        if not stripped or is_index or is_header or _TIMING.match(line) or stripped.startswith("NOTE"):
            out.append(line)
        else:
            out.append(fix_line(line, direction))
    return "\n".join(out)


def fix_ass(content: str, direction: str = "auto") -> str:
    """Fix the Text field of every Dialogue line in an ASS/SSA script."""
    out = []
    fmt_fields: list[str] | None = None
    in_events = False
    for line in content.replace("\r\n", "\n").split("\n"):
        low = line.strip().lower()
        if low.startswith("[") and low.endswith("]"):
            in_events = low == "[events]"
        elif in_events and low.startswith("format:"):
            fmt_fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
        elif in_events and low.startswith("dialogue:"):
            n = len(fmt_fields) if fmt_fields else 10
            prefix, rest = line.split(":", 1)
            parts = rest.split(",", n - 1)
            if len(parts) == n:
                parts[-1] = fix_text_block(parts[-1], direction, newline="\\N")
                line = prefix + ":" + ",".join(parts)
        out.append(line)
    return "\n".join(out)


def fix_subtitles(content: str, fmt: str, direction: str = "auto") -> str:
    fmt = fmt.lower().lstrip(".")
    if fmt in ("ass", "ssa"):
        return fix_ass(content, direction)
    if fmt in ("srt", "vtt"):
        return fix_srt(content, direction)
    raise ValueError(f"unsupported subtitle format: {fmt}")

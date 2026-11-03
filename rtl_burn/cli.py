"""Command line interface for rtl-burn."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .core import DIRECTIONS, fix_subtitles

SUPPORTED = (".srt", ".vtt", ".ass", ".ssa")


def _escape_filter_value(value: str) -> str:
    """Escape a value for use inside an ffmpeg filtergraph option."""
    for ch in ("\\", ":", "'", ",", "[", "]", ";"):
        value = value.replace(ch, "\\" + ch)
    return value


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1256"):  # cp1256 = legacy Windows Arabic/Persian
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def build_filter(subs: Path, font: str | None, fonts_dir: Path | None, size: int | None,
                 style: str | None) -> str:
    opts = [f"filename='{_escape_filter_value(str(subs))}'"]
    if fonts_dir:
        opts.append(f"fontsdir='{_escape_filter_value(str(fonts_dir))}'")
    force = []
    if font:
        force.append(f"FontName={font}")
    if size:
        force.append(f"FontSize={size}")
    if style:
        force.append(style)
    if force and subs.suffix.lower() not in (".ass", ".ssa"):
        opts.append(f"force_style='{_escape_filter_value(','.join(force))}'")
    return "subtitles=" + ":".join(opts)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="rtl-burn",
        description="Burn Persian/Arabic/Urdu/Hebrew subtitles into video with correct RTL layout.",
    )
    p.add_argument("video", nargs="?", help="input video (omit with --fix-only)")
    p.add_argument("subs", help="subtitle file: .srt, .vtt, .ass or .ssa")
    p.add_argument("-o", "--output", help="output video (default: <video>.rtl.mp4)")
    p.add_argument("--fix-only", metavar="OUT", help="only write a fixed subtitle file, no burning")
    p.add_argument("--direction", choices=DIRECTIONS, default="auto",
                   help="auto: fix lines containing RTL letters (default); rtl: force every line")
    p.add_argument("--font", help="font family name, e.g. Vazirmatn or 'Noto Naskh Arabic'")
    p.add_argument("--fonts-dir", type=Path, help="folder with .ttf/.otf files to use")
    p.add_argument("--size", type=int, help="font size (SRT/VTT only)")
    p.add_argument("--style", help="extra ASS style, e.g. 'Outline=2,PrimaryColour=&H00FFFFFF'")
    p.add_argument("--crf", type=int, default=20, help="H.264 quality, lower is better (default 20)")
    p.add_argument("--preset", default="veryfast", help="x264 preset (default veryfast)")
    p.add_argument("--preview", type=float, metavar="SEC",
                   help="write a single PNG frame at SEC instead of the whole video")
    p.add_argument("--dry-run", action="store_true", help="print the ffmpeg command and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    if not args.fix_only and not args.video:
        p.error("a video is required unless --fix-only is used")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    subs = Path(args.subs)
    if subs.suffix.lower() not in SUPPORTED:
        print(f"rtl-burn: unsupported subtitle type {subs.suffix!r}; use {', '.join(SUPPORTED)}",
              file=sys.stderr)
        return 2
    if not subs.is_file():
        print(f"rtl-burn: subtitle file not found: {subs}", file=sys.stderr)
        return 2

    fixed = fix_subtitles(_read_text(subs), subs.suffix, args.direction)

    if args.fix_only:
        Path(args.fix_only).write_text(fixed, encoding="utf-8")
        print(f"wrote {args.fix_only}")
        return 0

    video = Path(args.video)
    if not video.is_file():
        print(f"rtl-burn: video not found: {video}", file=sys.stderr)
        return 2
    if not args.dry_run and shutil.which("ffmpeg") is None:
        print("rtl-burn: ffmpeg not found. Install it: https://ffmpeg.org/download.html",
              file=sys.stderr)
        return 127

    if args.preview is not None:
        output = Path(args.output or video.with_suffix(".preview.png"))
    else:
        output = Path(args.output or video.with_name(video.stem + ".rtl.mp4"))

    with tempfile.TemporaryDirectory(prefix="rtl-burn-") as tmp:
        tmp_subs = Path(tmp) / ("subs" + subs.suffix.lower())
        tmp_subs.write_text(fixed, encoding="utf-8")
        vf = build_filter(tmp_subs, args.font, args.fonts_dir, args.size, args.style)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats", "-y"]
        if args.preview is not None:
            cmd += ["-ss", str(args.preview), "-copyts", "-i", str(video), "-vf", vf,
                    "-frames:v", "1", "-update", "1", str(output)]
        else:
            cmd += ["-i", str(video), "-vf", vf, "-c:v", "libx264", "-crf", str(args.crf),
                    "-preset", args.preset, "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-movflags", "+faststart", str(output)]
        if args.dry_run:
            print(" ".join(cmd))
            return 0
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("rtl-burn: ffmpeg failed (see output above)", file=sys.stderr)
            return result.returncode
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

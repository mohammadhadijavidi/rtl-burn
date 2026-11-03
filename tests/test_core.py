import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from rtl_burn.core import PDF, RLE, fix_ass, fix_line, fix_srt, first_strong_direction, has_rtl

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_detects_rtl_scripts():
    assert has_rtl("سلام")          # Persian
    assert has_rtl("مرحبا")         # Arabic
    assert has_rtl("שלום")          # Hebrew
    assert not has_rtl("Hello 2.5")
    assert first_strong_direction("2.5 سلام") == "rtl"
    assert first_strong_direction("Hi سلام") == "ltr"


def test_rtl_line_is_wrapped():
    assert fix_line("سلام دنیا.") == f"{RLE}سلام دنیا.{PDF}"


def test_mixed_line_starting_with_latin_is_still_rtl():
    assert fix_line("USD قیمت امروز").startswith(RLE)


def test_ltr_line_untouched():
    assert fix_line("Hello, world!") == "Hello, world!"


def test_idempotent():
    once = fix_line("سلام دنیا.")
    assert fix_line(once) == once


def test_ltr_mode_strips_controls():
    assert fix_line(f"{RLE}سلام{PDF}", "ltr") == "سلام"


def test_force_rtl():
    assert fix_line("Hello", "rtl") == f"{RLE}Hello{PDF}"


def test_leading_ass_tags_stay_outside():
    assert fix_line(r"{\an8}سلام") == r"{\an8}" + f"{RLE}سلام{PDF}"


def test_srt_keeps_index_and_timing():
    src = "1\n00:00:00,000 --> 00:00:02,000\nسلام.\nHello\n\n2\n00:00:02,000 --> 00:00:04,000\n12\n"
    out = fix_srt(src).split("\n")
    assert out[0] == "1"
    assert out[1] == "00:00:00,000 --> 00:00:02,000"
    assert out[2] == f"{RLE}سلام.{PDF}"
    assert out[3] == "Hello"
    assert out[5] == "2"
    assert out[7] == "12"  # a cue whose text is a number is not treated as an index


def test_vtt_header_kept():
    src = "WEBVTT\n\n00:00.000 --> 00:02.000\nسلام\n"
    out = fix_srt(src).split("\n")
    assert out[0] == "WEBVTT"
    assert out[2] == "00:00.000 --> 00:02.000"
    assert out[3] == f"{RLE}سلام{PDF}"


def test_ass_dialogue_text_only_with_commas():
    src = (
        "[Script Info]\nTitle: x\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,سلام، دنیا.\\Nخط دوم\n"
    )
    line = fix_ass(src).split("\n")[-2]
    assert line.startswith("Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,")
    text = line.split(",,0,0,0,,", 1)[1]
    assert text == f"{RLE}سلام، دنیا.{PDF}\\N{RLE}خط دوم{PDF}"


def test_cli_fix_only(tmp_path):
    out = tmp_path / "out.srt"
    r = subprocess.run([sys.executable, "-m", "rtl_burn", str(EXAMPLES / "fa.srt"),
                        "--fix-only", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert RLE in out.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_cli_burns_video(tmp_path):
    video = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=320x180:d=2", "-pix_fmt", "yuv420p", str(video)], check=True)
    out = tmp_path / "out.mp4"
    r = subprocess.run([sys.executable, "-m", "rtl_burn", str(video), str(EXAMPLES / "fa.srt"),
                        "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.stat().st_size > 0

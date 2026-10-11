import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from subslide import (
    build_parser,
    ms_to_timecode,
    parse_srt,
    parse_srt_timecode,
    parse_timestamp,
    serialize_srt,
    shift_blocks,
)

# --- parse_timestamp ---


def test_parse_timestamp_hh_mm():
    assert parse_timestamp("00:10") == 10 * 60_000


def test_parse_timestamp_hh_mm_nonzero():
    assert parse_timestamp("01:30") == 90 * 60_000


def test_parse_timestamp_hh_mm_ss():
    assert parse_timestamp("01:00:00") == 3_600_000


def test_parse_timestamp_full_comma():
    assert parse_timestamp("00:10:30,500") == 10 * 60_000 + 30_000 + 500


def test_parse_timestamp_full_dot():
    assert parse_timestamp("00:10:30.500") == 10 * 60_000 + 30_000 + 500


def test_parse_timestamp_invalid():
    with pytest.raises(ValueError, match="Unrecognized timestamp"):
        parse_timestamp("invalid")


def test_parse_timestamp_plain_seconds_rejected():
    with pytest.raises(ValueError, match="Unrecognized timestamp"):
        parse_timestamp("630")


# --- ms_to_timecode ---


def test_ms_to_timecode_basic():
    assert ms_to_timecode(3_723_500) == "01:02:03,500"


def test_ms_to_timecode_zero():
    assert ms_to_timecode(0) == "00:00:00,000"


def test_ms_to_timecode_clamps_negative():
    assert ms_to_timecode(-100) == "00:00:00,000"


def test_ms_to_timecode_max_ms():
    assert ms_to_timecode(999) == "00:00:00,999"


# --- parse_srt_timecode ---


def test_parse_srt_timecode():
    start, end = parse_srt_timecode("00:03:43,599 --> 00:03:45,350")
    assert start == 3 * 60_000 + 43_000 + 599
    assert end == 3 * 60_000 + 45_000 + 350


def test_parse_srt_timecode_invalid():
    with pytest.raises(ValueError, match="Invalid timecode"):
        parse_srt_timecode("not a timecode")


# --- parse_srt ---

SRT_SAMPLE = """\
1
00:03:43,599 --> 00:03:45,350
Hola.

2
00:03:45,392 --> 00:03:46,393
¿Cómo estás?

3
00:05:14,523 --> 00:05:17,317
Buenos días.
Esto es una prueba.
"""


def test_parse_srt_count():
    blocks = parse_srt(SRT_SAMPLE)
    assert len(blocks) == 3


def test_parse_srt_first_block():
    blocks = parse_srt(SRT_SAMPLE)
    b = blocks[0]
    assert b.index == 1
    assert b.start_ms == 3 * 60_000 + 43_000 + 599
    assert b.end_ms == 3 * 60_000 + 45_000 + 350
    assert b.lines == ["Hola."]


def test_parse_srt_multiline_text():
    blocks = parse_srt(SRT_SAMPLE)
    b = blocks[2]
    assert b.lines == ["Buenos días.", "Esto es una prueba."]


def test_parse_srt_empty_string():
    assert parse_srt("") == []


def test_parse_srt_invalid_timecode():
    bad = "1\nnot a timecode\nText\n"
    with pytest.raises(ValueError, match="block 1"):
        parse_srt(bad)


# --- serialize_srt ---


def test_serialize_srt_roundtrip():
    blocks = parse_srt(SRT_SAMPLE)
    result = serialize_srt(blocks)
    assert "00:03:43,599 --> 00:03:45,350" in result
    assert "Hola." in result
    assert "¿Cómo estás?" in result


def test_serialize_srt_multiline():
    blocks = parse_srt(SRT_SAMPLE)
    result = serialize_srt(blocks)
    assert "Buenos días.\nEsto es una prueba." in result


def test_serialize_srt_blank_line_between_blocks():
    blocks = parse_srt(SRT_SAMPLE)
    result = serialize_srt(blocks)
    # Blocks separated by exactly one blank line
    assert "\n\n" in result
    assert "\n\n\n" not in result


def test_serialize_srt_ends_with_newline():
    blocks = parse_srt(SRT_SAMPLE)
    result = serialize_srt(blocks)
    assert result.endswith("\n")


# --- shift_blocks ---
# SRT_SAMPLE block start times (ms):
#   block 0: start=223599, end=225350
#   block 1: start=225392, end=226393
#   block 2: start=314523, end=317317


def test_shift_all_delay():
    blocks = parse_srt(SRT_SAMPLE)
    result = shift_blocks(blocks, delta_ms=1_500, from_ms=None, to_ms=None)
    assert result[0].start_ms == 223_599 + 1_500
    assert result[0].end_ms == 225_350 + 1_500
    assert result[2].start_ms == 314_523 + 1_500


def test_shift_all_advance():
    blocks = parse_srt(SRT_SAMPLE)
    result = shift_blocks(blocks, delta_ms=-500, from_ms=None, to_ms=None)
    assert result[0].start_ms == 223_599 - 500


def test_shift_from_filters_earlier_blocks():
    blocks = parse_srt(SRT_SAMPLE)
    # from 5:14 — only block 2 matches
    result = shift_blocks(blocks, delta_ms=1_000, from_ms=314_523, to_ms=None)
    assert result[0].start_ms == 223_599  # unchanged
    assert result[1].start_ms == 225_392  # unchanged
    assert result[2].start_ms == 314_523 + 1_000  # shifted


def test_shift_to_filters_later_blocks():
    blocks = parse_srt(SRT_SAMPLE)
    # to 3:44 — only block 0 matches
    result = shift_blocks(blocks, delta_ms=1_000, from_ms=None, to_ms=224_000)
    assert result[0].start_ms == 223_599 + 1_000  # shifted
    assert result[1].start_ms == 225_392  # unchanged


def test_shift_range_filters():
    blocks = parse_srt(SRT_SAMPLE)
    # from 3:45 to 3:46 — only block 1 matches
    result = shift_blocks(blocks, delta_ms=2_000, from_ms=225_000, to_ms=226_000)
    assert result[0].start_ms == 223_599  # unchanged
    assert result[1].start_ms == 225_392 + 2_000  # shifted
    assert result[2].start_ms == 314_523  # unchanged


def test_shift_clamps_to_zero(capsys):
    blocks = parse_srt(SRT_SAMPLE)
    result = shift_blocks(blocks, delta_ms=-999_999, from_ms=None, to_ms=None)
    assert result[0].start_ms == 0
    assert result[0].end_ms == 0
    captured = capsys.readouterr()
    assert "clamped" in captured.err


def test_shift_clamp_warning_printed_once(capsys):
    blocks = parse_srt(SRT_SAMPLE)
    shift_blocks(blocks, delta_ms=-999_999, from_ms=None, to_ms=None)
    captured = capsys.readouterr()
    assert captured.err.count("clamped") == 1


# --- build_parser ---


def test_parser_delay():
    p = build_parser()
    args = p.parse_args(["--delay", "1.5", "movie.srt"])
    assert args.delay == 1.5
    assert args.advance is None
    assert args.file == "movie.srt"


def test_parser_advance_short():
    p = build_parser()
    args = p.parse_args(["-a", "0.5", "movie.srt"])
    assert args.advance == 0.5


def test_parser_from_to():
    p = build_parser()
    args = p.parse_args(["-d", "1", "-f", "00:10", "-t", "00:20", "movie.srt"])
    assert args.from_ts == "00:10"
    assert args.to_ts == "00:20"


def test_parser_in_place():
    p = build_parser()
    args = p.parse_args(["-d", "1", "-i", "movie.srt"])
    assert args.in_place is True


def test_parser_defaults():
    p = build_parser()
    args = p.parse_args(["-d", "1", "movie.srt"])
    assert args.from_ts is None
    assert args.to_ts is None
    assert args.in_place is False


# --- main: in-place failure handling ---


def test_in_place_failed_backup_copy_keeps_original(tmp_path, monkeypatch):
    import shutil

    import subslide

    src = tmp_path / "movie.srt"
    bkp = tmp_path / "movie.srt.bkp"
    original = "1\n00:00:01,000 --> 00:00:02,000\nHi\n"
    src.write_text(original, encoding="utf-8")
    bkp.write_text("STALE BACKUP", encoding="utf-8")

    real_copy2 = shutil.copy2

    def failing_copy2(s, d, *a, **kw):
        if Path(d) == bkp:
            raise OSError("disk full")
        return real_copy2(s, d, *a, **kw)

    monkeypatch.setattr(subslide.shutil, "copy2", failing_copy2)
    monkeypatch.setattr("builtins.input", lambda _="": "y")
    monkeypatch.setattr(sys, "argv", ["subslide", "-d", "1", "-i", str(src)])

    with pytest.raises(SystemExit) as exc:
        subslide.main()

    assert exc.value.code == 1
    assert src.read_text(encoding="utf-8") == original


# --- parse_srt: block separators ---


def test_parse_srt_whitespace_only_separator_splits_blocks():
    text = (
        "1\n00:00:01,000 --> 00:00:02,000\nHi\n"
        " \t\n"
        "2\n00:00:03,000 --> 00:00:04,000\nYo\n"
    )
    blocks = parse_srt(text)
    assert [b.index for b in blocks] == [1, 2]
    assert blocks[1].start_ms == 3_000
    assert blocks[0].lines == ["Hi"]


# --- timecode variants ---


def test_parse_srt_timecode_accepts_dot_separator():
    start, end = parse_srt_timecode("00:00:01.500 --> 00:00:02.250")
    assert (start, end) == (1_500, 2_250)


def test_parse_srt_timecode_accepts_trailing_coordinates():
    start, end = parse_srt_timecode(
        "00:00:01,000 --> 00:00:02,000 X1:10 X2:20 Y1:30 Y2:40"
    )
    assert (start, end) == (1_000, 2_000)


def test_parse_srt_preserves_trailing_coordinates_on_serialize():
    text = "1\n00:00:01,000 --> 00:00:02,000 X1:10 X2:20 Y1:30 Y2:40\nHi\n"
    out = serialize_srt(shift_blocks(parse_srt(text), 1_000, None, None))
    assert "00:00:02,000 --> 00:00:03,000 X1:10 X2:20 Y1:30 Y2:40\nHi" in out

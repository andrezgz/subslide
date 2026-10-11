import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "subslide.py"
FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = FIXTURES / "sample.srt"  # first sub at 00:03:43,599
SAMPLE_FILES = sorted(FIXTURES.glob("*.srt"))


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        input=stdin,
        check=False,
    )


# ── stdout output ─────────────────────────────────────────────────────────────


def test_stdout_output():
    r = run("--delay", "1.5", str(SAMPLE))
    assert r.returncode == 0
    assert "-->" in r.stdout
    assert r.stderr == ""


def test_delay_shifts_time():
    r = run("--delay", "60", str(SAMPLE))
    assert r.returncode == 0
    assert "00:04:43,599" in r.stdout  # 00:03:43,599 + 60s


def test_advance_shifts_time():
    r = run("--advance", "10", str(SAMPLE))
    assert r.returncode == 0
    assert "00:03:33,599" in r.stdout  # 00:03:43,599 - 10s


def test_from_filter_leaves_earlier_subtitles_unchanged():
    r = run("--delay", "60", "--from", "00:10", str(SAMPLE))
    assert r.returncode == 0
    assert "00:03:43,599" in r.stdout  # before 00:10, must not shift


def test_hh_mm_timestamp_format():
    r = run("--delay", "60", "--from", "00:05", "--to", "00:15", str(SAMPLE))
    assert r.returncode == 0


# ── all fixture files parse without error ─────────────────────────────────────


@pytest.mark.parametrize("srt", SAMPLE_FILES, ids=lambda p: p.name)
def test_all_fixture_files(srt: Path):
    r = run("--delay", "1.5", str(srt))
    assert r.returncode == 0
    assert "-->" in r.stdout


# ── latin-1 encoding fallback ─────────────────────────────────────────────────


def test_latin1_encoding_fallback(tmp_path):
    srt = tmp_path / "latin1.srt"
    content = "1\n00:01:00,000 --> 00:01:02,000\nH\xe9ros.\n"
    srt.write_bytes(content.encode("latin-1"))
    r = run("--delay", "1", str(srt))
    assert r.returncode == 0
    assert "-->" in r.stdout


# ── --in-place ────────────────────────────────────────────────────────────────


def test_in_place_creates_backup(tmp_path):
    src = tmp_path / "test.srt"
    shutil.copy(SAMPLE, src)
    r = run("--delay", "60", "--in-place", str(src))
    assert r.returncode == 0
    assert r.stdout == ""
    assert (tmp_path / "test.srt.bkp").exists()


def test_in_place_modifies_file(tmp_path):
    src = tmp_path / "test.srt"
    shutil.copy(SAMPLE, src)
    run("--delay", "60", "--in-place", str(src))
    assert "00:04:43,599" in src.read_text(encoding="utf-8")


def test_in_place_backup_preserves_original(tmp_path):
    src = tmp_path / "test.srt"
    shutil.copy(SAMPLE, src)
    run("--delay", "60", "--in-place", str(src))
    assert "00:03:43,599" in (tmp_path / "test.srt.bkp").read_text(encoding="utf-8")


def test_bkp_exists_confirm_yes(tmp_path):
    src = tmp_path / "test.srt"
    bkp = tmp_path / "test.srt.bkp"
    shutil.copy(SAMPLE, src)
    bkp.write_text("old", encoding="utf-8")
    r = run("--delay", "60", "--in-place", str(src), stdin="y\n")
    assert r.returncode == 0
    assert bkp.read_text(encoding="utf-8") != "old"


def test_bkp_exists_confirm_no(tmp_path):
    src = tmp_path / "test.srt"
    bkp = tmp_path / "test.srt.bkp"
    shutil.copy(SAMPLE, src)
    bkp.write_text("old", encoding="utf-8")
    r = run("--delay", "60", "--in-place", str(src), stdin="n\n")
    assert r.returncode == 1
    assert bkp.read_text(encoding="utf-8") == "old"


# ── error handling ────────────────────────────────────────────────────────────


def test_file_not_found():
    r = run("--delay", "1", "nonexistent.srt")
    assert r.returncode == 1
    assert "nonexistent.srt" in r.stderr


def test_from_greater_than_to():
    r = run("--delay", "1", "--from", "00:20", "--to", "00:10", str(SAMPLE))
    assert r.returncode != 0


# ── UTF-8 BOM ─────────────────────────────────────────────────────────────────

BOM_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHola\n"


def test_utf8_bom_file_is_parsed(tmp_path):
    src = tmp_path / "bom.srt"
    src.write_bytes(b"\xef\xbb\xbf" + BOM_SRT.encode("utf-8"))
    r = run("--delay", "1", str(src))
    assert r.returncode == 0, r.stderr
    assert "00:00:02,000 --> 00:00:03,000" in r.stdout


def test_utf8_bom_preserved_in_place(tmp_path):
    src = tmp_path / "bom.srt"
    src.write_bytes(b"\xef\xbb\xbf" + BOM_SRT.encode("utf-8"))
    r = run("--delay", "1", "--in-place", str(src))
    assert r.returncode == 0, r.stderr
    data = src.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert not data.startswith(b"\xef\xbb\xbf\xef\xbb\xbf")


# ── line endings ──────────────────────────────────────────────────────────────


def test_crlf_preserved_in_place(tmp_path):
    src = tmp_path / "crlf.srt"
    src.write_bytes(
        b"1\r\n00:00:01,000 --> 00:00:02,000\r\nHola\r\n\r\n"
        b"2\r\n00:00:03,000 --> 00:00:04,000\r\nChau\r\n"
    )
    r = run("--delay", "1", "--in-place", str(src))
    assert r.returncode == 0, r.stderr
    assert src.read_bytes() == (
        b"1\r\n00:00:02,000 --> 00:00:03,000\r\nHola\r\n\r\n"
        b"2\r\n00:00:04,000 --> 00:00:05,000\r\nChau\r\n"
    )


def test_lf_stays_lf_in_place(tmp_path):
    src = tmp_path / "lf.srt"
    src.write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\nHola\n")
    r = run("--delay", "1", "--in-place", str(src))
    assert r.returncode == 0, r.stderr
    assert b"\r" not in src.read_bytes()


# ── non-finite SECONDS ────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_non_finite_seconds_rejected(value):
    r = run("--delay", value, str(SAMPLE))
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert "SECONDS" in r.stderr


# ── non-interactive overwrite prompt ──────────────────────────────────────────


def test_bkp_exists_closed_stdin_aborts_cleanly(tmp_path):
    src = tmp_path / "test.srt"
    bkp = tmp_path / "test.srt.bkp"
    shutil.copy(SAMPLE, src)
    bkp.write_text("old", encoding="utf-8")
    r = run("--delay", "1", "--in-place", str(src), stdin="")
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "Aborted" in r.stderr
    assert bkp.read_text(encoding="utf-8") == "old"


def test_bkp_prompt_goes_to_stderr(tmp_path):
    src = tmp_path / "test.srt"
    bkp = tmp_path / "test.srt.bkp"
    shutil.copy(SAMPLE, src)
    bkp.write_text("old", encoding="utf-8")
    r = run("--delay", "1", "--in-place", str(src), stdin="n\n")
    assert "Overwrite?" not in r.stdout


# ── unsupported encodings ─────────────────────────────────────────────────────


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-be"])
def test_utf16_file_reports_unsupported_encoding(tmp_path, encoding):
    src = tmp_path / "u16.srt"
    content = "﻿1\n00:00:01,000 --> 00:00:02,000\nHola\n"
    src.write_bytes(content.encode(encoding))
    r = run("--delay", "1", str(src))
    assert r.returncode == 1
    assert "UTF-16" in r.stderr
    assert "Malformed" not in r.stderr

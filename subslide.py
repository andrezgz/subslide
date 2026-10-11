#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    index: int
    start_ms: int
    end_ms: int
    lines: list[str]
    extra: str = ""  # text after the end timecode, e.g. X1:.. Y1:.. coordinates


_TIMECODE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})(?:\s+(\S.*))?"
)


def _parse_timecode_line(s: str) -> tuple[int, int, str]:
    m = _TIMECODE_RE.fullmatch(s.strip())
    if not m:
        raise ValueError(f"Invalid timecode: {s!r}")
    h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups()[:8])
    start = h1 * 3_600_000 + m1 * 60_000 + s1 * 1_000 + ms1
    end = h2 * 3_600_000 + m2 * 60_000 + s2 * 1_000 + ms2
    return start, end, m.group(9) or ""


def parse_srt_timecode(s: str) -> tuple[int, int]:
    start, end, _ = _parse_timecode_line(s)
    return start, end


def parse_timestamp(s: str) -> int:
    """Parse user-supplied --from/--to timestamp to milliseconds."""
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})", s)
    if m:
        h, mn, sc, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
        return h * 3_600_000 + mn * 60_000 + sc * 1_000 + ms
    m = re.fullmatch(r"(\d+):(\d{2}):(\d{2})", s)
    if m:
        h, mn, sc = int(m[1]), int(m[2]), int(m[3])
        return h * 3_600_000 + mn * 60_000 + sc * 1_000
    m = re.fullmatch(r"(\d+):(\d{2})", s)
    if m:
        h, mn = int(m[1]), int(m[2])
        return h * 3_600_000 + mn * 60_000
    raise ValueError(f"Unrecognized timestamp format: {s!r}")


def ms_to_timecode(ms: int) -> str:
    rem = max(0, ms)
    h = rem // 3_600_000
    rem %= 3_600_000
    m = rem // 60_000
    rem %= 60_000
    s = rem // 1_000
    rem %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"


def parse_srt(text: str) -> list[Block]:
    """Parse SRT format text."""
    blocks: list[Block] = []
    chunks = re.split(r"\n[ \t]*\n\s*", text.strip())
    for raw_chunk in chunks:
        chunk = raw_chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        try:
            index = int(lines[0].strip())
        except (ValueError, IndexError):
            raise ValueError(f"Malformed block index near: {lines[0]!r}") from None
        if len(lines) < 2:
            raise ValueError(f"block {index}: missing timecode line")
        try:
            start_ms, end_ms, extra = _parse_timecode_line(lines[1])
        except ValueError as exc:
            raise ValueError(f"block {index}: {exc}") from exc
        text_lines = lines[2:]
        blocks.append(
            Block(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                lines=text_lines,
                extra=extra,
            )
        )
    return blocks


def serialize_srt(blocks: list[Block]) -> str:
    """Serialize blocks to SRT format."""
    parts = []
    for b in blocks:
        tc = f"{ms_to_timecode(b.start_ms)} --> {ms_to_timecode(b.end_ms)}"
        if b.extra:
            tc += f" {b.extra}"
        parts.append(f"{b.index}\n{tc}\n" + "\n".join(b.lines))
    return "\n\n".join(parts) + "\n"


def shift_blocks(
    blocks: list[Block],
    delta_ms: int,
    from_ms: int | None,
    to_ms: int | None,
) -> list[Block]:
    """Shift blocks by delta_ms, optionally filtering by time range.

    Blocks are shifted only if their start_ms falls within [from_ms, to_ms].
    Negative timestamps are clamped to 0, with a warning printed once to stderr.
    """
    result: list[Block] = []
    warned = False
    for b in blocks:
        in_range = (from_ms is None or b.start_ms >= from_ms) and (
            to_ms is None or b.start_ms <= to_ms
        )
        if in_range:
            new_start = b.start_ms + delta_ms
            new_end = b.end_ms + delta_ms
            if (new_start < 0 or new_end < 0) and not warned:
                print(
                    "Warning: some timestamps clamped to 00:00:00,000", file=sys.stderr
                )
                warned = True
            result.append(
                Block(
                    index=b.index,
                    start_ms=max(0, new_start),
                    end_ms=max(0, new_end),
                    lines=b.lines,
                    extra=b.extra,
                )
            )
        else:
            result.append(b)
    return result


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    amount = args.delay if args.delay is not None else args.advance
    if not math.isfinite(amount) or amount <= 0:
        parser.error("SECONDS must be a positive number")

    from_ms: int | None = None
    to_ms: int | None = None
    try:
        if args.from_ts is not None:
            from_ms = parse_timestamp(args.from_ts)
        if args.to_ts is not None:
            to_ms = parse_timestamp(args.to_ts)
    except ValueError as exc:
        parser.error(str(exc))

    if from_ms is not None and to_ms is not None and from_ms > to_ms:
        parser.error("--from must be earlier than --to")

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    encoding = "utf-8"
    try:
        raw = path.read_bytes()
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            print(
                f"Error: {args.file} is UTF-16, which is not supported; "
                "convert it to UTF-8 first",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            text = raw.decode("utf-8")
            if text.startswith("﻿"):
                text = text[1:]
                encoding = "utf-8-sig"
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
            encoding = "latin-1"
    except OSError as exc:
        print(f"Error reading {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")

    try:
        blocks = parse_srt(text)
    except ValueError as exc:
        print(f"Error parsing {args.file}: {exc}", file=sys.stderr)
        sys.exit(1)

    delta_ms = round(amount * 1_000)
    if args.advance is not None:
        delta_ms = -delta_ms

    blocks = shift_blocks(blocks, delta_ms=delta_ms, from_ms=from_ms, to_ms=to_ms)
    result = serialize_srt(blocks).replace("\n", newline)

    if args.in_place:
        bkp = path.with_suffix(path.suffix + ".bkp")
        if bkp.exists():
            print(
                f"{bkp} already exists. Overwrite? [y/N] ",
                end="",
                file=sys.stderr,
                flush=True,
            )
            try:
                answer = input().strip().lower()
            except EOFError:
                answer = ""
            if answer != "y":
                print("Aborted.", file=sys.stderr)
                sys.exit(1)
        try:
            shutil.copy2(path, bkp)
        except OSError as exc:
            print(f"Error creating backup {bkp}: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            path.write_bytes(result.encode(encoding))
        except OSError as exc:
            print(f"Error writing {args.file}: {exc}", file=sys.stderr)
            shutil.copy2(bkp, path)
            sys.exit(1)
    else:
        sys.stdout.buffer.write(result.encode("utf-8"))


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="subslide",
        description="Shift subtitle timings in an SRT file.",
    )
    p.add_argument("file", metavar="FILE", help="Path to the .srt file")

    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-d",
        "--delay",
        type=float,
        metavar="SECONDS",
        help="Shift subtitles later by SECONDS",
    )
    group.add_argument(
        "-a",
        "--advance",
        type=float,
        metavar="SECONDS",
        help="Shift subtitles earlier by SECONDS",
    )

    p.add_argument(
        "-f",
        "--from",
        dest="from_ts",
        metavar="TIMESTAMP",
        help="Only shift subtitles at or after this time",
    )
    p.add_argument(
        "-t",
        "--to",
        dest="to_ts",
        metavar="TIMESTAMP",
        help="Only shift subtitles at or before this time",
    )
    p.add_argument(
        "-i",
        "--in-place",
        action="store_true",
        help="Modify the file; creates FILE.bkp before changing",
    )
    return p


if __name__ == "__main__":
    main()

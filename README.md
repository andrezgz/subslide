# subslide

Shift subtitle timings in SRT files.

## Usage

```text
subslide [OPTIONS] FILE
```

### Options

| Flag | Short | Description |
|---|---|---|
| `--delay SECONDS` | `-d` | Shift subtitles later |
| `--advance SECONDS` | `-a` | Shift subtitles earlier |
| `--from TIMESTAMP` | `-f` | Only shift subtitles at or after this time |
| `--to TIMESTAMP` | `-t` | Only shift subtitles at or before this time |
| `--in-place` | `-i` | Modify the file; creates `FILE.bkp` first |

Exactly one of `--delay` or `--advance` is required.

### Timestamp formats

`--from` and `--to` accept:

- `HH:MM` — e.g. `00:10` (10 minutes)
- `HH:MM:SS` — e.g. `01:30:00`
- `HH:MM:SS,mmm` or `HH:MM:SS.mmm` — full SRT format

## Examples

```bash
# Delay all subtitles by 1.5 seconds, print to stdout
python3 subslide.py -d 1.5 movie.srt

# Advance subtitles after the 10-minute mark, edit in place
python3 subslide.py -a 0.5 -f 00:10 -i movie.srt

# Delay only subtitles between 5 and 20 minutes
python3 subslide.py -d 2 -f 00:05 -t 00:20 movie.srt

# Pipe output to a new file
python3 subslide.py -d 1.5 movie.srt > movie.fixed.srt
```

## Output

By default, output goes to **stdout** — safe for piping or preview.

With `--in-place`, the original file is backed up as `FILE.bkp` before being overwritten.
If a `.bkp` file already exists, you will be prompted to confirm before it is overwritten.

## Encoding

Files are read as UTF-8. If that fails, latin-1 is tried automatically.
UTF-16 files are not supported and are rejected with an error.

When using `--in-place`, the file is written back as it was read: the same
encoding, the UTF-8 BOM (if any) and the original line endings (LF or CRLF) are
preserved.

Output written to **stdout** is always UTF-8, even when the input was latin-1.

## Requirements

Python 3.10+, no external dependencies.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

## License

[MIT](LICENSE)

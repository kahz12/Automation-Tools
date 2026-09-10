# CLI cookbook

`atools` is the scriptable entry point for every utility. It discovers the
installed tools, forwards arguments to the tool's own parser, and preserves a
non-zero exit status when an operation fails.

```bash
atools --list                 # list available tools
atools <tool> --help          # show one tool's options
atools --json <tool> ...      # one JSON object on stdout
atools <tool> --json ...      # equivalent spelling
```

The interactive dashboard remains available as `automation-tools`; use
`atools` in cron jobs, shell scripts and CI. Destructive commands are dry-run
by default and require an explicit `--apply`, `--aplicar` or `--delete` flag.

## One working example per tool

All paths below are examples; replace them with paths on your machine.

```bash
atools archiver create ./project --output backup.zip --apply
atools converter ./photos webp --quality 85
atools duplicate_finder ./photos --export duplicates.csv
atools env_manager scan .
atools file_type ./downloads --show-unknown
atools flac_check ~/Music --no-md5 --export flac.csv
atools image_processor ./photos --op resize --max-size 1600
atools integrity create ./backups --algorithm sha256
atools log_analyzer ./logs --keywords "ERROR,CRITICAL"
atools metadata photo.jpg --export metadata.json
atools monitor --now
atools ocr scan.png --out scan.txt
atools organizer
atools password_generator generate --length 24 --count 3
atools pdf_builder images ./scans --output scans.pdf
atools pdf_toolkit merge "one.pdf,two.pdf" merged.pdf
atools readme_generator . --out README_generado.md
atools renamer ./photos --mode patron --pattern "trip_{:03d}"
atools similar_images ./photos --threshold 8 --export similar.csv
atools space_cleaner ~/Downloads --export cleanup.json
atools summarizer report.pdf --out summary.txt
atools transcriber recording.mp3 --mode srt --out recording.srt
atools translator notes.md --lang Spanish --out notes-es.md
atools vault ./secret_docs encrypt --password-file ~/.config/atools/password
atools web_clipper https://example.com/article --out article.md
atools youtube_downloader "https://youtu.be/VIDEO_ID" --mode audio
```

Run `atools <tool> --help` before automating a command to see defaults and
tool-specific safety switches. Paths containing spaces should be quoted.

## JSON output and exit codes

Automation-friendly commands can request a stable JSON envelope:

```bash
if result=$(atools --json file_type ./downloads); then
  jq -r '.output' <<<"$result"
else
  jq -r '.error // .output' <<<"$result" >&2
fi
```

The envelope contains `tool`, `ok`, `exit_code`, and `output`; failures may
also include `error`. Human-readable output is kept as a string so scripts do
not need to parse terminal formatting. Exit code `0` means success, `1` means
the tool completed but reported a failed check, `2` means invalid CLI usage or
an unknown tool, and `130` means the operation was cancelled with Ctrl-C.


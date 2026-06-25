<div align="center">

# Automation Tools

**A unified command-line toolkit of seventeen Python utilities for everyday automation.**

File organization · PDF toolkit · AI summarization · Translation · Web clipping · Price monitoring
Image conversion & batch processing · File encryption · Password management · Metadata forensics · Disk cleanup · YouTube downloads

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Termux-lightgrey.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Made with](https://img.shields.io/badge/Made%20with-Textual%20%2B%20Gemini-purple.svg)]()

</div>

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
- [Tools Reference](#tools-reference)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [License](#license)

---

## Overview

**Automation Tools** is a collection of seventeen purpose-built Python scripts, bundled behind a single interactive menu. Every tool runs standalone from the terminal, or can be launched via the unified `automation-tools` command for a guided experience.

<table>
<tr>
<td width="50%" valign="top">

### Highlights

- **Unified entry point** — one `automation-tools` command
- **Interactive menu** — navigable with arrow keys
- **Standalone scripts** — each tool works independently
- **AI-powered** — Gemini integration for summaries, translations, and README generation
- **Safe by default** — dry-run mode on destructive operations
- **Tested** — a `pytest` suite covering every tool and the menu wiring

</td>
<td width="50%" valign="top">

### Requirements

- **Python** 3.8 or newer
- **LibreOffice** (optional, for office-to-PDF conversion)
- **Google API Key** (optional, for AI features)
- **Python deps** (bundled in `requirements.txt`) — `yt-dlp`, `Pillow`, `cryptography`, …

</td>
</tr>
</table>

---

## Installation

### Quick Install (recommended)

A single command provisions the environment and registers a global `automation-tools` launcher:

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh | bash
```

<details>
<summary><b>Inspect the script before executing (safer)</b></summary>

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh -o install.sh
less install.sh
bash install.sh
```

</details>

### Manual Installation

```bash
git clone https://github.com/kahz12/Automation-Tools.git
cd Automation-Tools

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

---

## Usage

### Interactive Menu

Launch the guided menu from anywhere:

```bash
automation-tools        # after Quick Install
python3 run.py          # from a manual checkout
```

Navigate with the arrow keys; press `Enter` to run a tool. Recently used tools appear at the top.

### Direct Invocation

Every utility is also accessible directly. See the [Tools Reference](#tools-reference) below for script paths, arguments, and examples.

---

## Tools Reference

<div align="center">

| #  | Tool                                         | Purpose                                        |
|----|----------------------------------------------|------------------------------------------------|
| 01 | [Bulk Renamer](#01--bulk-renamer)            | Rename files by pattern, date, or substitution |
| 02 | [Price Monitor](#02--price-monitor)          | Track MercadoLibre & Amazon prices             |
| 03 | [AI Summarizer](#03--ai-summarizer)          | Executive summaries via Gemini                 |
| 04 | [Downloads Organizer](#04--downloads-organizer) | Auto-sort Downloads into categories         |
| 05 | [Image Converter](#05--image-converter)      | Convert images between formats                 |
| 06 | [PDF Converter](#06--pdf-converter)          | Office documents to PDF (LibreOffice)          |
| 07 | [File Translator](#07--file-translator)      | Translate files while preserving format        |
| 08 | [Duplicate Finder](#08--duplicate-finder)    | Find identical files by MD5 hash               |
| 09 | [YouTube Downloader](#09--youtube-downloader) | Download videos or audio (MP4 / MP3)          |
| 10 | [README Generator](#10--readme-generator)    | Auto-generate project READMEs via AI           |
| 11 | [Metadata Extractor](#11--metadata-extractor) | Forensic EXIF and PDF metadata dump           |
| 12 | [Password Manager](#12--password-manager)    | Generate and evaluate passwords                |
| 13 | [Space Cleaner](#13--space-cleaner)          | Identify and reclaim disk space                |
| 14 | [PDF Toolkit](#14--pdf-toolkit)              | Merge, split, extract, rotate, encrypt PDFs    |
| 15 | [Web Clipper](#15--web-clipper)              | Save a web article as Markdown or text         |
| 16 | [Image Processor](#16--image-processor)      | Batch resize, compress, or watermark images    |
| 17 | [Encryption Vault](#17--encryption-vault)    | Encrypt / decrypt files & folders with a password |

</div>

---

### 01 — Bulk Renamer

**Script:** `src/automation_tools/tools/renamer.py`

Rename multiple files in a directory using three strategies: sequential pattern, creation date, or text replacement.

> [!NOTE]
> Runs in **dry-run** (simulation) mode by default. Add `--aplicar` to persist changes.

**Arguments**

| Option        | Description                                                           |
|---------------|-----------------------------------------------------------------------|
| `directory`   | Target directory containing the files *(required)*                    |
| `--mode`      | Rename mode: `patron`, `fecha`, or `reemplazo` *(required)*           |
| `--ext`       | Filter files by extension (e.g., `.jpg`)                              |
| `--aplicar`   | Apply changes for real                                                |

**Examples**

```bash
# Pattern — sequential numbering
python3 src/automation_tools/tools/renamer.py ./photos --mode patron --pattern "trip_{:03d}" --ext .jpg --aplicar

# Date — prepend creation date (EXIF or filesystem)
python3 src/automation_tools/tools/renamer.py ./docs --mode fecha --keep-name --aplicar

# Replacement — substitute text in filenames
python3 src/automation_tools/tools/renamer.py ./files --mode reemplazo --old-text "Copy of " --new-text "" --aplicar
```

---

### 02 — Price Monitor

**Script:** `src/automation_tools/tools/monitor.py`

Tracks prices on **MercadoLibre** and **Amazon**. Triggers console alerts (and optionally Telegram) when a product hits the target price or drops by a configured percentage.

**Configuration** — copy the template, then edit your copy (full guide in [GUIDE_CONFIG.md](GUIDE_CONFIG.md)):

```bash
cp productos_a_monitorear.example.json productos_a_monitorear.json
```

`productos_a_monitorear.json` is git-ignored, so your Telegram / MercadoLibre tokens stay out of version control.

```json
{
  "settings": {
    "currency_code": "COP",
    "decimal_separator": ".",
    "thousands_separator": ","
  },
  "products": [
    {
      "name": "Nintendo Switch",
      "url": "https://articulo.mercadolibre.com.co/MCO-XXXXXXX",
      "target_price": 1200000
    }
  ]
}
```

**Arguments**

| Option         | Description                                  |
|----------------|----------------------------------------------|
| `--now`        | Run a single check and exit                  |
| `--interval`   | Minutes between checks (default: 60)         |
| `--historial`  | Display the recorded price history           |

**Examples**

```bash
python3 src/automation_tools/tools/monitor.py --now
python3 src/automation_tools/tools/monitor.py --interval 30
python3 src/automation_tools/tools/monitor.py --historial
```

---

### 03 — AI Summarizer

**Script:** `src/automation_tools/tools/summarizer.py`

Reads a PDF or text file and produces an **executive summary with bullet points** via the Google Gemini API.

> [!IMPORTANT]
> Requires a **Google API Key**, set via the `GOOGLE_API_KEY` environment variable or a `.env` file.

**Supported formats:** `.pdf`, `.txt`, `.md`, `.py`, `.json`

**Arguments**

| Option       | Description                                         |
|--------------|-----------------------------------------------------|
| `filepath`   | Path to the PDF or TXT file *(required)*            |
| `--key`      | Google API Key (optional if set in environment)     |
| `--out`      | Save the summary to an output file                  |

**Examples**

```bash
python3 src/automation_tools/tools/summarizer.py document.pdf
python3 src/automation_tools/tools/summarizer.py report.pdf --out summary.txt
python3 src/automation_tools/tools/summarizer.py contract.pdf --key YOUR_API_KEY
```

---

### 04 — Downloads Organizer

**Script:** `src/automation_tools/tools/organizer.py`

Moves files from your **Downloads** folder into categorized subfolders by extension. Zero configuration required.

**Default categories**

| Category     | Extensions                                                        |
|--------------|-------------------------------------------------------------------|
| Images       | `.jpg` `.png` `.gif` `.bmp` `.tiff` `.webp`                       |
| Documents    | `.pdf` `.doc` `.docx` `.txt` `.xls` `.xlsx` `.ppt` `.pptx`        |
| Videos       | `.mp4` `.mov` `.avi` `.mkv` `.flv` `.wmv`                         |
| Audio        | `.mp3` `.wav` `.aac` `.flac` `.ogg`                               |
| Archives     | `.zip` `.rar` `.7z` `.tar` `.gz`                                  |
| Executables  | `.exe` `.dmg` `.app` `.deb` `.rpm`                                |
| Code         | `.py` `.js` `.html` `.css` `.json` `.xml`                         |
| Other        | Any other extension                                               |

```bash
python3 src/automation_tools/tools/organizer.py
```

> [!TIP]
> Categories are customizable — edit the `CATEGORIES` dictionary at the top of the script.

---

### 05 — Image Converter

**Script:** `src/automation_tools/tools/converter.py`

Convert images between formats. Works on **individual files** and **entire directories** (batch mode).

**Supported formats:** `jpg` · `png` · `webp` · `bmp` · `tiff` · `gif`

**Arguments**

| Option          | Description                                                     |
|-----------------|-----------------------------------------------------------------|
| `input_path`    | Path to the image file or directory *(required)*                |
| `output_format` | Target format: `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif`       |

**Examples**

```bash
python3 src/automation_tools/tools/converter.py image.png jpg
python3 src/automation_tools/tools/converter.py photo.jpg webp
python3 src/automation_tools/tools/converter.py ./folder/ png
```

> [!NOTE]
> Transparency (RGBA / P modes) is automatically flattened to RGB when exporting as JPG.

---

### 06 — PDF Converter

**Script:** `src/automation_tools/tools/converter.py`

Converts office documents (`.docx`, `.odt`, `.pptx`, and more) to **PDF** using LibreOffice in headless mode.

> [!IMPORTANT]
> Requires **LibreOffice** installed on the system.

**Arguments**

| Option        | Description                                      |
|---------------|--------------------------------------------------|
| `input_path`  | Path to the document to convert *(required)*     |

**Example**

```bash
python3 src/automation_tools/tools/converter.py document.docx
```

The resulting PDF is saved alongside the source file.

---

### 07 — File Translator

**Script:** `src/automation_tools/tools/translator.py`

Translates entire text files to another language via the **Google Gemini API**. Preserves structure intelligently:

- **Source code** — translates only comments and string literals
- **Subtitles (`.srt`)** — only dialogue
- **JSON** — only values (keys untouched)

**Supported formats:** `.txt` `.md` `.srt` `.py` `.json` `.csv` `.xml` `.html` `.css` `.js`

**Arguments**

| Option       | Description                                                      |
|--------------|------------------------------------------------------------------|
| `filepath`   | Path to the file to translate *(required)*                       |
| `--lang`     | Target language *(required)* — e.g., `english`, `french`         |
| `--key`      | Google API Key (optional if set in environment)                  |
| `--out`      | Save the translation to an output file                           |

**Examples**

```bash
python3 src/automation_tools/tools/translator.py document.txt --lang english
python3 src/automation_tools/tools/translator.py movie.srt --lang portuguese --out movie_pt.srt
python3 src/automation_tools/tools/translator.py notes.md --lang french --key YOUR_API_KEY
```

---

### 08 — Duplicate Finder

**Script:** `src/automation_tools/tools/duplicate_finder.py`

Recursively scans a directory and finds **byte-for-byte identical** files by MD5 hash, regardless of filename.

**Arguments**

| Option       | Description                                           |
|--------------|-------------------------------------------------------|
| `directory`  | Path to the directory to scan *(required)*            |
| `--delete`   | Delete copies automatically (keeps the oldest)        |

**Examples**

```bash
python3 src/automation_tools/tools/duplicate_finder.py /path/to/scan
python3 src/automation_tools/tools/duplicate_finder.py /path/to/scan --delete
```

---

### 09 — YouTube Downloader

**Script:** `src/automation_tools/tools/youtube_downloader.py`

Downloads YouTube videos at **maximum quality** — as MP4 video or MP3 audio — directly into your Downloads folder. Powered by `yt-dlp`.

**Arguments**

| Option    | Description                                           |
|-----------|-------------------------------------------------------|
| `url`     | YouTube video URL *(required)*                        |
| `--mode`  | Output format: `video` (default) or `audio`           |

**Examples**

```bash
python3 src/automation_tools/tools/youtube_downloader.py "https://www.youtube.com/watch?v=Example"
python3 src/automation_tools/tools/youtube_downloader.py "https://www.youtube.com/watch?v=Example" --mode audio
```

---

### 10 — README Generator

**Script:** `src/automation_tools/tools/readme_generator.py`

Analyses a local project's structure and source code, then generates a **complete, professional `README.md`** via the Google Gemini API.

**Arguments**

| Option        | Description                                                |
|---------------|------------------------------------------------------------|
| `directory`   | Root folder of the project to document *(required)*        |
| `--key`       | Google API Key (optional if set in environment)            |
| `--out`       | Output file (default: `README_generado.md`)                |

**Examples**

```bash
python3 src/automation_tools/tools/readme_generator.py ./my_project
python3 src/automation_tools/tools/readme_generator.py ./my_project --out README_final.md --key YOUR_API_KEY
```

---

### 11 — Metadata Extractor

**Script:** `src/automation_tools/tools/metadata.py`

Forensic inspection of **hidden metadata**:

- **Images** — EXIF: camera model, lens, GPS coordinates, resolution, capture date. JPG · PNG · TIFF · WebP
- **PDFs** — Document info: author, creator, producer, encryption, page count
- **Other files** — Filesystem info: exact size, creation and modification timestamps

**Arguments**

| Option       | Description                                   |
|--------------|-----------------------------------------------|
| `filepath`   | Path to the file to analyze *(required)*      |

**Examples**

```bash
python3 src/automation_tools/tools/metadata.py photo.jpg
python3 src/automation_tools/tools/metadata.py document.pdf
```

---

### 12 — Password Manager

**Script:** `src/automation_tools/tools/password_generator.py`

Generates secure passwords and memorable passphrases, and evaluates the strength of existing credentials. Built on Python's cryptographically secure `secrets` module — **no external dependencies**.

<table>
<tr>
<td width="33%" valign="top">

#### Secure Passwords

Random passwords with configurable character sets.

| Parameter   | Default |
|-------------|---------|
| Length      | 16      |
| Symbols     | Yes     |
| Exclude ambiguous | No |
| Count       | 5       |

</td>
<td width="33%" valign="top">

#### Passphrases

Easy-to-remember phrases from a curated 391-word Spanish dictionary.

| Parameter    | Default |
|--------------|---------|
| Words        | 4       |
| Separator    | `-`     |
| Capitalize   | Yes     |
| Number suffix | Yes    |
| Symbol suffix | No     |

</td>
<td width="33%" valign="top">

#### Strength Evaluation

Score 0–100 plus detailed report.

| Metric       | Checked |
|--------------|---------|
| Length       | Yes     |
| Char variety | Yes     |
| Entropy bits | Yes     |
| Repetition   | Yes     |
| Common pwds  | Yes     |

</td>
</tr>
</table>

**Example output**

```
         Passwords (16 characters)
┏━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ # ┃ Password         ┃ Strength   ┃ Entropy  ┃
┡━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1 │ @%8cUst52T:Uh*Kp │ Very strong│  105 bits│
│ 2 │ K5#)I2asq4mo_(Rv │ Very strong│  105 bits│
└───┴──────────────────┴────────────┴──────────┘

╭───────────── Strength ──────────────╮
│  ████████████████████████████░░  95 │
╰─────────────────────────────────────╯
  Length            14 characters
  Character types   lowercase, UPPERCASE, numbers, symbols
  Entropy           91.8 bits
```

---

### 13 — Space Cleaner

**Script:** `src/automation_tools/tools/space_cleaner.py`

Scans a directory and reports three kinds of reclaimable space:

1. **Cache / junk** — `__pycache__`, `node_modules`, `.DS_Store`, `.mypy_cache`, `.pytest_cache`, `build`, `dist`, `target`…
2. **Large files** — beyond a configurable size threshold
3. **Stale files** — untouched for more than N days

> [!CAUTION]
> Runs in **dry-run mode by default**. Nothing is deleted unless you explicitly pass `--apply`.

**Arguments**

| Option        | Description                                                          |
|---------------|----------------------------------------------------------------------|
| `directory`   | Target directory to scan *(required)*                                |
| `--large`     | Large-file threshold in MB (default: 100)                            |
| `--old`       | Old-file threshold in days since last modification (default: 365)    |
| `--no-junk`   | Skip the cache/junk scan                                             |
| `--no-large`  | Skip the large-file scan                                             |
| `--no-old`    | Skip the old-file scan                                               |
| `--apply`     | Actually delete findings (default is dry-run)                        |
| `--all`       | When applying, also delete large/old files (not just cache)          |

**Examples**

```bash
# Dry-run scan with default thresholds (>100 MB, >365 days)
python3 src/automation_tools/tools/space_cleaner.py ./project

# Custom thresholds
python3 src/automation_tools/tools/space_cleaner.py ~/Downloads --large 50 --old 180

# Delete cache/junk only (confirmation prompt)
python3 src/automation_tools/tools/space_cleaner.py ~/code --apply

# Delete everything flagged, including large/old files
python3 src/automation_tools/tools/space_cleaner.py ~/code --apply --all
```

> [!WARNING]
> Review findings carefully before using `--all`. The tool never follows symlinks.

---

### 14 — PDF Toolkit

**Script:** `src/automation_tools/tools/pdf_toolkit.py`

Manipulate existing PDF files. Built entirely on `pypdf` (pure Python — **no external binaries**), so it behaves identically on Linux, Windows, and Termux/Android.

**Operations**

| Command   | Description                                                          |
|-----------|----------------------------------------------------------------------|
| `merge`   | Combine several PDFs (a comma-separated list **or** a folder) into one |
| `split`   | Explode a PDF into one file per page                                 |
| `extract` | Build a new PDF from a 1-based page selection (e.g. `1-3,5,8-10`)     |
| `rotate`  | Rotate pages clockwise by 90 / 180 / 270°                            |
| `encrypt` | Password-protect a PDF (AES-256 when available)                      |
| `decrypt` | Remove protection given the current password                         |

> [!NOTE]
> Existing output files are never overwritten without confirmation. Encrypted inputs must be decrypted first.

**Examples**

```bash
# Merge a list — or a whole folder — into one PDF
python3 src/automation_tools/tools/pdf_toolkit.py merge "a.pdf,b.pdf" merged.pdf
python3 src/automation_tools/tools/pdf_toolkit.py merge ./folder merged.pdf

# Split into one file per page
python3 src/automation_tools/tools/pdf_toolkit.py split report.pdf --out-dir pages/

# Extract pages 1-3 and 5 into a new document
python3 src/automation_tools/tools/pdf_toolkit.py extract report.pdf 1-3,5 --out selection.pdf

# Rotate page 2 by 90°
python3 src/automation_tools/tools/pdf_toolkit.py rotate scan.pdf 90 --pages 2

# Encrypt, then decrypt
python3 src/automation_tools/tools/pdf_toolkit.py encrypt private.pdf "myPassword"
python3 src/automation_tools/tools/pdf_toolkit.py decrypt private_encrypted.pdf "myPassword"
```

---

### 15 — Web Clipper

**Script:** `src/automation_tools/tools/web_clipper.py`

Fetches a web page, strips away the chrome (navigation, ads, scripts), isolates the **main article**, and saves it as clean **Markdown** or **plain text**. Relative links and images are resolved to absolute URLs, and a metadata header (title, source, date, author) is prepended. The output feeds neatly into the [AI Summarizer](#03--ai-summarizer) and [File Translator](#07--file-translator).

> [!NOTE]
> Uses only `requests` + `beautifulsoup4` with the stdlib HTML parser — no extra binaries or `lxml` required.

**Arguments**

| Option        | Description                                                  |
|---------------|--------------------------------------------------------------|
| `url`         | Page URL — scheme defaults to `https://` *(required)*        |
| `--text`      | Output plain text instead of Markdown                        |
| `--no-images` | Drop image references (Markdown only)                        |
| `--out`       | Output file path                                             |
| `--save`      | Save with an auto-generated filename (slug of the title)     |
| `--timeout`   | Network timeout in seconds (default: 20)                     |

**Examples**

```bash
python3 src/automation_tools/tools/web_clipper.py "https://example.com/article" --save
python3 src/automation_tools/tools/web_clipper.py example.com/post --text --out note.txt
python3 src/automation_tools/tools/web_clipper.py "https://example.com/post" --no-images --out article.md
```

---

### 16 — Image Processor

**Script:** `src/automation_tools/tools/image_processor.py`

Batch operations over a single image or a whole folder — **resize**, **compress**, or **watermark** — built only on Pillow, so it runs identically on Linux, Windows, and Termux/Android.

> [!NOTE]
> Originals are **never modified**. Results are written to a separate folder (`<input>/processed` by default).

**Arguments**

| Option        | Description                                                          |
|---------------|----------------------------------------------------------------------|
| `input_path`  | Image file or folder of images *(required)*                          |
| `--op`        | Operation: `resize` (default), `compress`, or `watermark`            |
| `--out-dir`   | Output folder (default: `<input>/processed`)                         |
| `--recursive` | Recurse into subfolders                                              |
| `--max-size`  | Resize: longest-side cap in px (default: 1920)                       |
| `--scale`     | Resize: by percentage instead of `--max-size`                        |
| `--quality`   | Compress: JPEG/WebP quality 1–100 (default: 80)                      |
| `--text`      | Watermark: the text to stamp                                         |
| `--position`  | Watermark: `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center` |
| `--opacity`   | Watermark: opacity 0–100 (default: 50)                               |

**Examples**

```bash
# Resize a folder so the longest side is at most 1024 px
python3 src/automation_tools/tools/image_processor.py ./photos --op resize --max-size 1024

# Compress images to ~40% quality to shrink file size
python3 src/automation_tools/tools/image_processor.py ./photos --op compress --quality 40

# Stamp a watermark in the bottom-right corner
python3 src/automation_tools/tools/image_processor.py poster.png --op watermark --text "© Ale 2026" --opacity 60
```

---

### 17 — Encryption Vault

**Script:** `src/automation_tools/tools/vault.py`

Encrypt or decrypt any file (or a whole folder) with a password. Uses only the `cryptography` library — no external binaries — so it behaves identically across platforms.

- **Key derivation** — PBKDF2-HMAC-SHA256 (600,000 iterations) with a random salt
- **Cipher** — Fernet (AES-128-CBC + HMAC-SHA256): **authenticated**, so a wrong password or any tampering is detected, never producing garbage output
- **Self-describing** — each `.enc` file stores its salt, so it can be decrypted standalone later

> [!IMPORTANT]
> Keep your password safe — without it, encrypted files **cannot** be recovered.

**Arguments**

| Option               | Description                                                     |
|----------------------|-----------------------------------------------------------------|
| `path`               | File or folder to process *(required)*                          |
| `action`             | `encrypt` or `decrypt` *(required)*                             |
| `--password`         | Password (you are prompted securely if omitted)                 |
| `--out-dir`          | Output folder (default: alongside each source file)             |
| `--remove-originals` | Delete each source file after processing (asks to confirm)      |
| `--no-recursive`     | Do not recurse into subfolders                                  |

**Examples**

```bash
# Encrypt a folder (each file -> file.enc)
python3 src/automation_tools/tools/vault.py ./secret_docs encrypt --password "myStrongPass"

# Decrypt a single file into a chosen folder
python3 src/automation_tools/tools/vault.py report.pdf.enc decrypt --out-dir ./restored
```

> [!NOTE]
> The CLI exits with a non-zero status if any file fails (e.g. wrong password), so it scripts cleanly.

---

## Testing

The project ships with a `pytest` suite that covers every tool plus the menu/screen wiring.

```bash
pip install -r requirements-dev.txt
pytest
```

Tests live in `tests/` and run entirely against temporary directories — they never touch your real files. Network- and API-backed paths (HaveIBeenPwned, Google Gemini, yt-dlp) are mocked, so the suite runs fully offline.

---

## Project Structure

```
Automation-Tools/
├── README.md
├── GUIDE_CONFIG.md
├── requirements.txt
├── requirements-dev.txt             Dev/test dependencies
├── pytest.ini                       Test configuration
├── productos_a_monitorear.example.json   Price-monitor config template
├── run.py                           User entry point
├── src/
│   └── automation_tools/
│       ├── __init__.py
│       ├── core/                    Cross-cutting concerns
│       │   ├── logger.py            Unified logging & Rich output
│       │   └── config.py            Settings & path resolution
│       ├── cli/                     Presentation layer
│       │   ├── menu.py              Menu data & entry point
│       │   ├── tui.py               Textual dashboard (home screen)
│       │   └── screens.py           Per-tool input screens
│       └── tools/                   Business logic
│           ├── renamer.py
│           ├── monitor.py
│           ├── gemini_utils.py
│           ├── summarizer.py
│           ├── translator.py
│           ├── duplicate_finder.py
│           ├── youtube_downloader.py
│           ├── readme_generator.py
│           ├── converter.py
│           ├── image_processor.py
│           ├── pdf_toolkit.py
│           ├── organizer.py
│           ├── metadata.py
│           ├── password_generator.py
│           ├── space_cleaner.py
│           ├── web_clipper.py
│           └── vault.py
└── tests/                           pytest suite (one file per module)
```

---

## License

Released under the **MIT License**.

<div align="center">

---

**Crafted by [Ale](https://github.com/kahz12)**

*Built with Python, Textual, Rich, Questionary, Pillow, cryptography, and the Google Gemini API.*

</div>

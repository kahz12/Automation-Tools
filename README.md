<div align="center">

# Automation Tools

**A unified command-line toolkit of twenty-three Python utilities for everyday automation.**

Files · Conversion · AI (8 providers) · Web & Multimedia · Encryption · Utilities

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Termux-lightgrey.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Made with](https://img.shields.io/badge/Made%20with-Textual%20%2B%20AI-purple.svg)]()

</div>

---

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
- [Tools](#tools)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [License](#license)

---

## Overview

**Automation Tools** bundles twenty-three standalone Python utilities behind a single interactive [Textual](https://textual.textualize.io/) menu. Launch the guided dashboard, or call any tool directly from the terminal. It favors pure-Python implementations, so the same code runs on **Linux, Windows, and Termux/Android**.

- **Unified launcher** — one `automation-tools` command, arrow-key navigation, a recent-tools list
- **Standalone scripts** — every tool also works on its own with a conventional CLI (`--help` everywhere)
- **AI-powered** — eight interchangeable providers (Gemini, OpenAI, Groq, Anthropic, Grok, Qwen, MiniMax, DeepSeek) for summaries, translation, OCR, transcription, and README generation
- **Safe by default** — destructive operations run dry-run first; image/encryption tools never touch originals
- **Tested** — a `pytest` suite covers every tool plus the menu wiring, and runs fully offline

---

## Installation

### Quick install

Provisions a virtual environment and registers a global `automation-tools` launcher:

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh | bash
```

<details>
<summary>Inspect the script before running it (recommended)</summary>

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh -o install.sh
less install.sh
bash install.sh
```
</details>

### Manual

```bash
git clone https://github.com/kahz12/Automation-Tools.git
cd Automation-Tools
python3 -m venv venv && source venv/bin/activate
pip install -e .            # add ".[dev]" to get pytest and pyflakes too
```

Installing the package registers the `automation-tools` command inside the virtual environment.

> **Requires Python 3.10+.** Optional extras: [LibreOffice](https://www.libreoffice.org/) (used by the PDF Builder for full-layout office → PDF when installed; it falls back to a pure-Python text engine otherwise) and an **API key for one of the eight AI providers** (AI tools) — see [Configuration](#configuration).

---

## Usage

Launch the interactive menu:

```bash
automation-tools     # after the quick install
python3 run.py       # from a manual checkout
```

Navigate with the arrow keys and press `Enter` to open a tool. Every utility is also scriptable directly — each one supports `--help`:

```bash
# Rename a batch of photos with a sequential pattern (dry-run unless --aplicar)
python3 src/automation_tools/tools/renamer.py ./photos --mode patron --pattern "trip_{:03d}" --aplicar

# Resize a folder of images so the longest side is at most 1024 px
python3 src/automation_tools/tools/image_processor.py ./pics --op resize --max-size 1024

# Encrypt a folder with a password
python3 src/automation_tools/tools/vault.py ./secret_docs encrypt --password "myStrongPass"

# Summarize a PDF with the default provider
python3 src/automation_tools/tools/summarizer.py report.pdf --out summary.txt

# Extract text from a scanned image
python3 src/automation_tools/tools/ocr.py scan.png --out scan.txt

# Any AI tool can switch provider and model per run
python3 src/automation_tools/tools/summarizer.py report.pdf --provider anthropic --model claude-sonnet-4-5

# Merge two PDFs into one
python3 src/automation_tools/tools/pdf_toolkit.py merge "a.pdf,b.pdf" merged.pdf

# Back up a folder to a timestamped zip, excluding logs (dry-run unless --apply)
python3 src/automation_tools/tools/archiver.py create ./project -x "*.log" "__pycache__" --apply

# Create a checksum manifest of a folder, then verify it later
python3 src/automation_tools/tools/integrity.py create ./backups
python3 src/automation_tools/tools/integrity.py verify ./backups --extra
```

---

## Tools

All modules live in `src/automation_tools/tools/`. Run any of them with `--help` for the full set of options.

### Files

| Tool | Module | Description |
|------|--------|-------------|
| Bulk Renamer | `renamer.py` | Rename files in batches by pattern, date, or text substitution (dry-run by default). |
| Downloads Organizer | `organizer.py` | Sort the Downloads folder into category subfolders, with undo and history. |
| Duplicate Finder | `duplicate_finder.py` | Find byte-identical files by MD5 hash; optional CSV report and auto-delete. |
| Space Cleaner | `space_cleaner.py` | Reclaim space from caches, large files, and stale files (dry-run by default). |
| Archiver | `archiver.py` | Bundle files/folders into a timestamped zip/tar backup, list it, or extract it — pure Python, dry-run by default, Zip Slip-safe. |
| Log Analyzer | `log_analyzer.py` | Scan a log file or folder of `.log` files for keywords or a regex; streams results into a report. |

### Conversion

| Tool | Module | Description |
|------|--------|-------------|
| Image Converter | `converter.py` | Convert images between formats (PNG/JPG/WebP…) or render PDF pages to images. |
| Image Processor | `image_processor.py` | Batch resize, compress, or watermark images — originals are never modified. |
| Similar Photos | `similar_images.py` | Group photos that look the same even when the files differ (resized, re-compressed, re-saved), using a perceptual hash. Dry-run by default. |
| File Type Check | `file_type.py` | Verify a file really is what its extension claims, by reading its magic number. Flags a `.jpg` that is actually an executable. |
| PDF Builder | `pdf_builder.py` | Convert a document to PDF, bundle images into one PDF, or merge a mixed batch into a single file. Pure Python by default; uses LibreOffice for full layout when it is installed. |
| PDF Toolkit | `pdf_toolkit.py` | Merge, split, extract, rotate, encrypt, or decrypt PDFs (pure Python, no binaries). |

### AI

| Tool | Module | Description |
|------|--------|-------------|
| AI Summarizer | `summarizer.py` | Generate an executive summary with bullet points from a PDF or text file. |
| File Translator | `translator.py` | Translate files while preserving structure (code comments, subtitles, JSON, Markdown). |
| README Generator | `readme_generator.py` | Analyze a project's structure and code, then draft a professional `README.md`. |
| Image OCR | `ocr.py` | Extract text from images or scans — single file or batch, as plain text or Markdown. |
| A/V Transcriber | `transcriber.py` | Transcribe audio or video into SRT subtitles or a plain-text transcript. |

### Web & Multimedia

| Tool | Module | Description |
|------|--------|-------------|
| Price Monitor | `monitor.py` | Track MercadoLibre & Amazon prices with target/drop alerts (optional Telegram). |
| YouTube Downloader | `youtube_downloader.py` | Download video (MP4) or audio (MP3); playlist support. Powered by `yt-dlp`. |
| Web Clipper | `web_clipper.py` | Save a page's main article as clean Markdown or plain text. |

### Utilities

| Tool | Module | Description |
|------|--------|-------------|
| Metadata Extractor | `metadata.py` | Inspect EXIF/PDF metadata; optionally strip EXIF (e.g. GPS) from images. |
| Password Manager | `password_generator.py` | Generate passwords/passphrases and score strength (HaveIBeenPwned check). |
| Encryption Vault | `vault.py` | Encrypt/decrypt files & folders with a password (AES, authenticated). |
| Integrity Checker | `integrity.py` | Create a checksum manifest (MD5/SHA-1/SHA-256/SHA-512) of a folder and verify it later — `sha256sum -c` compatible. |
| Dotenv Manager | `env_manager.py` | Generate a `.env.example` template, scan a tree for exposed `.env` files, and validate a `.env` against its template. |

---

## Configuration

**AI providers** — the five AI tools work with any of eight providers. Pick one
with `AI_PROVIDER`, or per run with `--provider` (the dashboard has a dropdown).
Unset means `gemini`, so existing setups keep working unchanged.

Each provider reads its own key. Export it, or copy `.env.example` to `.env` and
fill in only the ones you use:

```bash
cp .env.example .env

# or, for a single session:
export AI_PROVIDER="anthropic"
export ANTHROPIC_API_KEY="your-key-here"
```

| Provider | Environment variable | Text | Vision | Audio |
|----------|---------------------|:----:|:------:|:-----:|
| Gemini | `GOOGLE_API_KEY` | ✅ | ✅ | ✅ |
| OpenAI | `OPENAI_API_KEY` | ✅ | ✅ | ✅ |
| Groq | `GROQ_API_KEY` | ✅ | ✅ | ✅ |
| Anthropic | `ANTHROPIC_API_KEY` | ✅ | ✅ | — |
| Grok (xAI) | `XAI_API_KEY` | ✅ | ✅ | — |
| Qwen | `DASHSCOPE_API_KEY` | ✅ | ✅ | — |
| MiniMax | `MINIMAX_API_KEY` | ✅ | ✅ | — |
| DeepSeek | `DEEPSEEK_API_KEY` | ✅ | — | — |

Tools only offer providers that can do the job: DeepSeek is text-only, so it
never appears for OCR, and transcription is limited to Gemini, OpenAI, and Groq.
Choosing an unsupported combination on the CLI gives a message naming the
providers that can, rather than a failed API call.

Override the model with `--model` when you want a specific one:

```bash
python3 src/automation_tools/tools/translator.py notes.md --lang Spanish \
    --provider groq --model openai/gpt-oss-20b
```

**Price Monitor** — copy the template to your own (git-ignored) config, then edit it. See **[GUIDE_CONFIG.md](GUIDE_CONFIG.md)** for the full reference, including Telegram and MercadoLibre API setup.

```bash
cp productos_a_monitorear.example.json productos_a_monitorear.json
```

**Encryption Vault** — keys are derived with PBKDF2-HMAC-SHA256 and files are sealed with Fernet (AES-128-CBC + HMAC), so tampering and wrong passwords are detected. There is **no password recovery** — keep yours safe.

---

## Testing

Install the dev extra, then run the suite from the project root:

```bash
pip install -e ".[dev]"
pytest
pyflakes src/ tests/
```

Tests live in `tests/`, exercise temporary directories only (your real files are never touched), and mock all network/API paths (HaveIBeenPwned, the AI providers, yt-dlp) — so the suite runs fully offline. The same two commands run in CI on Python 3.10, 3.12 and 3.13 for every push and pull request.

---

## Project Structure

```
Automation-Tools/
├── run.py                              # User entry point
├── pyproject.toml                      # Packaging, dependencies, entry point
├── requirements.txt                    # Points at pyproject (pip install -r still works)
├── pytest.ini                          # Test configuration
├── productos_a_monitorear.example.json # Price-monitor config template
├── README.md  ·  GUIDE_CONFIG.md       # Documentation
├── .github/workflows/ci.yml            # pytest + pyflakes on 3.10 / 3.12 / 3.13
├── src/automation_tools/
│   ├── core/                           # logger (Rich output) · config (settings & paths)
│   ├── cli/                            # menu · tui (Textual dashboard) · screens
│   └── tools/                          # 23 tool modules (one per utility)
└── tests/                              # pytest suite (one file per module)
```

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE).

<div align="center">

---

**Crafted by [Ale](https://github.com/kahz12)**

*Built with Python, Textual, Rich, Questionary, Pillow, cryptography, and eight AI provider APIs.*

</div>

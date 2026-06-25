<div align="center">

# Automation Tools

**A unified command-line toolkit of seventeen Python utilities for everyday automation.**

Files · Conversion · AI (Gemini) · Web & Multimedia · Encryption · Utilities

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Termux-lightgrey.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Made with](https://img.shields.io/badge/Made%20with-Textual%20%2B%20Gemini-purple.svg)]()

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

**Automation Tools** bundles seventeen standalone Python utilities behind a single interactive [Textual](https://textual.textualize.io/) menu. Launch the guided dashboard, or call any tool directly from the terminal. It favors pure-Python implementations, so the same code runs on **Linux, Windows, and Termux/Android**.

- **Unified launcher** — one `automation-tools` command, arrow-key navigation, a recent-tools list
- **Standalone scripts** — every tool also works on its own with a conventional CLI (`--help` everywhere)
- **AI-powered** — Google Gemini for summaries, translation, and README generation
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
pip install -r requirements.txt
```

> **Optional dependencies:** [LibreOffice](https://www.libreoffice.org/) (office → PDF conversion) and a **Google API key** (AI tools).

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

# Summarize a PDF with Gemini
python3 src/automation_tools/tools/summarizer.py report.pdf --out summary.txt

# Merge two PDFs into one
python3 src/automation_tools/tools/pdf_toolkit.py merge "a.pdf,b.pdf" merged.pdf
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

### Conversion

| Tool | Module | Description |
|------|--------|-------------|
| Image Converter | `converter.py` | Convert images between formats (PNG/JPG/WebP…) or render PDF pages to images. |
| Image Processor | `image_processor.py` | Batch resize, compress, or watermark images — originals are never modified. |
| PDF Converter | `converter.py` | Convert office documents (`.docx`, `.odt`, `.pptx`…) to PDF via LibreOffice. |
| PDF Toolkit | `pdf_toolkit.py` | Merge, split, extract, rotate, encrypt, or decrypt PDFs (pure Python, no binaries). |

### AI (Google Gemini)

| Tool | Module | Description |
|------|--------|-------------|
| AI Summarizer | `summarizer.py` | Generate an executive summary with bullet points from a PDF or text file. |
| File Translator | `translator.py` | Translate files while preserving structure (code comments, subtitles, JSON, Markdown). |
| README Generator | `readme_generator.py` | Analyze a project's structure and code, then draft a professional `README.md`. |

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

---

## Configuration

**Google API key** (AI tools) — export it or place it in a `.env` file:

```bash
export GOOGLE_API_KEY="your-key-here"
```

**Price Monitor** — copy the template to your own (git-ignored) config, then edit it. See **[GUIDE_CONFIG.md](GUIDE_CONFIG.md)** for the full reference, including Telegram and MercadoLibre API setup.

```bash
cp productos_a_monitorear.example.json productos_a_monitorear.json
```

**Encryption Vault** — keys are derived with PBKDF2-HMAC-SHA256 and files are sealed with Fernet (AES-128-CBC + HMAC), so tampering and wrong passwords are detected. There is **no password recovery** — keep yours safe.

---

## Testing

The test dependencies (`pytest`) ship in `requirements.txt`. Run the suite from the project root:

```bash
pytest
```

Tests live in `tests/`, exercise temporary directories only (your real files are never touched), and mock all network/API paths (HaveIBeenPwned, Gemini, yt-dlp) — so the suite runs fully offline.

---

## Project Structure

```
Automation-Tools/
├── run.py                              # User entry point
├── requirements.txt                    # Runtime + test dependencies
├── pytest.ini                          # Test configuration
├── productos_a_monitorear.example.json # Price-monitor config template
├── README.md  ·  GUIDE_CONFIG.md       # Documentation
├── src/automation_tools/
│   ├── core/                           # logger (Rich output) · config (settings & paths)
│   ├── cli/                            # menu · tui (Textual dashboard) · screens
│   └── tools/                          # 17 tool modules (one per utility)
└── tests/                              # pytest suite (one file per module)
```

---

## License

Released under the **MIT License**.

<div align="center">

---

**Crafted by [Ale](https://github.com/kahz12)**

*Built with Python, Textual, Rich, Questionary, Pillow, cryptography, and the Google Gemini API.*

</div>

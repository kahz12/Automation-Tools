# Automation Tools

A collection of Python scripts to automate everyday tasks: file organization, price monitoring, AI-powered document summarization, image conversion, PDF generation, password management, and more.

## Quick Install

One-liner (Linux and Termux):

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh | bash
```

The script creates a global `automation-tools` command that launches the interactive menu from any directory.

### Safe install (recommended)

Inspect the script before running it:

```bash
curl -fsSL https://raw.githubusercontent.com/kahz12/Automation-Tools/main/install.sh -o install.sh
less install.sh
bash install.sh
```

## Manual Installation

1. Make sure you have Python 3 installed.
2. Create and activate a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Main Menu

The recommended way to use these tools is through the interactive menu:

```bash
python3 run.py
```

Navigate with your keyboard arrows and run any tool without needing to remember commands.

---

## Tools

Each tool can also be executed independently from the terminal. Below is the full documentation for each one.

---

### 1. Bulk Renamer

**Script:** `src/automation_tools/tools/renamer.py`

Renames multiple files in a directory using three modes: sequential pattern, creation date, or text replacement.

> [!NOTE]
> Runs in dry-run (simulation) mode by default to preview changes. Add `--aplicar` to apply them.

**Options:**

| Option | Description |
|---|---|
| `directory` | Target directory containing the files (required) |
| `--mode` | Rename mode: `patron`, `fecha`, or `reemplazo` (required) |
| `--ext` | Filter files by extension (e.g., `.jpg`) |
| `--aplicar` | Apply the changes for real |

**Examples:**

- **Pattern mode** -- Rename files sequentially:
  ```bash
  python3 src/automation_tools/tools/renamer.py /path/to/photos --mode patron --pattern "trip_{:03d}" --ext .jpg
  python3 src/automation_tools/tools/renamer.py /path/to/photos --mode patron --pattern "trip_{:03d}" --ext .jpg --aplicar
  ```
  Result: `trip_001.jpg`, `trip_002.jpg`, `trip_003.jpg`...

- **Date mode** -- Prepend the creation date (EXIF or filesystem) to the filename:
  ```bash
  python3 src/automation_tools/tools/renamer.py /path/to/docs --mode fecha --keep-name --aplicar
  python3 src/automation_tools/tools/renamer.py /path/to/docs --mode fecha --aplicar
  ```
  With `--keep-name`: `2024-02-17_document.pdf`
  Without: `2024-02-17_001.pdf`

- **Replacement mode** -- Find and replace text in filenames:
  ```bash
  python3 src/automation_tools/tools/renamer.py /path/to/files --mode reemplazo --old-text "Copy of " --new-text "" --aplicar
  ```

---

### 2. Price Monitor

**Script:** `src/automation_tools/tools/monitor.py`

Tracks prices on MercadoLibre and Amazon. Sends alerts via console (and optionally Telegram) when the price hits your target or drops by a configured percentage.

**Configuration:** Edit `productos_a_monitorear.json` (see [GUIDE_CONFIG.md](GUIDE_CONFIG.md) for full details):

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

**Examples:**

```bash
# Single immediate check
python3 src/automation_tools/tools/monitor.py --now

# Continuous monitoring (checks every hour by default)
python3 src/automation_tools/tools/monitor.py

# Custom interval (every 30 minutes)
python3 src/automation_tools/tools/monitor.py --interval 30

# View recorded price history
python3 src/automation_tools/tools/monitor.py --historial
```

| Option | Description |
|---|---|
| `--now` | Run a single check and exit |
| `--interval` | Minutes between checks (default: 60) |
| `--historial` | Display the recorded price history |

---

### 3. AI Summarizer

**Script:** `src/automation_tools/tools/summarizer.py`

Uses the Google Gemini API to read PDF or plain text files and generate an executive summary with key bullet points.

**Requirement:** A Google API Key, configurable in two ways:
- Environment variable: `export GOOGLE_API_KEY=your_key`
- `.env` file in the project root: `GOOGLE_API_KEY=your_key`

**Supported formats:** `.pdf`, `.txt`, `.md`, `.py`, `.json`

**Examples:**

```bash
# Summarize a PDF (API key taken from environment)
python3 src/automation_tools/tools/summarizer.py document.pdf

# Save the summary to a file
python3 src/automation_tools/tools/summarizer.py report.pdf --out summary.txt

# Pass the API key directly
python3 src/automation_tools/tools/summarizer.py contract.pdf --key YOUR_API_KEY
```

| Option | Description |
|---|---|
| `filepath` | Path to the PDF or TXT file (required) |
| `--key` | Google API Key (optional if set in environment) |
| `--out` | Save the summary to an output file |

---

### 4. Downloads Organizer

**Script:** `src/automation_tools/tools/organizer.py`

Automatically moves files from your Downloads folder into organized subfolders by type based on file extension. No arguments required.

**Default categories:**

| Category | Extensions |
|---|---|
| Images | `.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp` |
| Documents | `.pdf`, `.doc`, `.docx`, `.txt`, `.xls`, `.xlsx`, `.ppt`, `.pptx` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.flv`, `.wmv` |
| Audio | `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg` |
| Archives | `.zip`, `.rar`, `.7z`, `.tar`, `.gz` |
| Executables | `.exe`, `.dmg`, `.app`, `.deb`, `.rpm` |
| Code | `.py`, `.js`, `.html`, `.css`, `.json`, `.xml` |
| Other | Any other extension |

```bash
python3 src/automation_tools/tools/organizer.py
```

> [!TIP]
> Categories and extensions can be customized by editing the `CATEGORIES` dictionary in the script.

---

### 5. Image Converter

**Script:** `src/automation_tools/tools/converter.py`

Converts images between formats. Works with individual files and entire directories (batch conversion).

**Supported formats:** `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif`

**Examples:**

```bash
# Convert a single image to JPG
python3 src/automation_tools/tools/converter.py /path/to/image.png jpg

# Convert an image to WebP
python3 src/automation_tools/tools/converter.py /path/to/photo.jpg webp

# Batch convert all images in a directory to PNG
python3 src/automation_tools/tools/converter.py /path/to/folder/ png
```

| Option | Description |
|---|---|
| `input_path` | Path to the image file or directory (required) |
| `output_format` | Output format: `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif` (required) |

> [!NOTE]
> Images with transparency (RGBA/P mode) are automatically converted to RGB when exporting as JPG.

---

### 6. PDF Converter

**Script:** `src/automation_tools/tools/converter.py`

Converts office documents (`.docx`, `.odt`, `.pptx`, etc.) to PDF using LibreOffice in headless mode.

**Requirement:** LibreOffice must be installed on the system.

**Example:**

```bash
python3 src/automation_tools/tools/converter.py /path/to/document.docx
```

| Option | Description |
|---|---|
| `input_path` | Path to the file to convert (required) |

The resulting PDF is saved in the same directory as the input file.

---

### 7. File Translator

**Script:** `src/automation_tools/tools/translator.py`

Translates entire text files to another language using the Google Gemini API. Preserves original formatting: for source code it translates only comments and strings, for subtitles (`.srt`) only the text, for JSON only the values.

**Requirement:** Google API Key (same setup as the Summarizer).

**Supported formats:** `.txt`, `.md`, `.srt`, `.py`, `.json`, `.csv`, `.xml`, `.html`, `.css`, `.js`

**Examples:**

```bash
# Translate a text file to English
python3 src/automation_tools/tools/translator.py document.txt --lang english

# Translate subtitles to Portuguese and save the result
python3 src/automation_tools/tools/translator.py movie.srt --lang portuguese --out movie_pt.srt

# Translate a Markdown file to French with explicit API key
python3 src/automation_tools/tools/translator.py notes.md --lang french --key YOUR_API_KEY
```

| Option | Description |
|---|---|
| `filepath` | Path to the file to translate (required) |
| `--lang` | Target language (required, e.g., `english`, `french`) |
| `--key` | Google API Key (optional if set in environment) |
| `--out` | Save the translation to an output file |

---

### 8. Duplicate Finder

**Script:** `src/automation_tools/tools/duplicate_finder.py`

Recursively scans a directory and finds files that are exactly identical by comparing their content (MD5 hash), regardless of filename.

**Examples:**

```bash
# Find duplicates and prompt before deleting
python3 src/automation_tools/tools/duplicate_finder.py /path/to/scan

# Find and auto-delete duplicates (keeping the oldest)
python3 src/automation_tools/tools/duplicate_finder.py /path/to/scan --delete
```

| Option | Description |
|---|---|
| `directory` | Path to the directory to scan (required) |
| `--delete` | Automatically delete copies without prompting |

---

### 9. YouTube Downloader

**Script:** `src/automation_tools/tools/youtube_downloader.py`

Downloads YouTube videos in maximum quality (MP4 video or MP3 audio) directly to your Downloads folder.

**Requirement:** Depends on `yt-dlp` (included in `requirements.txt`).

**Examples:**

```bash
# Download as video (MP4)
python3 src/automation_tools/tools/youtube_downloader.py "https://www.youtube.com/watch?v=Example"

# Download audio only (MP3)
python3 src/automation_tools/tools/youtube_downloader.py "https://www.youtube.com/watch?v=Example" --mode audio
```

| Option | Description |
|---|---|
| `url` | YouTube video URL (required) |
| `--mode` | Download format: `video` (default) or `audio` |

---

### 10. README Generator (AI)

**Script:** `src/automation_tools/tools/readme_generator.py`

Uses the Google Gemini API to analyze the structure and key source code of a local project and generate a complete, professional `README.md` file.

**Requirement:** Google API Key (same setup as the Summarizer).

**Examples:**

```bash
# Generate a README (saved as README_generado.md by default)
python3 src/automation_tools/tools/readme_generator.py /path/to/my_project

# Specify output file and API key
python3 src/automation_tools/tools/readme_generator.py /path/to/my_project --out README_final.md --key YOUR_API_KEY
```

| Option | Description |
|---|---|
| `directory` | Root folder of the project to document (required) |
| `--key` | Google API Key (optional if set in environment) |
| `--out` | Output file (default: `README_generado.md`) |

---

### 11. Metadata Extractor

**Script:** `src/automation_tools/tools/metadata.py`

Forensic tool to extract and display hidden metadata from files.
- **Images:** Extracts EXIF data (camera model, lens, GPS data, resolution, date taken). Supports JPG, PNG, TIFF, WebP, etc.
- **PDFs:** Extracts document info (author, creator, producer, encryption status, page count).
- **Other files:** Displays basic filesystem info (exact size, creation and modification dates).

**Examples:**

```bash
python3 src/automation_tools/tools/metadata.py /path/to/photo.jpg
python3 src/automation_tools/tools/metadata.py /path/to/document.pdf
```

| Option | Description |
|---|---|
| `filepath` | Path to the file to analyze (required) |

---

### 12. Password Manager

**Script:** `src/automation_tools/tools/password_generator.py`

Generates secure passwords and memorable passphrases with customizable parameters. Also evaluates the strength of existing passwords with a detailed report. Uses Python's `secrets` module for cryptographically secure generation. No external dependencies required.

**Three modes of operation:**

#### Generate Secure Passwords

Creates random passwords with configurable character sets.

| Parameter | Default | Description |
|---|---|---|
| Length | 16 | Number of characters (4-128) |
| Symbols | Yes | Include special characters (`!@#$%^&*`...) |
| Ambiguous exclusion | No | Exclude visually similar characters (`I/l/1`, `O/0`) |
| Count | 5 | Number of passwords to generate (1-20) |

```
         Passwords (16 characters)
┏━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ # ┃ Password         ┃ Strength   ┃ Entropy  ┃
┡━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ 1 │ @%8cUst52T:Uh*Kp │ Very strong│  105 bits│
│ 2 │ K5#)I2asq4mo_(Rv │ Very strong│  105 bits│
└───┴──────────────────┴────────────┴──────────┘
```

#### Generate Memorable Passphrases

Creates easy-to-remember passphrases from a curated 391-word Spanish dictionary.

| Parameter | Default | Description |
|---|---|---|
| Words | 4 | Number of words (2-10) |
| Separator | `-` | Word separator (`-`, `.`, `_`, or space) |
| Capitalize | Yes | Capitalize each word |
| Add number | Yes | Append a random 3-digit number |
| Add symbol | No | Append a random special character |

Example output: `Canal-Norte-Plaza-869`, `Arbol.Selva.Tigre.214!`

#### Evaluate Password Strength

Analyzes an existing password and returns a detailed report:
- **Score:** 0-100 with a visual progress bar
- **Levels:** Very weak, Weak, Moderate, Strong, Very strong
- **Analysis:** Length, character variety, entropy (bits)
- **Penalties:** Repeated characters, sequential patterns, common passwords
- **Recommendations:** Actionable tips to improve strength

```
╭───────────── Strength ──────────────╮
│  ████████████████████████████░░  95 │
╰─────────────────────────────────────╯
  Length            14 characters
  Character types   lowercase, UPPERCASE, numbers, symbols
  Entropy           91.8 bits

  [+] Good password
```

---

## Project Structure

```
Automation-Tools/
├── requirements.txt
├── README.md
├── GUIDE_CONFIG.md
├── productos_a_monitorear.json
├── run.py                           (User entry point)
└── src/
    └── automation_tools/
        ├── __init__.py
        ├── core/                    (Cross-cutting concerns)
        │   ├── logger.py            (Unified logging & Rich output)
        │   └── config.py            (Settings & path resolution)
        ├── cli/                     (Presentation layer)
        │   └── menu.py              (Interactive menu)
        └── tools/                   (Business logic)
            ├── renamer.py
            ├── monitor.py
            ├── gemini_utils.py
            ├── summarizer.py
            ├── translator.py
            ├── duplicate_finder.py
            ├── youtube_downloader.py
            ├── readme_generator.py
            ├── converter.py
            ├── organizer.py
            ├── metadata.py
            └── password_generator.py
```

---

## License

Made with love by Ale.

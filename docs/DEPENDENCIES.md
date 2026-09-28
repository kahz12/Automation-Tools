# Dependencies and platform notes

The Python package declares its runtime dependencies in `pyproject.toml`.
Installing with `pip install -e .` (or the quick installer) creates an
isolated environment and installs them reproducibly from those constraints.
Development tools are available with `pip install -e ".[dev]"`.

## Optional system programs

| Program | Used by | Behaviour when absent |
|---|---|---|
| `ffmpeg` | `flac_check`, `youtube_downloader` and `instagram_downloader` post-processing | FLAC checks can inspect headers but cannot analyse audio; YouTube and Instagram downloads may not merge separate audio/video streams. |
| `libreoffice`/`soffice` | `pdf_builder` document conversion | The pure-Python fallback extracts text but cannot preserve full office layout. |
| Poppler (`pdftoppm` or `pdftocairo`) | `converter --from-pdf` through `pdf2image` | PDF rendering is unavailable until Poppler is installed. |
| `xclip`, `xsel`, `wl-copy`, `pbcopy`, `clip` or Termux API | `password_generator copy` | The password is printed/generated but cannot be copied automatically. |

Install the programs with the package manager for your platform. For example:

```bash
# Debian/Ubuntu
sudo apt-get install ffmpeg libreoffice poppler-utils xclip

# Fedora
sudo dnf install ffmpeg libreoffice poppler-utils xclip

# Arch
sudo pacman -S ffmpeg libreoffice poppler xclip

# Termux (where available)
pkg install ffmpeg
```

The installer only treats Git, Python 3 and the `venv` module as mandatory;
it prints hints for optional programs without failing the installation.

## Network and credentials

AI tools need a key for the selected provider (`.env.example` lists the
supported variables). `monitor` may contact MercadoLibre/Amazon and Telegram;
`web_clipper`, `youtube_downloader` and `instagram_downloader` need network
access. The Instagram downloader reads stories, highlights and private
accounts only with a logged-in session: a cookies file named by
`INSTAGRAM_COOKIES` or `--cookies`, or `--browser`. Password breach checking
uses HaveIBeenPwned's k-anonymity API. Tests mock these services and run
offline.

Keep `.env`, provider keys and password files outside version control. Use
`atools env_manager scan .` to find accidentally exposed dotenv files.

## Reproducible setup

```bash
git clone https://github.com/kahz12/Automation-Tools.git
cd Automation-Tools
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
atools --list
```

Pin the generated environment with your organisation's normal lockfile/tool
if you need byte-for-byte deployments; the project intentionally does not
publish release archives or pre-built packages.


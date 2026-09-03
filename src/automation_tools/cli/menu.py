import json

from automation_tools.core.logger import console, setup_logger
from automation_tools.core.config import load_environment, state_path
from automation_tools.cli.tui import AutomationApp

HISTORY_FILE = state_path(".menu_history.json")
HISTORY_MAX = 5


def _load_history() -> list:
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(names: list) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(names[:HISTORY_MAX], f)
    except Exception:
        pass


def _record_use(name: str) -> None:
    history = [n for n in _load_history() if n != name]
    history.insert(0, name)
    _save_history(history)


# Each entry: (label, None). The action comes from SCREEN_MAP in screens.py.
MENU_ENTRIES = [
    ("📂  Files", [
        ("✂️   Massive Renamer",    None),
        ("📦  Organize Downloads",  None),
        ("🧬  Duplicate Detector",  None),
        ("👯  Similar Photos",      None),
        ("🧹  Space Cleaner",       None),
        ("💾  Archiver",            None),
        ("🔍  Log Analyzer",        None),
    ]),
    ("🔄  Conversion", [
        ("🖼️   Image Converter",    None),
        ("🪄  Image Processor",     None),
        ("📄  Convert to PDF",      None),
        ("📑  PDF Toolkit",         None),
    ]),
    ("🧠  AI", [
        ("📝  Document Summarizer", None),
        ("🌐  File Translator",     None),
        ("📘  README Generator",    None),
        ("🔡  Image OCR",           None),
        ("🎤  A/V Transcriber",      None),
    ]),
    ("🌐  Web & Multimedia", [
        ("💰  Price Monitor",       None),
        ("📺  YouTube Downloader",  None),
        ("📰  Web Clipper",         None),
    ]),
    ("🔧  Utilities", [
        ("🔎  Metadata Extractor",  None),
        ("🔐  Password Manager",    None),
        ("🔒  Encryption Vault",    None),
        ("🧾  Integrity Checker",   None),
        ("⚙️  Dotenv Manager",      None),
        ("🔬  File Type Check",     None),
        ("🎼  FLAC Authenticity",    None),
    ]),
]


def main_menu() -> None:
    setup_logger()
    load_environment()
    try:
        AutomationApp(MENU_ENTRIES, _load_history(), record_use=_record_use).run()
    except KeyboardInterrupt:
        pass
    console.print()
    console.print("[bold #a78bfa]See you later![/] 👋")


if __name__ == "__main__":
    main_menu()

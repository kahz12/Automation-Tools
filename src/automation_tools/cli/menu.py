import json
import os
from typing import Optional

import questionary
from questionary import Choice, Separator

from automation_tools.core.logger import (
    console,
    print_banner,
    print_error,
    print_footer_tip,
    print_rule,
    print_section,
    print_success,
    print_warning,
    question_style,
)
from automation_tools.core.config import load_environment, get_env_var, get_project_root

# --- CLI Menu & Interaction Module ---
# This module implements the interactive Command Line Interface (CLI) for the project.
# It manages tool navigation, user input prompts, and a history of recently used tools.

# Path to the file that stores the most recently used tools.
HISTORY_FILE = os.path.join(get_project_root(), ".menu_history.json")
HISTORY_MAX = 5


def _load_history() -> list:
    """Loads the list of recently used tool names from a local JSON file."""
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(names: list) -> None:
    """Saves the list of recently used tool names to a local JSON file."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(names[:HISTORY_MAX], f)
    except Exception:
        pass


def _record_use(name: str) -> None:
    """Updates the history by adding the last used tool to the top of the list."""
    history = [n for n in _load_history() if n != name]
    history.insert(0, name)
    _save_history(history)

# Import individual tool wrappers.
from automation_tools.tools import (
    renamer,
    monitor,
    summarizer,
    converter,
    translator,
    duplicate_finder,
    youtube_downloader,
    readme_generator,
    metadata,
    organizer,
    password_generator,
    space_cleaner,
)


# ---------------------------------------------------------------------------
# Shared questionary helpers (standardized prompts for consistency).
# ---------------------------------------------------------------------------
QSTYLE = question_style()


def ask_select(message, choices, **kwargs):
    """Shows a selection list to the user."""
    return questionary.select(message, choices=choices, style=QSTYLE, **kwargs).ask()


def ask_text(message, **kwargs):
    """Prompts the user for a text string."""
    return questionary.text(message, style=QSTYLE, **kwargs).ask()


def ask_path(message, **kwargs):
    """Prompts the user for a file or directory path."""
    return questionary.path(message, style=QSTYLE, **kwargs).ask()


def ask_confirm(message, default=False, **kwargs):
    """Prompts the user for a Yes/No confirmation."""
    return questionary.confirm(message, default=default, style=QSTYLE, **kwargs).ask()


def ask_password(message, **kwargs):
    """Prompts the user for sensitive input (hidden text)."""
    return questionary.password(message, style=QSTYLE, **kwargs).ask()


def press_any_key():
    """Pauses execution until the user presses a key."""
    print_rule()
    questionary.press_any_key_to_continue(style=QSTYLE).ask()


def error_boundary(func):
    """
    Decorator that wraps tool execution to catch and display errors gracefully.
    Prevents the entire application from crashing on tool-specific failures.
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            console.print("\n[bold red]Execution interrupted.[/bold red]")
        except Exception as e:
            print_error(f"An unexpected error occurred: {e}")
        finally:
            press_any_key()
    return wrapper


# ---------------------------------------------------------------------------
# Tool-specific menu screens (Workflow definitions)
# ---------------------------------------------------------------------------

@error_boundary
def menu_renombrador():
    """Screen for the Massive Renamer tool."""
    print_section("Massive Renamer", "Rename batches of files using patterns, dates, or text replacement", "✂️")

    directory = ask_path("Which folder do you want to process?")
    if not directory:
        return

    mode = ask_select(
        "Which mode do you want to use?",
        choices=[
            Choice("🔢  Pattern (e.g., photo_001.jpg)", "patron"),
            Choice("📅  Date (e.g., 2024-01-01_file.jpg)", "fecha"),
            Choice("🔁  Text replacement (e.g., remove 'copy of')", "reemplazo"),
        ],
    )
    if not mode:
        return

    pattern, old_text, new_text = None, None, ""
    keep = False

    if mode == "patron":
        detected, count, max_index = renamer.detect_dominant_pattern(directory)
        if detected:
            console.print(
                f"[dim]Detected existing pattern '{detected}' "
                f"({count} file(s), max index: {max_index}).[/dim]"
            )
            if ask_confirm(
                f"Continue with this pattern from {max_index + 1}? (No = use a new pattern)",
                default=True,
            ):
                pattern = detected
            else:
                print_footer_tip("Use '{:03d}' for zero-padded numbering (001, 002...)")
                pattern = ask_text("Enter the new pattern (e.g., 'trip_{:03d}'):")
                if not pattern:
                    return
        else:
            print_footer_tip("Use '{:03d}' for zero-padded numbering (001, 002...)")
            pattern = ask_text("Enter the pattern (e.g., 'trip_{:03d}'):")
            if not pattern:
                return
    elif mode == "fecha":
        keep = ask_confirm("Keep original name as suffix?")
    elif mode == "reemplazo":
        old_text = ask_text("Text to find:")
        if not old_text:
            return
        new_text = ask_text("New text (leave empty to delete):")

    ext = ask_text("Filter by extension (optional, e.g., .jpg):")
    apply_changes = ask_confirm("Apply real changes? (No = simulation only)")
    preview = False
    if apply_changes:
        preview = ask_confirm("Confirm changes before applying (preview)?", default=True)

    renamer.run_massive_rename(
        directory=directory,
        mode=mode,
        apply_changes=apply_changes,
        ext_filter=ext,
        pattern=pattern,
        keep_name=keep,
        old_text=old_text,
        new_text=new_text,
        preview=preview,
    )


@error_boundary
def menu_monitor():
    """Screen for the Price Monitor tool."""
    print_section("Price Monitor", "Track prices on MercadoLibre and Amazon", "💰")

    action = ask_select(
        "What do you want to do?",
        choices=[
            Choice("⚡  Run a check right now", "now"),
            Choice("🔁  Start continuous monitoring (hourly)", "loop"),
            Choice("📝  View configuration (file)", "config"),
        ],
    )
    if not action:
        return

    if action == "now":
        monitor.run_price_monitor_job()
    elif action == "loop":
        monitor.run_continuous_monitor()
    elif action == "config":
        config_path = os.path.join(get_project_root(), "productos_a_monitorear.json")
        console.print(f"📄 Config file: [link=file://{config_path}]{config_path}[/link]")


def check_api_key() -> Optional[str]:
    """Helper to ensure the Google API Key is available for AI tools."""
    api_key = get_env_var("GOOGLE_API_KEY")
    if not api_key:
        print_warning("GOOGLE_API_KEY not detected in environment variables.")
        api_key = ask_password("Enter your Google API Key:")
    return api_key


@error_boundary
def menu_resumidor():
    """Screen for the AI Summarizer tool."""
    print_section("AI Summarizer", "Generate an executive summary of PDF or TXT files with Gemini", "📝")

    filepath = ask_path("Select the PDF or TXT file:")
    if not filepath:
        return

    api_key = check_api_key()
    if not api_key:
        return

    out_path = None
    if ask_confirm("Save summary to a file?"):
        out_path = os.path.splitext(filepath)[0] + "_summary.txt"
        console.print(f"[dim]Will be saved to: {out_path}[/dim]")

    summarizer.run_summarizer(filepath=filepath, api_key=api_key, out_path=out_path)


@error_boundary
def menu_convertir():
    """Screen for the Image Converter tool."""
    print_section("Image Converter", "Change format (png, jpg, webp, …) or render PDF to images", "🖼️")

    action = ask_select(
        "What do you want to do?",
        choices=[
            Choice("🖼️   Convert image or folder", "img"),
            Choice("📄  Render PDF to images", "pdf"),
        ],
    )
    if not action:
        return

    if action == "pdf":
        pdf_path = ask_path("Select the PDF to render:")
        if not pdf_path:
            return
        fmt = ask_select("Output format:", choices=["png", "jpg", "webp"]) or "png"
        dpi_raw = ask_text("DPI:", default="200")
        try:
            dpi = max(50, min(600, int(dpi_raw or "200")))
        except ValueError:
            dpi = 200
        converter.run_pdf_to_image(pdf_path, fmt, dpi=dpi)
        return

    img_path = ask_path("Select the image or folder to convert:")
    if not img_path:
        return

    fmt = ask_select(
        "Select output format:",
        choices=["png", "jpg", "webp", "tiff", "bmp", "gif"],
    )
    if not fmt:
        return

    quality = 85
    if fmt in ("jpg", "jpeg", "webp"):
        raw = ask_text("Quality (1-100):", default="85")
        try:
            quality = max(1, min(100, int(raw or "85")))
        except ValueError:
            quality = 85

    converter.run_image_converter(img_path, fmt, quality=quality)


@error_boundary
def menu_convertir_pdf():
    """Screen for the Office-to-PDF Converter tool."""
    print_section("Convert to PDF", "Transform Office documents to PDF using LibreOffice", "📄")

    filepath = ask_path("Select the file to convert (e.g., .docx, .odt, .pptx):")
    if filepath:
        converter.run_pdf_converter(filepath)


@error_boundary
def menu_traductor():
    """Screen for the AI Translator tool."""
    print_section("File Translator", "Translate text, subtitles, or code using Gemini", "🌐")

    filepath = ask_path("Select the file to translate:")
    if not filepath:
        return

    lang = ask_select(
        "Target language:",
        choices=["English", "Spanish", "French", "Portuguese", "German", "Italian", "Other"],
    )
    if not lang:
        return

    if lang == "Other":
        lang = ask_text("Type the target language:")
        if not lang:
            return

    api_key = check_api_key()
    if not api_key:
        return

    out_path = None
    if ask_confirm("Save translation to a file?"):
        base = os.path.splitext(filepath)[0]
        ext = os.path.splitext(filepath)[1]
        out_path = f"{base}_{lang.lower()}{ext}"
        console.print(f"[dim]Will be saved to: {out_path}[/dim]")

    translator.run_translator(filepath=filepath, target_lang=lang.lower(), api_key=api_key, out_path=out_path)


@error_boundary
def menu_detector_duplicados():
    """Screen for the Duplicate Finder tool."""
    print_section("Duplicate Detector", "Find identical files by content (MD5 hash)", "🧬")
    directory = ask_path("Which folder do you want to scan?")
    if not directory:
        return

    exclude_raw = ask_text(
        "Glob patterns to exclude (comma-separated, optional, e.g., '*.tmp,backup_*'):"
    )
    excludes = [p.strip() for p in exclude_raw.split(",") if p.strip()] if exclude_raw else None

    export_path = None
    if ask_confirm("Export CSV report of duplicates?", default=False):
        export_path = ask_text("CSV file path:", default="duplicates.csv") or "duplicates.csv"

    delete = ask_confirm("Automatically delete duplicates (keeping one original)?")
    duplicate_finder.run_duplicate_finder(
        directory, auto_delete=delete, excludes=excludes, export_path=export_path
    )


@error_boundary
def menu_descargador_youtube():
    """Screen for the YouTube Downloader tool."""
    print_section("YouTube Downloader", "Download videos and audio in maximum quality", "📺")
    url = ask_text("Video or playlist URL:")
    if not url:
        return

    mode = ask_select(
        "What do you want to download?",
        choices=[
            Choice("🎬  Video (High Quality MP4)", "video"),
            Choice("🎵  Audio (MP3)", "audio"),
        ],
    )
    if not mode:
        return

    # Auto-detect playlist URL and offer to enable playlist mode.
    is_playlist = "list=" in url or "playlist" in url.lower()
    playlist = False
    if is_playlist:
        playlist = ask_confirm("Playlist detected. Download all videos?", default=True)

    youtube_downloader.run_youtube_downloader(url, mode, playlist=playlist)


@error_boundary
def menu_generador_readme():
    """Screen for the AI README Generator tool."""
    print_section("README Generator (AI)", "Analyze a project and draft its README using Gemini", "📘")
    directory = ask_path("Project folder to analyze?")
    if not directory:
        return

    api_key = check_api_key()
    if not api_key:
        return

    readme_generator.run_readme_generator(directory, api_key)


@error_boundary
def menu_extractor_metadata():
    """Screen for the Metadata Extractor tool."""
    print_section("Metadata Extractor", "Reveal EXIF data from images and PDF information", "🔎")
    filepath = ask_path("File to inspect (PDF, JPG, PNG, etc)?")
    if not filepath:
        return

    export_path = None
    if ask_confirm("Export metadata to a file (JSON/CSV)?", default=False):
        export_path = ask_text("Output path (use .json or .csv):", default="metadata.json")

    clean = False
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".tiff", ".webp", ".bmp"):
        clean = ask_confirm(
            "Create a copy without EXIF (no GPS or camera data)?", default=False
        )

    metadata.run_metadata_extractor(filepath, export_path=export_path, clean_exif=clean)


@error_boundary
def menu_organizar_descargas():
    """Screen for the Downloads Organizer tool."""
    print_section("Organize Downloads", "Move files in Downloads into subfolders by type", "📦")

    action = ask_select(
        "What do you want to do?",
        choices=[
            Choice("📦  Organize now", "run"),
            Choice("↩️   Undo last organization", "undo"),
            Choice("🗂️   List history", "list"),
        ],
    )
    if not action:
        return

    if action == "run":
        policy = ask_select(
            "If a file already exists in the destination folder:",
            choices=[
                Choice("📝  Rename (file_1.ext)", "rename"),
                Choice("⏭️   Skip", "skip"),
                Choice("⚠️   Overwrite", "overwrite"),
            ],
        ) or "rename"
        organizer.run_download_organizer(collision_policy=policy)
    elif action == "undo":
        organizer.undo_last()
    elif action == "list":
        files = organizer.list_history()
        if not files:
            print_warning("No history found.")
        else:
            for f in files:
                console.print(f"  [dim]•[/dim] {f}")


@error_boundary
def menu_password_generator():
    """Screen for the Password Manager tool."""
    print_section("Password Manager", "Generate passwords, phrases, and evaluate strength", "🔐")

    action = ask_select(
        "What do you want to do?",
        choices=[
            Choice("🎲  Generate secure password", "secure"),
            Choice("🧠  Generate memorable passphrase", "passphrase"),
            Choice("🛡️   Evaluate password strength", "strength"),
        ],
    )
    if not action:
        return

    if action == "secure":
        length_str = ask_text("Password length:", default="16")
        if not length_str:
            return
        try:
            length = int(length_str)
            if length < 4:
                print_warning("Minimum length adjusted to 4.")
                length = 4
            elif length > 128:
                print_warning("Maximum length adjusted to 128.")
                length = 128
        except ValueError:
            print_error("Invalid length.")
            return

        use_special = ask_confirm("Include symbols (!@#$%...)?", default=True)
        exclude_ambiguous = ask_confirm("Exclude ambiguous characters (I/l/1, O/0)?", default=False)

        count_str = ask_text("How many to generate?", default="5")
        count = min(max(int(count_str or "5"), 1), 20)

        password_generator.run_generate_password(
            length=length,
            use_special=use_special,
            exclude_ambiguous=exclude_ambiguous,
            count=count,
        )

        if ask_confirm("Copy the first password to clipboard?", default=False):
            pwd = password_generator.generate_password(
                length=length, use_special=use_special, exclude_ambiguous=exclude_ambiguous
            )
            if pwd:
                password_generator.run_copy_password(pwd)

    elif action == "passphrase":
        words_str = ask_text("How many words?", default="4")
        num_words = min(max(int(words_str or "4"), 2), 10)

        separator = ask_select("Separator:", choices=["-", ".", "_", " "]) or "-"

        capitalize = ask_confirm("Capitalize words?", default=True)
        add_number = ask_confirm("Add number at the end?", default=True)
        add_special = ask_confirm("Add symbol at the end?", default=False)

        count_str = ask_text("How many to generate?", default="5")
        count = min(max(int(count_str or "5"), 1), 20)

        password_generator.run_generate_passphrase(
            num_words=num_words,
            separator=separator,
            capitalize=capitalize,
            add_number=add_number,
            add_special=add_special,
            count=count,
        )

    elif action == "strength":
        pwd = ask_password("Enter the password to evaluate:")
        if pwd:
            check_breach = ask_confirm(
                "Check HaveIBeenPwned? (secure k-anonymity)", default=True
            )
            password_generator.run_evaluate_strength(pwd, check_breach=check_breach)


@error_boundary
def menu_limpiador_espacio():
    """Screen for the Space Cleaner tool."""
    print_section("Space Cleaner", "Detect cache, large, and old files (dry-run by default)", "🧹")

    directory = ask_path("Which folder do you want to analyze?")
    if not directory:
        return

    find_junk = ask_confirm(
        "Find junk/cache (__pycache__, node_modules, .DS_Store, etc.)?", default=True
    )

    find_large = ask_confirm("Find large files?", default=True)
    large_mb = space_cleaner.DEFAULT_LARGE_MB
    if find_large:
        raw = ask_text("Large file threshold (MB):", default=str(space_cleaner.DEFAULT_LARGE_MB))
        try:
            large_mb = max(1, int(raw or space_cleaner.DEFAULT_LARGE_MB))
        except ValueError:
            print_warning("Invalid value, using 100 MB.")

    find_old = ask_confirm("Find old files?", default=True)
    old_days = space_cleaner.DEFAULT_OLD_DAYS
    if find_old:
        raw = ask_text(
            "Age threshold (days since last modification):",
            default=str(space_cleaner.DEFAULT_OLD_DAYS),
        )
        try:
            old_days = max(1, int(raw or space_cleaner.DEFAULT_OLD_DAYS))
        except ValueError:
            print_warning("Invalid value, using 365 days.")

    apply = ask_confirm("Apply deletion? (No = simulation only)", default=False)

    delete_all = False
    if apply:
        delete_all = ask_confirm(
            "Include large/old files in the deletion? (only cache if you answer No)",
            default=False,
        )

    export_path = None
    if ask_confirm("Export scan report to a file?", default=False):
        export_path = ask_text("Path (.json or .csv):", default="cleaning_report.json")

    space_cleaner.run_space_cleaner(
        directory=directory,
        large_mb=large_mb,
        old_days=old_days,
        find_junk=find_junk,
        find_large=find_large,
        find_old=find_old,
        apply=apply,
        delete_large_and_old=delete_all,
        export_path=export_path,
    )


# ---------------------------------------------------------------------------
# Main menu layout — grouped by category with icons and separators.
# ---------------------------------------------------------------------------
MENU_ENTRIES = [
    ("📂  Files", [
        ("✂️   Massive Renamer",      menu_renombrador),
        ("📦  Organize Downloads",      menu_organizar_descargas),
        ("🧬  Duplicate Detector",   menu_detector_duplicados),
        ("🧹  Space Cleaner",     menu_limpiador_espacio),
    ]),
    ("🔄  Conversion", [
        ("🖼️   Image Converter",         menu_convertir),
        ("📄  Convert to PDF",           menu_convertir_pdf),
    ]),
    ("🧠  AI (Gemini)", [
        ("📝  Document Summarizer",   menu_resumidor),
        ("🌐  File Translator",     menu_traductor),
        ("📘  README Generator",       menu_generador_readme),
    ]),
    ("🌐  Web & Multimedia", [
        ("💰  Price Monitor",        menu_monitor),
        ("📺  YouTube Downloader",      menu_descargador_youtube),
    ]),
    ("🔧  Utilities", [
        ("🔎  Metadata Extractor",    menu_extractor_metadata),
        ("🔐  Password Manager",     menu_password_generator),
    ]),
]


def _label_to_action():
    """Flat map {label → action} across all menu groups for easy lookup."""
    flat = {}
    for _, entries in MENU_ENTRIES:
        for label, action in entries:
            flat[label.strip()] = (label, action)
    return flat


def _build_menu_choices():
    """Constructs the list of choices for the main menu, including history and categories."""
    choices = []

    # Recently used tools: Top of the menu.
    flat = _label_to_action()
    recents = _load_history()
    visible_recents = [r for r in recents if r in flat]
    if visible_recents:
        choices.append(Separator("── 🕘  Recents ──"))
        for label_key in visible_recents[:HISTORY_MAX]:
            label, action = flat[label_key]
            choices.append(Choice(f"  {label}", value=action))

    # Categorized tools.
    for group_label, entries in MENU_ENTRIES:
        choices.append(Separator(f"── {group_label} ──"))
        for label, action in entries:
            choices.append(Choice(f"  {label}", value=action))
    choices.append(Separator(" "))
    choices.append(Choice("  🚪  Exit", value="exit"))
    return choices


def main_menu():
    """
    Main application loop.
    Loads the environment, displays the banner, and handles user tool selection.
    """
    load_environment()

    while True:
        print_banner()
        print_footer_tip("Type to filter · ↑/↓ navigate · Enter choose · Ctrl+C cancel.")
        console.print()

        # `use_search_filter=True` enables typing-to-filter in questionary.
        selection = questionary.select(
            "What do you want to do today?",
            choices=_build_menu_choices(),
            style=QSTYLE,
            use_indicator=True,
            use_search_filter=True,
            use_jk_keys=False,
            qmark="▸",
        ).ask()

        if selection is None or selection == "exit":
            console.print()
            console.print("[bold #a78bfa]See you later![/] 👋")
            break

        # Record usage history.
        flat = _label_to_action()
        for label_key, (_, action) in flat.items():
            if action is selection:
                _record_use(label_key)
                break

        # Execute the selected tool's menu screen.
        selection()


if __name__ == "__main__":
    main_menu()

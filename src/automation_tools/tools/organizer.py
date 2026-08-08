import os
import json
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning
from automation_tools.core.config import get_downloads_folder, get_project_root

# Define categories and their associated file extensions
# Note: Keeping Spanish keys to maintain consistency with existing user folders.
CATEGORIES = {
    'Imágenes': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],  # Images
    'Documentos': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'],  # Documents
    'Videos': ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'],  # Videos
    'Audio': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],  # Audio
    'Comprimidos': ['.zip', '.rar', '.7z', '.tar', '.gz'],  # Compressed/Archives
    'Ejecutables': ['.exe', '.dmg', '.app', '.deb', '.rpm', '.AppImage', '.apk'],  # Executables
    'Programación': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.c', '.cpp', '.ts', '.go', '.rs', '.md'],  # Code/Dev
    'Otros': []  # Others
}

# Directory to store move history for undo functionality
HISTORY_DIR = os.path.join(get_project_root(), ".organizer_history")


def create_directories_if_not_exist(downloads_path: str) -> None:
    """Creates the category folders under `downloads_path` if they are missing."""
    for category in CATEGORIES:
        category_path = os.path.join(downloads_path, category)
        if not os.path.exists(category_path):
            os.makedirs(category_path)
            console.print(f"[dim]Folder created: {category_path}[/dim]")


def get_target_category(filename: str) -> str:
    """Category folder a file belongs to, from its extension."""
    file_extension = os.path.splitext(filename)[1].lower()
    for category, extensions in CATEGORIES.items():
        if file_extension in extensions:
            return category
    return 'Otros'


def _resolve_collision(dst: str, policy: str) -> Optional[str]:
    """Applies the collision `policy` ("skip", "overwrite" or "rename"). None means skip the move."""
    if not os.path.exists(dst):
        return dst
    if policy == "skip":
        return None
    if policy == "overwrite":
        return dst
    # rename policy: append _1, _2... before the extension
    base, ext = os.path.splitext(dst)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _save_history(moves: List[Dict[str, str]], root_path: str) -> Optional[str]:
    """Writes the moves to a JSON file so the run can be undone later."""
    if not moves:
        return None
    os.makedirs(HISTORY_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    history_path = os.path.join(HISTORY_DIR, f"organize_{stamp}.json")
    payload = {
        "timestamp": stamp,
        "root": root_path,
        "moves": moves,
    }
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return history_path


def run_download_organizer(collision_policy: str = "rename") -> None:
    """Sorts the downloads folder into category subfolders."""
    downloads_path = get_downloads_folder()

    print_step(f"Organizing folder: [bold]{downloads_path}[/bold]")

    if not os.path.isdir(downloads_path):
        print_error(f"The folder '{downloads_path}' does not exist or is not a directory.")
        return

    create_directories_if_not_exist(downloads_path)

    moved_count = 0
    skipped_count = 0
    moves: List[Dict[str, str]] = []

    for filename in os.listdir(downloads_path):
        source_path = os.path.join(downloads_path, filename)

        # Skip directories to avoid recursive organization
        if os.path.isdir(source_path):
            continue

        category = get_target_category(filename)
        raw_dst = os.path.join(downloads_path, category, filename)
        final_dst = _resolve_collision(raw_dst, collision_policy)

        if final_dst is None:
            console.print(f"[yellow]Skipped (already exists):[/yellow] '{filename}'")
            skipped_count += 1
            continue

        try:
            shutil.move(source_path, final_dst)
            renamed = " [dim](renamed)[/dim]" if final_dst != raw_dst else ""
            console.print(f"Moved: '{filename}' to '[green]{category}[/green]'{renamed}")
            moves.append({"from": source_path, "to": final_dst})
            moved_count += 1
        except Exception as e:
            print_error(f"Error moving '{filename}': {e}")

    history_path = _save_history(moves, downloads_path)
    print_success(f"Files moved: {moved_count}. Skipped: {skipped_count}.")
    if history_path:
        console.print(f"[dim]📝 History: {history_path}[/dim]")
        console.print("[dim]   To revert: use organizer.undo_last() or from the menu.[/dim]")


def list_history() -> List[str]:
    """History files, newest first."""
    if not os.path.isdir(HISTORY_DIR):
        return []
    files = [os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def undo_from_file(history_path: str) -> None:
    """Puts every file recorded in a history file back where it came from."""
    if not os.path.isfile(history_path):
        print_error(f"History file not found: {history_path}")
        return
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print_error(f"Corrupt history file: {e}")
        return

    moves = payload.get("moves", [])
    if not moves:
        print_warning("History contains no moves.")
        return

    print_step(f"Reverting {len(moves)} movement(s) from {payload.get('timestamp', '?')}...")

    reverted = 0
    # Revert in reverse order to ensure consistency
    for m in reversed(moves):
        src, dst = m["to"], m["from"]
        if not os.path.exists(src):
            console.print(f"[yellow]Not found:[/yellow] {src}")
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                console.print(f"[yellow]Destination already exists, skipping:[/yellow] {dst}")
                continue
            shutil.move(src, dst)
            reverted += 1
        except Exception as e:
            print_error(f"Error reverting {src}: {e}")

    if reverted:
        try:
            # Delete history file if at least some moves were reverted
            os.remove(history_path)
        except OSError:
            pass
    print_success(f"Successfully reverted {reverted}/{len(moves)} movements.")


def undo_last() -> None:
    """Reverts the most recent reorganization run.
    """
    files = list_history()
    if not files:
        print_warning("No history found to revert.")
        return
    undo_from_file(files[0])


def main():
    """Main entry point for the organizer tool.
    """
    run_download_organizer()


if __name__ == "__main__":
    main()

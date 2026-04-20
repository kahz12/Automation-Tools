import os
import json
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning
from automation_tools.core.config import get_downloads_folder, get_project_root

# Define las categorías y las extensiones de archivo asociadas
CATEGORIES = {
    'Imágenes': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],
    'Documentos': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'],
    'Videos': ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'],
    'Audio': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],
    'Comprimidos': ['.zip', '.rar', '.7z', '.tar', '.gz'],
    'Ejecutables': ['.exe', '.dmg', '.app', '.deb', '.rpm', '.AppImage', '.apk'],
    'Programación': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.c', '.cpp', '.ts', '.go', '.rs', '.md'],
    'Otros': []
}

HISTORY_DIR = os.path.join(get_project_root(), ".organizer_history")


def create_directories_if_not_exist(downloads_path: str) -> None:
    """Crea los directorios para cada categoría si no existen."""
    for category in CATEGORIES:
        category_path = os.path.join(downloads_path, category)
        if not os.path.exists(category_path):
            os.makedirs(category_path)
            console.print(f"[dim]Carpeta creada: {category_path}[/dim]")


def get_target_category(filename: str) -> str:
    """Determina la categoría de un archivo según su extensión."""
    file_extension = os.path.splitext(filename)[1].lower()
    for category, extensions in CATEGORIES.items():
        if file_extension in extensions:
            return category
    return 'Otros'


def _resolve_collision(dst: str, policy: str) -> Optional[str]:
    """Apply collision policy. Returns the final destination or None if skipped."""
    if not os.path.exists(dst):
        return dst
    if policy == "skip":
        return None
    if policy == "overwrite":
        return dst
    # rename: append _1, _2...
    base, ext = os.path.splitext(dst)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _save_history(moves: List[Dict[str, str]], root_path: str) -> Optional[str]:
    """Persist moves as a JSON file for undo. Returns the history file path."""
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
    """Organiza la carpeta de descargas.

    collision_policy: "rename" (por defecto), "skip", o "overwrite".
    """
    downloads_path = get_downloads_folder()

    print_step(f"Organizando la carpeta: [bold]{downloads_path}[/bold]")

    if not os.path.isdir(downloads_path):
        print_error(f"La carpeta '{downloads_path}' no existe o no es un directorio.")
        return

    create_directories_if_not_exist(downloads_path)

    moved_count = 0
    skipped_count = 0
    moves: List[Dict[str, str]] = []

    for filename in os.listdir(downloads_path):
        source_path = os.path.join(downloads_path, filename)

        if os.path.isdir(source_path):
            continue

        category = get_target_category(filename)
        raw_dst = os.path.join(downloads_path, category, filename)
        final_dst = _resolve_collision(raw_dst, collision_policy)

        if final_dst is None:
            console.print(f"[yellow]Saltado (ya existe):[/yellow] '{filename}'")
            skipped_count += 1
            continue

        try:
            shutil.move(source_path, final_dst)
            renamed = " [dim](renombrado)[/dim]" if final_dst != raw_dst else ""
            console.print(f"Movido: '{filename}' a '[green]{category}[/green]'{renamed}")
            moves.append({"from": source_path, "to": final_dst})
            moved_count += 1
        except Exception as e:
            print_error(f"Error al mover '{filename}': {e}")

    history_path = _save_history(moves, downloads_path)
    print_success(f"Archivos movidos: {moved_count}. Saltados: {skipped_count}.")
    if history_path:
        console.print(f"[dim]📝 Historial: {history_path}[/dim]")
        console.print("[dim]   Para revertir: organizer.undo_last() o desde el menú.[/dim]")


def list_history() -> List[str]:
    """Returns history files sorted newest-first."""
    if not os.path.isdir(HISTORY_DIR):
        return []
    files = [os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def undo_from_file(history_path: str) -> None:
    """Reverts moves recorded in a history JSON file."""
    if not os.path.isfile(history_path):
        print_error(f"No existe el archivo de historial: {history_path}")
        return
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        print_error(f"Historial corrupto: {e}")
        return

    moves = payload.get("moves", [])
    if not moves:
        print_warning("El historial no contiene movimientos.")
        return

    print_step(f"Revirtiendo {len(moves)} movimiento(s) de {payload.get('timestamp', '?')}...")

    reverted = 0
    for m in reversed(moves):
        src, dst = m["to"], m["from"]
        if not os.path.exists(src):
            console.print(f"[yellow]No encontrado:[/yellow] {src}")
            continue
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                console.print(f"[yellow]Ya existe destino, saltando:[/yellow] {dst}")
                continue
            shutil.move(src, dst)
            reverted += 1
        except Exception as e:
            print_error(f"Error al revertir {src}: {e}")

    if reverted:
        try:
            os.remove(history_path)
        except OSError:
            pass
    print_success(f"Revertidos {reverted}/{len(moves)} movimientos.")


def undo_last() -> None:
    """Reverts the most recent organize run."""
    files = list_history()
    if not files:
        print_warning("No hay historial para revertir.")
        return
    undo_from_file(files[0])


def main():
    run_download_organizer()


if __name__ == "__main__":
    main()

import os
import hashlib
import argparse
import csv
import fnmatch
from typing import Dict, List, Optional, Set
from collections import defaultdict

import questionary

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", "venv", ".venv", ".cache"]


def hash_file(filepath: str, chunk_size: int = 8192) -> Optional[str]:
    """Calcula el hash MD5 de un archivo."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print_error(f"Error al leer {filepath}: {e}")
        return None


def _matches_any(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def find_duplicates(
    directory: str,
    excludes: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """Encuentra archivos duplicados recursivamente, respetando excludes."""
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    print_step(f"Buscando duplicados en: [bold]{directory}[/bold]...")
    if patterns:
        console.print(f"[dim]Excluyendo: {', '.join(patterns)}[/dim]")

    hashes: Dict[str, List[str]] = defaultdict(list)
    symlinks: List[str] = []

    for root, dirs, files in os.walk(directory):
        # Prune excluded directories in-place.
        dirs[:] = [d for d in dirs if not _matches_any(d, patterns)]

        for filename in files:
            if _matches_any(filename, patterns):
                continue
            filepath = os.path.join(root, filename)
            if os.path.islink(filepath):
                symlinks.append(filepath)
                continue

            file_hash = hash_file(filepath)
            if file_hash:
                hashes[file_hash].append(filepath)

    if symlinks:
        console.print(f"[dim]🔗 Se omitieron {len(symlinks)} symlinks (no se hashean).[/dim]")
        for link in symlinks[:10]:
            console.print(f"[dim]   → {link}[/dim]")
        if len(symlinks) > 10:
            console.print(f"[dim]   ... y {len(symlinks) - 10} más[/dim]")

    return {h: paths for h, paths in hashes.items() if len(paths) > 1}


def _export_duplicates(duplicates: Dict[str, List[str]], out_path: str) -> None:
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["hash", "size_bytes", "role", "path"])
            for h, paths in duplicates.items():
                paths_sorted = sorted(paths, key=os.path.getmtime)
                for i, p in enumerate(paths_sorted):
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = 0
                    role = "original" if i == 0 else "duplicate"
                    writer.writerow([h, size, role, p])
        print_success(f"Reporte exportado a: {out_path}")
    except Exception as e:
        print_error(f"No se pudo exportar el reporte: {e}")


def run_duplicate_finder(
    directory: str,
    auto_delete: bool = False,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
) -> None:
    """Core function to find and optionally delete duplicates."""
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    duplicates = find_duplicates(directory, excludes=excludes)

    if not duplicates:
        print_success("No se encontraron archivos duplicados.")
        return

    total_wasted_bytes = 0
    console.print(f"\n[bold yellow]¡Se encontraron {len(duplicates)} grupos de duplicados![/bold yellow]\n")

    for h, paths in duplicates.items():
        paths.sort(key=lambda x: os.path.getmtime(x))

        console.print(f"[cyan]Grupo Hash: {h[:8]}...[/cyan]")
        console.print(f"  [green](Original)[/green] {paths[0]}")

        file_size = os.path.getsize(paths[0])
        total_wasted_bytes += file_size * (len(paths) - 1)

        for p in paths[1:]:
            console.print(f"  [red](Copia)[/red]    {p}")
        print()

    mb_saved = total_wasted_bytes / (1024 * 1024)
    console.print(f"Espacio recuperable: [bold green]{mb_saved:.2f} MB[/bold green]\n")

    if export_path:
        _export_duplicates(duplicates, export_path)

    confirm = True if auto_delete else questionary.confirm("¿Deseas eliminar todas las copias (manteniendo el original de cada grupo)?").ask()

    if confirm:
        deleted = 0
        for h, paths in duplicates.items():
            for p in paths[1:]:
                try:
                    os.remove(p)
                    deleted += 1
                    console.print(f"[dim]Eliminado: {p}[/dim]")
                except Exception as e:
                    print_error(f"Error al eliminar {p}: {e}")

        print_success(f"¡Proceso completado! Se eliminaron {deleted} archivos.")
    else:
        print_warning("No se eliminó ningún archivo.")


def main():
    parser = argparse.ArgumentParser(description="Detector de Archivos Duplicados")
    parser.add_argument("directory", help="Directorio a escanear")
    parser.add_argument("--delete", action="store_true", help="Eliminar duplicados automaticamente")
    parser.add_argument(
        "--exclude",
        help="Patrones glob separados por coma para excluir (ej: '*.tmp,backup_*')",
    )
    parser.add_argument("--export", help="Exportar reporte CSV de duplicados")
    args = parser.parse_args()

    excludes = [p.strip() for p in args.exclude.split(",")] if args.exclude else None
    run_duplicate_finder(args.directory, args.delete, excludes=excludes, export_path=args.export)


if __name__ == "__main__":
    main()

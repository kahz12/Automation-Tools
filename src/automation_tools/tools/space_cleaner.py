import os
import argparse
import csv
import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

import questionary
from rich.table import Table

from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Caches and build artifacts that are safe to delete (they get regenerated).
JUNK_DIRS = {
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".cache",
    ".gradle",
    ".idea",
    ".parcel-cache",
    "build",
    "dist",
    ".next",
    ".nuxt",
    "target",  # Rust/Java
}

JUNK_FILES = {
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}

JUNK_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
    ".tmp",
    ".bak",
    ".swp",
}

# Nombres de carpeta/archivo que JAMÁS deben eliminarse aunque coincidan
# con algún patrón de basura. Protege configs y fuentes de verdad.
PROTECTED_NAMES = {
    ".git",
    ".gitignore",
    ".env",
    ".env.local",
    ".venv",
    "venv",
    "env",
    "config",
    "configs",
    ".ssh",
    ".gnupg",
    ".aws",
    ".kube",
    "id_rsa",
    "id_ed25519",
}

DEFAULT_LARGE_MB = 100
DEFAULT_OLD_DAYS = 365


def _is_protected(path: str) -> bool:
    """True if any path segment matches a protected name."""
    parts = set(os.path.normpath(path).split(os.sep))
    return bool(parts & PROTECTED_NAMES)


def _disk_free(path: str) -> int:
    """Available bytes on the filesystem containing `path`."""
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return 0


@dataclass
class CleanItem:
    path: str
    size: int
    reason: str  # "junk", "large", "old"
    is_dir: bool = False


@dataclass
class ScanReport:
    junk: List[CleanItem] = field(default_factory=list)
    large: List[CleanItem] = field(default_factory=list)
    old: List[CleanItem] = field(default_factory=list)

    def all_items(self) -> List[CleanItem]:
        return self.junk + self.large + self.old

    def total_bytes(self) -> int:
        # Avoid double-counting: if a large/old file sits inside a junk dir it
        # is already accounted for by the junk dir total.
        junk_roots = tuple(i.path + os.sep for i in self.junk)
        total = sum(i.size for i in self.junk)
        for item in self.large + self.old:
            if not item.path.startswith(junk_roots):
                total += item.size
        return total


def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path, onerror=lambda _: None):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.islink(fp):
                continue
            try:
                total += os.path.getsize(fp)
            except OSError:
                continue
    return total


def scan(
    directory: str,
    large_mb: int = DEFAULT_LARGE_MB,
    old_days: int = DEFAULT_OLD_DAYS,
    find_junk: bool = True,
    find_large: bool = True,
    find_old: bool = True,
) -> ScanReport:
    report = ScanReport()
    large_bytes = large_mb * 1024 * 1024
    old_cutoff = time.time() - old_days * 86400
    junk_paths: List[str] = []

    print_step(f"Escaneando: [bold]{directory}[/bold]")

    for root, dirs, files in os.walk(directory, topdown=True, onerror=lambda _: None):
        # Never descend into protected dirs.
        dirs[:] = [d for d in dirs if d not in PROTECTED_NAMES]

        if find_junk:
            matched = [d for d in dirs if d in JUNK_DIRS]
            for d in matched:
                full = os.path.join(root, d)
                if _is_protected(full):
                    continue
                size = dir_size(full)
                report.junk.append(CleanItem(full, size, "junk", is_dir=True))
                junk_paths.append(full + os.sep)
            # Don't descend into junk dirs (faster + avoids double-listing).
            dirs[:] = [d for d in dirs if d not in JUNK_DIRS]

        for filename in files:
            fp = os.path.join(root, filename)
            if os.path.islink(fp):
                continue
            if _is_protected(fp):
                continue

            if find_junk and (
                filename in JUNK_FILES
                or os.path.splitext(filename)[1].lower() in JUNK_EXTENSIONS
            ):
                try:
                    report.junk.append(
                        CleanItem(fp, os.path.getsize(fp), "junk", is_dir=False)
                    )
                except OSError:
                    pass
                continue

            # Skip files already inside a detected junk dir.
            if any(fp.startswith(j) for j in junk_paths):
                continue

            try:
                st = os.stat(fp)
            except OSError:
                continue

            if find_large and st.st_size >= large_bytes:
                report.large.append(CleanItem(fp, st.st_size, "large", is_dir=False))

            if find_old and st.st_mtime < old_cutoff:
                report.old.append(CleanItem(fp, st.st_size, "old", is_dir=False))

    report.junk.sort(key=lambda i: i.size, reverse=True)
    report.large.sort(key=lambda i: i.size, reverse=True)
    report.old.sort(key=lambda i: i.size, reverse=True)
    return report


def _print_section(title: str, items: List[CleanItem], limit: int = 20) -> None:
    if not items:
        return
    table = Table(title=title, show_lines=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Tamaño", justify="right", style="yellow")
    table.add_column("Tipo", width=8)
    table.add_column("Ruta", overflow="fold")

    for idx, item in enumerate(items[:limit], 1):
        kind = "DIR" if item.is_dir else "FILE"
        table.add_row(str(idx), human_size(item.size), kind, item.path)
    console.print(table)

    if len(items) > limit:
        console.print(
            f"[dim]... y {len(items) - limit} más (ocultos).[/dim]"
        )


def print_report(report: ScanReport) -> None:
    _print_section("Caché / Basura", report.junk)
    _print_section("Archivos grandes", report.large)
    _print_section("Archivos antiguos", report.old)

    total = report.total_bytes()
    console.print(
        f"\nEspacio recuperable estimado: [bold green]{human_size(total)}[/bold green]"
    )


def _delete_item(item: CleanItem) -> Tuple[bool, Optional[str]]:
    try:
        if item.is_dir:
            shutil.rmtree(item.path, ignore_errors=False)
        else:
            os.remove(item.path)
        return True, None
    except Exception as e:
        return False, str(e)


def delete_items(items: Iterable[CleanItem]) -> int:
    deleted = 0
    freed = 0
    for item in items:
        ok, err = _delete_item(item)
        if ok:
            deleted += 1
            freed += item.size
            console.print(f"[dim]Eliminado:[/dim] {item.path}")
        else:
            print_error(f"No se pudo eliminar {item.path}: {err}")
    if deleted:
        print_success(
            f"Eliminados {deleted} elementos. Espacio liberado: {human_size(freed)}"
        )
    return deleted


def export_report(report: ScanReport, out_path: str) -> None:
    """Export scan report to JSON or CSV based on extension."""
    items = [
        {"path": i.path, "size_bytes": i.size, "reason": i.reason, "is_dir": i.is_dir}
        for i in report.all_items()
    ]
    try:
        ext = os.path.splitext(out_path)[1].lower()
        if ext == ".csv":
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["path", "size_bytes", "reason", "is_dir"])
                writer.writeheader()
                writer.writerows(items)
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "total_bytes": report.total_bytes(),
                        "items": items,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
        print_success(f"Reporte exportado a: {out_path}")
    except Exception as e:
        print_error(f"No se pudo exportar el reporte: {e}")


def run_space_cleaner(
    directory: str,
    large_mb: int = DEFAULT_LARGE_MB,
    old_days: int = DEFAULT_OLD_DAYS,
    find_junk: bool = True,
    find_large: bool = True,
    find_old: bool = True,
    apply: bool = False,
    delete_large_and_old: bool = False,
    export_path: Optional[str] = None,
) -> None:
    """Core function: scans the directory and optionally deletes findings.

    By default runs in dry-run and only deletes junk/cache items on confirmation
    (never large/old files unless `delete_large_and_old=True`).
    """
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    free_before = _disk_free(directory)

    report = scan(
        directory,
        large_mb=large_mb,
        old_days=old_days,
        find_junk=find_junk,
        find_large=find_large,
        find_old=find_old,
    )

    if not report.all_items():
        print_success("Nada que limpiar. Todo se ve bien.")
        if export_path:
            export_report(report, export_path)
        return

    print_report(report)

    if export_path:
        export_report(report, export_path)

    if not apply:
        print_warning("Modo simulación (dry-run). No se eliminó nada.")
        return

    # Only auto-delete junk by default; large/old needs explicit opt-in.
    to_delete: List[CleanItem] = list(report.junk)
    if delete_large_and_old:
        to_delete += report.large + report.old

    if not to_delete:
        print_warning("Nada seleccionado para eliminar.")
        return

    confirm = questionary.confirm(
        f"¿Eliminar {len(to_delete)} elementos ({human_size(sum(i.size for i in to_delete))})?",
        default=False,
    ).ask()
    if not confirm:
        print_warning("Cancelado. No se eliminó nada.")
        return

    delete_items(to_delete)

    free_after = _disk_free(directory)
    if free_before and free_after:
        real_freed = max(0, free_after - free_before)
        console.print(
            f"[bold]📊 Espacio libre antes:[/bold] {human_size(free_before)}  →  "
            f"[bold]después:[/bold] {human_size(free_after)}  "
            f"([green]+{human_size(real_freed)} liberados[/green])"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Limpiador de espacio: detecta caché, archivos grandes y antiguos."
    )
    parser.add_argument("directory", help="Directorio a escanear")
    parser.add_argument(
        "--large",
        type=int,
        default=DEFAULT_LARGE_MB,
        help=f"Umbral de archivo grande en MB (default: {DEFAULT_LARGE_MB})",
    )
    parser.add_argument(
        "--old",
        type=int,
        default=DEFAULT_OLD_DAYS,
        help=f"Umbral de archivo antiguo en días (default: {DEFAULT_OLD_DAYS})",
    )
    parser.add_argument(
        "--no-junk", action="store_true", help="Omitir búsqueda de caché/basura"
    )
    parser.add_argument(
        "--no-large", action="store_true", help="Omitir búsqueda de archivos grandes"
    )
    parser.add_argument(
        "--no-old", action="store_true", help="Omitir búsqueda de archivos antiguos"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Aplicar eliminación (por defecto es dry-run)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Al aplicar, también eliminar archivos grandes y antiguos (no solo caché)",
    )
    parser.add_argument(
        "--export",
        help="Exportar reporte de escaneo a JSON o CSV (según extensión)",
    )
    args = parser.parse_args()

    run_space_cleaner(
        directory=args.directory,
        large_mb=args.large,
        old_days=args.old,
        find_junk=not args.no_junk,
        find_large=not args.no_large,
        find_old=not args.no_old,
        apply=args.apply,
        delete_large_and_old=args.all,
        export_path=args.export,
    )


if __name__ == "__main__":
    main()

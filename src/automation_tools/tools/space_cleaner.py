import os
import argparse
import csv
import json
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from rich.table import Table

from automation_tools.core import fs
from automation_tools.core import prompt
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Finds junk (caches, build artifacts), oversized files and stale ones, and can
# delete them. Dry-run unless told otherwise.

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

# Directory or file names that should NEVER be deleted, even if they match a junk pattern.
# Protects configuration and source-of-truth files.
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
    """Returns True if any part of the path matches a protected name."""
    parts = set(os.path.normpath(path).split(os.sep))
    return bool(parts & PROTECTED_NAMES)


def _disk_free(path: str) -> int:
    """Returns the available bytes on the filesystem containing the given path."""
    try:
        return shutil.disk_usage(path).free
    except Exception:
        return 0


@dataclass
class CleanItem:
    """Represents a file or directory identified for cleaning."""
    path: str
    size: int
    reason: str  # "junk", "large", or "old"
    is_dir: bool = False


@dataclass
class ScanReport:
    """Aggregates all items found during a scan."""
    junk: List[CleanItem] = field(default_factory=list)
    large: List[CleanItem] = field(default_factory=list)
    old: List[CleanItem] = field(default_factory=list)

    def all_items(self) -> List[CleanItem]:
        """Returns a flat list of all identified items."""
        return self.junk + self.large + self.old

    def total_bytes(self) -> int:
        """Calculates the total size of all items.
        Avoids double-counting: if a large/old file sits inside a junk dir,
        it is only counted once as part of the junk dir.
        """
        junk_roots = tuple(i.path + os.sep for i in self.junk)
        total = sum(i.size for i in self.junk)
        for item in self.large + self.old:
            if not item.path.startswith(junk_roots):
                total += item.size
        return total


def human_size(n: int) -> str:
    """Converts a byte count into a human-readable string (e.g., 1.5 GB)."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def dir_size(path: str) -> int:
    """Calculates the total size of a directory by summing all its files."""
    total = 0
    for fp in fs.walk_files(path):
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
    """Crawls the directory tree to identify items that match the cleaning criteria.
    - find_junk: Look for known temporary/cache files.
    - find_large: Look for files exceeding a size threshold.
    - find_old: Look for files not modified within a certain timeframe.
    """
    report = ScanReport()
    large_bytes = large_mb * 1024 * 1024
    old_cutoff = time.time() - old_days * 86400
    junk_paths: List[str] = []

    print_step(f"Scanning: [bold]{directory}[/bold]")

    for root, dirs, files in os.walk(directory, topdown=True, onerror=lambda _: None):
        # Prevent descending into protected system or configuration directories.
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
            # Prune junk directories from further traversal to save time and avoid duplicates.
            dirs[:] = [d for d in dirs if d not in JUNK_DIRS]

        for filename in files:
            fp = os.path.join(root, filename)
            if os.path.islink(fp):
                continue
            if _is_protected(fp):
                continue

            # Identify specific junk files or extensions.
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

            # Skip files already accounted for within a detected junk directory.
            if any(fp.startswith(j) for j in junk_paths):
                continue

            try:
                st = os.stat(fp)
            except OSError:
                continue

            # Identify large files.
            if find_large and st.st_size >= large_bytes:
                report.large.append(CleanItem(fp, st.st_size, "large", is_dir=False))

            # Identify old files.
            if find_old and st.st_mtime < old_cutoff:
                report.old.append(CleanItem(fp, st.st_size, "old", is_dir=False))

    # Sort results by size (largest first) for the report.
    report.junk.sort(key=lambda i: i.size, reverse=True)
    report.large.sort(key=lambda i: i.size, reverse=True)
    report.old.sort(key=lambda i: i.size, reverse=True)
    return report


def _print_section(title: str, items: List[CleanItem], limit: int = 20) -> None:
    """Renders a specific scan category as a table in the terminal."""
    if not items:
        return
    table = Table(title=title, show_lines=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Type", width=8)
    table.add_column("Path", overflow="fold")

    for idx, item in enumerate(items[:limit], 1):
        kind = "DIR" if item.is_dir else "FILE"
        table.add_row(str(idx), human_size(item.size), kind, item.path)
    console.print(table)

    if len(items) > limit:
        console.print(
            f"[dim]... and {len(items) - limit} more (hidden).[/dim]"
        )


def print_report(report: ScanReport) -> None:
    """Displays the full scan results to the user."""
    _print_section("Cache / Junk", report.junk)
    _print_section("Large Files", report.large)
    _print_section("Old Files", report.old)

    total = report.total_bytes()
    console.print(
        f"\nEstimated recoverable space: [bold green]{human_size(total)}[/bold green]"
    )


def _delete_item(item: CleanItem) -> Tuple[bool, Optional[str]]:
    """Helper to physically delete a file or directory."""
    try:
        if item.is_dir:
            shutil.rmtree(item.path, ignore_errors=False)
        else:
            os.remove(item.path)
        return True, None
    except Exception as e:
        return False, str(e)


def delete_items(items: Iterable[CleanItem]) -> int:
    """Iterates through items and deletes them, tracking progress and freed space."""
    deleted = 0
    freed = 0
    for item in items:
        ok, err = _delete_item(item)
        if ok:
            deleted += 1
            freed += item.size
            console.print(f"[dim]Deleted:[/dim] {item.path}")
        else:
            print_error(f"Failed to delete {item.path}: {err}")
    if deleted:
        print_success(
            f"Deleted {deleted} items. Space freed: {human_size(freed)}"
        )
    return deleted


def export_report(report: ScanReport, out_path: str) -> None:
    """Exports the scan results to a JSON or CSV file for external analysis."""
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
        print_success(f"Report exported to: {out_path}")
    except Exception as e:
        print_error(f"Failed to export report: {e}")


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
    """Core workflow for the Space Cleaner:
    1. Scans the directory based on user criteria.
    2. Displays or exports the report.
    3. If 'apply' is True, prompts user to confirm deletion of identified items.
    """
    if not os.path.isdir(directory):
        print_error(f"Directory '{directory}' does not exist.")
        return

    # Track free disk space before and after cleaning.
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
        print_success("Nothing to clean. Everything looks good!")
        if export_path:
            export_report(report, export_path)
        return

    print_report(report)

    if export_path:
        export_report(report, export_path)

    if not apply:
        print_warning("Simulation mode (dry-run). Nothing was deleted.")
        return

    # By default, only safe junk/cache is considered for auto-deletion.
    # User must explicitly choose to include large/old files.
    to_delete: List[CleanItem] = list(report.junk)
    if delete_large_and_old:
        to_delete += report.large + report.old

    if not to_delete:
        print_warning("No items selected for deletion.")
        return

    confirm = prompt.confirm(
        f"Delete {len(to_delete)} items ({human_size(sum(i.size for i in to_delete))})?",
        default=False,
    )
    if not confirm:
        print_warning("Cancelled. Nothing was deleted.")
        return

    delete_items(to_delete)

    # Final summary of space saved.
    free_after = _disk_free(directory)
    if free_before and free_after:
        real_freed = max(0, free_after - free_before)
        console.print(
            f"[bold]📊 Disk free before:[/bold] {human_size(free_before)}  →  "
            f"[bold]after:[/bold] {human_size(free_after)}  "
            f"([green]+{human_size(real_freed)} freed[/green])"
        )


def main():
    """CLI entry point for standalone use of the Space Cleaner."""
    parser = argparse.ArgumentParser(
        description="Space Cleaner: Detects cache, junk, large, and old files."
    )
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument(
        "--large",
        type=int,
        default=DEFAULT_LARGE_MB,
        help=f"Large file threshold in MB (default: {DEFAULT_LARGE_MB})",
    )
    parser.add_argument(
        "--old",
        type=int,
        default=DEFAULT_OLD_DAYS,
        help=f"Old file threshold in days (default: {DEFAULT_OLD_DAYS})",
    )
    parser.add_argument(
        "--no-junk", action="store_true", help="Skip junk/cache search"
    )
    parser.add_argument(
        "--no-large", action="store_true", help="Skip large file search"
    )
    parser.add_argument(
        "--no-old", action="store_true", help="Skip old file search"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletion (defaults to dry-run)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="When applying, also delete large and old files (not just cache)",
    )
    parser.add_argument(
        "--export",
        help="Export scan report to JSON or CSV (based on extension)",
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

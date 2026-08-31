import os
import hashlib
import argparse
from typing import Dict, List, Optional
from collections import defaultdict


from automation_tools.core import fs
from automation_tools.core import prompt
from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning
from automation_tools.core.report import export_rows

# Default directory and file patterns to exclude from the scan
DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", "venv", ".venv", ".cache"]


def hash_file(filepath: str, chunk_size: int = 8192) -> Optional[str]:
    """MD5 of a file, read in chunks. None if it cannot be read."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print_error(f"Error reading {filepath}: {e}")
        return None


def find_duplicates(
    directory: str,
    excludes: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """Walks `directory` and returns {md5: [paths]} for the files that appear more than once."""
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    print_step(f"Searching for duplicates in: [bold]{directory}[/bold]...")
    if patterns:
        console.print(f"[dim]Excluding: {', '.join(patterns)}[/dim]")

    hashes: Dict[str, List[str]] = defaultdict(list)
    symlinks: List[str] = []

    for filepath in fs.walk_files(directory, excludes=patterns, include_symlinks=True):
        if os.path.islink(filepath):
            # Reported, never hashed: two names for one file are not copies.
            symlinks.append(filepath)
            continue

        file_hash = hash_file(filepath)
        if file_hash:
            hashes[file_hash].append(filepath)

    if symlinks:
        console.print(f"[dim]🔗 Omitted {len(symlinks)} symlinks (not hashed).[/dim]")
        for link in symlinks[:10]:
            console.print(f"[dim]   → {link}[/dim]")
        if len(symlinks) > 10:
            console.print(f"[dim]   ... and {len(symlinks) - 10} more[/dim]")

    # Return only groups with more than one file (actual duplicates)
    return {h: paths for h, paths in hashes.items() if len(paths) > 1}


def _duplicate_rows(duplicates: Dict[str, List[str]]):
    for digest, paths in duplicates.items():
        # Oldest first, so the original is the one that keeps its role.
        for index, path in enumerate(sorted(paths, key=os.path.getmtime)):
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            yield [digest, size, "original" if index == 0 else "duplicate", path]


def _export_duplicates(duplicates: Dict[str, List[str]], out_path: str) -> bool:
    """Writes the duplicate report to `out_path` as CSV."""
    return export_rows(out_path, ["hash", "size_bytes", "role", "path"],
                       _duplicate_rows(duplicates))


def run_duplicate_finder(
    directory: str,
    auto_delete: bool = False,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
) -> None:
    """Finds duplicates under `directory`, optionally exporting a CSV or deleting them."""
    if not os.path.isdir(directory):
        print_error(f"The directory '{directory}' does not exist.")
        return

    duplicates = find_duplicates(directory, excludes=excludes)

    if not duplicates:
        print_success("No duplicate files found.")
        return

    total_wasted_bytes = 0
    console.print(f"\n[bold yellow]Found {len(duplicates)} groups of duplicates![/bold yellow]\n")

    for h, paths in duplicates.items():
        # Sort by modification time (oldest first)
        paths.sort(key=lambda x: os.path.getmtime(x))

        console.print(f"[cyan]Hash Group: {h[:8]}...[/cyan]")
        console.print(f"  [green](Original)[/green] {paths[0]}")

        file_size = os.path.getsize(paths[0])
        total_wasted_bytes += file_size * (len(paths) - 1)

        for p in paths[1:]:
            console.print(f"  [red](Copy)[/red]    {p}")
        console.print()

    mb_saved = total_wasted_bytes / (1024 * 1024)
    console.print(f"Recoverable space: [bold green]{mb_saved:.2f} MB[/bold green]\n")

    if export_path:
        _export_duplicates(duplicates, export_path)

    # default=False matters in the TUI: the modal focuses whichever button the
    # default names, and this one wipes files, so it must not open with Yes
    # under the cursor.
    confirm = auto_delete or prompt.confirm(
        "Do you want to delete all copies (keeping the original in each group)?",
        default=False,
    )

    if confirm:
        deleted = 0
        for h, paths in duplicates.items():
            # Skip the first one (original), delete the rest
            for p in paths[1:]:
                try:
                    os.remove(p)
                    deleted += 1
                    console.print(f"[dim]Deleted: {p}[/dim]")
                except Exception as e:
                    print_error(f"Error deleting {p}: {e}")

        print_success(f"Process completed! {deleted} files were deleted.")
    else:
        print_warning("No files were deleted.")


def main():
    """Main entry point for the duplicate finder CLI.
    """
    parser = argparse.ArgumentParser(description="Duplicate File Finder")
    parser.add_argument("directory", help="Directory to scan")
    parser.add_argument("--delete", action="store_true", help="Automatically delete duplicates")
    parser.add_argument(
        "--exclude",
        help="Comma-separated glob patterns to exclude (e.g.: '*.tmp,backup_*')",
    )
    parser.add_argument("--export", help="Export a CSV report of duplicates")
    args = parser.parse_args()

    excludes = [p.strip() for p in args.exclude.split(",")] if args.exclude else None
    run_duplicate_finder(args.directory, args.delete, excludes=excludes, export_path=args.export)


if __name__ == "__main__":
    main()

import os
import hashlib
import argparse
import csv
import fnmatch
from typing import Dict, List, Optional
from collections import defaultdict

import questionary

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

# Default directory and file patterns to exclude from the scan
DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", "venv", ".venv", ".cache"]


def hash_file(filepath: str, chunk_size: int = 8192) -> Optional[str]:
    """
    Calculates the MD5 hash of a file.
    
    Args:
        filepath (str): Path to the file to hash.
        chunk_size (int): Size of chunks to read from the file.
        
    Returns:
        Optional[str]: Hexadecimal MD5 hash string, or None if an error occurs.
    """
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print_error(f"Error reading {filepath}: {e}")
        return None


def _matches_any(name: str, patterns: List[str]) -> bool:
    """
    Checks if a name matches any of the given glob patterns.
    
    Args:
        name (str): The name (file or directory) to check.
        patterns (List[str]): A list of glob patterns.
        
    Returns:
        bool: True if it matches any pattern, False otherwise.
    """
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def find_duplicates(
    directory: str,
    excludes: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """
    Recursively finds duplicate files in a directory, respecting exclude patterns.
    
    Args:
        directory (str): The root directory to start the search.
        excludes (Optional[List[str]]): Additional glob patterns to exclude.
        
    Returns:
        Dict[str, List[str]]: A dictionary mapping MD5 hashes to lists of duplicate file paths.
    """
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    print_step(f"Searching for duplicates in: [bold]{directory}[/bold]...")
    if patterns:
        console.print(f"[dim]Excluding: {', '.join(patterns)}[/dim]")

    hashes: Dict[str, List[str]] = defaultdict(list)
    symlinks: List[str] = []

    for root, dirs, files in os.walk(directory):
        # Prune excluded directories in-place to avoid traversing them.
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
        console.print(f"[dim]🔗 Omitted {len(symlinks)} symlinks (not hashed).[/dim]")
        for link in symlinks[:10]:
            console.print(f"[dim]   → {link}[/dim]")
        if len(symlinks) > 10:
            console.print(f"[dim]   ... and {len(symlinks) - 10} more[/dim]")

    # Return only groups with more than one file (actual duplicates)
    return {h: paths for h, paths in hashes.items() if len(paths) > 1}


def _export_duplicates(duplicates: Dict[str, List[str]], out_path: str) -> None:
    """
    Exports the duplicate file report to a CSV file.
    
    Args:
        duplicates (Dict[str, List[str]]): Dictionary of duplicates.
        out_path (str): Path to the output CSV file.
    """
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["hash", "size_bytes", "role", "path"])
            for h, paths in duplicates.items():
                # Sort by modification time to identify the 'oldest' as the potential original
                paths_sorted = sorted(paths, key=os.path.getmtime)
                for i, p in enumerate(paths_sorted):
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = 0
                    role = "original" if i == 0 else "duplicate"
                    writer.writerow([h, size, role, p])
        print_success(f"Report exported to: {out_path}")
    except Exception as e:
        print_error(f"Could not export report: {e}")


def run_duplicate_finder(
    directory: str,
    auto_delete: bool = False,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
) -> None:
    """
    Core function to find and optionally delete duplicate files.
    
    Args:
        directory (str): Directory to scan.
        auto_delete (bool): If True, delete duplicates without asking.
        excludes (Optional[List[str]]): List of patterns to exclude.
        export_path (Optional[str]): Path to export CSV report.
    """
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

    confirm = True if auto_delete else questionary.confirm("Do you want to delete all copies (keeping the original in each group)?").ask()

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
    """
    Main entry point for the duplicate finder CLI.
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

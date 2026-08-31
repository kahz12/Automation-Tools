import argparse
import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from automation_tools.core import fs
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)
from rich.table import Table

# Create a checksum manifest of a folder (one hash per file) and verify it
# later to detect corrupted, modified, missing or new files. Handy for
# validating backups, SD-card copies, or long-term archives.
#
# The manifest uses the GNU coreutils format ("<hash>  <relative/path>"), so
# it is also verifiable with standard tools: `sha256sum -c checksums.sha256`.
# Verification is read-only; creating a manifest only writes one text file.

# Supported hash algorithms → the default manifest filename for each.
ALGORITHMS = {
    "md5": "checksums.md5",
    "sha1": "checksums.sha1",
    "sha256": "checksums.sha256",
    "sha512": "checksums.sha512",
}
DEFAULT_ALGORITHM = "sha256"

# Hex-digest length → algorithm, used to auto-detect a manifest's algorithm.
_DIGEST_LENGTHS = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}

# Manifest names probed (in order) when verifying without an explicit path.
_DEFAULT_MANIFEST_NAMES = list(ALGORITHMS.values()) + ["SHA256SUMS", "MD5SUMS"]


@dataclass
class VerifyResult:
    """Outcome of checking a directory against a manifest."""
    ok: List[str] = field(default_factory=list)        # unchanged files
    modified: List[str] = field(default_factory=list)  # hash mismatch
    missing: List[str] = field(default_factory=list)   # in manifest, not on disk
    extra: List[str] = field(default_factory=list)     # on disk, not in manifest
    unreadable: List[str] = field(default_factory=list)

    @property
    def intact(self) -> bool:
        return not (self.modified or self.missing or self.unreadable)


def hash_file(filepath: str, algorithm: str = DEFAULT_ALGORITHM,
              chunk_size: int = 65536) -> Optional[str]:
    """Returns the hex digest of a file, or None if it cannot be read."""
    hasher = hashlib.new(algorithm)
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def collect_files(
    directory: str,
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
    skip: Optional[List[str]] = None,
) -> List[str]:
    """Returns the sorted relative (forward-slashed) paths of every regular file
    under `directory`, applying exclude patterns and (unless include_hidden)
    skipping dotfiles. Symlinks are never followed. Paths in `skip` (e.g. the
    manifest itself) are always omitted.
    """
    exclude = exclude or []
    skip_set = {os.path.abspath(s) for s in (skip or [])}
    directory = os.path.abspath(directory)
    files: List[str] = []

    for fp in fs.walk_files(directory, excludes=exclude, match_relative=True,
                            include_hidden=include_hidden):
        if os.path.abspath(fp) in skip_set:
            continue
        files.append(os.path.relpath(fp, directory).replace(os.sep, "/"))

    return files


def build_manifest(
    directory: str,
    algorithm: str = DEFAULT_ALGORITHM,
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
    skip: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """Hashes every collected file under `directory`.

    Returns (entries, unreadable) where entries maps relative path → hex
    digest and unreadable lists files that could not be opened.
    """
    entries: Dict[str, str] = {}
    unreadable: List[str] = []
    for rel in collect_files(directory, exclude, include_hidden, skip):
        digest = hash_file(os.path.join(directory, rel), algorithm)
        if digest is None:
            unreadable.append(rel)
        else:
            entries[rel] = digest
    return entries, unreadable


def write_manifest(entries: Dict[str, str], out_path: str) -> None:
    """Writes entries in GNU coreutils format: '<hash>  <path>' per line."""
    with open(out_path, "w", encoding="utf-8") as f:
        for rel in sorted(entries):
            f.write(f"{entries[rel]}  {rel}\n")


def parse_manifest(manifest_path: str) -> Tuple[str, Dict[str, str]]:
    """Reads a coreutils-style manifest, returning (algorithm, entries).

    The algorithm is inferred from the digest length. Raises ValueError if the
    file has no valid lines or mixes digest lengths.
    """
    entries: Dict[str, str] = {}
    algorithm: Optional[str] = None

    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # "<hash>  <path>", and coreutils also allows "<hash> *<path>" (binary)
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"malformed manifest line: {line!r}")
            digest, path = parts[0].lower(), parts[1]
            if path.startswith("*"):
                path = path[1:]
            alg = _DIGEST_LENGTHS.get(len(digest))
            if alg is None or not all(c in "0123456789abcdef" for c in digest):
                raise ValueError(f"unrecognized digest on line: {line!r}")
            if algorithm is None:
                algorithm = alg
            elif algorithm != alg:
                raise ValueError("manifest mixes different digest lengths")
            entries[path.replace(os.sep, "/")] = digest

    if not entries or algorithm is None:
        raise ValueError("manifest contains no checksum entries")
    return algorithm, entries


def find_manifest(directory: str) -> Optional[str]:
    """Returns the first well-known manifest file found inside `directory`."""
    for name in _DEFAULT_MANIFEST_NAMES:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def verify_manifest(
    directory: str,
    manifest_path: str,
    check_extra: bool = False,
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
) -> VerifyResult:
    """Re-hashes every file listed in the manifest and compares digests.

    With check_extra, also reports files present on disk but absent from the
    manifest (the manifest file itself is never counted as extra).
    """
    algorithm, expected = parse_manifest(manifest_path)
    result = VerifyResult()

    for rel, digest in expected.items():
        fp = os.path.join(directory, rel)
        if not os.path.isfile(fp):
            result.missing.append(rel)
            continue
        actual = hash_file(fp, algorithm)
        if actual is None:
            result.unreadable.append(rel)
        elif actual == digest:
            result.ok.append(rel)
        else:
            result.modified.append(rel)

    if check_extra:
        on_disk = collect_files(directory, exclude, include_hidden, skip=[manifest_path])
        result.extra = [rel for rel in on_disk if rel not in expected]

    return result


def _print_group(title: str, style: str, items: List[str], limit: int = 30) -> None:
    if not items:
        return
    console.print(f"\n[bold {style}]{title} ({len(items)}):[/bold {style}]")
    for rel in items[:limit]:
        console.print(f"  [{style}]•[/{style}] {rel}")
    if len(items) > limit:
        console.print(f"[dim]  ... and {len(items) - limit} more.[/dim]")


def _run_create(
    directory: str,
    output: Optional[str],
    algorithm: str,
    exclude: Optional[List[str]],
    include_hidden: bool,
) -> bool:
    if not os.path.isdir(directory):
        print_error(f"The directory '{directory}' does not exist.")
        return False
    algorithm = algorithm if algorithm in ALGORITHMS else DEFAULT_ALGORITHM
    output = output or os.path.join(directory, ALGORITHMS[algorithm])

    print_step(f"Hashing files in [bold]{directory}[/bold] ({algorithm})…")
    entries, unreadable = build_manifest(
        directory, algorithm, exclude, include_hidden, skip=[output]
    )
    for rel in unreadable:
        print_warning(f"Could not read: {rel}")
    if not entries:
        print_warning("No files matched — nothing to hash.")
        return False

    try:
        write_manifest(entries, output)
    except OSError as e:
        print_error(f"Could not write manifest: {e}")
        return False

    print_success(f"Manifest created: {output} — {len(entries)} file(s) hashed.")
    console.print(f"[dim]Verify later with this tool or: {algorithm}sum -c {os.path.basename(output)}[/dim]")
    return True


def _run_verify(
    directory: str,
    manifest: Optional[str],
    check_extra: bool,
    exclude: Optional[List[str]],
    include_hidden: bool,
) -> bool:
    if not os.path.isdir(directory):
        print_error(f"The directory '{directory}' does not exist.")
        return False

    manifest = manifest or find_manifest(directory)
    if not manifest:
        print_error(
            "No manifest found. Provide one, or create it first with the 'create' action."
        )
        return False
    if not os.path.isfile(manifest):
        print_error(f"The manifest '{manifest}' does not exist.")
        return False

    print_step(f"Verifying [bold]{directory}[/bold] against {os.path.basename(manifest)}…")
    try:
        result = verify_manifest(directory, manifest, check_extra, exclude, include_hidden)
    except ValueError as e:
        print_error(f"Invalid manifest: {e}")
        return False

    total = len(result.ok) + len(result.modified) + len(result.missing) + len(result.unreadable)
    table = Table(title="Integrity report", header_style="bold cyan")
    table.add_column("Status")
    table.add_column("Files", justify="right")
    table.add_row("[green]✓ Intact[/green]", str(len(result.ok)))
    table.add_row("[red]✗ Modified[/red]", str(len(result.modified)))
    table.add_row("[red]? Missing[/red]", str(len(result.missing)))
    if result.unreadable:
        table.add_row("[yellow]! Unreadable[/yellow]", str(len(result.unreadable)))
    if check_extra:
        table.add_row("[yellow]+ Not in manifest[/yellow]", str(len(result.extra)))
    console.print(table)

    _print_group("Modified files", "red", result.modified)
    _print_group("Missing files", "red", result.missing)
    _print_group("Unreadable files", "yellow", result.unreadable)
    if check_extra:
        _print_group("New files not in manifest", "yellow", result.extra)

    if result.intact:
        print_success(f"All {total} file(s) verified — the data is intact.")
        if check_extra and result.extra:
            print_warning(f"{len(result.extra)} new file(s) are not covered by the manifest.")
        return True

    print_error(
        f"Integrity check FAILED: {len(result.modified)} modified, "
        f"{len(result.missing)} missing, {len(result.unreadable)} unreadable."
    )
    return False


def run_integrity(
    action: str,
    directory: str,
    manifest: Optional[str] = None,
    output: Optional[str] = None,
    algorithm: str = DEFAULT_ALGORITHM,
    exclude: Optional[List[str]] = None,
    include_hidden: bool = False,
    check_extra: bool = False,
) -> bool:
    """Single entry point shared by the CLI and the interactive menu.

    action:
        "create": hash `directory` and write a checksum manifest to `output`.
        "verify": compare `directory` against `manifest` (auto-detected if omitted).
    """
    if action == "create":
        return _run_create(directory, output, algorithm, exclude, include_hidden)
    if action == "verify":
        return _run_verify(directory, manifest, check_extra, exclude, include_hidden)

    print_error(f"Unknown action: '{action}'. Use create or verify.")
    return False


def main() -> None:
    """CLI entry point for the Integrity Checker."""
    parser = argparse.ArgumentParser(
        description="Integrity Checker: create a checksum manifest of a folder and verify it later."
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_create = sub.add_parser("create", help="Hash a folder and write a checksum manifest.")
    p_create.add_argument("directory", help="Folder to hash.")
    p_create.add_argument("-o", "--output", help="Manifest path (default: <directory>/checksums.<alg>).")
    p_create.add_argument(
        "-a", "--algorithm", default=DEFAULT_ALGORITHM, choices=list(ALGORITHMS),
        help=f"Hash algorithm (default: {DEFAULT_ALGORITHM}).",
    )
    p_create.add_argument(
        "-x", "--exclude", nargs="*", default=[],
        help="Glob patterns to exclude (e.g. '*.log' '__pycache__').",
    )
    p_create.add_argument("--hidden", action="store_true", help="Include hidden dotfiles.")

    p_verify = sub.add_parser("verify", help="Verify a folder against a manifest (read-only).")
    p_verify.add_argument("directory", help="Folder to verify.")
    p_verify.add_argument(
        "-m", "--manifest",
        help="Manifest file (default: auto-detect checksums.* inside the folder).",
    )
    p_verify.add_argument(
        "--extra", action="store_true",
        help="Also report files on disk that are not in the manifest.",
    )
    p_verify.add_argument(
        "-x", "--exclude", nargs="*", default=[],
        help="Glob patterns to ignore in the --extra scan.",
    )
    p_verify.add_argument("--hidden", action="store_true", help="Include hidden dotfiles in the --extra scan.")

    args = parser.parse_args()

    ok = run_integrity(
        action=args.action,
        directory=args.directory,
        manifest=getattr(args, "manifest", None),
        output=getattr(args, "output", None),
        algorithm=getattr(args, "algorithm", DEFAULT_ALGORITHM),
        exclude=getattr(args, "exclude", None),
        include_hidden=getattr(args, "hidden", False),
        check_extra=getattr(args, "extra", False),
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

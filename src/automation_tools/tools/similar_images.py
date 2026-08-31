import argparse
import csv
import fnmatch
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import questionary
from rich.table import Table

from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Finds photos that look the same without being the same file.
#
# The Duplicate Detector hashes bytes, so it only ever catches exact copies.
# That misses what actually fills a phone: the same picture resized, sent
# through a chat app and re-compressed, saved as another format, or shot twice
# in a burst. Those are different files down to the last byte and identical to
# the eye.
#
# The trick is a perceptual hash (dHash): shrink the image to a 9x8 greyscale
# thumbnail and record, for each pixel, whether it is brighter than the one to
# its right. That throws away resolution, colour depth and compression noise
# and keeps the coarse structure, so two versions of one photo land on the same
# 64-bit value. Comparing two hashes is a XOR and a bit count.
#
# Only Pillow is needed, which the project already depends on: no numpy, no
# imagehash, no C extensions, so it runs the same on Termux as anywhere else.

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif")

DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", "venv", ".venv", ".cache", ".thumbnails"]

# Hash side, in pixels. 8 gives the 64-bit hash the thresholds below assume.
HASH_SIZE = 8

# Hamming distance under which two images are called the same picture. 0 is
# pixel-structure identical; 10 starts pulling in merely similar compositions.
DEFAULT_THRESHOLD = 5
MAX_THRESHOLD = 64


@dataclass
class ImageInfo:
    """One scanned image and everything needed to rank it inside its group."""
    path: str
    hash: int
    size: int      # bytes on disk
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


def human_size(n: int) -> str:
    """Converts a byte count into a human-readable string (e.g. 1.5 MB)."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# ── Hashing ──────────────────────────────────────────────────────────────────
def dhash(path: str, size: int = HASH_SIZE) -> Optional[Tuple[int, int, int]]:
    """Perceptual hash of an image, as (hash, width, height). None if unreadable.

    The image is reduced to (size+1) x size greyscale pixels and each row turns
    into `size` bits comparing neighbouring brightness. Scaling, re-encoding and
    a colour-to-grey conversion all leave the result unchanged.
    """
    try:
        with Image.open(path) as img:
            width, height = img.size
            # tobytes() on mode "L" is one byte per pixel, row-major. getdata()
            # would do as well but is deprecated from Pillow 14.
            small = img.convert("L").resize((size + 1, size), Image.LANCZOS)
            pixels = small.tobytes()
    except Exception:
        return None

    bits = 0
    stride = size + 1
    for row in range(size):
        base = row * stride
        for col in range(size):
            bits = (bits << 1) | int(pixels[base + col] > pixels[base + col + 1])
    return bits, width, height


def hamming(a: int, b: int) -> int:
    """Number of differing bits between two hashes."""
    return (a ^ b).bit_count()


# ── Scanning ─────────────────────────────────────────────────────────────────
def _matches_any(name: str, patterns: List[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def scan_images(
    directory: str,
    recursive: bool = True,
    excludes: Optional[List[str]] = None,
) -> Tuple[List[ImageInfo], int]:
    """Hashes every supported image under `directory`.

    Returns (images, unreadable_count). Symlinks are never followed.
    """
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    images: List[ImageInfo] = []
    unreadable = 0

    def consider(full: str, name: str) -> None:
        nonlocal unreadable
        if not name.lower().endswith(SUPPORTED_EXTENSIONS):
            return
        if _matches_any(name, patterns) or os.path.islink(full):
            return
        result = dhash(full)
        if result is None:
            unreadable += 1
            return
        bits, width, height = result
        try:
            size = os.path.getsize(full)
        except OSError:
            unreadable += 1
            return
        images.append(ImageInfo(full, bits, size, width, height))

    if recursive:
        for root, dirs, names in os.walk(directory):
            dirs[:] = [d for d in dirs if not _matches_any(d, patterns)]
            for name in sorted(names):
                consider(os.path.join(root, name), name)
    else:
        for name in sorted(os.listdir(directory)):
            full = os.path.join(directory, name)
            if os.path.isfile(full):
                consider(full, name)

    return images, unreadable


def group_similar(images: List[ImageInfo], threshold: int = DEFAULT_THRESHOLD) -> List[List[ImageInfo]]:
    """Clusters images whose hashes are within `threshold` bits of each other.

    Similarity is not transitive, so this uses union-find: A near B and B near C
    puts all three in one group even when A and C are further apart. That is the
    behaviour you want for a burst of shots that drift frame by frame.

    Exactly equal hashes are merged first through a dictionary, so the pairwise
    pass only runs over distinct hashes. On a real photo folder, where most
    matches are re-saves of the same picture, that is the difference between a
    quick scan and a quadratic one.
    """
    parent = list(range(len(images)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    by_hash: Dict[int, List[int]] = {}
    for index, image in enumerate(images):
        by_hash.setdefault(image.hash, []).append(index)

    representatives = []
    for indexes in by_hash.values():
        for other in indexes[1:]:
            union(indexes[0], other)
        representatives.append(indexes[0])

    if threshold > 0:
        for i in range(len(representatives)):
            for j in range(i + 1, len(representatives)):
                a, b = representatives[i], representatives[j]
                if hamming(images[a].hash, images[b].hash) <= threshold:
                    union(a, b)

    clusters: Dict[int, List[ImageInfo]] = {}
    for index in range(len(images)):
        clusters.setdefault(find(index), []).append(images[index])

    groups = [group for group in clusters.values() if len(group) > 1]
    for group in groups:
        group.sort(key=_rank, reverse=True)
    groups.sort(key=lambda g: sum(i.size for i in g[1:]), reverse=True)
    return groups


def _rank(image: ImageInfo) -> Tuple[int, int, str]:
    """Sort key that puts the version worth keeping first.

    Most pixels wins, then the larger file (less compression), then the path so
    two identical candidates always order the same way.
    """
    return image.pixels, image.size, image.path


def reclaimable_bytes(groups: List[List[ImageInfo]]) -> int:
    """Bytes freed by keeping only the best copy in every group."""
    return sum(image.size for group in groups for image in group[1:])


# ── Reporting ────────────────────────────────────────────────────────────────
def print_groups(groups: List[List[ImageInfo]], limit: int = 20) -> None:
    """Renders each group as a table, keeper first."""
    for number, group in enumerate(groups[:limit], 1):
        keeper = group[0]
        table = Table(
            title=f"Group {number} — {len(group)} versions of the same picture",
            header_style="bold cyan", title_style="bold magenta",
        )
        table.add_column("Keep", width=6)
        table.add_column("Resolution", justify="right")
        table.add_column("Size", justify="right", style="yellow")
        table.add_column("Diff", justify="right", style="dim")
        table.add_column("Path", overflow="fold")
        for image in group:
            is_keeper = image is keeper
            table.add_row(
                "[green]✓[/green]" if is_keeper else "[red]✗[/red]",
                f"{image.width}x{image.height}",
                human_size(image.size),
                "—" if is_keeper else str(hamming(keeper.hash, image.hash)),
                image.path,
            )
        console.print(table)
    if len(groups) > limit:
        console.print(f"[dim]... and {len(groups) - limit} more group(s) (hidden).[/dim]")


def export_groups(groups: List[List[ImageInfo]], out_path: str) -> None:
    """Writes the groups to `out_path` as CSV."""
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["group", "role", "width", "height", "size_bytes", "distance", "path"])
            for number, group in enumerate(groups, 1):
                keeper = group[0]
                for image in group:
                    is_keeper = image is keeper
                    writer.writerow([
                        number,
                        "keep" if is_keeper else "duplicate",
                        image.width, image.height, image.size,
                        0 if is_keeper else hamming(keeper.hash, image.hash),
                        image.path,
                    ])
        print_success(f"Report exported to: {out_path}")
    except OSError as e:
        print_error(f"Could not export report: {e}")


# ── Entry point ──────────────────────────────────────────────────────────────
def run_similar_images(
    directory: str,
    threshold: int = DEFAULT_THRESHOLD,
    recursive: bool = True,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
    apply: bool = False,
) -> bool:
    """Finds near-duplicate images and, with `apply`, deletes the extra copies.

    Nothing is removed unless `apply` is on and the confirmation is accepted;
    the best version of each group is always kept.

    Returns True when the scan completed, whether or not it found anything.
    """
    if not HAS_PILLOW:
        print_error("Pillow is not installed. Install it with 'pip install Pillow'.")
        return False
    if not os.path.isdir(directory):
        print_error(f"The directory '{directory}' does not exist.")
        return False
    if not 0 <= threshold <= MAX_THRESHOLD:
        print_error(f"Threshold must be between 0 and {MAX_THRESHOLD}.")
        return False

    print_step(f"Hashing images in [bold]{directory}[/bold] (threshold {threshold})…")
    images, unreadable = scan_images(directory, recursive=recursive, excludes=excludes)
    if unreadable:
        print_warning(f"{unreadable} file(s) could not be read as images.")
    if not images:
        print_error(f"No images found ({', '.join(SUPPORTED_EXTENSIONS)}).")
        return False

    console.print(f"[dim]{len(images)} image(s) hashed.[/dim]")
    groups = group_similar(images, threshold=threshold)

    if not groups:
        print_success("No visually similar images found.")
        return True

    total = sum(len(group) for group in groups)
    console.print(
        f"\n[bold yellow]{len(groups)} group(s) covering {total} image(s).[/bold yellow]\n"
    )
    print_groups(groups)

    reclaimable = reclaimable_bytes(groups)
    console.print(
        f"\nRecoverable space: [bold green]{human_size(reclaimable)}[/bold green] "
        f"([dim]keeping the best copy of each group[/dim])\n"
    )

    if export_path:
        export_groups(groups, export_path)

    if not apply:
        print_warning("Simulation mode (dry-run). Nothing was deleted.")
        return True

    doomed = [image for group in groups for image in group[1:]]
    confirm = questionary.confirm(
        f"Delete {len(doomed)} extra copy/copies ({human_size(reclaimable)})? "
        "The best version of each group is kept. This cannot be undone.",
        default=False,
    ).ask()
    if not confirm:
        print_warning("Cancelled. Nothing was deleted.")
        return True

    deleted = 0
    freed = 0
    for image in doomed:
        try:
            os.remove(image.path)
            deleted += 1
            freed += image.size
            console.print(f"[dim]Deleted:[/dim] {image.path}")
        except OSError as e:
            print_error(f"Could not delete {image.path}: {e}")

    print_success(f"Deleted {deleted}/{len(doomed)} file(s). Space freed: {human_size(freed)}")
    return True


def main() -> None:
    """CLI entry point for the Similar Photo Finder."""
    parser = argparse.ArgumentParser(
        description="Find photos that look the same even when the files differ."
    )
    parser.add_argument("directory", help="Folder to scan.")
    parser.add_argument(
        "-t", "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Bits of difference still counted as the same picture "
             f"(0 = strict, default: {DEFAULT_THRESHOLD}).",
    )
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse into subfolders.")
    parser.add_argument(
        "-x", "--exclude", nargs="*", default=[],
        help="Glob patterns to skip (e.g. '*_thumb.jpg').",
    )
    parser.add_argument("--export", help="Write a CSV report to this path.")
    parser.add_argument(
        "--apply", action="store_true",
        help="Delete the extra copies after confirming (defaults to dry-run).",
    )
    args = parser.parse_args()

    ok = run_similar_images(
        directory=args.directory,
        threshold=args.threshold,
        recursive=not args.no_recursive,
        excludes=args.exclude,
        export_path=args.export,
        apply=args.apply,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

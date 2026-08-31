import fnmatch
import os
from typing import Iterator, Optional, Sequence

# One directory walk for the whole toolkit.
#
# Twelve tools had grown their own. Seven of them skipped symlinks and five did
# not; two pruned their own output folder and the rest would happily re-process
# what they had just written; three carried a byte-identical copy of the
# exclude list. None of that was a decision, it was drift, and every fix had to
# be made twelve times.
#
# The defaults here are the careful ones: symlinks are not followed, unreadable
# directories are skipped instead of raising, and the order is sorted so two
# runs over the same tree produce the same report.

DEFAULT_EXCLUDES = [".git", "node_modules", "__pycache__", "venv", ".venv", ".cache"]


def matches_any(name: str, patterns: Sequence[str]) -> bool:
    """Whether `name` matches any of the glob patterns."""
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def is_hidden(rel_path: str) -> bool:
    """Whether any component of a relative path starts with a dot."""
    return any(part.startswith(".") for part in rel_path.replace(os.sep, "/").split("/") if part)


def walk_files(
    path: str,
    *,
    recursive: bool = True,
    excludes: Optional[Sequence[str]] = None,
    extensions: Optional[Sequence[str]] = None,
    include_hidden: bool = True,
    include_symlinks: bool = False,
    skip_dir: Optional[str] = None,
    match_relative: bool = False,
) -> Iterator[str]:
    """Yields the files under `path`, in a stable order.

    A path that is already a file yields just itself, still subject to the
    filters, so callers do not need the usual isfile/isdir branch.

    `excludes` are globs tested against each file's name and each directory's
    name; with `match_relative` the path relative to `path` counts too, which
    is what a pattern like "docs/*.md" needs.

    `skip_dir` is never descended into. It exists for the tools that write
    their results back into the tree they are reading: without it the second
    run picks up the first run's output.

    Symlinks are skipped unless asked for, and symlinked directories are never
    followed at all, which is what stops a loop from walking forever.
    """
    patterns = list(excludes or [])
    suffixes = tuple(e.lower() for e in extensions) if extensions else None
    skip = os.path.abspath(skip_dir) if skip_dir else None
    root_path = path

    def _wanted(full: str, name: str) -> bool:
        if suffixes and not name.lower().endswith(suffixes):
            return False
        if not include_symlinks and os.path.islink(full):
            return False
        if patterns:
            subjects = [name]
            if match_relative:
                # A pattern should catch "docs/notes.md" as readily as
                # "notes.md", so both the relative path and the bare name are
                # candidates. Directory components are already handled by
                # pruning them out of the walk.
                subjects.append(os.path.relpath(full, root_path).replace(os.sep, "/"))
            if any(matches_any(subject, patterns) for subject in subjects):
                return False
        if not include_hidden:
            rel = os.path.relpath(full, root_path)
            if is_hidden(rel if rel != "." else name):
                return False
        return True

    if os.path.isfile(path):
        if _wanted(path, os.path.basename(path)):
            yield path
        return

    if not recursive:
        try:
            names = sorted(os.listdir(path))
        except OSError:
            return
        for name in names:
            full = os.path.join(path, name)
            if os.path.isfile(full) and _wanted(full, name):
                yield full
        return

    # onerror defaults to swallowing the error entirely; a folder we cannot
    # read is a folder with nothing in it as far as any of these tools go.
    for root, dirs, names in os.walk(path, onerror=lambda _: None):
        dirs[:] = sorted(
            d for d in dirs
            if not os.path.islink(os.path.join(root, d))
            and not (patterns and matches_any(d, patterns))
            and not (skip and os.path.abspath(os.path.join(root, d)) == skip)
            and not (not include_hidden and d.startswith("."))
        )
        for name in sorted(names):
            full = os.path.join(root, name)
            if _wanted(full, name):
                yield full

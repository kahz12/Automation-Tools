"""Tests for the shared directory walk.

Twelve tools used to carry their own version of this, and they disagreed:
seven skipped symlinks and five followed them, two pruned their own output
folder and the rest re-read what they had just written. These are the
guarantees that now hold everywhere.
"""
import os

import pytest

from conftest import needs_symlinks

from automation_tools.core import fs


@pytest.fixture
def tree(tmp_path):
    """A small tree with the awkward cases in it."""
    (tmp_path / "sub" / "deep").mkdir(parents=True)
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".hidden").mkdir()
    for rel in ("a.txt", "b.log", "sub/c.txt", "sub/deep/d.log",
                "__pycache__/cached.txt", ".hidden/secret.txt", ".dotfile"):
        (tmp_path / rel).write_text("x", encoding="utf-8")
    return tmp_path


def names(paths, root):
    return sorted(os.path.relpath(p, root).replace(os.sep, "/") for p in paths)


def test_walks_the_whole_tree_by_default(tree):
    assert names(fs.walk_files(str(tree)), tree) == [
        ".dotfile", ".hidden/secret.txt", "__pycache__/cached.txt",
        "a.txt", "b.log", "sub/c.txt", "sub/deep/d.log",
    ]


def test_a_single_file_yields_itself(tmp_path):
    target = tmp_path / "only.txt"
    target.write_text("x", encoding="utf-8")
    assert list(fs.walk_files(str(target))) == [str(target)]


def test_a_single_file_still_obeys_the_filters(tmp_path):
    target = tmp_path / "only.txt"
    target.write_text("x", encoding="utf-8")
    assert list(fs.walk_files(str(target), extensions=(".png",))) == []


def test_non_recursive_stays_in_the_top_folder(tree):
    assert names(fs.walk_files(str(tree), recursive=False), tree) == [
        ".dotfile", "a.txt", "b.log"]


def test_excludes_prune_directories_and_drop_files(tree):
    found = names(fs.walk_files(str(tree), excludes=["__pycache__", "*.log"]), tree)
    assert "__pycache__/cached.txt" not in found
    assert not any(f.endswith(".log") for f in found)


def test_extensions_filter_case_insensitively(tmp_path):
    (tmp_path / "a.JPG").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    assert names(fs.walk_files(str(tmp_path), extensions=(".jpg",)), tmp_path) == ["a.JPG"]


def test_hidden_files_and_folders_can_be_left_out(tree):
    found = names(fs.walk_files(str(tree), include_hidden=False), tree)
    assert found == ["__pycache__/cached.txt", "a.txt", "b.log",
                     "sub/c.txt", "sub/deep/d.log"]


@needs_symlinks
def test_symlinked_files_are_skipped_unless_asked_for(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("x", encoding="utf-8")
    os.symlink(str(real), str(tmp_path / "link.txt"))

    assert names(fs.walk_files(str(tmp_path)), tmp_path) == ["real.txt"]
    assert names(fs.walk_files(str(tmp_path), include_symlinks=True), tmp_path) == [
        "link.txt", "real.txt"]


@needs_symlinks
def test_a_symlinked_directory_is_never_followed(tmp_path):
    """A link pointing at an ancestor is how a walk runs forever."""
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "f.txt").write_text("x", encoding="utf-8")
    os.symlink(str(tmp_path), str(tmp_path / "real" / "loop"))

    assert names(fs.walk_files(str(tmp_path)), tmp_path) == ["real/f.txt"]


def test_the_output_folder_can_be_kept_out_of_the_walk(tree):
    out = tree / "sub"
    found = names(fs.walk_files(str(tree), skip_dir=str(out)), tree)
    assert not any(f.startswith("sub/") for f in found)


def test_match_relative_also_matches_the_bare_name(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    (tmp_path / "keep.txt").write_text("x", encoding="utf-8")

    assert names(fs.walk_files(str(tmp_path), excludes=["docs/*.md"],
                               match_relative=True), tmp_path) == ["keep.txt", "notes.md"]
    assert names(fs.walk_files(str(tmp_path), excludes=["notes.md"],
                               match_relative=True), tmp_path) == ["keep.txt"]


def test_the_order_is_stable_across_runs(tree):
    assert list(fs.walk_files(str(tree))) == list(fs.walk_files(str(tree)))


def test_an_unreadable_folder_is_skipped_not_raised(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "f.txt").write_text("x", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("x", encoding="utf-8")
    os.chmod(locked, 0o000)
    try:
        found = names(fs.walk_files(str(tmp_path)), tmp_path)
    finally:
        os.chmod(locked, 0o755)
    assert "ok.txt" in found


def test_a_missing_path_yields_nothing(tmp_path):
    assert list(fs.walk_files(str(tmp_path / "nope"))) == []


def test_matches_any_and_is_hidden():
    assert fs.matches_any("foo.tmp", ["*.tmp"]) is True
    assert fs.matches_any("foo.txt", ["*.tmp"]) is False
    assert fs.is_hidden("a/.b/c") is True
    assert fs.is_hidden("a/b/c") is False

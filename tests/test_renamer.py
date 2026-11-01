import os

import pytest

from automation_tools.tools import renamer


def test_build_pattern_regex():
    rx = renamer._build_pattern_regex("doc_{:03d}")
    assert rx is not None
    m = rx.match("doc_007")
    assert m and m.group(1) == "007"
    assert renamer._build_pattern_regex("no-placeholder") is None


def test_split_pattern_files():
    files = ["doc_001.txt", "doc_002.txt", "other.txt"]
    matching, pending, max_index = renamer._split_pattern_files(files, "doc_{:03d}")
    assert set(matching) == {"doc_001.txt", "doc_002.txt"}
    assert pending == ["other.txt"]
    assert max_index == 2


def test_generate_new_name_patron():
    assert renamer.generate_new_name("x.txt", ".", "patron", index=5, pattern="f_{:03d}") == "f_005.txt"


def test_generate_new_name_reemplazo():
    out = renamer.generate_new_name("foo_bar.txt", ".", "reemplazo", old_text="bar", new_text="baz")
    assert out == "foo_baz.txt"


def test_detect_dominant_pattern(tmp_path):
    for i in range(1, 4):
        (tmp_path / f"photo_{i:03d}.jpg").write_text("x")
    pattern, count, max_index = renamer.detect_dominant_pattern(str(tmp_path))
    assert pattern == "photo_{:03d}"
    assert count == 3
    assert max_index == 3


def test_auto_version_name(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert renamer._auto_version_name(str(tmp_path), "a.txt", set()) == "a_1.txt"
    assert renamer._auto_version_name(str(tmp_path), "b.txt", set()) == "b.txt"


def test_run_massive_rename_dry_run(tmp_path):
    for n in ("a.txt", "b.txt"):
        (tmp_path / n).write_text("x")
    renamer.run_massive_rename(str(tmp_path), mode="patron", pattern="f_{:03d}", apply_changes=False)
    # Dry-run leaves originals in place.
    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "f_001.txt").exists()


def test_run_massive_rename_apply(tmp_path):
    for n in ("a.txt", "b.txt"):
        (tmp_path / n).write_text("x")
    renamer.run_massive_rename(str(tmp_path), mode="patron", pattern="f_{:03d}", apply_changes=True)
    names = set(os.listdir(tmp_path))
    assert {"f_001.txt", "f_002.txt"} <= names


@pytest.mark.parametrize("pattern", ["{x}", "{1}", "x_{", "{0.real.nope}", "{0[1]}", "{:s}"])
def test_a_bad_pattern_is_refused_before_anything_is_renamed(tmp_path, pattern):
    """`{x}` and `{1}` used to end in a KeyError/IndexError traceback."""
    (tmp_path / "a.txt").write_text("x")

    ok = renamer.run_massive_rename(str(tmp_path), mode="patron", pattern=pattern,
                                    apply_changes=True)

    assert ok is False
    assert sorted(os.listdir(tmp_path)) == ["a.txt"]


def test_replace_mode_without_the_text_to_find_is_an_error(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    assert renamer.run_massive_rename(str(tmp_path), mode="reemplazo") is False


def test_replacing_spaces_works(tmp_path):
    (tmp_path / "a b.txt").write_text("x")
    renamer.run_massive_rename(str(tmp_path), mode="reemplazo", old_text=" ", new_text="_",
                               apply_changes=True)
    assert sorted(os.listdir(tmp_path)) == ["a_b.txt"]


def test_the_dry_run_hint_names_a_flag_that_exists(tmp_path, capsys):
    (tmp_path / "a.txt").write_text("x")
    renamer.run_massive_rename(str(tmp_path), mode="patron", pattern="f_{}")
    out = capsys.readouterr().out
    assert "--apply" in out
    assert "apply_changes" not in out

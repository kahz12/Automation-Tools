import os
import zipfile

from automation_tools.tools import archiver as ar


def _make_tree(root):
    """Creates a small source tree: data/{a.txt, sub/b.txt, debug.log, .hidden}."""
    data = root / "data"
    (data / "sub").mkdir(parents=True)
    (data / "a.txt").write_text("hello")
    (data / "sub" / "b.txt").write_text("world")
    (data / "debug.log").write_text("noise")
    (data / ".hidden").write_text("secret")
    return str(data)


def test_human_size():
    assert ar.human_size(0) == "0.0 B"
    assert ar.human_size(2048) == "2.0 KB"


def test_ensure_extension():
    assert ar._ensure_extension("backup", "zip") == "backup.zip"
    assert ar._ensure_extension("backup.zip", "zip") == "backup.zip"
    assert ar._ensure_extension("b", "tar.gz") == "b.tar.gz"


def test_default_output_is_timestamped(tmp_path):
    data = _make_tree(tmp_path)
    name = ar._default_output([data], "zip")
    assert name.startswith("data_") and name.endswith(".zip")


def test_collect_entries_roots_under_source_name(tmp_path):
    data = _make_tree(tmp_path)
    entries = ar.collect_entries([data])
    names = {e.arcname for e in entries}
    # arcnames are rooted at the source folder's name, dotfiles skipped by default
    assert names == {"data/a.txt", "data/sub/b.txt", "data/debug.log"}


def test_collect_entries_exclude_patterns(tmp_path):
    data = _make_tree(tmp_path)
    entries = ar.collect_entries([data], exclude=["*.log"])
    names = {e.arcname for e in entries}
    assert names == {"data/a.txt", "data/sub/b.txt"}


def test_collect_entries_exclude_folder(tmp_path):
    data = _make_tree(tmp_path)
    entries = ar.collect_entries([data], exclude=["sub"])
    names = {e.arcname for e in entries}
    assert "data/sub/b.txt" not in names
    assert "data/a.txt" in names


def test_collect_entries_include_hidden(tmp_path):
    data = _make_tree(tmp_path)
    entries = ar.collect_entries([data], include_hidden=True)
    names = {e.arcname for e in entries}
    assert "data/.hidden" in names


def test_collect_entries_single_file(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("x")
    entries = ar.collect_entries([str(f)])
    assert [e.arcname for e in entries] == ["note.txt"]


def test_create_and_list_zip(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "backup.zip")
    entries = ar.collect_entries([data], exclude=["*.log"])
    ar.create_archive(entries, out, "zip")
    assert os.path.isfile(out)
    listed = dict(ar.list_archive(out))
    assert set(listed) == {"data/a.txt", "data/sub/b.txt"}
    assert listed["data/a.txt"] == 5


def test_create_and_list_targz(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "backup.tar.gz")
    entries = ar.collect_entries([data])
    ar.create_archive(entries, out, "tar.gz")
    assert ar._detect_format(out) == "tar"
    names = {name for name, _ in ar.list_archive(out)}
    assert "data/a.txt" in names


def test_extract_round_trip(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "backup.zip")
    ar.create_archive(ar.collect_entries([data]), out, "zip")

    dest = str(tmp_path / "restored")
    written, skipped = ar.extract_archive(out, dest)
    assert skipped == []
    assert os.path.isfile(os.path.join(dest, "data", "a.txt"))
    with open(os.path.join(dest, "data", "sub", "b.txt")) as fh:
        assert fh.read() == "world"
    assert len(written) == 3


def test_extract_dry_run_writes_nothing(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "backup.zip")
    ar.create_archive(ar.collect_entries([data]), out, "zip")

    dest = str(tmp_path / "preview")
    written, _ = ar.extract_archive(out, dest, dry_run=True)
    assert written  # reported as would-be-written
    assert not os.path.exists(os.path.join(dest, "data", "a.txt"))


def test_extract_skips_existing_without_overwrite(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "backup.zip")
    ar.create_archive(ar.collect_entries([data]), out, "zip")

    dest = tmp_path / "restored"
    (dest / "data").mkdir(parents=True)
    (dest / "data" / "a.txt").write_text("KEEP ME")

    written, skipped = ar.extract_archive(out, str(dest), overwrite=False)
    assert (dest / "data" / "a.txt").read_text() == "KEEP ME"
    assert any(name.endswith("a.txt") for name, _ in skipped)

    ar.extract_archive(out, str(dest), overwrite=True)
    assert (dest / "data" / "a.txt").read_text() == "hello"


def test_extract_blocks_zip_slip(tmp_path):
    evil = str(tmp_path / "evil.zip")
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escaped.txt", "pwned")
        zf.writestr("ok/inside.txt", "fine")

    dest = tmp_path / "evil_out"
    written, skipped = ar.extract_archive(evil, str(dest))
    assert written == ["ok/inside.txt"]
    assert any(reason.startswith("unsafe path") for _, reason in skipped)
    # nothing escaped the destination
    assert not (tmp_path / "escaped.txt").exists()


def test_run_archiver_create_dry_run(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "b.zip")
    ok = ar.run_archiver("create", sources=[data], output=out, apply=False)
    assert ok is True
    assert not os.path.exists(out)  # dry-run writes nothing


def test_run_archiver_create_apply(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "b.zip")
    ok = ar.run_archiver("create", sources=[data], output=out, apply=True)
    assert ok is True
    assert os.path.isfile(out)


def test_run_archiver_unknown_action(tmp_path):
    assert ar.run_archiver("frobnicate") is False


def test_run_archiver_missing_source(tmp_path):
    assert ar.run_archiver("create", sources=[str(tmp_path / "nope")], apply=True) is False

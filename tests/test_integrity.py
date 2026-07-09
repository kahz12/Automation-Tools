import hashlib
import os

from automation_tools.tools import integrity as it


def _make_tree(root):
    """Creates a small source tree: data/{a.txt, sub/b.txt, debug.log, .hidden}."""
    data = root / "data"
    (data / "sub").mkdir(parents=True)
    (data / "a.txt").write_text("hello")
    (data / "sub" / "b.txt").write_text("world")
    (data / "debug.log").write_text("noise")
    (data / ".hidden").write_text("secret")
    return str(data)


def test_hash_file_matches_hashlib(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hello")
    assert it.hash_file(str(f)) == hashlib.sha256(b"hello").hexdigest()
    assert it.hash_file(str(f), "md5") == hashlib.md5(b"hello").hexdigest()


def test_hash_file_unreadable_returns_none(tmp_path):
    assert it.hash_file(str(tmp_path / "nope.txt")) is None


def test_collect_files_skips_hidden_and_excludes(tmp_path):
    data = _make_tree(tmp_path)
    assert it.collect_files(data) == ["a.txt", "debug.log", "sub/b.txt"]
    assert it.collect_files(data, exclude=["*.log"]) == ["a.txt", "sub/b.txt"]
    assert it.collect_files(data, exclude=["sub"]) == ["a.txt", "debug.log"]
    assert ".hidden" in it.collect_files(data, include_hidden=True)


def test_collect_files_skips_manifest_itself(tmp_path):
    data = _make_tree(tmp_path)
    manifest = os.path.join(data, "checksums.sha256")
    with open(manifest, "w") as f:
        f.write("")
    assert "checksums.sha256" not in it.collect_files(data, skip=[manifest])


def test_manifest_round_trip(tmp_path):
    data = _make_tree(tmp_path)
    entries, unreadable = it.build_manifest(data)
    assert unreadable == []
    out = str(tmp_path / "checksums.sha256")
    it.write_manifest(entries, out)

    algorithm, parsed = it.parse_manifest(out)
    assert algorithm == "sha256"
    assert parsed == entries


def test_parse_manifest_detects_md5_and_binary_marker(tmp_path):
    out = tmp_path / "sums.md5"
    digest = hashlib.md5(b"x").hexdigest()
    out.write_text(f"{digest} *file.bin\n")
    algorithm, parsed = it.parse_manifest(str(out))
    assert algorithm == "md5"
    assert parsed == {"file.bin": digest}


def test_parse_manifest_rejects_garbage(tmp_path):
    out = tmp_path / "bad.txt"
    out.write_text("this is not a manifest\n")
    try:
        it.parse_manifest(str(out))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_verify_intact(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "checksums.sha256")
    entries, _ = it.build_manifest(data)
    it.write_manifest(entries, out)

    result = it.verify_manifest(data, out)
    assert result.intact
    assert len(result.ok) == 3
    assert result.modified == result.missing == result.extra == []


def test_verify_detects_modified_missing_and_extra(tmp_path):
    data = _make_tree(tmp_path)
    out = str(tmp_path / "checksums.sha256")
    entries, _ = it.build_manifest(data)
    it.write_manifest(entries, out)

    (tmp_path / "data" / "a.txt").write_text("TAMPERED")
    (tmp_path / "data" / "debug.log").unlink()
    (tmp_path / "data" / "new.txt").write_text("surprise")

    result = it.verify_manifest(data, out, check_extra=True)
    assert not result.intact
    assert result.modified == ["a.txt"]
    assert result.missing == ["debug.log"]
    assert result.extra == ["new.txt"]
    assert result.ok == ["sub/b.txt"]


def test_verify_manifest_inside_folder_not_extra(tmp_path):
    data = _make_tree(tmp_path)
    ok = it.run_integrity("create", directory=data)
    assert ok is True
    manifest = os.path.join(data, "checksums.sha256")
    assert os.path.isfile(manifest)

    result = it.verify_manifest(data, manifest, check_extra=True)
    assert result.intact
    assert result.extra == []


def test_find_manifest(tmp_path):
    data = _make_tree(tmp_path)
    assert it.find_manifest(data) is None
    it.run_integrity("create", directory=data)
    assert it.find_manifest(data) == os.path.join(data, "checksums.sha256")


def test_run_integrity_create_and_verify(tmp_path):
    data = _make_tree(tmp_path)
    assert it.run_integrity("create", directory=data, algorithm="sha512") is True
    assert it.run_integrity("verify", directory=data) is True

    (tmp_path / "data" / "a.txt").write_text("TAMPERED")
    assert it.run_integrity("verify", directory=data) is False


def test_run_integrity_missing_directory(tmp_path):
    assert it.run_integrity("create", directory=str(tmp_path / "nope")) is False
    assert it.run_integrity("verify", directory=str(tmp_path / "nope")) is False


def test_run_integrity_verify_without_manifest(tmp_path):
    data = _make_tree(tmp_path)
    assert it.run_integrity("verify", directory=data) is False


def test_run_integrity_unknown_action(tmp_path):
    assert it.run_integrity("frobnicate", directory=str(tmp_path)) is False


def test_run_integrity_empty_directory(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert it.run_integrity("create", directory=str(empty)) is False

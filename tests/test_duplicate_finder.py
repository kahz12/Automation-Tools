from automation_tools.tools import duplicate_finder as df


def test_hash_file_identical_and_different(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.bin"
    c = tmp_path / "c.bin"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    c.write_bytes(b"different")
    assert df.hash_file(str(a)) == df.hash_file(str(b))
    assert df.hash_file(str(a)) != df.hash_file(str(c))


def test_matches_any():
    assert df._matches_any("foo.tmp", ["*.tmp"]) is True
    assert df._matches_any("foo.txt", ["*.tmp"]) is False


def test_find_duplicates(tmp_path):
    (tmp_path / "x1.txt").write_text("dup")
    (tmp_path / "x2.txt").write_text("dup")
    (tmp_path / "unique.txt").write_text("solo")
    dups = df.find_duplicates(str(tmp_path))
    # Exactly one group of duplicates, with two members.
    assert len(dups) == 1
    (paths,) = dups.values()
    assert len(paths) == 2


def test_find_duplicates_respects_excludes(tmp_path):
    (tmp_path / "x1.log").write_text("dup")
    (tmp_path / "x2.log").write_text("dup")
    dups = df.find_duplicates(str(tmp_path), excludes=["*.log"])
    assert dups == {}

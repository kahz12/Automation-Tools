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


def test_find_duplicates_does_not_hash_unique_sizes(tmp_path, monkeypatch):
    (tmp_path / "a.bin").write_bytes(b"same")
    (tmp_path / "b.bin").write_bytes(b"same")
    (tmp_path / "unique.bin").write_bytes(b"a different size")
    hashed = []
    real_hash = df.hash_file

    def recording_hash(path, chunk_size=8192):
        hashed.append(path)
        return real_hash(path, chunk_size)

    monkeypatch.setattr(df, "hash_file", recording_hash)
    dups = df.find_duplicates(str(tmp_path))

    assert len(dups) == 1
    assert str(tmp_path / "unique.bin") not in hashed

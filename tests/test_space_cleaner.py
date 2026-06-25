import os

from automation_tools.tools import space_cleaner as sc


def test_human_size():
    assert sc.human_size(0) == "0.0 B"
    assert sc.human_size(2048) == "2.0 KB"


def test_is_protected():
    assert sc._is_protected(os.path.join("home", ".git", "config")) is True
    assert sc._is_protected(os.path.join("home", "project", "src")) is False


def test_dir_size(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 100)
    (tmp_path / "b").write_bytes(b"y" * 50)
    assert sc.dir_size(str(tmp_path)) == 150


def test_scan_finds_junk_dir(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "mod.pyc").write_bytes(b"x" * 10)
    (tmp_path / "keep.txt").write_text("hello")

    report = sc.scan(str(tmp_path), find_large=False, find_old=False)
    junk_paths = [item.path for item in report.junk]
    assert any(p.endswith("__pycache__") for p in junk_paths)
    assert report.total_bytes() >= 10


def test_scan_finds_large_file(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * (2 * 1024 * 1024))  # 2 MB
    report = sc.scan(str(tmp_path), large_mb=1, find_junk=False, find_old=False)
    assert any(item.path.endswith("big.bin") for item in report.large)

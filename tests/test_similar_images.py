"""Tests for the Similar Photo Finder.

The point of the tool is catching what MD5 cannot, so the fixtures are
deliberately the transformations that change every byte while leaving the
picture recognisable: rescaling, re-compression and a colour drop.
"""
import types

import pytest
from PIL import Image

from automation_tools.tools import similar_images as si


@pytest.fixture
def photo(tmp_path):
    """Writes a detailed picture and returns (path, PIL image).

    A flat colour would hash to the same value as any other flat colour, so the
    fixture carries real structure for the hash to latch onto.
    """
    img = Image.new("RGB", (600, 400))
    img.putdata([
        ((x * 3) % 256, (y * 5) % 256, (x + y) % 256)
        for y in range(400) for x in range(600)
    ])
    path = tmp_path / "original.png"
    img.save(str(path))
    return str(path), img


@pytest.fixture
def accept_confirm(monkeypatch):
    def _set(answer):
        monkeypatch.setattr(
            si.questionary, "confirm",
            lambda *a, **k: types.SimpleNamespace(ask=lambda: answer),
        )
    return _set


# ── hashing ─────────────────────────────────────────────────────────────────
def test_hash_survives_resize_recompression_and_greyscale(tmp_path, photo):
    path, img = photo
    base = si.dhash(path)[0]

    img.resize((300, 200)).save(str(tmp_path / "small.png"))
    img.save(str(tmp_path / "lossy.jpg"), quality=35)
    img.convert("L").save(str(tmp_path / "grey.png"))

    for name in ("small.png", "lossy.jpg", "grey.png"):
        assert si.hamming(base, si.dhash(str(tmp_path / name))[0]) == 0, name


def test_hash_separates_a_different_picture(tmp_path, photo):
    path, _img = photo
    other = tmp_path / "other.png"
    Image.new("RGB", (600, 400), (10, 200, 90)).save(str(other))
    assert si.hamming(si.dhash(path)[0], si.dhash(str(other))[0]) > si.DEFAULT_THRESHOLD


def test_hash_reports_the_real_dimensions(photo):
    path, _img = photo
    _bits, width, height = si.dhash(path)
    assert (width, height) == (600, 400)


def test_hash_returns_none_for_a_non_image(tmp_path):
    broken = tmp_path / "broken.png"
    broken.write_text("not an image", encoding="utf-8")
    assert si.dhash(str(broken)) is None


def test_hamming_counts_differing_bits():
    assert si.hamming(0b1011, 0b1011) == 0
    assert si.hamming(0b1011, 0b1000) == 2


# ── grouping ────────────────────────────────────────────────────────────────
def _info(path, bits, size=100, width=10, height=10):
    return si.ImageInfo(path, bits, size, width, height)


def test_group_similar_ignores_lone_images():
    items = [_info("a", 0b0000), _info("b", 0b1111111111)]
    assert si.group_similar(items, threshold=1) == []


def test_group_similar_is_transitive_across_a_chain():
    # a-b and b-c are each within the threshold while a-c is not; a burst of
    # shots drifting frame by frame still belongs in one group.
    items = [_info("a", 0b0000), _info("b", 0b0011), _info("c", 0b1111)]
    groups = si.group_similar(items, threshold=2)
    assert len(groups) == 1
    assert sorted(i.path for i in groups[0]) == ["a", "b", "c"]


def test_group_similar_threshold_zero_keeps_only_exact_hashes():
    items = [_info("a", 0b0000), _info("b", 0b0001), _info("c", 0b0000)]
    groups = si.group_similar(items, threshold=0)
    assert len(groups) == 1
    assert sorted(i.path for i in groups[0]) == ["a", "c"]


def test_keeper_is_the_highest_resolution_copy():
    items = [
        _info("small", 0b0, size=900, width=100, height=100),
        _info("big", 0b0, size=100, width=800, height=600),
    ]
    group = si.group_similar(items, threshold=0)[0]
    assert group[0].path == "big"


def test_keeper_breaks_a_resolution_tie_on_file_size():
    items = [
        _info("thin", 0b0, size=100, width=800, height=600),
        _info("fat", 0b0, size=900, width=800, height=600),
    ]
    assert si.group_similar(items, threshold=0)[0][0].path == "fat"


def test_reclaimable_bytes_excludes_the_keeper():
    groups = [[_info("k", 0b0, size=500), _info("d1", 0b0, size=100), _info("d2", 0b0, size=50)]]
    assert si.reclaimable_bytes(groups) == 150


# ── scanning ────────────────────────────────────────────────────────────────
def test_scan_walks_subfolders_and_skips_non_images(tmp_path, photo, make_image):
    _path, img = photo
    (tmp_path / "sub").mkdir()
    img.resize((120, 80)).save(str(tmp_path / "sub" / "copy.png"))
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")

    images, unreadable = si.scan_images(str(tmp_path))
    assert {p.path.split("/")[-1] for p in images} == {"original.png", "copy.png"}
    assert unreadable == 0


def test_scan_respects_no_recursive(tmp_path, photo, make_image):
    _path, img = photo
    (tmp_path / "sub").mkdir()
    img.resize((120, 80)).save(str(tmp_path / "sub" / "copy.png"))

    images, _ = si.scan_images(str(tmp_path), recursive=False)
    assert [p.path.split("/")[-1] for p in images] == ["original.png"]


def test_scan_applies_exclude_patterns(tmp_path, photo, make_image):
    _path, img = photo
    img.resize((120, 80)).save(str(tmp_path / "thumb_copy.png"))
    images, _ = si.scan_images(str(tmp_path), excludes=["thumb_*"])
    assert [p.path.split("/")[-1] for p in images] == ["original.png"]


def test_scan_counts_unreadable_files(tmp_path, photo):
    (tmp_path / "broken.png").write_text("nope", encoding="utf-8")
    _images, unreadable = si.scan_images(str(tmp_path))
    assert unreadable == 1


# ── entry point ─────────────────────────────────────────────────────────────
def test_dry_run_never_deletes(tmp_path, photo):
    _path, img = photo
    img.resize((300, 200)).save(str(tmp_path / "copy.png"))
    before = sorted(p.name for p in tmp_path.iterdir())

    assert si.run_similar_images(str(tmp_path), apply=False) is True
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_apply_keeps_the_best_copy_and_deletes_the_rest(tmp_path, photo, accept_confirm):
    _path, img = photo
    img.resize((300, 200)).save(str(tmp_path / "medium.png"))
    img.resize((150, 100)).save(str(tmp_path / "tiny.png"))
    accept_confirm(True)

    assert si.run_similar_images(str(tmp_path), apply=True) is True
    survivors = sorted(p.name for p in tmp_path.iterdir())
    assert survivors == ["original.png"]


def test_apply_deletes_nothing_when_the_confirmation_is_declined(tmp_path, photo, accept_confirm):
    _path, img = photo
    img.resize((300, 200)).save(str(tmp_path / "copy.png"))
    accept_confirm(False)

    assert si.run_similar_images(str(tmp_path), apply=True) is True
    assert sorted(p.name for p in tmp_path.iterdir()) == ["copy.png", "original.png"]


def test_run_exports_a_csv_report(tmp_path, photo):
    _path, img = photo
    img.resize((300, 200)).save(str(tmp_path / "copy.png"))
    report = tmp_path / "report.csv"

    si.run_similar_images(str(tmp_path), export_path=str(report))
    text = report.read_text(encoding="utf-8")
    assert "group,role,width,height,size_bytes,distance,path" in text
    assert "keep" in text and "duplicate" in text


def test_run_reports_a_missing_directory(tmp_path):
    assert si.run_similar_images(str(tmp_path / "nope")) is False


def test_run_rejects_an_out_of_range_threshold(tmp_path, photo):
    assert si.run_similar_images(str(tmp_path), threshold=99) is False


def test_run_succeeds_when_nothing_is_similar(tmp_path, photo):
    other = tmp_path / "other.png"
    Image.new("RGB", (600, 400), (10, 200, 90)).save(str(other))
    assert si.run_similar_images(str(tmp_path)) is True
    assert sorted(p.name for p in tmp_path.iterdir()) == ["original.png", "other.png"]

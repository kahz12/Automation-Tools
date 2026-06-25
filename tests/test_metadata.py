from automation_tools.tools import metadata


def test_format_bytes():
    assert metadata.format_bytes(1536) == "1.50 KB"
    assert metadata.format_bytes(0) == "0.00 B"


def test_get_basic_info(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("hello")
    info = metadata.get_basic_info(str(f))
    for key in ("Size", "Created", "Modified", "Path"):
        assert key in info


def test_extract_pdf_metadata(tmp_path, make_pdf):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    meta = metadata.extract_pdf_metadata(src)
    assert meta["Number of Pages"] == 3


def test_extract_image_metadata(tmp_path, make_image):
    src = make_image(tmp_path / "p.png", size=(50, 40))
    meta = metadata.extract_image_metadata(src)
    assert meta["Format"] == "PNG"
    assert meta["Resolution"] == "50x40 px"


def test_clean_image_exif(tmp_path, make_image):
    src = make_image(tmp_path / "p.jpg", size=(20, 20))
    out = metadata.clean_image_exif(src)
    assert out is not None
    import os
    assert os.path.exists(out)

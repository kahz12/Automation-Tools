import pytest
from PIL import Image

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


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "P"])
def test_clean_image_exif_keeps_the_pixels_in_every_mode(tmp_path, mode):
    """Stripping metadata rewrites the pixels, so it must not change them.

    P mode is the one that used to come out black: the palette lives outside
    the pixel data, so copying only the indexes loses every colour.
    """
    base = Image.new("RGB", (24, 18))
    base.putdata([((x * 7) % 256, (y * 11) % 256, (x + y) % 256)
                  for y in range(18) for x in range(24)])
    src = tmp_path / f"src_{mode}.png"
    base.convert(mode).save(str(src))

    out = metadata.clean_image_exif(str(src))
    with Image.open(out) as cleaned, Image.open(str(src)) as original:
        assert cleaned.mode == original.mode
        assert cleaned.convert("RGB").tobytes() == original.convert("RGB").tobytes()

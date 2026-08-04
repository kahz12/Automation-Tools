from PIL import Image

from automation_tools.tools import converter


def test_format_map():
    assert converter.FORMAT_MAP["jpg"] == "JPEG"
    assert converter.FORMAT_MAP["png"] == "PNG"


def test_convert_single_file(tmp_path, make_image):
    src = make_image(tmp_path / "pic.png", size=(40, 30))
    assert converter.convert_single_file(src, "jpg") is True
    out = tmp_path / "pic.jpg"
    assert out.exists()
    with Image.open(out) as im:
        assert im.format == "JPEG"


def test_convert_rgba_to_jpeg(tmp_path, make_image):
    src = make_image(tmp_path / "pic.png", size=(40, 30), mode="RGBA")
    assert converter.convert_single_file(src, "jpg") is True
    with Image.open(tmp_path / "pic.jpg") as im:
        assert im.mode == "RGB"


def test_convert_unsupported_format(tmp_path, make_image):
    src = make_image(tmp_path / "pic.png")
    assert converter.convert_single_file(src, "xyz") is False


def test_run_image_converter_directory(tmp_path, make_image):
    make_image(tmp_path / "a.png")
    make_image(tmp_path / "b.png")
    # Use BMP: a universally available encoder (WebP is optional in some Pillow builds).
    converter.run_image_converter(str(tmp_path), "bmp")
    assert (tmp_path / "a.bmp").exists()
    assert (tmp_path / "b.bmp").exists()

from PIL import Image

from automation_tools.tools import image_processor as ip


def test_human_size():
    assert ip.human_size(0) == "0.0 B"
    assert ip.human_size(1536) == "1.5 KB"
    assert ip.human_size(1024 * 1024) == "1.0 MB"


def test_resize_caps_longest_side():
    img = Image.new("RGB", (4000, 2000))
    out = ip._resize_image(img, max_size=1000, scale_percent=None)
    assert max(out.size) == 1000
    assert out.size == (1000, 500)


def test_resize_does_not_upscale():
    img = Image.new("RGB", (100, 80))
    out = ip._resize_image(img, max_size=1000, scale_percent=None)
    assert out.size == (100, 80)


def test_resize_by_percent():
    img = Image.new("RGB", (200, 100))
    out = ip._resize_image(img, max_size=None, scale_percent=50)
    assert out.size == (100, 50)


def test_watermark_returns_rgba():
    img = Image.new("RGB", (300, 200), (10, 10, 10))
    out = ip._apply_watermark(img, "© test", "bottom-right", 60)
    assert out.mode == "RGBA"
    assert out.size == (300, 200)


def test_save_image_jpeg_from_rgba(tmp_path):
    img = Image.new("RGBA", (20, 20), (1, 2, 3, 128))
    out = str(tmp_path / "x.jpg")
    ip._save_image(img, out, quality=80)
    with Image.open(out) as reopened:
        assert reopened.mode == "RGB"
        assert reopened.format == "JPEG"


def test_run_resize_keeps_original(tmp_path, make_image):
    src = make_image(tmp_path / "big.jpg", size=(2000, 1500))
    ip.run_batch_image_processor(str(src), operation="resize", max_size=500)
    # Original is untouched.
    with Image.open(src) as o:
        assert o.size == (2000, 1500)
    # Output lands in a 'processed' subfolder.
    out = tmp_path / "processed" / "big.jpg"
    assert out.exists()
    with Image.open(out) as r:
        assert max(r.size) == 500


def test_run_compress_folder(tmp_path, make_image):
    make_image(tmp_path / "a.jpg", size=(800, 600))
    make_image(tmp_path / "b.jpg", size=(800, 600))
    ip.run_batch_image_processor(str(tmp_path), operation="compress", quality=30,
                                 output_dir=str(tmp_path / "out"))
    assert (tmp_path / "out" / "a.jpg").exists()
    assert (tmp_path / "out" / "b.jpg").exists()


def test_run_watermark(tmp_path, make_image):
    make_image(tmp_path / "p.png", size=(400, 300), mode="RGBA")
    ip.run_batch_image_processor(str(tmp_path), operation="watermark",
                                 watermark_text="mark", output_dir=str(tmp_path / "wm"))
    assert (tmp_path / "wm" / "p.png").exists()


def test_run_validation_errors(tmp_path, make_image):
    make_image(tmp_path / "p.png")
    # watermark without text -> handled, no output dir created with files
    ip.run_batch_image_processor(str(tmp_path), operation="watermark", watermark_text="",
                                 output_dir=str(tmp_path / "o1"))
    assert not (tmp_path / "o1" / "p.png").exists()
    # unknown operation
    ip.run_batch_image_processor(str(tmp_path), operation="rotate",
                                 output_dir=str(tmp_path / "o2"))
    assert not (tmp_path / "o2" / "p.png").exists()


def test_run_no_images(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    ip.run_batch_image_processor(str(tmp_path), operation="resize",
                                 output_dir=str(tmp_path / "o"))
    assert not (tmp_path / "o" / "notes.txt").exists()

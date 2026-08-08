"""Tests for the AI OCR tool. Provider calls are mocked so the suite stays offline."""
import os

import pytest

from automation_tools.tools import ocr


class _StubVisionProvider:
    def __init__(self, text="HELLO WORLD"):
        self.name = "stub"
        self.text = text
        self.calls = []

    def generate_vision(self, prompt, image_bytes, mime_type, *, model=None):
        self.calls.append({"prompt": prompt, "mime_type": mime_type})
        return self.text


@pytest.fixture
def fake_provider(monkeypatch):
    """Intercepts get_provider in ocr; returns (stub, calls)."""
    stub = _StubVisionProvider()
    calls = []

    def fake_get_provider(capability, name=None, api_key=None, model=None):
        calls.append({"capability": capability, "name": name, "model": model})
        return stub

    monkeypatch.setattr(ocr, "get_provider", fake_get_provider)
    return stub, calls


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_image_to_bytes_png(tmp_path, make_image):
    src = make_image(tmp_path / "p.png")
    data, mime = ocr._image_to_bytes(src)
    assert mime == "image/png"
    assert len(data) > 0


def test_image_to_bytes_jpeg(tmp_path, make_image):
    src = make_image(tmp_path / "p.jpg")
    _, mime = ocr._image_to_bytes(src)
    assert mime == "image/jpeg"


def test_image_to_bytes_normalizes_bmp(tmp_path, make_image):
    src = make_image(tmp_path / "p.bmp")
    data, mime = ocr._image_to_bytes(src)
    # BMP is not sent natively; it is converted to PNG.
    assert mime == "image/png"
    assert data[:4] == b"\x89PNG"


def test_collect_images_single_file(tmp_path, make_image):
    src = make_image(tmp_path / "one.png")
    assert ocr._collect_images(src) == [src]


def test_collect_images_ignores_non_images(tmp_path, make_image):
    make_image(tmp_path / "a.png")
    make_image(tmp_path / "b.jpg")
    (tmp_path / "notes.txt").write_text("ignore")
    found = {os.path.basename(p) for p in ocr._collect_images(str(tmp_path))}
    assert found == {"a.png", "b.jpg"}


def test_collect_images_recursive(tmp_path, make_image):
    sub = tmp_path / "sub"
    sub.mkdir()
    make_image(tmp_path / "top.png")
    make_image(sub / "deep.png")
    flat = ocr._collect_images(str(tmp_path), recursive=False)
    deep = ocr._collect_images(str(tmp_path), recursive=True)
    assert len(flat) == 1
    assert len(deep) == 2


def test_build_prompt_variants():
    plain = ocr._build_prompt()
    assert "OCR" in plain and "Markdown" not in plain
    md = ocr._build_prompt(markdown=True)
    assert "Markdown" in md
    lang = ocr._build_prompt(language="Spanish")
    assert "Spanish" in lang


def test_output_path(tmp_path):
    src = str(tmp_path / "scan.png")
    assert ocr._output_path(src, None, ".txt") == str(tmp_path / "scan.txt")
    assert ocr._output_path(src, "/out", ".md") == os.path.join("/out", "scan.md")


# ── run_ocr workflow (mocked provider) ────────────────────────────────────────
def test_run_ocr_single_saves_file(tmp_path, make_image, fake_provider):
    src = make_image(tmp_path / "scan.png")
    out = str(tmp_path / "result.txt")
    ok = ocr.run_ocr(src, out_path=out)
    assert ok is True
    assert open(out).read() == "HELLO WORLD"


def test_run_ocr_batch_writes_per_image(tmp_path, make_image, fake_provider):
    make_image(tmp_path / "a.png")
    make_image(tmp_path / "b.png")
    ok = ocr.run_ocr(str(tmp_path), markdown=True)
    assert ok is True
    produced = sorted(f for f in os.listdir(tmp_path) if f.endswith(".md"))
    assert produced == ["a.md", "b.md"]
    assert (tmp_path / "a.md").read_text() == "HELLO WORLD"


def test_run_ocr_missing_path_returns_false(tmp_path, fake_provider):
    assert ocr.run_ocr(str(tmp_path / "nope.png")) is False


def test_run_ocr_no_images_returns_false(tmp_path, fake_provider):
    (tmp_path / "readme.txt").write_text("x")
    assert ocr.run_ocr(str(tmp_path)) is False


def test_run_ocr_reports_a_provider_error(tmp_path, make_image, monkeypatch, capsys):
    from automation_tools.ai.base import CapabilityError

    def boom(capability, name=None, api_key=None, model=None):
        raise CapabilityError("'deepseek' does not support vision.")

    monkeypatch.setattr(ocr, "get_provider", boom)
    assert ocr.run_ocr(str(make_image(tmp_path / "a.png")), provider="deepseek") is False
    assert "does not support" in capsys.readouterr().out


def test_run_ocr_asks_for_a_vision_provider(tmp_path, make_image, fake_provider):
    from automation_tools.ai.base import Capability

    _stub, calls = fake_provider
    ocr.run_ocr(str(make_image(tmp_path / "a.png")), provider="openai", model="gpt-4o")

    assert calls[0]["capability"] is Capability.VISION
    assert calls[0]["name"] == "openai"
    assert calls[0]["model"] == "gpt-4o"


def test_run_ocr_sends_the_built_prompt_and_mime_type(tmp_path, make_image, fake_provider):
    """`_build_prompt`'s output (tested in isolation above) actually reaches
    `generate_vision`, along with the right MIME type for the source image."""
    stub, _calls = fake_provider
    src = make_image(tmp_path / "scan.png")

    ocr.run_ocr(src, markdown=True, language="Spanish")

    assert stub.calls[0]["prompt"] == ocr._build_prompt(markdown=True, language="Spanish")
    assert stub.calls[0]["mime_type"] == "image/png"

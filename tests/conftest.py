"""Shared pytest fixtures for the Automation-Tools test suite."""
import pytest
from PIL import Image
from pypdf import PdfWriter


@pytest.fixture
def make_image():
    """Factory that writes a small image file and returns its path."""
    def _make(path, size=(64, 48), color=(120, 30, 30), mode="RGB"):
        if mode == "RGBA":
            color = (color[0], color[1], color[2], 255)
        Image.new(mode, size, color).save(str(path))
        return str(path)
    return _make


@pytest.fixture
def make_pdf():
    """Factory that writes a blank multi-page PDF and returns its path."""
    def _make(path, pages=3, width=200, height=200):
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=width, height=height)
        with open(str(path), "wb") as fh:
            writer.write(fh)
        return str(path)
    return _make

import pytest
from pypdf import PdfReader

from automation_tools.tools import pdf_toolkit as pt


def test_parse_pages_ranges_and_dedup():
    assert pt._parse_pages("1-3,5", 10) == [0, 1, 2, 4]
    # Order preserved, duplicates removed.
    assert pt._parse_pages("3,1,1,2", 5) == [2, 0, 1]


def test_parse_pages_out_of_range():
    with pytest.raises(ValueError):
        pt._parse_pages("11", 10)


def test_parse_pages_reversed_range():
    assert pt._parse_pages("3-1", 5) == [0, 1, 2]


def test_split(tmp_path, make_pdf):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    out_dir = tmp_path / "pages"
    pt.run_pdf_split(src, output_dir=str(out_dir))
    produced = sorted(p.name for p in out_dir.glob("*.pdf"))
    assert len(produced) == 3


def test_extract(tmp_path, make_pdf):
    src = make_pdf(tmp_path / "doc.pdf", pages=5)
    out = tmp_path / "extract.pdf"
    pt.run_pdf_extract(src, "1,3", output_path=str(out))
    assert out.exists()
    assert len(PdfReader(str(out)).pages) == 2


def test_merge(tmp_path, make_pdf):
    a = make_pdf(tmp_path / "a.pdf", pages=2)
    b = make_pdf(tmp_path / "b.pdf", pages=3)
    out = tmp_path / "merged.pdf"
    pt.run_pdf_merge(f"{a},{b}", str(out))
    assert out.exists()
    assert len(PdfReader(str(out)).pages) == 5

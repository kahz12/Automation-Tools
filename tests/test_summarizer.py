from pypdf import PdfWriter

from automation_tools.tools import summarizer


def test_extract_text_from_pdf_accepts_pages_without_text(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as handle:
        writer.write(handle)

    assert summarizer.extract_text_from_pdf(str(path)) == ""

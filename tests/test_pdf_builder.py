"""Tests for the PDF builder.

The Office fixtures are built by hand rather than checked in as binaries: a
.docx/.odt/.pptx is a zip of XML, so writing one here keeps the suite readable
and proves the reader against the exact structure Word and LibreOffice emit.
"""
import zipfile

import pytest
from pypdf import PdfReader

from automation_tools.tools import pdf_builder as pb

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
ODF_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


# ── fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture
def make_docx():
    def _make(path, body):
        with zipfile.ZipFile(str(path), "w") as archive:
            archive.writestr(
                "word/document.xml",
                f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>',
            )
        return str(path)
    return _make


@pytest.fixture
def make_pptx():
    def _make(path, slides):
        with zipfile.ZipFile(str(path), "w") as archive:
            for index, lines in enumerate(slides, 1):
                paragraphs = "".join(
                    f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in lines
                )
                archive.writestr(
                    f"ppt/slides/slide{index}.xml",
                    f'<p:sld xmlns:p="p" xmlns:a="{A}"><p:cSld><p:spTree><p:sp>'
                    f"<p:txBody>{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
                )
        return str(path)
    return _make


def pdf_text(path):
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def pdf_pages(path):
    return len(PdfReader(str(path)).pages)


# ── readers ─────────────────────────────────────────────────────────────────
def test_read_docx_headings_lists_and_tables(tmp_path, make_docx):
    src = make_docx(tmp_path / "d.docx", (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Titulo</w:t></w:r></w:p>'
        "<w:p><w:r><w:t>Un </w:t></w:r><w:r><w:t>parrafo.</w:t></w:r></w:p>"
        "<w:p><w:pPr><w:numPr><w:ilvl w:val=\"0\"/></w:numPr></w:pPr><w:r><w:t>Item</w:t></w:r></w:p>"
        "<w:p/>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>B</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
    ))
    blocks = pb.read_docx(src)
    kinds = [b.kind for b in blocks]
    assert kinds == ["h1", "p", "li", "table"]
    # Runs inside one paragraph are joined, empty paragraphs dropped.
    assert blocks[1].text == "Un parrafo."
    assert blocks[3].rows == [["A", "B"]]


def test_read_pptx_one_page_per_slide_in_numeric_order(tmp_path, make_pptx):
    src = make_pptx(tmp_path / "p.pptx", [[f"Slide {i}", "bullet"] for i in range(1, 12)])
    blocks = pb.read_pptx(src)
    headings = [b.text for b in blocks if b.kind == "h1"]
    # slide10 and slide11 must not sort ahead of slide2.
    assert headings == [f"Slide {i}" for i in range(1, 12)]
    assert sum(1 for b in blocks if b.kind == "break") == 10


def test_read_odt_does_not_duplicate_list_paragraphs(tmp_path):
    src = tmp_path / "d.odt"
    with zipfile.ZipFile(str(src), "w") as archive:
        archive.writestr("content.xml", (
            '<office:document-content '
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            f'xmlns:text="{ODF_TEXT}"><office:body><office:text>'
            '<text:h text:outline-level="2">Sub</text:h>'
            "<text:p>Suelto</text:p>"
            "<text:list><text:list-item><text:p>Dentro</text:p></text:list-item></text:list>"
            "</office:text></office:body></office:document-content>"
        ))
    blocks = pb.read_odt(str(src))
    assert [(b.kind, b.text) for b in blocks] == [
        ("h2", "Sub"), ("p", "Suelto"), ("li", "Dentro"),
    ]


def test_read_markdown_headings_lists_and_code(tmp_path):
    src = tmp_path / "n.md"
    src.write_text(
        "# Uno\n\ntexto suelto\n\n- a\n2. b\n\n```\ncode line\n```\n", encoding="utf-8"
    )
    blocks = pb.read_markdown(str(src))
    assert [b.kind for b in blocks] == ["h1", "p", "li", "li", "p"]
    assert blocks[-1].text == "code line"


def test_read_csv_sniffs_the_delimiter(tmp_path):
    src = tmp_path / "d.csv"
    src.write_text("a;b\n1;2\n", encoding="utf-8")
    blocks = pb.read_csv(str(src))
    assert len(blocks) == 1 and blocks[0].rows == [["a", "b"], ["1", "2"]]


def test_extract_blocks_rejects_unknown_extension(tmp_path):
    src = tmp_path / "x.xyz"
    src.write_text("hi", encoding="utf-8")
    with pytest.raises(ValueError):
        pb.extract_blocks(str(src))


# ── document action ─────────────────────────────────────────────────────────
def test_document_renders_text_and_unicode(tmp_path, make_docx):
    src = make_docx(tmp_path / "d.docx",
                    "<w:p><w:r><w:t>Acentos: ñ á ü — fin</w:t></w:r></w:p>")
    out = tmp_path / "d.pdf"
    assert pb.run_pdf_builder("document", [src], output=str(out), use_libreoffice=False)
    assert "Acentos" in pdf_text(out)


def test_document_refuses_to_overwrite_its_source(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4\n")
    assert pb.run_pdf_builder("document", [str(src)], output=str(src)) is False


def test_document_reports_a_corrupt_office_file(tmp_path):
    src = tmp_path / "broken.docx"
    src.write_text("not a zip", encoding="utf-8")
    assert pb.run_pdf_builder("document", [str(src)], use_libreoffice=False) is False


def test_unknown_page_size_is_rejected(tmp_path):
    src = tmp_path / "n.md"
    src.write_text("# hi\n", encoding="utf-8")
    assert pb.run_pdf_builder("document", [str(src)], page_size="a3") is False


# ── images action ───────────────────────────────────────────────────────────
def test_images_folder_becomes_one_page_each_in_name_order(tmp_path, make_image):
    for index in (3, 1, 2):
        make_image(tmp_path / f"img_{index:03d}.png", size=(120, 90))
    out = tmp_path / "album.pdf"
    assert pb.run_pdf_builder("images", [str(tmp_path)], output=str(out))
    assert pdf_pages(out) == 3


def test_images_flattens_transparency(tmp_path, make_image):
    src = make_image(tmp_path / "t.png", size=(80, 60), mode="RGBA")
    out = tmp_path / "t.pdf"
    assert pb.run_pdf_builder("images", [src], output=str(out))
    assert pdf_pages(out) == 1


def test_images_needs_at_least_one_image(tmp_path):
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")
    assert pb.run_pdf_builder("images", [str(tmp_path)]) is False


# ── merge action ────────────────────────────────────────────────────────────
def test_merge_mixes_documents_images_and_pdfs(tmp_path, make_docx, make_pptx, make_image):
    doc = make_docx(tmp_path / "d.docx", "<w:p><w:r><w:t>uno</w:t></w:r></w:p>")
    deck = make_pptx(tmp_path / "p.pptx", [["S1"], ["S2"]])
    img = make_image(tmp_path / "i.png", size=(100, 80))
    existing = tmp_path / "e.pdf"
    assert pb.run_pdf_builder("images", [img], output=str(existing))

    out = tmp_path / "all.pdf"
    assert pb.run_pdf_builder("merge", [doc, deck, img, str(existing)],
                              output=str(out), use_libreoffice=False)
    # 1 doc page + 2 slides + 1 image + 1 existing page
    assert pdf_pages(out) == 5


def test_merge_skips_unreadable_inputs_but_keeps_going(tmp_path, make_docx):
    good = make_docx(tmp_path / "g.docx", "<w:p><w:r><w:t>ok</w:t></w:r></w:p>")
    bad = tmp_path / "b.docx"
    bad.write_text("not a zip", encoding="utf-8")
    out = tmp_path / "m.pdf"
    assert pb.run_pdf_builder("merge", [good, str(bad), good],
                              output=str(out), use_libreoffice=False)
    assert pdf_pages(out) == 2


def test_merge_needs_two_files(tmp_path):
    src = tmp_path / "n.md"
    src.write_text("# hi\n", encoding="utf-8")
    assert pb.run_pdf_builder("merge", [str(src)]) is False


def test_unknown_action_is_rejected(tmp_path):
    src = tmp_path / "n.md"
    src.write_text("# hi\n", encoding="utf-8")
    assert pb.run_pdf_builder("nope", [str(src)]) is False


# ── LibreOffice handoff ─────────────────────────────────────────────────────
def test_office_files_prefer_libreoffice_when_present(tmp_path, monkeypatch, make_docx):
    src = make_docx(tmp_path / "d.docx", "<w:p><w:r><w:t>python engine</w:t></w:r></w:p>")
    calls = []

    def fake_convert(binary, source, out_path, timeout=240):
        calls.append(source)
        pb.render_pdf([pb.Block("p", "libreoffice engine")], out_path)
        return True

    monkeypatch.setattr(pb, "libreoffice_binary", lambda: "/usr/bin/libreoffice")
    monkeypatch.setattr(pb, "convert_with_libreoffice", fake_convert)

    out = tmp_path / "d.pdf"
    assert pb.run_pdf_builder("document", [src], output=str(out))
    assert calls == [src]
    assert "libreoffice engine" in pdf_text(out)


def test_libreoffice_failure_falls_back_to_the_python_engine(tmp_path, monkeypatch, make_docx):
    src = make_docx(tmp_path / "d.docx", "<w:p><w:r><w:t>python engine</w:t></w:r></w:p>")
    monkeypatch.setattr(pb, "libreoffice_binary", lambda: "/usr/bin/libreoffice")
    monkeypatch.setattr(pb, "convert_with_libreoffice",
                        lambda *a, **k: False)

    out = tmp_path / "d.pdf"
    assert pb.run_pdf_builder("document", [src], output=str(out))
    assert "python engine" in pdf_text(out)


def test_use_libreoffice_false_never_calls_it(tmp_path, monkeypatch, make_docx):
    src = make_docx(tmp_path / "d.docx", "<w:p><w:r><w:t>python engine</w:t></w:r></w:p>")

    def boom():
        raise AssertionError("LibreOffice must not be probed when it is switched off")

    monkeypatch.setattr(pb, "libreoffice_binary", boom)
    out = tmp_path / "d.pdf"
    assert pb.run_pdf_builder("document", [src], output=str(out), use_libreoffice=False)


def test_non_office_formats_never_reach_libreoffice(tmp_path, monkeypatch):
    src = tmp_path / "n.md"
    src.write_text("# hola\n", encoding="utf-8")

    def boom():
        raise AssertionError("Markdown does not go through LibreOffice")

    monkeypatch.setattr(pb, "libreoffice_binary", boom)
    out = tmp_path / "n.pdf"
    assert pb.run_pdf_builder("document", [str(src)], output=str(out))
    assert "hola" in pdf_text(out)

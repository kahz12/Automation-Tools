import argparse
import csv
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Build PDFs out of other things: one document, a pile of images, or a mixed
# batch merged into a single file.
#
# This replaces the old LibreOffice-only converter. Office formats are read with
# nothing but `zipfile` and `xml.etree` from the standard library (a .docx, .odt
# or .pptx is a zip of XML), so there is no lxml, no python-docx and no external
# binary in the default path. Pages are drawn with fpdf2, images placed with
# Pillow, and existing PDFs stitched in with pypdf.
#
# LibreOffice is still used when it happens to be on PATH, because the pure
# Python route can only recover the text: headings, paragraphs and lists survive,
# while embedded images, real tables, columns and fonts do not. Pass
# use_libreoffice=False to force the Python engine and get the same output on
# every machine.

try:
    from fpdf import FPDF
    from fpdf.fonts import FontFace
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# ── Formats ──────────────────────────────────────────────────────────────────
OFFICE_EXTS = {".docx", ".odt", ".pptx"}
TEXT_EXTS = {".txt", ".md", ".markdown", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
DOCUMENT_EXTS = OFFICE_EXTS | TEXT_EXTS
SUPPORTED_EXTS = DOCUMENT_EXTS | IMAGE_EXTS | {".pdf"}

PAGE_SIZES = ("a4", "letter")

# XML namespaces. A .docx and a .pptx are both OOXML but their text lives under
# different namespaces, and .odt is ODF, so all three need naming.
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_ODF_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_ODF_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"

# Regular/bold TrueType pairs, in the order they are probed. A TTF is what makes
# characters outside latin-1 (dashes, curly quotes, the euro sign) render at all;
# without one the core Helvetica font is used and those get replaced.
_FONT_CANDIDATES: Tuple[Tuple[str, str], ...] = (
    ("/system/fonts/Roboto-Regular.ttf",
     "/system/fonts/Roboto-Bold.ttf"),                                     # Android
    ("/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",
     "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),  # Termux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),              # Debian/Ubuntu
    ("/usr/share/fonts/TTF/DejaVuSans.ttf",
     "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),                          # Arch
    ("/Library/Fonts/Arial.ttf",
     "/Library/Fonts/Arial Bold.ttf"),                                     # macOS
    ("C:\\Windows\\Fonts\\arial.ttf",
     "C:\\Windows\\Fonts\\arialbd.ttf"),                                   # Windows
)
_FONT_FAMILY = "body"
_FALLBACK_FONT = "Helvetica"


@dataclass
class Block:
    """One piece of a document, already stripped of its original formatting.

    `kind` is "h1".."h3", "p", "li", "table" or "break" (a forced page break,
    used between slides). Only tables carry `rows`.
    """
    kind: str
    text: str = ""
    rows: List[List[str]] = field(default_factory=list)


# ── Office readers (standard library only) ───────────────────────────────────
def _q(namespace: str, tag: str) -> str:
    return f"{{{namespace}}}{tag}"


def _heading_level(style: Optional[str]) -> Optional[str]:
    """Maps a Word style name like 'Heading2' or 'Ttulo 1' onto h1..h3."""
    if not style:
        return None
    match = re.search(r"(\d+)", style)
    lowered = style.lower()
    if "head" in lowered or "titre" in lowered or "titulo" in lowered or "ttulo" in lowered:
        level = int(match.group(1)) if match else 1
        return f"h{min(max(level, 1), 3)}"
    if lowered.startswith("title"):
        return "h1"
    return None


def read_docx(path: str) -> List[Block]:
    """Paragraphs, headings, list items and tables out of a .docx."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))

    body = root.find(_q(_W, "body"))
    if body is None:
        return []

    blocks: List[Block] = []
    for node in body:
        if node.tag == _q(_W, "p"):
            text = "".join(t.text or "" for t in node.iter(_q(_W, "t"))).strip()
            if not text:
                continue
            properties = node.find(_q(_W, "pPr"))
            style = None
            numbered = False
            if properties is not None:
                style_node = properties.find(_q(_W, "pStyle"))
                if style_node is not None:
                    style = style_node.get(_q(_W, "val"))
                numbered = properties.find(_q(_W, "numPr")) is not None
            level = _heading_level(style)
            if level:
                blocks.append(Block(level, text))
            elif numbered or (style or "").lower().startswith("list"):
                blocks.append(Block("li", text))
            else:
                blocks.append(Block("p", text))
        elif node.tag == _q(_W, "tbl"):
            rows = []
            for row in node.iter(_q(_W, "tr")):
                cells = [
                    "".join(t.text or "" for t in cell.iter(_q(_W, "t"))).strip()
                    for cell in row.findall(_q(_W, "tc"))
                ]
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append(Block("table", rows=rows))
    return blocks


def read_odt(path: str) -> List[Block]:
    """Headings, paragraphs, list items and tables out of an .odt."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))

    blocks: List[Block] = []
    seen_in_list: set = set()

    for node in root.iter():
        if node.tag == _q(_ODF_TEXT, "h"):
            text = "".join(node.itertext()).strip()
            if text:
                level = node.get(_q(_ODF_TEXT, "outline-level")) or "1"
                try:
                    number = min(max(int(level), 1), 3)
                except ValueError:
                    number = 1
                blocks.append(Block(f"h{number}", text))
        elif node.tag == _q(_ODF_TEXT, "list"):
            for item in node.iter(_q(_ODF_TEXT, "p")):
                text = "".join(item.itertext()).strip()
                if text:
                    seen_in_list.add(id(item))
                    blocks.append(Block("li", text))
        elif node.tag == _q(_ODF_TEXT, "p"):
            if id(node) in seen_in_list:
                continue
            text = "".join(node.itertext()).strip()
            if text:
                blocks.append(Block("p", text))
        elif node.tag == _q(_ODF_TABLE, "table"):
            rows = []
            for row in node.iter(_q(_ODF_TABLE, "table-row")):
                cells = [
                    "".join(cell.itertext()).strip()
                    for cell in row.findall(_q(_ODF_TABLE, "table-cell"))
                ]
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append(Block("table", rows=rows))
    return blocks


def read_pptx(path: str) -> List[Block]:
    """One page per slide: the first line becomes the heading, the rest bullets."""
    with zipfile.ZipFile(path) as archive:
        names = [
            name for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        # slide10 must not sort before slide2.
        names.sort(key=lambda n: int(re.search(r"(\d+)", os.path.basename(n)).group(1)))

        blocks: List[Block] = []
        for index, name in enumerate(names):
            root = ET.fromstring(archive.read(name))
            lines = []
            for paragraph in root.iter(_q(_A, "p")):
                text = "".join(t.text or "" for t in paragraph.iter(_q(_A, "t"))).strip()
                if text:
                    lines.append(text)
            if not lines:
                continue
            if index:
                blocks.append(Block("break"))
            blocks.append(Block("h1", lines[0]))
            blocks.extend(Block("li", line) for line in lines[1:])
    return blocks


# ── Text readers ─────────────────────────────────────────────────────────────
def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def read_plain(path: str) -> List[Block]:
    """A .txt becomes one block per blank-line-separated paragraph."""
    text = _read_text_file(path)
    return [
        Block("p", " ".join(chunk.split()))
        for chunk in re.split(r"\n\s*\n", text)
        if chunk.strip()
    ]


def read_markdown(path: str) -> List[Block]:
    """Headings, bullet and numbered lists, fenced code and paragraphs."""
    blocks: List[Block] = []
    paragraph: List[str] = []
    in_code = False

    def flush() -> None:
        if paragraph:
            blocks.append(Block("p", " ".join(paragraph)))
            paragraph.clear()

    for raw in _read_text_file(path).splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            flush()
            in_code = not in_code
            continue
        if in_code:
            blocks.append(Block("p", raw))
            continue
        if not line.strip():
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            flush()
            level = min(len(heading.group(1)), 3)
            blocks.append(Block(f"h{level}", heading.group(2).strip()))
            continue
        item = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$", line)
        if item:
            flush()
            blocks.append(Block("li", item.group(1).strip()))
            continue
        paragraph.append(line.strip())
    flush()
    return blocks


def read_csv(path: str) -> List[Block]:
    """A .csv becomes a single table block, delimiter sniffed from the file."""
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = [[(cell or "").strip() for cell in row] for row in csv.reader(handle, dialect)]
    rows = [row for row in rows if any(row)]
    return [Block("table", rows=rows)] if rows else []


_READERS = {
    ".docx": read_docx,
    ".odt": read_odt,
    ".pptx": read_pptx,
    ".txt": read_plain,
    ".md": read_markdown,
    ".markdown": read_markdown,
    ".csv": read_csv,
}


def extract_blocks(path: str) -> List[Block]:
    """Reads any supported document into blocks. Raises ValueError on the rest."""
    ext = os.path.splitext(path)[1].lower()
    reader = _READERS.get(ext)
    if reader is None:
        raise ValueError(f"cannot read '{ext}' as a document")
    return reader(path)


# ── Rendering ────────────────────────────────────────────────────────────────
_SIZES = {"h1": 18, "h2": 14, "h3": 12, "p": 11, "li": 11}
_SPACE_BEFORE = {"h1": 5, "h2": 4, "h3": 3, "p": 0, "li": 0}


class _Document(FPDF if HAS_FPDF else object):  # type: ignore[misc]
    """FPDF subclass that stamps a page number on every page."""

    def __init__(self, page_size: str = "a4") -> None:
        super().__init__(orientation="P", unit="mm", format=page_size.upper())
        self.font_family_name = _FALLBACK_FONT
        self.set_auto_page_break(auto=True, margin=18)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font(self.font_family_name, "", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, str(self.page_no()), align="C")
        self.set_text_color(0, 0, 0)


def _register_font(pdf: "_Document") -> str:
    """Registers the first available TrueType pair, or keeps the core font.

    fpdf2 raises when asked for a bold style a family never registered, so when
    only the regular face exists it is registered under "B" as well: bold text
    then simply looks regular instead of crashing the render.
    """
    for regular, bold in _FONT_CANDIDATES:
        if not os.path.isfile(regular):
            continue
        try:
            pdf.add_font(_FONT_FAMILY, "", regular)
            pdf.add_font(_FONT_FAMILY, "B", bold if os.path.isfile(bold) else regular)
            return _FONT_FAMILY
        except Exception:
            continue
    return _FALLBACK_FONT


def _encode_for(font: str, text: str) -> str:
    """Drops characters the core font cannot represent.

    Helvetica is latin-1 only. Spanish accents survive it, but dashes, curly
    quotes and the euro sign do not, and fpdf2 would raise rather than skip them.
    """
    if font != _FALLBACK_FONT:
        return text
    return text.encode("latin-1", "replace").decode("latin-1")


def _render_table(pdf: "_Document", font: str, rows: List[List[str]]) -> None:
    """Draws a table, first row treated as the header."""
    if not rows:
        return
    width = max(len(row) for row in rows)
    normalised = [row + [""] * (width - len(row)) for row in rows]
    pdf.set_font(font, "", max(7, min(10, int(90 / max(width, 1)))))
    # fpdf2 treats the first row as the header and refuses to render without a
    # style for it, so the shading is spelled out rather than left to default.
    with pdf.table(
        line_height=pdf.font_size * 1.8,
        text_align="LEFT",
        headings_style=FontFace(emphasis="BOLD", fill_color=(232, 232, 238)),
    ) as table:
        for row in normalised:
            table_row = table.row()
            for cell in row:
                table_row.cell(_encode_for(font, cell))
    pdf.ln(3)


def render_pdf(blocks: List[Block], out_path: str, title: Optional[str] = None,
               page_size: str = "a4") -> bool:
    """Draws blocks into a PDF at `out_path`."""
    if not HAS_FPDF:
        print_error("Missing 'fpdf2'. Install it with 'pip install fpdf2'.")
        return False
    if not blocks:
        print_error("The document has no readable text.")
        return False

    pdf = _Document(page_size=page_size)
    font = _register_font(pdf)
    pdf.font_family_name = font
    pdf.add_page()

    if title:
        pdf.set_font(font, "B", 20)
        pdf.multi_cell(0, 10, _encode_for(font, title))
        pdf.ln(4)

    for block in blocks:
        if block.kind == "break":
            pdf.add_page()
            continue
        if block.kind == "table":
            _render_table(pdf, font, block.rows)
            continue

        size = _SIZES.get(block.kind, 11)
        style = "B" if block.kind.startswith("h") else ""
        gap = _SPACE_BEFORE.get(block.kind, 0)
        if gap:
            pdf.ln(gap)
        pdf.set_font(font, style, size)
        if block.kind == "li":
            pdf.set_x(pdf.l_margin + 6)
            pdf.multi_cell(0, size * 0.55, _encode_for(font, f"\u2022  {block.text}"))
        else:
            pdf.multi_cell(0, size * 0.55, _encode_for(font, block.text))
        pdf.ln(2)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        pdf.output(out_path)
    except Exception as e:
        print_error(f"Could not write '{out_path}': {e}")
        return False
    return True


# ── Images ───────────────────────────────────────────────────────────────────
def images_to_pdf(paths: List[str], out_path: str, page_size: str = "a4",
                  fit_to_page: bool = True) -> bool:
    """Puts every image on its own page of a single PDF, in the order given.

    With fit_to_page the image is scaled to sit inside a standard page; without
    it each page is cut to the image's own proportions, which suits photo sets.
    """
    if not HAS_PILLOW:
        print_error("Pillow is not installed. Install it with 'pip install Pillow'.")
        return False
    if not paths:
        print_error("No images to place.")
        return False

    pages = []
    for path in paths:
        try:
            with Image.open(path) as img:
                # PDF has no alpha channel, so flatten onto white rather than
                # letting Pillow fail or blacken the transparent areas.
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                    canvas = Image.new("RGB", img.size, (255, 255, 255))
                    canvas.paste(img, mask=img.split()[-1])
                    page = canvas
                else:
                    page = img.convert("RGB")

                if fit_to_page:
                    # 150 dpi keeps the file reasonable while staying sharp.
                    dims = (1240, 1754) if page_size.lower() == "a4" else (1275, 1650)
                    sheet = Image.new("RGB", dims, (255, 255, 255))
                    scaled = page.copy()
                    scaled.thumbnail(dims, Image.LANCZOS)
                    sheet.paste(
                        scaled,
                        ((dims[0] - scaled.width) // 2, (dims[1] - scaled.height) // 2),
                    )
                    page = sheet
                pages.append(page)
        except Exception as e:
            print_warning(f"Skipping '{os.path.basename(path)}': {e}")

    if not pages:
        print_error("None of the images could be read.")
        return False

    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        pages[0].save(out_path, "PDF", resolution=150.0,
                      save_all=True, append_images=pages[1:])
    except Exception as e:
        print_error(f"Could not write '{out_path}': {e}")
        return False
    console.print(f"  [dim]{len(pages)} image(s) placed[/dim]")
    return True


# ── LibreOffice (optional) ───────────────────────────────────────────────────
def libreoffice_binary() -> Optional[str]:
    """Path to a LibreOffice binary if one is installed, else None."""
    for name in ("libreoffice", "soffice"):
        found = shutil.which(name)
        if found:
            return found
    return None


def convert_with_libreoffice(binary: str, src: str, out_path: str,
                             timeout: int = 240) -> bool:
    """Converts through headless LibreOffice, writing exactly to `out_path`.

    It renders into a temp folder and moves the result, because LibreOffice
    names the output itself and drops it in --outdir; letting it write straight
    into the destination folder would clobber a same-named file next to it.
    """
    with tempfile.TemporaryDirectory() as staging:
        command = [
            binary, "--headless", "--convert-to", "pdf",
            "--outdir", staging, os.path.abspath(src),
        ]
        try:
            subprocess.run(
                command, check=True, timeout=timeout,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False
        produced = os.path.join(
            staging, os.path.splitext(os.path.basename(src))[0] + ".pdf"
        )
        if not os.path.isfile(produced):
            return False
        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
            shutil.move(produced, out_path)
        except OSError:
            return False
    return True


# ── One document → one PDF ───────────────────────────────────────────────────
def document_to_pdf(src: str, out_path: str, use_libreoffice: bool = True,
                    page_size: str = "a4", quiet: bool = False) -> bool:
    """Converts a single document, preferring LibreOffice when it is available."""
    ext = os.path.splitext(src)[1].lower()

    if ext in IMAGE_EXTS:
        return images_to_pdf([src], out_path, page_size=page_size)
    if ext == ".pdf":
        try:
            shutil.copyfile(src, out_path)
            return True
        except OSError as e:
            print_error(f"Could not copy '{src}': {e}")
            return False
    if ext not in DOCUMENT_EXTS:
        print_error(
            f"Unsupported format '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTS))}"
        )
        return False

    if use_libreoffice and ext in OFFICE_EXTS:
        binary = libreoffice_binary()
        if binary and convert_with_libreoffice(binary, src, out_path):
            if not quiet:
                console.print("  [dim]engine: LibreOffice (full layout)[/dim]")
            return True
        if binary and not quiet:
            print_warning("LibreOffice failed; falling back to the Python engine.")

    try:
        blocks = extract_blocks(src)
    except (zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        print_error(f"'{os.path.basename(src)}' is not a readable {ext} file: {e}")
        return False
    except (ValueError, OSError) as e:
        print_error(f"Could not read '{os.path.basename(src)}': {e}")
        return False

    if not quiet:
        console.print("  [dim]engine: Python (text only)[/dim]")
    title = os.path.splitext(os.path.basename(src))[0] if ext in OFFICE_EXTS else None
    return render_pdf(blocks, out_path, title=title, page_size=page_size)


# ── Many inputs → one PDF ────────────────────────────────────────────────────
def merge_to_pdf(paths: List[str], out_path: str, use_libreoffice: bool = True,
                 page_size: str = "a4") -> bool:
    """Converts every input to PDF and stitches them together in order.

    Images, documents and ready-made PDFs can be mixed freely; each contributes
    its own pages.
    """
    if not HAS_PYPDF:
        print_error("Missing 'pypdf'. Install it with 'pip install pypdf'.")
        return False

    writer = PdfWriter()
    added = 0
    with tempfile.TemporaryDirectory() as staging:
        for index, src in enumerate(paths, 1):
            name = os.path.basename(src)
            console.print(f"  [dim]• {name}…[/dim]")
            part = os.path.join(staging, f"{index:04d}.pdf")
            if not document_to_pdf(src, part, use_libreoffice=use_libreoffice,
                                   page_size=page_size, quiet=True):
                print_warning(f"Skipping '{name}'.")
                continue
            try:
                reader = PdfReader(part)
                if reader.is_encrypted and not reader.decrypt(""):
                    print_warning(f"Skipping '{name}': it is password-protected.")
                    continue
                writer.append(reader)
                added += 1
            except Exception as e:
                print_warning(f"Skipping '{name}': {e}")

        if not added:
            print_error("Nothing could be converted, so no PDF was written.")
            return False

        try:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
            with open(out_path, "wb") as handle:
                writer.write(handle)
        except OSError as e:
            print_error(f"Could not write '{out_path}': {e}")
            return False

    console.print(f"  [dim]{added}/{len(paths)} input(s) merged[/dim]")
    return True


# ── Input collection ─────────────────────────────────────────────────────────
def collect_inputs(raw: List[str], only: Optional[set] = None) -> List[str]:
    """Expands the given paths into a sorted list of usable files.

    A folder contributes its files sorted by name, which is what makes
    'scan_001.jpg, scan_002.jpg, …' come out in the right order.
    """
    allowed = only or SUPPORTED_EXTS
    files: List[str] = []
    for entry in raw:
        entry = entry.strip()
        if not entry:
            continue
        if os.path.isdir(entry):
            for name in sorted(os.listdir(entry)):
                full = os.path.join(entry, name)
                if os.path.isfile(full) and os.path.splitext(name)[1].lower() in allowed:
                    files.append(full)
        elif os.path.isfile(entry):
            files.append(entry)
        else:
            print_warning(f"Not found, skipping: {entry}")
    return files


def _default_output(sources: List[str], suffix: str) -> str:
    base = os.path.splitext(os.path.abspath(sources[0]).rstrip(os.sep))[0]
    if os.path.isdir(sources[0]):
        base = os.path.abspath(sources[0].rstrip(os.sep))
    return f"{base}{suffix}.pdf"


# ── Entry point ──────────────────────────────────────────────────────────────
def run_pdf_builder(
    action: str,
    inputs: Optional[List[str]] = None,
    output: Optional[str] = None,
    use_libreoffice: bool = True,
    page_size: str = "a4",
    fit_to_page: bool = True,
) -> bool:
    """Single entry point shared by the CLI and the interactive menu.

    action:
        "document": convert one document to PDF.
        "images":   put a set of images into one PDF, one per page.
        "merge":    convert several inputs and join them into a single PDF.
    """
    if not HAS_FPDF:
        print_error("Missing 'fpdf2'. Install it with 'pip install fpdf2'.")
        return False
    if page_size.lower() not in PAGE_SIZES:
        print_error(f"Unknown page size '{page_size}'. Use: {', '.join(PAGE_SIZES)}.")
        return False
    if not inputs:
        print_error("At least one input file or folder is required.")
        return False

    if action == "document":
        files = collect_inputs(inputs, only=DOCUMENT_EXTS | IMAGE_EXTS)
        if not files:
            print_error("No convertible document found.")
            return False
        if len(files) > 1:
            print_warning(
                f"{len(files)} files given; converting only '{os.path.basename(files[0])}'. "
                "Use the merge action to join them into one PDF."
            )
        src = files[0]
        out = output or (os.path.splitext(src)[0] + ".pdf")
        if os.path.abspath(out) == os.path.abspath(src):
            print_error("The output would overwrite the source file.")
            return False
        print_step(f"Converting '{os.path.basename(src)}' → {out}")
        if not document_to_pdf(src, out, use_libreoffice=use_libreoffice,
                               page_size=page_size):
            return False
        print_success(f"PDF created: {out}")
        return True

    if action == "images":
        files = collect_inputs(inputs, only=IMAGE_EXTS)
        if not files:
            print_error(f"No images found ({', '.join(sorted(IMAGE_EXTS))}).")
            return False
        out = output or _default_output(inputs, "_images")
        print_step(f"Building a PDF from {len(files)} image(s) → {out}")
        if not images_to_pdf(files, out, page_size=page_size, fit_to_page=fit_to_page):
            return False
        print_success(f"PDF created: {out}")
        return True

    if action == "merge":
        files = collect_inputs(inputs)
        if len(files) < 2:
            print_error("Merging needs at least two files.")
            return False
        out = output or _default_output(inputs, "_merged")
        print_step(f"Merging {len(files)} file(s) → {out}")
        if not merge_to_pdf(files, out, use_libreoffice=use_libreoffice,
                            page_size=page_size):
            return False
        print_success(f"PDF created: {out}")
        return True

    print_error(f"Unknown action: '{action}'. Use document, images or merge.")
    return False


def main() -> None:
    """CLI entry point for the PDF builder."""
    parser = argparse.ArgumentParser(
        description="Build PDFs: convert a document, bundle images, or merge many files."
    )
    sub = parser.add_subparsers(dest="action", required=True)

    p_doc = sub.add_parser("document", help="Convert one document to PDF.")
    p_doc.add_argument("input", help="Document to convert.")
    p_doc.add_argument("-o", "--output", help="Output PDF path.")

    p_img = sub.add_parser("images", help="Put images into one PDF, one per page.")
    p_img.add_argument("inputs", nargs="+", help="Image files and/or folders.")
    p_img.add_argument("-o", "--output", help="Output PDF path.")
    p_img.add_argument(
        "--exact", action="store_true",
        help="Size each page to its image instead of fitting it to a sheet.",
    )

    p_merge = sub.add_parser("merge", help="Convert several inputs into a single PDF.")
    p_merge.add_argument("inputs", nargs="+", help="Files and/or folders, in order.")
    p_merge.add_argument("-o", "--output", help="Output PDF path.")

    for sub_parser in (p_doc, p_img, p_merge):
        sub_parser.add_argument(
            "--page-size", default="a4", choices=list(PAGE_SIZES),
            help="Page size (default: a4).",
        )
    for sub_parser in (p_doc, p_merge):
        sub_parser.add_argument(
            "--no-libreoffice", action="store_true",
            help="Always use the Python engine, even if LibreOffice is installed.",
        )

    args = parser.parse_args()
    raw = [args.input] if args.action == "document" else args.inputs

    ok = run_pdf_builder(
        action=args.action,
        inputs=raw,
        output=args.output,
        use_libreoffice=not getattr(args, "no_libreoffice", False),
        page_size=args.page_size,
        fit_to_page=not getattr(args, "exact", False),
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""Screens for the tools that turn one format into another."""
from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, RadioButton, RadioSet, Static, Switch


from automation_tools.cli.screens.base import ToolScreen


# ── 4. Image / PDF Converter ───────────────────────────────────────────────
class ConverterScreen(ToolScreen):
    TOOL_TITLE = "🖼️   Image Converter"
    TOOL_DESC = "Convert images between formats or render PDF pages to images"

    def compose_fields(self) -> ComposeResult:
        yield Label("Mode:", classes="field-label")
        with RadioSet(id="mode"):
            yield RadioButton("🖼️   Convert image or folder", id="rb-img", value=True)
            yield RadioButton("📄  Render PDF to images", id="rb-pdf")
        yield Label("File or folder path:", classes="field-label")
        yield Input(placeholder="/path/to/image_or_folder", id="path")
        # Image options
        with Vertical(id="sec-img", classes="sub-section"):
            yield Label("Output format:", classes="field-label")
            with RadioSet(id="img-fmt"):
                yield RadioButton("PNG", id="rb-png", value=True)
                yield RadioButton("JPG", id="rb-jpg")
                yield RadioButton("WEBP", id="rb-webp")
                yield RadioButton("TIFF", id="rb-tiff")
            with Vertical(id="sec-quality", classes="sub-section"):
                yield Label("Quality (1–100):", classes="field-label")
                yield Input(placeholder="85", id="quality")
        # PDF options
        with Vertical(id="sec-pdf-opts", classes="sub-section"):
            yield Label("Output format:", classes="field-label")
            with RadioSet(id="pdf-fmt"):
                yield RadioButton("PNG", id="rb-pdf-png", value=True)
                yield RadioButton("JPG", id="rb-pdf-jpg")
                yield RadioButton("WEBP", id="rb-pdf-webp")
            yield Label("DPI:", classes="field-label")
            yield Input(placeholder="200", id="dpi")

    def on_mount(self) -> None:
        self.query_one("#sec-pdf-opts").display = False
        self.query_one("#sec-quality").display = False

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-img"
        self.query_one("#sec-img").display = (rid == "rb-img")
        self.query_one("#sec-pdf-opts").display = (rid == "rb-pdf")

    @on(RadioSet.Changed, "#img-fmt")
    def _fmt_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-png"
        self.query_one("#sec-quality").display = rid in ("rb-jpg", "rb-webp")

    async def action_do_run(self) -> None:
        from automation_tools.tools import converter
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        mode = self._rval(self.query_one("#mode", RadioSet)) or "rb-img"
        if mode == "rb-pdf":
            fmt_map = {"rb-pdf-png": "png", "rb-pdf-jpg": "jpg", "rb-pdf-webp": "webp"}
            fmt = fmt_map.get(self._rval(self.query_one("#pdf-fmt", RadioSet)) or "rb-pdf-png", "png")
            try:
                dpi = max(50, min(600, int(self._ival(self.query_one("#dpi", Input)) or "200")))
            except ValueError:
                dpi = 200
            await self._run_tool(converter.run_pdf_to_image, input_path=path,
                                 output_format=fmt, dpi=dpi)
        else:
            fmt_map = {"rb-png": "png", "rb-jpg": "jpg", "rb-webp": "webp", "rb-tiff": "tiff"}
            fmt = fmt_map.get(self._rval(self.query_one("#img-fmt", RadioSet)) or "rb-png", "png")
            try:
                quality = max(1, min(100, int(self._ival(self.query_one("#quality", Input)) or "85")))
            except ValueError:
                quality = 85
            await self._run_tool(converter.run_image_converter, input_path=path,
                                 output_format=fmt, quality=quality)


class ImageProcessorScreen(ToolScreen):
    TOOL_TITLE = "🪄  Image Processor"
    TOOL_DESC = "Batch resize, compress or watermark images. Originals are kept"

    def compose_fields(self) -> ComposeResult:
        yield Label("Operation:", classes="field-label")
        with RadioSet(id="op"):
            yield RadioButton("📐  Resize", id="rb-resize", value=True)
            yield RadioButton("🗜️   Compress", id="rb-compress")
            yield RadioButton("🪄  Watermark", id="rb-watermark")
        yield Label("Image file or folder:", classes="field-label")
        yield Input(placeholder="/path/to/image_or_folder", id="path")
        # Resize options
        with Vertical(id="sec-resize", classes="sub-section"):
            yield Label("Max dimension — longest side, px (leave empty if using %):",
                        classes="field-label")
            yield Input(placeholder="1920", id="max-size")
            yield Label("Or scale by percentage (e.g. 50):", classes="field-label")
            yield Input(placeholder="(optional)", id="scale")
        # Compress options
        with Vertical(id="sec-compress", classes="sub-section"):
            yield Label("Quality (1–100, lower = smaller file):", classes="field-label")
            yield Input(placeholder="80", id="quality")
        # Watermark options
        with Vertical(id="sec-watermark", classes="sub-section"):
            yield Label("Watermark text:", classes="field-label")
            yield Input(placeholder="© My Name 2026", id="wm-text")
            yield Label("Position:", classes="field-label")
            with RadioSet(id="wm-pos"):
                yield RadioButton("Bottom-right", id="rb-br", value=True)
                yield RadioButton("Bottom-left", id="rb-bl")
                yield RadioButton("Top-right", id="rb-tr")
                yield RadioButton("Top-left", id="rb-tl")
                yield RadioButton("Center", id="rb-center")
            yield Label("Opacity (0–100):", classes="field-label")
            yield Input(placeholder="50", id="wm-opacity")
        yield Label("Recurse into subfolders?", classes="field-label")
        yield Switch(id="recursive", value=False)
        yield Label("Output folder (leave empty for '<input>/processed'):",
                    classes="field-label")
        yield Input(placeholder="(optional)", id="out-dir")

    def on_mount(self) -> None:
        self.query_one("#sec-compress").display = False
        self.query_one("#sec-watermark").display = False

    @on(RadioSet.Changed, "#op")
    def _op_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-resize"
        self.query_one("#sec-resize").display = (rid == "rb-resize")
        self.query_one("#sec-compress").display = (rid == "rb-compress")
        self.query_one("#sec-watermark").display = (rid == "rb-watermark")

    async def action_do_run(self) -> None:
        from automation_tools.tools import image_processor

        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return

        op_map = {"rb-resize": "resize", "rb-compress": "compress", "rb-watermark": "watermark"}
        operation = op_map.get(self._rval(self.query_one("#op", RadioSet)) or "rb-resize", "resize")
        out_dir = self._ival(self.query_one("#out-dir", Input)) or None
        recursive = self._bval(self.query_one("#recursive", Switch))

        kwargs: dict = {
            "input_path": path,
            "operation": operation,
            "output_dir": out_dir,
            "recursive": recursive,
        }

        if operation == "resize":
            scale_raw = self._ival(self.query_one("#scale", Input))
            max_raw = self._ival(self.query_one("#max-size", Input))
            scale_percent = None
            max_size = None
            if scale_raw:
                try:
                    scale_percent = max(1, min(1000, int(scale_raw)))
                except ValueError:
                    self._err("Scale must be a whole number.")
                    return
            else:
                try:
                    max_size = max(1, int(max_raw or "1920"))
                except ValueError:
                    self._err("Max dimension must be a whole number.")
                    return
            kwargs["scale_percent"] = scale_percent
            kwargs["max_size"] = max_size
        elif operation == "compress":
            try:
                kwargs["quality"] = max(1, min(100, int(self._ival(self.query_one("#quality", Input)) or "80")))
            except ValueError:
                kwargs["quality"] = 80
        else:  # watermark
            text = self._ival(self.query_one("#wm-text", Input))
            if not text:
                self._err("Watermark text is required.")
                return
            pos_map = {
                "rb-br": "bottom-right", "rb-bl": "bottom-left",
                "rb-tr": "top-right", "rb-tl": "top-left", "rb-center": "center",
            }
            kwargs["watermark_text"] = text
            kwargs["wm_position"] = pos_map.get(
                self._rval(self.query_one("#wm-pos", RadioSet)) or "rb-br", "bottom-right"
            )
            try:
                kwargs["wm_opacity"] = max(0, min(100, int(self._ival(self.query_one("#wm-opacity", Input)) or "50")))
            except ValueError:
                kwargs["wm_opacity"] = 50

        await self._run_tool(image_processor.run_batch_image_processor, **kwargs)


# ── 5. Convert to PDF ──────────────────────────────────────────────────────
class PdfConverterScreen(ToolScreen):
    TOOL_TITLE = "📄  Convert to PDF"
    TOOL_DESC = "Convert a document, bundle images, or merge several files into one PDF"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("📄  Convert one document to PDF", id="rb-document", value=True)
            yield RadioButton("🖼️   Bundle images into one PDF", id="rb-images")
            yield RadioButton("🔗  Merge several files into one PDF", id="rb-merge")

        # Document
        with Vertical(id="sec-document", classes="sub-section"):
            yield Label("Document (.docx, .odt, .pptx, .txt, .md, .csv):",
                        classes="field-label")
            yield Input(placeholder="/path/to/document.docx", id="doc-input")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: same name, .pdf", id="doc-out")

        # Images
        with Vertical(id="sec-images", classes="sub-section"):
            yield Label("Images — files and/or a folder (comma-separated):",
                        classes="field-label")
            yield Input(placeholder="/path/to/scans    or    /a.jpg, /b.png", id="img-inputs")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <source>_images.pdf", id="img-out")
            yield Label("Fit each image to a page? (off = page matches the image)",
                        classes="field-label")
            yield Switch(id="img-fit", value=True)

        # Merge
        with Vertical(id="sec-merge", classes="sub-section"):
            yield Label("Files and/or folders, in order (comma-separated):",
                        classes="field-label")
            yield Input(placeholder="/report.docx, /slides.pptx, /photos", id="merge-inputs")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <source>_merged.pdf", id="merge-out")

        yield Static("[dim #4b5563]── Options ──────────────────────────[/]", classes="section-sep")
        yield Label("Page size:", classes="field-label")
        with RadioSet(id="page-size"):
            yield RadioButton("A4", id="rb-a4", value=True)
            yield RadioButton("Letter", id="rb-letter")
        yield Label("Use LibreOffice for Office files when it is installed?",
                    classes="field-label")
        yield Switch(id="use-lo", value=True)

    _SECTIONS = ("document", "images", "merge")

    def on_mount(self) -> None:
        for name in self._SECTIONS:
            if name != "document":
                self.query_one(f"#sec-{name}").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-document"
        selected = rid.replace("rb-", "")
        for name in self._SECTIONS:
            self.query_one(f"#sec-{name}").display = (name == selected)

    @staticmethod
    def _split(value: str) -> list:
        return [item.strip() for item in value.split(",") if item.strip()]

    async def action_do_run(self) -> None:
        from automation_tools.tools import pdf_builder
        action = (self._rval(self.query_one("#action", RadioSet)) or "rb-document").replace("rb-", "")
        page_size = "letter" if self._rval(self.query_one("#page-size", RadioSet)) == "rb-letter" else "a4"
        use_lo = self._bval(self.query_one("#use-lo", Switch))

        if action == "document":
            src = self._ival(self.query_one("#doc-input", Input))
            if not src:
                self._err("A document path is required.")
                return
            inputs, out = [src], self._ival(self.query_one("#doc-out", Input)) or None
            fit = True
        elif action == "images":
            inputs = self._split(self._ival(self.query_one("#img-inputs", Input)))
            if not inputs:
                self._err("At least one image file or folder is required.")
                return
            out = self._ival(self.query_one("#img-out", Input)) or None
            fit = self._bval(self.query_one("#img-fit", Switch))
        else:  # merge
            inputs = self._split(self._ival(self.query_one("#merge-inputs", Input)))
            if not inputs:
                self._err("At least one file or folder is required.")
                return
            out, fit = self._ival(self.query_one("#merge-out", Input)) or None, True

        await self._run_tool(
            pdf_builder.run_pdf_builder,
            action=action,
            inputs=inputs,
            output=out,
            use_libreoffice=use_lo,
            page_size=page_size,
            fit_to_page=fit,
        )


# ── 14. PDF Toolkit ────────────────────────────────────────────────────────
class PdfToolkitScreen(ToolScreen):
    TOOL_TITLE = "📑  PDF Toolkit"
    TOOL_DESC = "Merge, split, extract, rotate, encrypt or decrypt PDF files"

    def compose_fields(self) -> ComposeResult:
        yield Label("Operation:", classes="field-label")
        with RadioSet(id="op"):
            yield RadioButton("🔗  Merge several PDFs into one", id="rb-merge", value=True)
            yield RadioButton("✂️   Split into one file per page", id="rb-split")
            yield RadioButton("📑  Extract selected pages", id="rb-extract")
            yield RadioButton("🔄  Rotate pages", id="rb-rotate")
            yield RadioButton("🔒  Encrypt (set a password)", id="rb-encrypt")
            yield RadioButton("🔓  Decrypt (remove password)", id="rb-decrypt")

        # Merge
        with Vertical(id="sec-merge", classes="sub-section"):
            yield Label("PDF files (comma-separated) or a folder:", classes="field-label")
            yield Input(placeholder="/a.pdf, /b.pdf    or    /folder", id="merge-input")
            yield Label("Output PDF path:", classes="field-label")
            yield Input(placeholder="/path/to/merged.pdf", id="merge-out")

        # Split
        with Vertical(id="sec-split", classes="sub-section"):
            yield Label("PDF file to split:", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="split-input")
            yield Label("Output folder (optional):", classes="field-label")
            yield Input(placeholder="default: <name>_pages", id="split-out")

        # Extract
        with Vertical(id="sec-extract", classes="sub-section"):
            yield Label("PDF file:", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="extract-input")
            yield Label("Pages to keep (1-based, e.g. 1-3,5,8-10):", classes="field-label")
            yield Input(placeholder="1-3,5", id="extract-pages")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <name>_extract.pdf", id="extract-out")

        # Rotate
        with Vertical(id="sec-rotate", classes="sub-section"):
            yield Label("PDF file:", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="rotate-input")
            yield Label("Angle (clockwise):", classes="field-label")
            with RadioSet(id="rotate-angle"):
                yield RadioButton("90°", id="rb-90", value=True)
                yield RadioButton("180°", id="rb-180")
                yield RadioButton("270°", id="rb-270")
            yield Label("Pages (optional, blank = all pages):", classes="field-label")
            yield Input(placeholder="all pages", id="rotate-pages")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <name>_rotated.pdf", id="rotate-out")

        # Encrypt
        with Vertical(id="sec-encrypt", classes="sub-section"):
            yield Label("PDF file:", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="encrypt-input")
            yield Label("Password to set:", classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="encrypt-pwd")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <name>_encrypted.pdf", id="encrypt-out")

        # Decrypt
        with Vertical(id="sec-decrypt", classes="sub-section"):
            yield Label("Encrypted PDF file:", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="decrypt-input")
            yield Label("Current password:", classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="decrypt-pwd")
            yield Label("Output PDF (optional):", classes="field-label")
            yield Input(placeholder="default: <name>_decrypted.pdf", id="decrypt-out")

    _SECTIONS = ("merge", "split", "extract", "rotate", "encrypt", "decrypt")

    def on_mount(self) -> None:
        for name in self._SECTIONS:
            if name != "merge":
                self.query_one(f"#sec-{name}").display = False

    @on(RadioSet.Changed, "#op")
    def _op_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-merge"
        selected = rid.replace("rb-", "")
        for name in self._SECTIONS:
            self.query_one(f"#sec-{name}").display = (name == selected)

    async def action_do_run(self) -> None:
        from automation_tools.tools import pdf_toolkit
        op = (self._rval(self.query_one("#op", RadioSet)) or "rb-merge").replace("rb-", "")

        if op == "merge":
            inputs = self._ival(self.query_one("#merge-input", Input))
            out = self._ival(self.query_one("#merge-out", Input))
            if not inputs:
                self._err("Provide PDF files or a folder.")
                return
            if not out:
                self._err("Output path is required.")
                return
            await self._run_tool(pdf_toolkit.run_pdf_merge, inputs=inputs, output_path=out)

        elif op == "split":
            inp = self._ival(self.query_one("#split-input", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            out = self._ival(self.query_one("#split-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_split, input_path=inp, output_dir=out)

        elif op == "extract":
            inp = self._ival(self.query_one("#extract-input", Input))
            pages = self._ival(self.query_one("#extract-pages", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            if not pages:
                self._err("Page selection is required.")
                return
            out = self._ival(self.query_one("#extract-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_extract, input_path=inp,
                                 pages=pages, output_path=out)

        elif op == "rotate":
            inp = self._ival(self.query_one("#rotate-input", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            angle_map = {"rb-90": 90, "rb-180": 180, "rb-270": 270}
            angle = angle_map.get(self._rval(self.query_one("#rotate-angle", RadioSet)) or "rb-90", 90)
            pages = self._ival(self.query_one("#rotate-pages", Input)) or None
            out = self._ival(self.query_one("#rotate-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_rotate, input_path=inp,
                                 angle=angle, pages=pages, output_path=out)

        elif op == "encrypt":
            inp = self._ival(self.query_one("#encrypt-input", Input))
            pwd = self._ival(self.query_one("#encrypt-pwd", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            if not pwd:
                self._err("Password is required.")
                return
            out = self._ival(self.query_one("#encrypt-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_encrypt, input_path=inp,
                                 password=pwd, output_path=out)

        else:  # decrypt
            inp = self._ival(self.query_one("#decrypt-input", Input))
            pwd = self._ival(self.query_one("#decrypt-pwd", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            out = self._ival(self.query_one("#decrypt-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_decrypt, input_path=inp,
                                 password=pwd, output_path=out)



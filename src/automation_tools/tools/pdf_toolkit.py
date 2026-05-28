import argparse
import os
from typing import List, Optional

import questionary

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

# --- PDF Toolkit ---
# Manipulate existing PDF files: merge, split, extract pages, rotate, and
# encrypt / decrypt. Built entirely on `pypdf` (pure Python — no external
# binaries), so it runs the same on Linux, Windows and Termux/Android.

try:
    from pypdf import PdfReader, PdfWriter
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


# ── helpers ──────────────────────────────────────────────────────────────────
def _require_pypdf() -> bool:
    if not HAS_PYPDF:
        print_error("Missing 'pypdf'. Install it with 'pip install pypdf'.")
        return False
    return True


def _resolve_out(input_path: str, suffix: str) -> str:
    """Build a default output path next to the input: 'file_<suffix>.pdf'."""
    base, _ = os.path.splitext(input_path)
    return f"{base}_{suffix}.pdf"


def _confirm_overwrite(path: str) -> bool:
    """Ask before clobbering an existing file (modal in the TUI, prompt in CLI)."""
    if not os.path.exists(path):
        return True
    return bool(
        questionary.confirm(f"'{path}' already exists. Overwrite it?", default=False).ask()
    )


def _open_reader(path: str) -> Optional["PdfReader"]:
    """Open a PDF, transparently unlocking files with an empty password."""
    if not os.path.isfile(path):
        print_error(f"Not a file: '{path}'")
        return None
    try:
        reader = PdfReader(path)
        if reader.is_encrypted and not reader.decrypt(""):
            print_error(
                f"'{path}' is password-protected. Use the Decrypt action first."
            )
            return None
        return reader
    except Exception as e:
        print_error(f"Could not read '{path}': {e}")
        return None


def _parse_pages(spec: str, total: int) -> List[int]:
    """Turn a 1-based spec like '1-3,5,8-10' into ordered, de-duped 0-based indices."""
    indices: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                start, end = end, start
            page_numbers = range(start, end + 1)
        else:
            page_numbers = [int(part)]
        for n in page_numbers:
            if not (1 <= n <= total):
                raise ValueError(f"page {n} is out of range (document has {total} pages)")
            if (n - 1) not in indices:
                indices.append(n - 1)
    if not indices:
        raise ValueError("no pages selected")
    return indices


def _write(writer: "PdfWriter", output_path: str) -> bool:
    try:
        with open(output_path, "wb") as fh:
            writer.write(fh)
        return True
    except Exception as e:
        print_error(f"Could not write '{output_path}': {e}")
        return False


# ── operations ───────────────────────────────────────────────────────────────
def run_pdf_merge(inputs: str, output_path: str) -> None:
    """Merge several PDFs into one. `inputs` is a folder or a comma-separated list."""
    if not _require_pypdf():
        return
    if os.path.isdir(inputs):
        files = sorted(
            os.path.join(inputs, f)
            for f in os.listdir(inputs)
            if f.lower().endswith(".pdf")
        )
    else:
        files = [p.strip() for p in inputs.split(",") if p.strip()]

    if len(files) < 2:
        print_error("Provide at least two PDF files (or a folder containing them).")
        return
    if not output_path:
        print_error("An output path is required for merging.")
        return
    if not output_path.lower().endswith(".pdf"):
        output_path += ".pdf"
    if not _confirm_overwrite(output_path):
        print_warning("Cancelled.")
        return

    writer = PdfWriter()
    merged = 0
    for path in files:
        reader = _open_reader(path)
        if reader is None:
            return
        writer.append(reader)
        merged += 1
        print_step(f"Added '{path}' ({len(reader.pages)} pages)")

    if _write(writer, output_path):
        print_success(f"Merged {merged} files → '{output_path}'")


def run_pdf_split(input_path: str, output_dir: Optional[str] = None) -> None:
    """Split a PDF into one file per page inside an output folder."""
    if not _require_pypdf():
        return
    reader = _open_reader(input_path)
    if reader is None:
        return

    out_dir = output_dir or (os.path.splitext(input_path)[0] + "_pages")
    os.makedirs(out_dir, exist_ok=True)
    total = len(reader.pages)
    pad = max(3, len(str(total)))

    print_step(f"Splitting {total} pages into '{out_dir}'…")
    written = 0
    for i, page in enumerate(reader.pages, 1):
        writer = PdfWriter()
        writer.add_page(page)
        out = os.path.join(out_dir, f"page_{i:0{pad}d}.pdf")
        if _write(writer, out):
            console.print(f"  → {out}")
            written += 1

    print_success(f"{written}/{total} page(s) written to '{out_dir}'")


def run_pdf_extract(input_path: str, pages: str, output_path: Optional[str] = None) -> None:
    """Build a new PDF from selected pages (1-based spec, e.g. '1-3,5,8-10')."""
    if not _require_pypdf():
        return
    reader = _open_reader(input_path)
    if reader is None:
        return

    try:
        indices = _parse_pages(pages, len(reader.pages))
    except ValueError as e:
        print_error(f"Invalid page selection: {e}")
        return

    out = output_path or _resolve_out(input_path, "extract")
    if not _confirm_overwrite(out):
        print_warning("Cancelled.")
        return

    writer = PdfWriter()
    for idx in indices:
        writer.add_page(reader.pages[idx])
    if _write(writer, out):
        print_success(f"Extracted {len(indices)} page(s) → '{out}'")


def run_pdf_rotate(
    input_path: str,
    angle: int,
    pages: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Rotate pages clockwise by 90/180/270 degrees (all pages, or a 1-based spec)."""
    if not _require_pypdf():
        return
    if angle % 90 != 0:
        print_error("Angle must be a multiple of 90 (90, 180 or 270).")
        return
    reader = _open_reader(input_path)
    if reader is None:
        return

    total = len(reader.pages)
    if pages:
        try:
            targets = set(_parse_pages(pages, total))
        except ValueError as e:
            print_error(f"Invalid page selection: {e}")
            return
    else:
        targets = set(range(total))

    out = output_path or _resolve_out(input_path, "rotated")
    if not _confirm_overwrite(out):
        print_warning("Cancelled.")
        return

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in targets:
            page.rotate(angle)
        writer.add_page(page)
    if _write(writer, out):
        print_success(f"Rotated {len(targets)} page(s) by {angle}° → '{out}'")


def run_pdf_encrypt(input_path: str, password: str, output_path: Optional[str] = None) -> None:
    """Password-protect a PDF (AES-256 when available)."""
    if not _require_pypdf():
        return
    if not password:
        print_error("A password is required to encrypt.")
        return
    reader = _open_reader(input_path)
    if reader is None:
        return

    out = output_path or _resolve_out(input_path, "encrypted")
    if not _confirm_overwrite(out):
        print_warning("Cancelled.")
        return

    writer = PdfWriter()
    writer.append(reader)
    try:
        writer.encrypt(user_password=password, algorithm="AES-256")
    except Exception:
        # Older pypdf or unsupported algorithm — fall back to default cipher.
        writer.encrypt(user_password=password)
    if _write(writer, out):
        print_success(f"Encrypted → '{out}'")
        print_warning("Keep the password safe — there is no way to recover it.")


def run_pdf_decrypt(input_path: str, password: str, output_path: Optional[str] = None) -> None:
    """Remove protection from a PDF given its current password."""
    if not _require_pypdf():
        return
    if not os.path.isfile(input_path):
        print_error(f"Not a file: '{input_path}'")
        return
    try:
        reader = PdfReader(input_path)
    except Exception as e:
        print_error(f"Could not read '{input_path}': {e}")
        return

    if not reader.is_encrypted:
        print_warning("This PDF is not encrypted — nothing to do.")
        return
    if not reader.decrypt(password or ""):
        print_error("Wrong password — could not unlock the PDF.")
        return

    out = output_path or _resolve_out(input_path, "decrypted")
    if not _confirm_overwrite(out):
        print_warning("Cancelled.")
        return

    writer = PdfWriter()
    writer.append(reader)
    if _write(writer, out):
        print_success(f"Decrypted → '{out}'")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    """Standalone entry point for the PDF Toolkit."""
    parser = argparse.ArgumentParser(description="Merge, split, extract, rotate, encrypt or decrypt PDFs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_merge = sub.add_parser("merge", help="Merge several PDFs into one.")
    p_merge.add_argument("inputs", help="Folder, or comma-separated list of PDF files.")
    p_merge.add_argument("output", help="Output PDF path.")

    p_split = sub.add_parser("split", help="Split a PDF into one file per page.")
    p_split.add_argument("input", help="Input PDF path.")
    p_split.add_argument("--out-dir", help="Output folder (default: <name>_pages).")

    p_extract = sub.add_parser("extract", help="Extract selected pages into a new PDF.")
    p_extract.add_argument("input", help="Input PDF path.")
    p_extract.add_argument("pages", help="1-based selection, e.g. '1-3,5,8-10'.")
    p_extract.add_argument("--out", help="Output PDF path.")

    p_rotate = sub.add_parser("rotate", help="Rotate pages clockwise.")
    p_rotate.add_argument("input", help="Input PDF path.")
    p_rotate.add_argument("angle", type=int, help="90, 180 or 270.")
    p_rotate.add_argument("--pages", help="1-based selection (default: all pages).")
    p_rotate.add_argument("--out", help="Output PDF path.")

    p_enc = sub.add_parser("encrypt", help="Password-protect a PDF.")
    p_enc.add_argument("input", help="Input PDF path.")
    p_enc.add_argument("password", help="Password to set.")
    p_enc.add_argument("--out", help="Output PDF path.")

    p_dec = sub.add_parser("decrypt", help="Remove protection from a PDF.")
    p_dec.add_argument("input", help="Input PDF path.")
    p_dec.add_argument("password", help="Current password.")
    p_dec.add_argument("--out", help="Output PDF path.")

    args = parser.parse_args()
    if args.command == "merge":
        run_pdf_merge(args.inputs, args.output)
    elif args.command == "split":
        run_pdf_split(args.input, output_dir=args.out_dir)
    elif args.command == "extract":
        run_pdf_extract(args.input, args.pages, output_path=args.out)
    elif args.command == "rotate":
        run_pdf_rotate(args.input, args.angle, pages=args.pages, output_path=args.out)
    elif args.command == "encrypt":
        run_pdf_encrypt(args.input, args.password, output_path=args.out)
    elif args.command == "decrypt":
        run_pdf_decrypt(args.input, args.password, output_path=args.out)


if __name__ == "__main__":
    main()

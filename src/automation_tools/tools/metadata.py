import os
import argparse
import datetime
from typing import Dict, Any, Optional

import pypdf
from rich.table import Table

from automation_tools.core.logger import console, print_error, print_success, print_warning
from automation_tools.core.report import export_json, export_rows, is_csv

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def format_bytes(size: float) -> str:
    """Formats a byte count as KB/MB/GB/TB."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def get_basic_info(filepath: str) -> Dict[str, str]:
    """Basic filesystem information for a file."""
    stat = os.stat(filepath)
    return {
        "Size": format_bytes(stat.st_size),
        "Created": datetime.datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
        "Modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        "Path": os.path.abspath(filepath)
    }


def print_metadata_table(title: str, metadata_dict: Dict[str, Any]) -> None:
    """Prints a metadata dict as a Rich table."""
    if not metadata_dict:
        print_warning(f"No specific metadata found for {title}")
        return

    table = Table(title=title, show_header=True, title_style="bold magenta", header_style="bold cyan")
    table.add_column("Property", style="blue", no_wrap=True)
    table.add_column("Value", style="green")

    for key, value in metadata_dict.items():
        str_val = str(value)
        # Truncate long values for display
        if len(str_val) > 100:
            str_val = str_val[:97] + "..."
        table.add_row(str(key), str_val)

    console.print(table)
    console.print()


def extract_pdf_metadata(filepath: str) -> Dict[str, Any]:
    """Metadata of a PDF, via pypdf."""
    metadata: Dict[str, Any] = {}
    try:
        reader = pypdf.PdfReader(filepath)
        if reader.is_encrypted:
            metadata['Status'] = "Encrypted/Password Protected"
            metadata['Number of Pages'] = "Unknown (requires password)"
            return metadata

        info = reader.metadata
        if info:
            for key, value in info.items():
                # Remove leading slash usually found in PDF metadata keys
                clean_key = key.lstrip('/')
                metadata[clean_key] = value

        metadata['Number of Pages'] = len(reader.pages)
    except Exception as e:
        print_error(f"Error reading PDF: {e}")

    return metadata


def read_exif(img: "Image.Image") -> Dict[Any, Any]:
    """EXIF tags as {tag_id: value}, main IFD plus the Exif sub-IFD.

    getexif() is the public API and every image class has it. The private
    _getexif() used before is only defined on JPEG, TIFF and PNG, so a .bmp
    raised AttributeError and the read reported an error for a format the
    tool advertises as supported.
    """
    try:
        exif = img.getexif()
    except Exception:
        return {}
    tags: Dict[Any, Any] = dict(exif)
    try:
        tags.update(exif.get_ifd(ExifTags.IFD.Exif))
    except Exception:
        # Older Pillow without ExifTags.IFD, or an image with no sub-IFD.
        pass
    return tags


def extract_image_metadata(filepath: str) -> Dict[str, Any]:
    """EXIF plus basic image properties, via Pillow."""
    metadata: Dict[str, Any] = {}
    if not HAS_PILLOW:
        print_error("Pillow is not installed. Required for reading image metadata.")
        return metadata

    try:
        with Image.open(filepath) as img:
            metadata['Format'] = img.format
            metadata['Color Mode'] = img.mode
            metadata['Resolution'] = f"{img.width}x{img.height} px"

            exif_data = read_exif(img)
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    # Skip MakerNote or raw bytes to avoid clutter/errors
                    if tag_name == 'MakerNote' or isinstance(value, bytes):
                        continue
                    metadata[tag_name] = value

    except Exception as e:
        print_error(f"Error reading image: {e}")

    return metadata


def export_metadata(basic: Dict[str, Any], specific: Dict[str, Any], out_path: str) -> None:
    """Writes the metadata to `out_path`, as JSON or CSV depending on its extension."""
    if is_csv(out_path):
        rows = ([["basic", k, v] for k, v in basic.items()]
                + [["specific", k, str(v)] for k, v in specific.items()])
        export_rows(out_path, ["section", "property", "value"], rows)
    else:
        export_json(out_path, {
            "basic": basic,
            "specific": {k: str(v) for k, v in specific.items()},
        })


def clean_image_exif(filepath: str, out_path: Optional[str] = None) -> Optional[str]:
    """Strips EXIF (GPS, camera, dates) by rewriting the pixels into a new file.

    Defaults to filename_clean.ext. Returns the output path, or None on failure.
    """
    if not HAS_PILLOW:
        print_error("Pillow is not installed.")
        return None
    if not os.path.exists(filepath):
        print_error(f"Does not exist: {filepath}")
        return None

    out_path = out_path or (os.path.splitext(filepath)[0] + "_clean" + os.path.splitext(filepath)[1])
    try:
        with Image.open(filepath) as img:
            # Copy the pixels into a blank image, which is what leaves the
            # metadata behind. Going through raw bytes rather than getdata()
            # skips building a Python list of one tuple per pixel, and
            # getdata() is deprecated for removal in Pillow 14.
            clean = Image.frombytes(img.mode, img.size, img.tobytes())
            # In P/PA mode the pixels are palette indexes, so copying them into
            # a blank image without also copying the palette rendered every
            # colour as entry 0, i.e. a black picture.
            if img.mode in ("P", "PA"):
                palette = img.getpalette()
                if palette:
                    clean.putpalette(palette)
            clean.save(out_path)
        print_success(f"EXIF removed. Clean image saved at: {out_path}")
        return out_path
    except Exception as e:
        print_error(f"Could not clean EXIF: {e}")
        return None


def run_metadata_extractor(filepath: str, export_path: Optional[str] = None, clean_exif: bool = False) -> None:
    """Extracts and displays a file's metadata, optionally exporting it or writing an EXIF-free copy."""
    if not os.path.exists(filepath):
        print_error(f"The file '{filepath}' does not exist.")
        return

    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    console.print(f"\n[bold blue]Analyzing: {filename}[/bold blue]\n")

    basic_info = get_basic_info(filepath)
    print_metadata_table("System Information", basic_info)

    specific: Dict[str, Any] = {}
    if ext == '.pdf':
        specific = extract_pdf_metadata(filepath)
        print_metadata_table("Metadata and Document Info (PDF)", specific)
    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp', '.bmp']:
        specific = extract_image_metadata(filepath)
        print_metadata_table("EXIF Metadata and Image Information", specific)
    else:
        print_warning(f"Specific analysis not supported for format '{ext}'.")

    if export_path:
        export_metadata(basic_info, specific, export_path)

    if clean_exif:
        if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp', '.bmp']:
            clean_image_exif(filepath)
        else:
            print_warning("EXIF cleaning only applies to image files.")


def main():
    """Main entry point for the metadata extractor CLI.
    """
    parser = argparse.ArgumentParser(description="File Metadata Extractor (PDF, Images)")
    parser.add_argument("filepath", help="Path to the file to analyze")
    parser.add_argument("--export", help="Export metadata to JSON or CSV")
    parser.add_argument("--clean-exif", action="store_true", help="Create a copy without EXIF (images only)")
    args = parser.parse_args()

    run_metadata_extractor(args.filepath, export_path=args.export, clean_exif=args.clean_exif)


if __name__ == "__main__":
    main()

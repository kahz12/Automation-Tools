import os
import argparse
import csv
import datetime
import json
from typing import Dict, Any, Optional

import pypdf
from rich.table import Table

from automation_tools.core.logger import console, print_error, print_success, print_warning

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def format_bytes(size: float) -> str:
    """
    Formats bytes into a human-readable format (KB, MB, GB, TB).
    
    Args:
        size (float): The size in bytes.
        
    Returns:
        str: A formatted string representing the size.
    """
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def get_basic_info(filepath: str) -> Dict[str, str]:
    """
    Gets basic file system information for a file.
    
    Args:
        filepath (str): Path to the file.
        
    Returns:
        Dict[str, str]: Dictionary containing basic file info.
    """
    stat = os.stat(filepath)
    return {
        "Size": format_bytes(stat.st_size),
        "Created": datetime.datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
        "Modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        "Path": os.path.abspath(filepath)
    }


def print_metadata_table(title: str, metadata_dict: Dict[str, Any]) -> None:
    """
    Prints a dictionary of metadata as a formatted table using Rich.
    
    Args:
        title (str): The title of the table.
        metadata_dict (Dict[str, Any]): The metadata to display.
    """
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
    """
    Extracts metadata from a PDF file using pypdf.
    
    Args:
        filepath (str): Path to the PDF file.
        
    Returns:
        Dict[str, Any]: Dictionary containing PDF metadata.
    """
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


def extract_image_metadata(filepath: str) -> Dict[str, Any]:
    """
    Extracts EXIF metadata and basic properties of an image using Pillow.
    
    Args:
        filepath (str): Path to the image file.
        
    Returns:
        Dict[str, Any]: Dictionary containing image metadata.
    """
    metadata: Dict[str, Any] = {}
    if not HAS_PILLOW:
        print_error("Pillow is not installed. Required for reading image metadata.")
        return metadata

    try:
        with Image.open(filepath) as img:
            metadata['Format'] = img.format
            metadata['Color Mode'] = img.mode
            metadata['Resolution'] = f"{img.width}x{img.height} px"

            exif_data = img._getexif()
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
    """
    Exports metadata to a JSON or CSV file based on the file extension.
    
    Args:
        basic (Dict[str, Any]): Basic file information.
        specific (Dict[str, Any]): Specific file metadata (PDF/Image).
        out_path (str): The destination file path.
    """
    ext = os.path.splitext(out_path)[1].lower()
    try:
        if ext == ".csv":
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["section", "property", "value"])
                for k, v in basic.items():
                    writer.writerow(["basic", k, v])
                for k, v in specific.items():
                    writer.writerow(["specific", k, str(v)])
        else:
            payload = {"basic": basic, "specific": {k: str(v) for k, v in specific.items()}}
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        print_success(f"Metadata exported to: {out_path}")
    except Exception as e:
        print_error(f"Failed to export metadata: {e}")


def clean_image_exif(filepath: str, out_path: Optional[str] = None) -> Optional[str]:
    """
    Removes EXIF metadata (GPS, camera info, dates) from an image by rewriting pixels.
    
    Args:
        filepath (str): Path to the source image.
        out_path (Optional[str]): Path to the output clean image. Defaults to filename_clean.ext.
        
    Returns:
        Optional[str]: The output path on success, None otherwise.
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
            # Get pixel data and create a new image without metadata
            data = list(img.getdata())
            clean = Image.new(img.mode, img.size)
            clean.putdata(data)
            clean.save(out_path)
        print_success(f"EXIF removed. Clean image saved at: {out_path}")
        return out_path
    except Exception as e:
        print_error(f"Could not clean EXIF: {e}")
        return None


def run_metadata_extractor(filepath: str, export_path: Optional[str] = None, clean_exif: bool = False) -> None:
    """
    Core function to extract, display, and optionally export or clean file metadata.
    
    Args:
        filepath (str): Path to the file to analyze.
        export_path (Optional[str]): Path where metadata should be exported.
        clean_exif (bool): Whether to create a copy of the image without EXIF metadata.
    """
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
    """
    Main entry point for the metadata extractor CLI.
    """
    parser = argparse.ArgumentParser(description="File Metadata Extractor (PDF, Images)")
    parser.add_argument("filepath", help="Path to the file to analyze")
    parser.add_argument("--export", help="Export metadata to JSON or CSV")
    parser.add_argument("--clean-exif", action="store_true", help="Create a copy without EXIF (images only)")
    args = parser.parse_args()

    run_metadata_extractor(args.filepath, export_path=args.export, clean_exif=args.clean_exif)


if __name__ == "__main__":
    main()

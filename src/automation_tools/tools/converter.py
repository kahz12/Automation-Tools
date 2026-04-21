import argparse
import os
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# Mapping of file extensions to Pillow image formats
FORMAT_MAP = {
    'jpg': 'JPEG',
    'jpeg': 'JPEG',
    'png': 'PNG',
    'webp': 'WEBP',
    'bmp': 'BMP',
    'tiff': 'TIFF',
    'gif': 'GIF',
}


def convert_single_file(
    input_path: str,
    output_format: str,
    quality: int = 85,
) -> bool:
    """
    Converts a single image file to the specified format.
    
    Args:
        input_path (str): Path to the source image file.
        output_format (str): The target format (e.g., 'png', 'jpg', 'webp').
        quality (int): Quality setting for JPEG and WebP output (1-100).
        
    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    try:
        pillow_format = FORMAT_MAP.get(output_format.lower())
        if not pillow_format:
            print_error(f"Unsupported output format: {output_format}")
            return False

        if not HAS_PILLOW:
            print_error("Pillow is not installed. Install it with 'pip install Pillow'.")
            return False

        with Image.open(input_path) as img:
            # JPEG does not support transparency; convert to RGB if necessary
            if pillow_format == 'JPEG' and img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_directory = os.path.dirname(input_path) if os.path.dirname(input_path) else '.'
            output_filename = f"{base_name}.{output_format.lower()}"
            output_path = os.path.join(output_directory, output_filename)

            save_kwargs = {'format': pillow_format}
            if pillow_format in ('JPEG', 'WEBP'):
                save_kwargs['quality'] = max(1, min(100, quality))
                if pillow_format == 'JPEG':
                    save_kwargs['optimize'] = True

            img.save(output_path, **save_kwargs)

        console.print(f"Converted: '{input_path}' -> [green]'{output_path}'[/green]")
        return True
    except Exception as e:
        print_error(f"Error converting '{input_path}': {e}")
        return False


def run_image_converter(input_path: str, output_format: str, quality: int = 85) -> None:
    """
    Core function to convert an image or a directory of images.
    
    Args:
        input_path (str): Path to an image file or a directory containing images.
        output_format (str): The target format for the images.
        quality (int): Quality setting for JPEG/WebP (1-100).
    """
    if not os.path.exists(input_path):
        print_error(f"The path '{input_path}' is not valid.")
        return

    if os.path.isdir(input_path):
        print_step(f"Processing directory: {input_path}")
        supported_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif')
        files = [f for f in os.listdir(input_path) if f.lower().endswith(supported_extensions)]

        if not files:
            print_error("No supported images found in the directory.")
            return

        success_count = 0
        for file in files:
            full_path = os.path.join(input_path, file)
            if convert_single_file(full_path, output_format, quality=quality):
                success_count += 1

        print_success(f"Process completed. {success_count}/{len(files)} images converted.")

    elif os.path.isfile(input_path):
        if convert_single_file(input_path, output_format, quality=quality):
            print_success("Image converted.")


def run_pdf_converter(input_path: str) -> None:
    """
    Converts a document (docx, odt, etc.) to PDF using LibreOffice headless mode.
    
    Args:
        input_path (str): Path to the source document.
    """
    import subprocess

    if not os.path.exists(input_path):
        print_error(f"The file '{input_path}' does not exist.")
        return

    try:
        print_step(f"Converting '{input_path}' to PDF...")

        command = [
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(input_path) or '.',
            input_path
        ]

        # Execute LibreOffice command
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print_success("The PDF has been saved in the same folder.")

    except FileNotFoundError:
        print_error("LibreOffice is not installed or not found in PATH.")
    except subprocess.CalledProcessError as e:
        print_error(f"An error occurred while converting the document: {e}")
    except Exception as e:
        print_error(f"Unexpected error: {e}")


def run_pdf_to_image(input_path: str, output_format: str = "png", dpi: int = 200) -> None:
    """
    Converts each page of a PDF file to an image.
    Requires `pdf2image` library and `poppler` binaries.
    
    Args:
        input_path (str): Path to the PDF file.
        output_format (str): The target image format (default: 'png').
        dpi (int): Dots per inch for rendering (default: 200).
    """
    if not os.path.exists(input_path):
        print_error(f"The file '{input_path}' does not exist.")
        return

    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        print_error(
            "Missing 'pdf2image'. Install it with 'pip install pdf2image' and 'poppler' binary "
            "(Termux: 'pkg install poppler'; Debian/Ubuntu: 'apt install poppler-utils')."
        )
        return

    fmt = output_format.lower()
    if FORMAT_MAP.get(fmt) is None:
        print_error(f"Unsupported format: {fmt}")
        return

    try:
        print_step(f"Rendering PDF to {fmt.upper()} at {dpi} dpi…")
        pages = convert_from_path(input_path, dpi=dpi)
        base = os.path.splitext(input_path)[0]
        out_dir = base + "_pages"
        os.makedirs(out_dir, exist_ok=True)

        for i, page in enumerate(pages, 1):
            out = os.path.join(out_dir, f"page_{i:03d}.{fmt}")
            # Convert to RGB if format is JPEG to ensure compatibility
            if fmt in ("jpg", "jpeg") and page.mode != "RGB":
                page = page.convert("RGB")
            page.save(out, FORMAT_MAP[fmt])
            console.print(f"  → {out}")

        print_success(f"{len(pages)} page(s) exported to: {out_dir}")
    except Exception as e:
        print_error(f"Error converting PDF: {e}")


def main():
    """
    Main entry point for the converter tool CLI.
    Parses arguments and dispatches to appropriate conversion function.
    """
    parser = argparse.ArgumentParser(description="Converts an image or directory to a different format.")
    parser.add_argument("input_path", help="Path to the input file or directory.")
    parser.add_argument("output_format", help="Output format (png, jpg, webp, ...).")
    parser.add_argument("--quality", type=int, default=85, help="JPEG/WebP quality (1-100, default 85).")
    parser.add_argument("--from-pdf", action="store_true", help="Render PDF to images (requires pdf2image).")
    parser.add_argument("--dpi", type=int, default=200, help="DPI when rendering PDF (default 200).")
    args = parser.parse_args()

    if args.from_pdf:
        run_pdf_to_image(args.input_path, args.output_format, dpi=args.dpi)
    else:
        run_image_converter(args.input_path, args.output_format, quality=args.quality)


if __name__ == "__main__":
    main()

import argparse
import os
import tempfile
from typing import Any

from automation_tools.core.logger import console, print_error, print_step, print_success

try:
    from PIL import Image
    from PIL.Image import Image as PillowImage
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


def _next_output_path(input_path: str, output_format: str) -> str:
    """Return an output path that cannot overwrite an existing filesystem entry.

    Conversion is often run over a directory containing files with the same
    stem (for example ``photo.jpg`` and ``photo.png``).  Both would naturally
    map to ``photo.webp``; choose a numbered suffix for the later result.  A
    same-format conversion gets the existing ``_converted`` name first, then
    the same numbering policy.  ``lexists`` also protects dangling symlinks.
    """
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_directory = os.path.dirname(input_path) if os.path.dirname(input_path) else '.'
    ext = output_format.lower()
    source = os.path.normcase(os.path.abspath(input_path))
    preferred = os.path.join(output_directory, f"{base_name}.{ext}")

    if os.path.normcase(os.path.abspath(preferred)) == source:
        stem = f"{base_name}_converted"
        candidate = os.path.join(output_directory, f"{stem}.{ext}")
        index = 1
        while os.path.lexists(candidate):
            candidate = os.path.join(output_directory, f"{stem}_{index}.{ext}")
            index += 1
        return candidate

    if not os.path.lexists(preferred):
        return preferred

    # The preferred name is occupied by another input or a prior result.
    # Number from the base (base_1, base_2, …), rather than nesting suffixes
    # (base_1_2), so repeated runs remain predictable.
    index = 1
    while True:
        candidate = os.path.join(output_directory, f"{base_name}_{index}.{ext}")
        if not os.path.lexists(candidate):
            return candidate
        index += 1


def convert_single_file(
    input_path: str,
    output_format: str,
    quality: int = 85,
) -> bool:
    """Converts one image file to `output_format`. False if it could not be read or written."""
    try:
        pillow_format = FORMAT_MAP.get(output_format.lower())
        if not pillow_format:
            print_error(f"Unsupported output format: {output_format}")
            return False

        if not HAS_PILLOW:
            print_error("Pillow is not installed. Install it with 'pip install Pillow'.")
            return False

        with Image.open(input_path) as img:
            image: PillowImage = img
            # JPEG does not support transparency; convert to RGB if necessary
            if pillow_format == 'JPEG' and image.mode in ('RGBA', 'P', 'LA'):
                image = image.convert('RGB')

            output_path = _next_output_path(input_path, output_format)

            save_kwargs: dict[str, Any] = {'format': pillow_format}
            if pillow_format in ('JPEG', 'WEBP'):
                save_kwargs['quality'] = max(1, min(100, quality))
                if pillow_format == 'JPEG':
                    save_kwargs['optimize'] = True

            image.save(output_path, **save_kwargs)

        console.print(f"Converted: '{input_path}' -> [green]'{output_path}'[/green]")
        return True
    except Exception as e:
        print_error(f"Error converting '{input_path}': {e}")
        return False


def run_image_converter(input_path: str, output_format: str, quality: int = 85) -> None:
    """Converts an image, or every image in a directory, to `output_format`."""
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


def run_pdf_to_image(input_path: str, output_format: str = "png", dpi: int = 200) -> None:
    """Renders each page of a PDF as an image. Needs `pdf2image` and the poppler binaries."""
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
        base = os.path.splitext(input_path)[0]
        out_dir = base + "_pages"
        os.makedirs(out_dir, exist_ok=True)
        # Ask pdf2image for temporary paths instead of retaining every raster
        # page in memory.  A 300-page PDF can otherwise consume gigabytes.
        with tempfile.TemporaryDirectory(prefix="pdf-pages-") as staging:
            page_paths = convert_from_path(
                input_path, dpi=dpi, output_folder=staging,
                paths_only=True, fmt=fmt,
            )
            for i, page_path in enumerate(page_paths, 1):
                out = os.path.join(out_dir, f"page_{i:03d}.{fmt}")
                with Image.open(page_path) as page:
                    image: PillowImage = page
                    if fmt in ("jpg", "jpeg") and image.mode != "RGB":
                        image = image.convert("RGB")
                    image.save(out, FORMAT_MAP[fmt])
                console.print(f"  → {out}")

        print_success(f"{len(page_paths)} page(s) exported to: {out_dir}")
    except Exception as e:
        print_error(f"Error converting PDF: {e}")


def main():
    """Main entry point for the converter tool CLI.
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

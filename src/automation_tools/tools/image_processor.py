import argparse
import os
from typing import Optional, Tuple

from automation_tools.core import fs
from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

# Bulk operations over a single image or a whole folder, built only on Pillow
# so it runs the same on Linux, Windows and Termux/Android (no extra binaries):
#   resize:    shrink by longest side or by percentage (keeps aspect ratio).
#   compress:  re-encode at a target quality to reduce file size.
#   watermark: stamp a semi-transparent text label onto each image.
# Outputs are always written to a separate folder, so the originals are never
# touched unless the user explicitly points the output at the source folder.

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# Extensions we accept as input, and how Pillow names each output format.
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".gif")
FORMAT_MAP = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
    "bmp": "BMP",
    "tiff": "TIFF",
    "gif": "GIF",
}

# Anchor positions accepted for the watermark.
WATERMARK_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")

# Common TrueType font locations across platforms; falls back to Pillow's
# bitmap font when none are present (e.g. a bare Termux install).
_FONT_CANDIDATES = (
    "/system/fonts/Roboto-Regular.ttf",                                   # Android
    "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf",     # Termux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                    # Debian/Ubuntu
    "/usr/share/fonts/TTF/DejaVuSans.ttf",                                # Arch
    "/Library/Fonts/Arial.ttf",                                           # macOS
    "C:\\Windows\\Fonts\\arial.ttf",                                      # Windows
)


def human_size(n: int) -> str:
    """Converts a byte count into a human-readable string (e.g. 1.5 MB)."""
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _load_font(size: int) -> "ImageFont.ImageFont":
    """Loads a scalable TrueType font, falling back to Pillow's default."""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _resize_image(
    img: "Image.Image",
    max_size: Optional[int],
    scale_percent: Optional[int],
) -> "Image.Image":
    """Resizes an image preserving aspect ratio.

    If `scale_percent` is given it takes priority; otherwise the longest side is
    capped at `max_size` (images already smaller are left alone; it never upscales).
    """
    if scale_percent:
        new_w = max(1, int(img.width * scale_percent / 100))
        new_h = max(1, int(img.height * scale_percent / 100))
    elif max_size:
        longest = max(img.width, img.height)
        if longest <= max_size:
            return img  # already within bounds; don't upscale
        ratio = max_size / longest
        new_w = max(1, int(img.width * ratio))
        new_h = max(1, int(img.height * ratio))
    else:
        return img
    return img.resize((new_w, new_h), Image.LANCZOS)


def _apply_watermark(
    img: "Image.Image",
    text: str,
    position: str,
    opacity: int,
) -> "Image.Image":
    """Stamps a semi-transparent text watermark (with a subtle shadow) onto the image."""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # Scale the font to the image so the stamp reads on both thumbnails and 4K.
    font_size = max(14, base.width // 22)
    font = _load_font(font_size)

    # Measure the text box (textbbox is available on modern Pillow).
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        text_w, text_h = draw.textlength(text, font=font), font_size

    margin = max(8, base.width // 50)
    positions = {
        "top-left": (margin, margin),
        "top-right": (base.width - text_w - margin, margin),
        "bottom-left": (margin, base.height - text_h - margin * 2),
        "bottom-right": (base.width - text_w - margin, base.height - text_h - margin * 2),
        "center": ((base.width - text_w) // 2, (base.height - text_h) // 2),
    }
    x, y = positions.get(position, positions["bottom-right"])

    alpha = max(0, min(255, int(255 * opacity / 100)))
    # Shadow first, then the light text on top for legibility over any background.
    draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, alpha))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))

    return Image.alpha_composite(base, overlay)


def _save_image(img: "Image.Image", output_path: str, quality: int) -> None:
    """Saves an image, handling JPEG's lack of transparency and quality flags."""
    ext = os.path.splitext(output_path)[1].lower().lstrip(".")
    pil_format = FORMAT_MAP.get(ext, "PNG")

    if pil_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    save_kwargs = {"format": pil_format}
    if pil_format in ("JPEG", "WEBP"):
        save_kwargs["quality"] = max(1, min(100, quality))
        if pil_format == "JPEG":
            save_kwargs["optimize"] = True

    img.save(output_path, **save_kwargs)


def _process_one(
    input_path: str,
    output_path: str,
    operation: str,
    max_size: Optional[int],
    scale_percent: Optional[int],
    quality: int,
    watermark_text: str,
    wm_position: str,
    wm_opacity: int,
) -> Tuple[bool, int, int]:
    """Applies a single operation to one file.

    Returns (success, original_bytes, new_bytes).
    """
    try:
        original_bytes = os.path.getsize(input_path)
        with Image.open(input_path) as img:
            # Honour EXIF orientation so portrait photos aren't rotated wrong.
            img = ImageOps.exif_transpose(img)

            if operation == "resize":
                img = _resize_image(img, max_size, scale_percent)
            elif operation == "watermark":
                img = _apply_watermark(img, watermark_text, wm_position, wm_opacity)
            # "compress" needs no transform; the quality drop happens on save.

            _save_image(img, output_path, quality)

        new_bytes = os.path.getsize(output_path)
        return True, original_bytes, new_bytes
    except Exception as e:
        print_error(f"Error processing '{os.path.basename(input_path)}': {e}")
        return False, 0, 0


def _resolve_output_dir(input_path: str, output_dir: Optional[str]) -> str:
    """Picks the destination folder, defaulting to a 'processed' subfolder."""
    if output_dir:
        return output_dir
    if os.path.isdir(input_path):
        return os.path.join(input_path, "processed")
    parent = os.path.dirname(input_path) or "."
    return os.path.join(parent, "processed")


def _collect_files(input_path: str, recursive: bool,
                   exclude_dir: Optional[str] = None) -> list:
    """Returns the list of supported image files for the given path.

    `exclude_dir` is pruned from the walk. The destination defaults to a
    `processed` subfolder of the source, so without this a recursive second run
    picked up its own output from the first one and processed it again.
    """
    return list(fs.walk_files(input_path, recursive=recursive,
                             extensions=SUPPORTED_EXTENSIONS,
                             skip_dir=exclude_dir))


def run_batch_image_processor(
    input_path: str,
    operation: str = "resize",
    output_dir: Optional[str] = None,
    max_size: Optional[int] = 1920,
    scale_percent: Optional[int] = None,
    quality: int = 80,
    watermark_text: str = "",
    wm_position: str = "bottom-right",
    wm_opacity: int = 50,
    recursive: bool = False,
) -> None:
    """Core workflow for the batch image processor.

    `operation` is one of "resize", "compress" or "watermark", and each one reads
    only its own knobs: resize takes `max_size` or `scale_percent`, compress takes
    `quality`, watermark takes `watermark_text` / `wm_position` / `wm_opacity`.
    Results go to a `processed` subfolder unless `output_dir` says otherwise.
    """
    if not HAS_PILLOW:
        print_error("Pillow is not installed. Install it with 'pip install Pillow'.")
        return

    if operation not in ("resize", "compress", "watermark"):
        print_error(f"Unknown operation: '{operation}'. Use resize, compress or watermark.")
        return

    if not os.path.exists(input_path):
        print_error(f"The path '{input_path}' is not valid.")
        return

    if operation == "watermark" and not watermark_text:
        print_error("Watermark mode needs a text (use --text).")
        return

    if operation == "resize" and not scale_percent and not max_size:
        print_error("Resize mode needs --max-size or --scale.")
        return

    # Resolve the destination first so the scan can skip it.
    out_dir = _resolve_output_dir(input_path, output_dir)

    files = _collect_files(input_path, recursive, exclude_dir=out_dir)
    if not files:
        print_error("No supported images found (.png, .jpg, .webp, .bmp, .tiff, .gif).")
        return

    os.makedirs(out_dir, exist_ok=True)

    labels = {"resize": "Resizing", "compress": "Compressing", "watermark": "Watermarking"}
    print_step(f"{labels[operation]} {len(files)} image(s) → [bold]{out_dir}[/bold]")

    success = 0
    total_in = 0
    total_out = 0
    for filepath in files:
        filename = os.path.basename(filepath)
        output_path = os.path.join(out_dir, filename)

        # Never silently overwrite the original when the output lands in the
        # same folder as the source, so add an operation suffix instead.
        if os.path.abspath(output_path) == os.path.abspath(filepath):
            base, ext = os.path.splitext(filename)
            output_path = os.path.join(out_dir, f"{base}_{operation}{ext}")

        ok, in_bytes, out_bytes = _process_one(
            filepath, output_path, operation,
            max_size=max_size, scale_percent=scale_percent, quality=quality,
            watermark_text=watermark_text, wm_position=wm_position, wm_opacity=wm_opacity,
        )
        if not ok:
            continue

        success += 1
        total_in += in_bytes
        total_out += out_bytes

        if operation == "compress" and in_bytes:
            saved = in_bytes - out_bytes
            pct = (saved / in_bytes * 100) if in_bytes else 0
            tag = (
                f"[green]−{human_size(saved)} ({pct:.0f}%)[/green]" if saved > 0
                else "[yellow]no gain[/yellow]"
            )
            console.print(f"  ✓ {filename}: {human_size(in_bytes)} → {human_size(out_bytes)}  {tag}")
        else:
            console.print(f"  ✓ {filename} → '{os.path.basename(output_path)}'")

    if success == 0:
        print_warning("No images were processed.")
        return

    print_success(f"Done. {success}/{len(files)} image(s) processed → {out_dir}")
    if operation == "compress" and total_in:
        saved = total_in - total_out
        pct = (saved / total_in * 100) if total_in else 0
        console.print(
            f"[bold]📊 Total:[/bold] {human_size(total_in)} → {human_size(total_out)} "
            f"([green]saved {human_size(max(0, saved))} · {pct:.0f}%[/green])"
        )


def main() -> None:
    """CLI entry point for the Batch Image Processor."""
    parser = argparse.ArgumentParser(
        description="Batch image processor: resize, compress or watermark images."
    )
    parser.add_argument("input_path", help="Image file or folder of images.")
    parser.add_argument(
        "--op", choices=["resize", "compress", "watermark"], default="resize",
        help="Operation to apply (default: resize).",
    )
    parser.add_argument("--out-dir", help="Output folder (default: <input>/processed).")
    parser.add_argument("--recursive", action="store_true", help="Recurse into subfolders.")
    # resize
    parser.add_argument("--max-size", type=int, default=1920,
                        help="Longest-side cap in px for resize (default: 1920).")
    parser.add_argument("--scale", type=int, default=None,
                        help="Resize by this percentage instead of --max-size.")
    # compress / save
    parser.add_argument("--quality", type=int, default=80,
                        help="JPEG/WebP quality 1-100 (default: 80).")
    # watermark
    parser.add_argument("--text", default="", help="Watermark text.")
    parser.add_argument("--position", choices=list(WATERMARK_POSITIONS), default="bottom-right",
                        help="Watermark anchor (default: bottom-right).")
    parser.add_argument("--opacity", type=int, default=50,
                        help="Watermark opacity 0-100 (default: 50).")
    args = parser.parse_args()

    run_batch_image_processor(
        input_path=args.input_path,
        operation=args.op,
        output_dir=args.out_dir,
        max_size=args.max_size,
        scale_percent=args.scale,
        quality=args.quality,
        watermark_text=args.text,
        wm_position=args.position,
        wm_opacity=args.opacity,
        recursive=args.recursive,
    )


if __name__ == "__main__":
    main()

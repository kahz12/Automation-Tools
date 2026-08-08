import argparse
import io
import os
from typing import List, Optional, Tuple

from automation_tools.ai import AIProviderError, Capability, get_provider
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Extract text from images or scanned documents using a vision-capable AI
# provider. Works on a single image or a whole folder (batch), and can output
# either a faithful plain-text transcription or reconstructed Markdown
# (headings, lists, tables). It complements the AI Summarizer/Translator, which
# only handle text-based files; this one reads pixels.

# Formats accepted directly, mapped to their MIME type.
DIRECT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
# Other raster formats we can OCR by first normalizing them to PNG via Pillow.
CONVERTIBLE_EXTS = {".bmp", ".gif", ".tif", ".tiff"}
IMAGE_EXTS = set(DIRECT_MIME) | CONVERTIBLE_EXTS


def _image_to_bytes(path: str) -> Tuple[bytes, str]:
    """Loads an image as (data, mime_type) ready for the vision provider.

    Formats the API accepts natively are sent as-is; anything else (BMP, GIF,
    TIFF…) is converted to PNG with Pillow so it can still be processed.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in DIRECT_MIME:
        with open(path, "rb") as f:
            return f.read(), DIRECT_MIME[ext]

    from PIL import Image

    with Image.open(path) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return buf.getvalue(), "image/png"


def _collect_images(path: str, recursive: bool = False) -> List[str]:
    """Returns the image files to process for a file or directory `path`."""
    if os.path.isfile(path):
        return [path] if os.path.splitext(path)[1].lower() in IMAGE_EXTS else []

    images: List[str] = []
    if recursive:
        for root, _, files in os.walk(path):
            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                    images.append(os.path.join(root, name))
    else:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full) and os.path.splitext(name)[1].lower() in IMAGE_EXTS:
                images.append(full)
    return images


def _build_prompt(markdown: bool = False, language: Optional[str] = None) -> str:
    """Builds the OCR instruction sent alongside the image."""
    parts = [
        "You are a precise OCR engine. Transcribe ALL text visible in the image "
        "exactly as it appears, preserving line breaks, paragraphs, and reading "
        "order. Do not translate, summarize, correct spelling, or add any "
        "commentary. If a region is unreadable, write [illegible] in its place.",
    ]
    if markdown:
        parts.append(
            "Format the result as clean Markdown, reconstructing headings, lists, "
            "and tables where the layout implies them."
        )
    if language:
        parts.append(f"The text is primarily written in {language}.")
    parts.append("Output only the transcribed text, nothing else.")
    return " ".join(parts)


def ocr_image(
    provider,
    path: str,
    markdown: bool = False,
    language: Optional[str] = None,
) -> Optional[str]:
    """Runs OCR on a single image and returns the transcribed text (or None)."""
    try:
        image_bytes, mime_type = _image_to_bytes(path)
    except Exception as e:
        print_error(f"Could not read image '{os.path.basename(path)}': {e}")
        return None

    prompt = _build_prompt(markdown=markdown, language=language)
    return provider.generate_vision(prompt, image_bytes, mime_type)


def _output_path(src: str, out_dir: Optional[str], ext: str) -> str:
    """Computes the .txt/.md output path for a source image."""
    base = os.path.splitext(os.path.basename(src))[0] + ext
    target_dir = out_dir if out_dir else os.path.dirname(src) or "."
    return os.path.join(target_dir, base)


def _write_text(text: str, out_path: str) -> bool:
    """Writes transcribed text to disk, returning success."""
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        print_error(f"Could not write '{out_path}': {e}")
        return False


def run_ocr(
    path: str,
    api_key: Optional[str] = None,
    out_path: Optional[str] = None,
    markdown: bool = False,
    language: Optional[str] = None,
    recursive: bool = False,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> bool:
    """Core workflow: OCR a single image or every image in a folder.

    - Single image: prints the text and, if `out_path` is given, saves it there.
    - Folder: writes each result next to its source (or into `out_path` used as
      a directory) as a .txt/.md file, and prints a summary.

    Returns True if at least one image was transcribed successfully.
    """
    if not os.path.exists(path):
        print_error(f"The path '{path}' does not exist.")
        return False

    images = _collect_images(path, recursive=recursive)
    if not images:
        print_error(f"No supported images found ({', '.join(sorted(IMAGE_EXTS))}).")
        return False

    try:
        ai = get_provider(Capability.VISION, name=provider, api_key=api_key, model=model)
    except AIProviderError as e:
        print_error(str(e))
        return False

    ext = ".md" if markdown else ".txt"

    # Single-image mode: print the result, optionally save to a file.
    if os.path.isfile(path):
        print_step(f"Reading text from '{os.path.basename(path)}' with {ai.name}…")
        text = ocr_image(ai, path, markdown=markdown, language=language)
        if not text:
            print_error("No text could be extracted.")
            return False
        console.print(f"\n[cyan]{'=' * 40}[/cyan]")
        console.print("[bold]EXTRACTED TEXT[/bold]")
        console.print(f"[cyan]{'=' * 40}[/cyan]\n")
        console.print(text)
        if out_path:
            if _write_text(text, out_path):
                print_success(f"Text saved to: {out_path}")
        return True

    # Batch mode: one output file per image.
    print_step(f"Running OCR on {len(images)} image(s)…")
    done = 0
    for img in images:
        console.print(f"[dim]  • {os.path.basename(img)}…[/dim]")
        text = ocr_image(ai, img, markdown=markdown, language=language)
        if not text:
            print_warning(f"No text extracted from {os.path.basename(img)}.")
            continue
        target = _output_path(img, out_path, ext)
        if _write_text(text, target):
            console.print(f"  ✓ {os.path.basename(img)} → '{os.path.basename(target)}'")
            done += 1

    if done:
        print_success(f"Transcribed {done}/{len(images)} image(s).")
    else:
        print_error("No images could be transcribed.")
    return done > 0


def main() -> None:
    """CLI entry point for the AI OCR tool."""
    parser = argparse.ArgumentParser(
        description="AI OCR: extract text from images or scans using a vision-capable AI provider."
    )
    parser.add_argument("path", help="Image file or a folder of images.")
    parser.add_argument("--key", help="API key for the chosen provider (optional)")
    parser.add_argument("--out", help="Output file (single image) or output folder (batch).")
    parser.add_argument("--markdown", action="store_true",
                        help="Reconstruct layout as Markdown instead of plain text.")
    parser.add_argument("--language", help="Hint for the primary language of the text.")
    parser.add_argument("--recursive", action="store_true",
                        help="Recurse into subfolders when a folder is given.")
    parser.add_argument("--provider",
                        help="AI provider (default: $AI_PROVIDER, or gemini)")
    parser.add_argument("--model", help="Override the provider's default model")
    args = parser.parse_args()

    ok = run_ocr(
        path=args.path,
        api_key=args.key,
        out_path=args.out,
        markdown=args.markdown,
        language=args.language,
        recursive=args.recursive,
        provider=args.provider,
        model=args.model,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

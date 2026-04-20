import argparse
import os
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


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
    """Convierte un único archivo de imagen. `quality` aplica a JPEG/WebP."""
    try:
        pillow_format = FORMAT_MAP.get(output_format.lower())
        if not pillow_format:
            print_error(f"Formato de salida no soportado: {output_format}")
            return False

        if not HAS_PILLOW:
            print_error("Pillow no está instalado. Instálalo con 'pip install Pillow'.")
            return False

        with Image.open(input_path) as img:
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

        console.print(f"Convertida: '{input_path}' -> [green]'{output_path}'[/green]")
        return True
    except Exception as e:
        print_error(f"Error al convertir '{input_path}': {e}")
        return False


def run_image_converter(input_path: str, output_format: str, quality: int = 85) -> None:
    """Core function to convert an image or directory of images."""
    if not os.path.exists(input_path):
        print_error(f"La ruta '{input_path}' no es válida.")
        return

    if os.path.isdir(input_path):
        print_step(f"Procesando directorio: {input_path}")
        supported_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif')
        files = [f for f in os.listdir(input_path) if f.lower().endswith(supported_extensions)]

        if not files:
            print_error("No se encontraron imágenes soportadas en el directorio.")
            return

        success_count = 0
        for file in files:
            full_path = os.path.join(input_path, file)
            if convert_single_file(full_path, output_format, quality=quality):
                success_count += 1

        print_success(f"Proceso completado. {success_count}/{len(files)} imágenes convertidas.")

    elif os.path.isfile(input_path):
        if convert_single_file(input_path, output_format, quality=quality):
            print_success("Imagen convertida.")


def run_pdf_converter(input_path: str) -> None:
    """Convierte un documento (docx, odt, etc) a PDF usando LibreOffice headless."""
    import subprocess

    if not os.path.exists(input_path):
        print_error(f"El archivo '{input_path}' no existe.")
        return

    try:
        print_step(f"Convirtiendo '{input_path}' a PDF...")

        command = [
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(input_path) or '.',
            input_path
        ]

        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        print_success("El PDF se ha guardado en la misma carpeta.")

    except FileNotFoundError:
        print_error("LibreOffice no está instalado o no se encuentra en el PATH.")
    except subprocess.CalledProcessError as e:
        print_error(f"Ocurrió un error al convertir el documento: {e}")
    except Exception as e:
        print_error(f"Error inesperado: {e}")


def run_pdf_to_image(input_path: str, output_format: str = "png", dpi: int = 200) -> None:
    """Convierte cada página de un PDF a una imagen. Requiere `pdf2image` + poppler."""
    if not os.path.exists(input_path):
        print_error(f"El archivo '{input_path}' no existe.")
        return

    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        print_error(
            "Falta 'pdf2image'. Instala con 'pip install pdf2image' y el binario 'poppler' "
            "(Termux: 'pkg install poppler'; Debian/Ubuntu: 'apt install poppler-utils')."
        )
        return

    fmt = output_format.lower()
    if FORMAT_MAP.get(fmt) is None:
        print_error(f"Formato no soportado: {fmt}")
        return

    try:
        print_step(f"Renderizando PDF a {fmt.upper()} a {dpi} dpi…")
        pages = convert_from_path(input_path, dpi=dpi)
        base = os.path.splitext(input_path)[0]
        out_dir = base + "_pages"
        os.makedirs(out_dir, exist_ok=True)

        for i, page in enumerate(pages, 1):
            out = os.path.join(out_dir, f"page_{i:03d}.{fmt}")
            # Convert for JPEG compatibility.
            if fmt in ("jpg", "jpeg") and page.mode != "RGB":
                page = page.convert("RGB")
            page.save(out, FORMAT_MAP[fmt])
            console.print(f"  → {out}")

        print_success(f"{len(pages)} página(s) exportada(s) en: {out_dir}")
    except Exception as e:
        print_error(f"Error al convertir PDF: {e}")


def main():
    parser = argparse.ArgumentParser(description="Convierte una imagen o directorio a formato diferente.")
    parser.add_argument("input_path", help="Ruta al archivo o directorio de entrada.")
    parser.add_argument("output_format", help="Formato de salida (png, jpg, webp, ...).")
    parser.add_argument("--quality", type=int, default=85, help="Calidad JPEG/WebP (1-100, default 85).")
    parser.add_argument("--from-pdf", action="store_true", help="Renderizar PDF a imágenes (requiere pdf2image).")
    parser.add_argument("--dpi", type=int, default=200, help="DPI al renderizar PDF (default 200).")
    args = parser.parse_args()

    if args.from_pdf:
        run_pdf_to_image(args.input_path, args.output_format, dpi=args.dpi)
    else:
        run_image_converter(args.input_path, args.output_format, quality=args.quality)


if __name__ == "__main__":
    main()

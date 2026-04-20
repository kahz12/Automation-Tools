import os
import argparse
import csv
import datetime
import json
from typing import Dict, Any, Optional

import pypdf
from rich.table import Table

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def format_bytes(size: float) -> str:
    """Formatea bytes a un formato legible (KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def get_basic_info(filepath: str) -> Dict[str, str]:
    """Obtiene informacion basica del sistema de archivos."""
    stat = os.stat(filepath)
    return {
        "Tamaño": format_bytes(stat.st_size),
        "Creado": datetime.datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
        "Modificado": datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        "Ruta": os.path.abspath(filepath)
    }


def print_metadata_table(title: str, metadata_dict: Dict[str, Any]) -> None:
    """Imprime un diccionario de metadatos como una tabla formateada en Rich."""
    if not metadata_dict:
        print_warning(f"No se encontraron metadatos especificos para {title}")
        return

    table = Table(title=title, show_header=True, title_style="bold magenta", header_style="bold cyan")
    table.add_column("Propiedad", style="blue", no_wrap=True)
    table.add_column("Valor", style="green")

    for key, value in metadata_dict.items():
        str_val = str(value)
        if len(str_val) > 100:
            str_val = str_val[:97] + "..."
        table.add_row(str(key), str_val)

    console.print(table)
    console.print()


def extract_pdf_metadata(filepath: str) -> Dict[str, Any]:
    """Extrae metadatos de un archivo PDF usando pypdf."""
    metadata: Dict[str, Any] = {}
    try:
        reader = pypdf.PdfReader(filepath)
        if reader.is_encrypted:
            metadata['Estado'] = "Encriptado/Protegido con contraseña"
            metadata['Número de Páginas'] = "Desconocido (requiere contraseña)"
            return metadata

        info = reader.metadata
        if info:
            for key, value in info.items():
                clean_key = key.lstrip('/')
                metadata[clean_key] = value

        metadata['Número de Páginas'] = len(reader.pages)
    except Exception as e:
        print_error(f"Error al leer PDF: {e}")

    return metadata


def extract_image_metadata(filepath: str) -> Dict[str, Any]:
    """Extrae metadatos EXIF y propiedades basicas de una imagen usando Pillow."""
    metadata: Dict[str, Any] = {}
    if not HAS_PILLOW:
        print_error("Pillow no está instalado para leer metadatos de imágenes.")
        return metadata

    try:
        with Image.open(filepath) as img:
            metadata['Formato'] = img.format
            metadata['Modo de Color'] = img.mode
            metadata['Resolución'] = f"{img.width}x{img.height} px"

            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag_name == 'MakerNote' or isinstance(value, bytes):
                        continue
                    metadata[tag_name] = value

    except Exception as e:
        print_error(f"Error al leer Imagen: {e}")

    return metadata


def export_metadata(basic: Dict[str, Any], specific: Dict[str, Any], out_path: str) -> None:
    """Export metadata to JSON or CSV based on file extension."""
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
        print_success(f"Metadatos exportados a: {out_path}")
    except Exception as e:
        print_error(f"No se pudo exportar los metadatos: {e}")


def clean_image_exif(filepath: str, out_path: Optional[str] = None) -> Optional[str]:
    """Remove EXIF (GPS, cámara, fecha) de una imagen, reescribiendo los píxeles.

    Returns the output path on success, None otherwise.
    """
    if not HAS_PILLOW:
        print_error("Pillow no está instalado.")
        return None
    if not os.path.exists(filepath):
        print_error(f"No existe: {filepath}")
        return None

    out_path = out_path or (os.path.splitext(filepath)[0] + "_clean" + os.path.splitext(filepath)[1])
    try:
        with Image.open(filepath) as img:
            data = list(img.getdata())
            clean = Image.new(img.mode, img.size)
            clean.putdata(data)
            clean.save(out_path)
        print_success(f"EXIF eliminado. Imagen limpia: {out_path}")
        return out_path
    except Exception as e:
        print_error(f"No se pudo limpiar EXIF: {e}")
        return None


def run_metadata_extractor(filepath: str, export_path: Optional[str] = None, clean_exif: bool = False) -> None:
    """Core function: extract, display, optionally export/clean metadata."""
    if not os.path.exists(filepath):
        print_error(f"El archivo '{filepath}' no existe.")
        return

    filename = os.path.basename(filepath)
    ext = os.path.splitext(filename)[1].lower()

    console.print(f"\n[bold blue]Analizando: {filename}[/bold blue]\n")

    basic_info = get_basic_info(filepath)
    print_metadata_table("Información del Sistema", basic_info)

    specific: Dict[str, Any] = {}
    if ext == '.pdf':
        specific = extract_pdf_metadata(filepath)
        print_metadata_table("Metadatos y Document Info (PDF)", specific)
    elif ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp', '.bmp']:
        specific = extract_image_metadata(filepath)
        print_metadata_table("Metadatos EXIF e Información de Imagen", specific)
    else:
        print_warning(f"Análisis especifico no soportado para formatos '{ext}'.")

    if export_path:
        export_metadata(basic_info, specific, export_path)

    if clean_exif:
        if ext in ['.jpg', '.jpeg', '.png', '.tiff', '.webp', '.bmp']:
            clean_image_exif(filepath)
        else:
            print_warning("La limpieza de EXIF solo aplica a imágenes.")


def main():
    parser = argparse.ArgumentParser(description="Extractor de Metadatos de Archivos (PDF, Imagenes)")
    parser.add_argument("filepath", help="Ruta al archivo a analizar")
    parser.add_argument("--export", help="Exportar metadatos a JSON o CSV")
    parser.add_argument("--clean-exif", action="store_true", help="Crear copia sin EXIF (solo imágenes)")
    args = parser.parse_args()

    run_metadata_extractor(args.filepath, export_path=args.export, clean_exif=args.clean_exif)


if __name__ == "__main__":
    main()

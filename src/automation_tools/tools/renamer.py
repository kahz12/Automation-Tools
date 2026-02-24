import os
import datetime
import argparse
from typing import Optional, List

from automation_tools.core.logger import console, print_error, print_success, print_warning, print_step

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def get_file_date(filepath: str) -> datetime.datetime:
    """Gets the original creation date of the file, prefering EXIF if available."""
    date_taken = None
    if HAS_PILLOW:
        try:
            with Image.open(filepath) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        if tag in ExifTags.TAGS and ExifTags.TAGS[tag] == 'DateTimeOriginal':
                            date_taken = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                            break
        except Exception:
            pass 

    if not date_taken:
        timestamp = os.path.getmtime(filepath)
        date_taken = datetime.datetime.fromtimestamp(timestamp)
    
    return date_taken


def generate_new_name(
    filename: str, 
    directory: str,
    mode: str,
    index: int = 0,
    pattern: Optional[str] = None,
    date_format: str = "%Y-%m-%d",
    keep_name: bool = False,
    old_text: Optional[str] = None,
    new_text: str = ""
) -> str:
    """Generates a new name based on the chosen mode."""
    name, ext = os.path.splitext(filename)
    
    if mode == 'patron':
        if not pattern:
            return filename
        try:
            new_name = pattern.format(index) + ext
        except ValueError:
             new_name = f"{pattern}_{index:03d}{ext}"
        return new_name

    elif mode == 'fecha':
        filepath = os.path.join(directory, filename)
        date = get_file_date(filepath)
        date_str = date.strftime(date_format)
        
        if keep_name:
            new_name = f"{date_str}_{name}{ext}"
        else:
            new_name = f"{date_str}_{index:03d}{ext}"
        return new_name

    elif mode == 'reemplazo':
        if not old_text:
            return filename
        new_base = name.replace(old_text, new_text)
        return new_base + ext

    return filename


def run_massive_rename(
    directory: str,
    mode: str,
    apply_changes: bool = False,
    ext_filter: Optional[str] = None,
    pattern: Optional[str] = None,
    date_format: str = "%Y-%m-%d",
    keep_name: bool = False,
    old_text: Optional[str] = None,
    new_text: str = ""
) -> None:
    """Core function to execute massive rename without argparse dependency."""
    
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    files = sorted([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])
    
    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter.lower())]

    if not files:
        print_warning("No se encontraron archivos para procesar.")
        return

    print_step(f"Procesando {len(files)} archivos en '{directory}'...")
    print_step(f"Modo: {mode}")
    
    if not apply_changes:
        console.print("[yellow]MODO SIMULACIÓN (DRY-RUN): No se harán cambios reales.[/yellow]\n")

    count = 1
    for filename in files:
        new_name = generate_new_name(
            filename=filename, 
            directory=directory,
            mode=mode, 
            index=count,
            pattern=pattern,
            date_format=date_format,
            keep_name=keep_name,
            old_text=old_text,
            new_text=new_text
        )
        
        if new_name == filename:
            continue

        src = os.path.join(directory, filename)
        dst = os.path.join(directory, new_name)

        if os.path.exists(dst) and new_name != filename:
            console.print(f"[bold red][!][/bold red] Conflicto: '{new_name}' ya existe. Saltando '{filename}'.")
            continue
            
        console.print(f"'{filename}' -> '{new_name}'")
        
        if apply_changes:
            try:
                os.rename(src, dst)
            except Exception as e:
                print_error(f"Error al renombrar '{filename}': {e}")
        
        count += 1

    if not apply_changes:
        console.print("\n[dim]Para aplicar estos cambios, ejecuta con apply_changes=True[/dim]")
    else:
        print_success("Renombrado completado.")


def main():
    """CLI Entry point for standalone execution."""
    parser = argparse.ArgumentParser(description="Renombrador Masivo Inteligente de Archivos")
    
    parser.add_argument("directory", help="Directorio donde están los archivos")
    parser.add_argument("--mode", choices=['patron', 'fecha', 'reemplazo'], required=True, help="Modo de renombrado")
    parser.add_argument("--ext", help="Filtrar por extensión (ej: .jpg)")
    parser.add_argument("--aplicar", action="store_true", help="Aplicar los cambios reales")
    
    parser.add_argument("--pattern", help="Patrón para el nuevo nombre (ej: 'viaje_{:03d}')")
    parser.add_argument("--date-format", default="%Y-%m-%d", help="Formato de fecha (default: YYYY-MM-DD)")
    parser.add_argument("--keep-name", action="store_true", help="Mantener nombre original")
    parser.add_argument("--old-text", help="Texto a buscar para reemplazar")
    parser.add_argument("--new-text", default="", help="Texto nuevo")

    args = parser.parse_args()
    
    run_massive_rename(
        directory=args.directory,
        mode=args.mode,
        apply_changes=args.aplicar,
        ext_filter=args.ext,
        pattern=args.pattern,
        date_format=args.date_format,
        keep_name=args.keep_name,
        old_text=args.old_text,
        new_text=args.new_text
    )

if __name__ == "__main__":
    main()

import os
import sys
import argparse
import datetime
import shutil

# Intentar importar Pillow para metadatos EXIF
try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

def get_file_date(filepath):
    """
    Obtiene la fecha de creación original del archivo.
    Se intenta usar metadatos EXIF para imágenes, si no se usa la fecha de modificación del sistema.
    """
    date_taken = None
    if HAS_PILLOW:
        try:
            with Image.open(filepath) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        if tag in ExifTags.TAGS and ExifTags.TAGS[tag] == 'DateTimeOriginal':
                            # Formato EXIF: 'YYYY:MM:DD HH:MM:SS'
                            date_taken = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                            break
        except Exception:
            pass # No es una imagen o no tiene EXIF legible

    if not date_taken:
        # Se usa la fecha de modificación del sistema (mtime)
        timestamp = os.path.getmtime(filepath)
        date_taken = datetime.datetime.fromtimestamp(timestamp)
    
    return date_taken

def generate_new_name(filename, args, index=0):
    """
    Genera el nuevo nombre del archivo basado en el modo seleccionado.
    """
    name, ext = os.path.splitext(filename)
    
    if args.mode == 'patron':
        # Modo Patrón: ej. "vacaciones_001.jpg"
        # El patrón debe tener un marcador para el número, ej: "foto_{:03d}"
        try:
            new_name = args.pattern.format(index) + ext
        except ValueError:
             # Si el usuario no puso placeholders, se agrega al final
             new_name = f"{args.pattern}_{index:03d}{ext}"
        return new_name

    elif args.mode == 'fecha':
        # Modo Fecha: ej. "2024-02-17_original.jpg" o "2024-02-17_001.jpg"
        filepath = os.path.join(args.directory, filename)
        date = get_file_date(filepath)
        date_str = date.strftime(args.date_format)
        
        if args.keep_name:
            new_name = f"{date_str}_{name}{ext}"
        else:
            new_name = f"{date_str}_{index:03d}{ext}"
        return new_name

    elif args.mode == 'reemplazo':
        # Modo Reemplazo: reemplaza texto en el nombre
        if not args.old_text:
            print("Error: Se debe especificar --old-text para el modo reemplazo.")
            sys.exit(1)
        
        new_base = name.replace(args.old_text, args.new_text)
        return new_base + ext

    return filename

def main():
    parser = argparse.ArgumentParser(description="Renombrador Masivo Inteligente de Archivos")
    
    parser.add_argument("directory", help="Directorio donde están los archivos")
    parser.add_argument("--mode", choices=['patron', 'fecha', 'reemplazo'], required=True, help="Modo de renombrado")
    parser.add_argument("--ext", help="Filtrar por extensión (ej: .jpg). Si no se especifica, procesa todos.")
    parser.add_argument("--aplicar", action="store_true", help="Aplicar los cambios (por defecto es solo simulación/dry-run)")
    
    # Argumentos para modo Patrón
    parser.add_argument("--pattern", help="Patrón para el nuevo nombre (ej: 'viaje_{:03d}')")
    
    # Argumentos para modo Fecha
    parser.add_argument("--date-format", default="%Y-%m-%d", help="Formato de fecha (default: YYYY-MM-DD)")
    parser.add_argument("--keep-name", action="store_true", help="Mantener el nombre original junto a la fecha")
    
    # Argumentos para modo Reemplazo
    parser.add_argument("--old-text", help="Texto a buscar para reemplazar")
    parser.add_argument("--new-text", default="", help="Texto nuevo (default: vacío/borrar)")

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: El directorio '{args.directory}' no existe.")
        return

    # Se obtienen los archivos, ordenados alfabéticamente para consistencia
    files = sorted([f for f in os.listdir(args.directory) if os.path.isfile(os.path.join(args.directory, f))])
    
    # Se filtran por extensión si se solicita
    if args.ext:
        files = [f for f in files if f.lower().endswith(args.ext.lower())]

    if not files:
        print("No se encontraron archivos para procesar.")
        return

    print(f"Procesando {len(files)} archivos en '{args.directory}'...")
    print(f"Modo: {args.mode}")
    if not args.aplicar:
        print("MODO SIMULACIÓN (DRY-RUN): No se harán cambios reales.\n")

    count = 1
    for filename in files:
        # Se calcula el nuevo nombre
        new_name = generate_new_name(filename, args, index=count)
        
        # Se evita renombrar si el nombre no cambia
        if new_name == filename:
            continue

        # Ruta completa
        src = os.path.join(args.directory, filename)
        dst = os.path.join(args.directory, new_name)

        # Se muestra qué se haría
        if os.path.exists(dst) and new_name != filename:
            print(f"[!] Conflicto: '{new_name}' ya existe. Saltando '{filename}'.")
            continue
            
        print(f"'{filename}' -> '{new_name}'")
        
        if args.aplicar:
            try:
                os.rename(src, dst)
            except Exception as e:
                print(f"Error al renombrar '{filename}': {e}")
        
        count += 1

    if not args.aplicar:
        print("\nPara aplicar estos cambios, ejecuta el comando de nuevo con la opción --aplicar")
    else:
        print("\nRenombrado completado.")

if __name__ == "__main__":
    main()

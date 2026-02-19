# ─── Imports ───
import argparse
import os
from PIL import Image

# ─── Funciones ───
def convert_single_file(input_path, output_format):
    """Convierte un único archivo de imagen."""
    # Mapeo de extensiones comunes a nombres de formato de Pillow
    FORMAT_MAP = {
        'jpg': 'JPEG',
        'jpeg': 'JPEG',
        'png': 'PNG',
        'webp': 'WEBP',
        'bmp': 'BMP',
        'tiff': 'TIFF',
        'gif': 'GIF',
    }
    try:
        pillow_format = FORMAT_MAP.get(output_format.lower())
        if not pillow_format:
            print(f"Formato de salida no soportado: {output_format}")
            return False

        img = Image.open(input_path)
        # Convertir a RGB si es necesario (ej. PNG con transparencia -> JPG)
        if pillow_format == 'JPEG' and img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_directory = os.path.dirname(input_path) if os.path.dirname(input_path) else '.'
        output_filename = f"{base_name}.{output_format.lower()}"
        output_path = os.path.join(output_directory, output_filename)
        
        img.save(output_path, format=pillow_format)
        print(f"Convertida: '{input_path}' -> '{output_path}'")
        return True
    except Exception as e:
        print(f"Error al convertir '{input_path}': {e}")
        return False

def convert_image(input_path, output_format):
    """
    Convierte una imagen o todas las imágenes de un directorio a otro formato.

    Args:
        input_path (str): Ruta al archivo de imagen o directorio.
        output_format (str): Formato de salida deseado (ej. 'png', 'jpg', 'webp').
    """
    if os.path.isdir(input_path):
        print(f"Procesando directorio: {input_path}")
        supported_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.gif')
        files = [f for f in os.listdir(input_path) if f.lower().endswith(supported_extensions)]
        
        if not files:
            print("No se encontraron imágenes soportadas en el directorio.")
            return

        success_count = 0
        for file in files:
            full_path = os.path.join(input_path, file)
            if convert_single_file(full_path, output_format):
                success_count += 1
        
        print(f"\nProceso completado. {success_count}/{len(files)} imágenes convertidas.")

    elif os.path.isfile(input_path):
        convert_single_file(input_path, output_format)
    else:
        print(f"Error: La ruta '{input_path}' no es válida.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convierte una imagen o directorio de imágenes a un formato diferente.")
    parser.add_argument("input_path", help="Ruta al archivo de imagen o directorio de entrada.")
    parser.add_argument("output_format", help="Formato de salida deseado (ej. png, jpg, webp).")

    args = parser.parse_args()

    convert_image(args.input_path, args.output_format)

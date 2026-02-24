import argparse
import os
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step, print_success

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

def convert_single_file(input_path: str, output_format: str) -> bool:
    """Convierte un único archivo de imagen."""
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
            
            img.save(output_path, format=pillow_format)
            
        console.print(f"Convertida: '{input_path}' -> [green]'{output_path}'[/green]")
        return True
    except Exception as e:
        print_error(f"Error al convertir '{input_path}': {e}")
        return False

def run_image_converter(input_path: str, output_format: str) -> None:
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
            if convert_single_file(full_path, output_format):
                success_count += 1
        
        print_success(f"Proceso completado. {success_count}/{len(files)} imágenes convertidas.")

    elif os.path.isfile(input_path):
        if convert_single_file(input_path, output_format):
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

def main():
    parser = argparse.ArgumentParser(description="Convierte una imagen o directorio a formato diferente.")
    parser.add_argument("input_path", help="Ruta al archivo o directorio de entrada.")
    parser.add_argument("output_format", help="Formato de salida deseado (ej. png, jpg, webp).")
    args = parser.parse_args()

    run_image_converter(args.input_path, args.output_format)

if __name__ == "__main__":
    main()

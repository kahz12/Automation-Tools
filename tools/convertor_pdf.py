# ─── Imports ───
import subprocess
import os
import sys

# ─── Funciones ───
def convert_to_pdf(input_path):
    # Comprobar si el archivo existe
    if not os.path.exists(input_path):
        print(f"Error: El archivo {input_path} no existe.")
        return

    try:
        print(f"Convirtiendo {input_path} a PDF...")
        
        # Comando de LibreOffice para conversión
        command = [
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', os.path.dirname(input_path) or '.',
            input_path
        ]
        
        # Ejecutar el comando
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        print(f"¡Éxito! El PDF se ha guardado en la misma carpeta.")
        
    except subprocess.CalledProcessError as e:
        print(f"Ocurrió un error durante la conversión: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 script.py documento.docx")
    else:
        convert_to_pdf(sys.argv[1])

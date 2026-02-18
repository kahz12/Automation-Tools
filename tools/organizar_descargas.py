import os
import shutil

# --- Configuración ---
# Define la carpeta de Descargas (se expandirá a la ruta completa del usuario)
DOWNLOADS_PATH = os.path.expanduser('~/Descargas')

# Define las categorías y las extensiones de archivo asociadas
# Se pueden personalizar estas categorías y añadir más extensiones
CATEGORIES = {
    'Imágenes': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],
    'Documentos': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'],
    'Videos': ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'],
    'Audio': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],
    'Comprimidos': ['.zip', '.rar', '.7z', '.tar', '.gz'],
    'Ejecutables': ['.exe', '.dmg', '.app', '.deb', '.rpm'],
    'Programación': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.c', '.cpp'],
    'Otros': [] # Para archivos que no coincidan con ninguna categoría
}

def organize_downloads():
    print(f"Organizando la carpeta: {DOWNLOADS_PATH}")

    if not os.path.isdir(DOWNLOADS_PATH):
        print(f"Error: La carpeta '{DOWNLOADS_PATH}' no existe o no es un directorio.")
        return

    # Crear las carpetas de categoría si no existen
    for category in CATEGORIES:
        category_path = os.path.join(DOWNLOADS_PATH, category)
        if not os.path.exists(category_path):
            os.makedirs(category_path)
            print(f"Carpeta creada: {category_path}")

    # Recorrer los archivos en la carpeta de Descargas
    for filename in os.listdir(DOWNLOADS_PATH):
        source_path = os.path.join(DOWNLOADS_PATH, filename)

        # Ignorar directorios y el propio script
        if os.path.isdir(source_path):
            if filename not in CATEGORIES: # Evitar mover las carpetas de categoría
                print(f"Ignorando directorio: {filename}")
            continue
        if filename == os.path.basename(__file__): # Ignorar el propio script
            continue

        # Obtener la extensión del archivo
        file_extension = os.path.splitext(filename)[1].lower()

        moved = False
        for category, extensions in CATEGORIES.items():
            if file_extension in extensions:
                destination_path = os.path.join(DOWNLOADS_PATH, category, filename)
                try:
                    shutil.move(source_path, destination_path)
                    print(f"Movido: '{filename}' a '{category}'")
                    moved = True
                    break
                except shutil.Error as e:
                    print(f"Error al mover '{filename}' a '{category}': {e}")
                    # Si el archivo ya existe en el destino, se podría renombrar o sobrescribir
                    # Por ahora, simplemente se muestra el error
                except Exception as e:
                    print(f"Error inesperado al mover '{filename}': {e}")
                    moved = True # Considerar como "manejado" para no caer en "Otros"

        if not moved:
            # Mover a la carpeta 'Otros' si no coincide con ninguna categoría
            other_path = os.path.join(DOWNLOADS_PATH, 'Otros', filename)
            try:
                shutil.move(source_path, other_path)
                print(f"Movido: '{filename}' a 'Otros'")
            except shutil.Error as e:
                print(f"Error al mover '{filename}' a 'Otros': {e}")
            except Exception as e:
                print(f"Error inesperado al mover '{filename}' a 'Otros': {e}")

    print("Organización completada.")

if __name__ == "__main__":
    organize_downloads()

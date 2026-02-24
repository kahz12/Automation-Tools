import os
import shutil

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.core.config import get_downloads_folder

# Define las categorías y las extensiones de archivo asociadas
CATEGORIES = {
    'Imágenes': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],
    'Documentos': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'],
    'Videos': ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv'],
    'Audio': ['.mp3', '.wav', '.aac', '.flac', '.ogg'],
    'Comprimidos': ['.zip', '.rar', '.7z', '.tar', '.gz'],
    'Ejecutables': ['.exe', '.dmg', '.app', '.deb', '.rpm', '.AppImage'],
    'Programación': ['.py', '.js', '.html', '.css', '.json', '.xml', '.java', '.c', '.cpp', '.ts', '.go', '.rs'],
    'Otros': []
}

def create_directories_if_not_exist(downloads_path: str) -> None:
    """Crea los directorios para cada categoría si no existen."""
    for category in CATEGORIES:
        category_path = os.path.join(downloads_path, category)
        if not os.path.exists(category_path):
            os.makedirs(category_path)
            console.print(f"[dim]Carpeta creada: {category_path}[/dim]")

def get_target_category(filename: str) -> str:
    """Determina la categoría de un archivo según su extensión."""
    file_extension = os.path.splitext(filename)[1].lower()
    for category, extensions in CATEGORIES.items():
        if file_extension in extensions:
            return category
    return 'Otros'

def run_download_organizer() -> None:
    """Core function to organize files in the Downloads folder."""
    downloads_path = get_downloads_folder()
    
    print_step(f"Organizando la carpeta: [bold]{downloads_path}[/bold]")

    if not os.path.isdir(downloads_path):
        print_error(f"La carpeta '{downloads_path}' no existe o no es un directorio.")
        return

    create_directories_if_not_exist(downloads_path)

    moved_count = 0
    ignored_count = 0

    for filename in os.listdir(downloads_path):
        source_path = os.path.join(downloads_path, filename)

        if os.path.isdir(source_path):
            if filename not in CATEGORIES:
                ignored_count += 1
            continue
            
        if filename == os.path.basename(__file__):
            continue

        category = get_target_category(filename)
        destination_path = os.path.join(downloads_path, category, filename)
        
        try:
            shutil.move(source_path, destination_path)
            console.print(f"Movido: '{filename}' a '[green]{category}[/green]'")
            moved_count += 1
        except shutil.Error as e:
            print_error(f"Error al mover '{filename}': {e}")
        except Exception as e:
            print_error(f"Error inesperado al mover '{filename}': {e}")

    print_success(f"Organización completada. Archivos movidos: {moved_count}.")

def main():
    run_download_organizer()

if __name__ == "__main__":
    main()

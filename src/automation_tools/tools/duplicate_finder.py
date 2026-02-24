import os
import hashlib
import argparse
from typing import Dict, List, Optional
from collections import defaultdict

import questionary

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

def hash_file(filepath: str, chunk_size: int = 8192) -> Optional[str]:
    """Calcula el hash MD5 de un archivo."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print_error(f"Error al leer {filepath}: {e}")
        return None

def find_duplicates(directory: str) -> Dict[str, List[str]]:
    """Encuentra archivos duplicados en un directorio recursivamente."""
    print_step(f"Buscando duplicados en: [bold]{directory}[/bold]...")
    hashes = defaultdict(list)
    
    for root, _, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            if os.path.islink(filepath):
                continue
            
            file_hash = hash_file(filepath)
            if file_hash:
                hashes[file_hash].append(filepath)
                
    return {h: paths for h, paths in hashes.items() if len(paths) > 1}

def run_duplicate_finder(directory: str, auto_delete: bool = False) -> None:
    """Core function to find and optionally delete duplicates."""
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    duplicates = find_duplicates(directory)

    if not duplicates:
        print_success("No se encontraron archivos duplicados.")
        return

    total_wasted_bytes = 0
    console.print(f"\n[bold yellow]¡Se encontraron {len(duplicates)} grupos de duplicados![/bold yellow]\n")

    for h, paths in duplicates.items():
        paths.sort(key=lambda x: os.path.getctime(x))
        
        console.print(f"[cyan]Grupo Hash: {h[:8]}...[/cyan]")
        console.print(f"  [green](Original)[/green] {paths[0]}")
        
        file_size = os.path.getsize(paths[0])
        total_wasted_bytes += file_size * (len(paths) - 1)
        
        for p in paths[1:]:
            console.print(f"  [red](Copia)[/red]    {p}")
        print()

    mb_saved = total_wasted_bytes / (1024 * 1024)
    console.print(f"Espacio recuperable: [bold green]{mb_saved:.2f} MB[/bold green]\n")

    confirm = True if auto_delete else questionary.confirm("¿Deseas eliminar todas las copias (manteniendo el original de cada grupo)?").ask()

    if confirm:
        deleted = 0
        for h, paths in duplicates.items():
            for p in paths[1:]: 
                try:
                    os.remove(p)
                    deleted += 1
                    console.print(f"[dim]Eliminado: {p}[/dim]")
                except Exception as e:
                    print_error(f"Error al eliminar {p}: {e}")
        
        print_success(f"¡Proceso completado! Se eliminaron {deleted} archivos.")
    else:
        print_warning("No se eliminó ningún archivo.")

def main():
    parser = argparse.ArgumentParser(description="Detector de Archivos Duplicados")
    parser.add_argument("directory", help="Directorio a escanear")
    parser.add_argument("--delete", action="store_true", help="Eliminar duplicados automaticamente")
    args = parser.parse_args()

    run_duplicate_finder(args.directory, args.delete)

if __name__ == "__main__":
    main()

import os
import argparse
import subprocess
import sys

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.core.config import get_downloads_folder

def run_youtube_downloader(url: str, mode: str = 'video') -> None:
    """Core function to download video or audio using yt-dlp."""
    output_dir = get_downloads_folder()
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    print_step(f"Preparando descarga en: [bold]{output_dir}[/bold]")
    
    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    cmd = [sys.executable, '-m', 'yt_dlp']
    
    if mode == 'audio':
        print_step("Modo: Audio (MP3)")
        cmd.extend([
            '-x',                      
            '--audio-format', 'mp3',   
            '--audio-quality', '0',    
        ])
    else:
        print_step("Modo: Video (Maxima resolucion)")
        cmd.extend([
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best', 
        ])
        
    cmd.extend(['-o', output_template, url])
    
    console.print(f"[cyan]{'-' * 50}[/cyan]")
    try:
        subprocess.run(cmd, check=True)
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_success("¡Descarga completada exitosamente!")
    except subprocess.CalledProcessError as e:
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_error(f"Error durante la descarga (codigo {e.returncode})")
    except FileNotFoundError:
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_error("No se encontró 'yt-dlp'. Asegúrate de tenerlo instalado (pip install yt-dlp).")


def main():
    parser = argparse.ArgumentParser(description="Descargador de YouTube (Video/Audio)")
    parser.add_argument("url", help="URL del video de YouTube")
    parser.add_argument("--mode", choices=['video', 'audio'], default='video', help="Formato de descarga")
    args = parser.parse_args()
    
    run_youtube_downloader(args.url, args.mode)


if __name__ == "__main__":
    main()

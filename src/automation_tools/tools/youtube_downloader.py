import os
import argparse
import subprocess
import sys

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.core.config import get_downloads_folder


def _is_playlist(url: str) -> bool:
    """Best-effort detection of playlist URLs."""
    return "playlist" in url.lower() or "list=" in url.lower()


def run_youtube_downloader(
    url: str,
    mode: str = 'video',
    playlist: bool = False,
    resume: bool = True,
) -> None:
    """Download video/audio using yt-dlp. Supports playlists and resume.

    - `playlist=True`: enables playlist download; otherwise auto-detected.
    - `resume=True`: yt-dlp reanuda descargas parciales y salta ya descargados.
    """
    output_dir = get_downloads_folder()

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    is_playlist = playlist or _is_playlist(url)

    print_step(f"Preparando descarga en: [bold]{output_dir}[/bold]")
    if is_playlist:
        print_step("📚 Modo Playlist activado.")

    # For playlists, group videos into a subfolder per playlist.
    if is_playlist:
        output_template = os.path.join(
            output_dir, '%(playlist_title)s', '%(playlist_index)03d - %(title)s.%(ext)s'
        )
    else:
        output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

    cmd = [sys.executable, '-m', 'yt_dlp']

    # Resume + skip already downloaded.
    if resume:
        cmd.extend(['--continue', '--no-overwrites'])
        # Archive file lets re-runs skip videos previously completed.
        archive = os.path.join(output_dir, '.yt_archive.txt')
        cmd.extend(['--download-archive', archive])

    if is_playlist:
        cmd.append('--yes-playlist')
    else:
        cmd.append('--no-playlist')

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
        if resume:
            console.print("[dim]💡 Si la descarga quedó a medias, vuelve a ejecutar: "
                          "se reanudará automáticamente desde donde quedó.[/dim]")
    except FileNotFoundError:
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_error("No se encontró 'yt-dlp'. Asegúrate de tenerlo instalado (pip install yt-dlp).")


def main():
    parser = argparse.ArgumentParser(description="Descargador de YouTube (Video/Audio)")
    parser.add_argument("url", help="URL del video o playlist")
    parser.add_argument("--mode", choices=['video', 'audio'], default='video', help="Formato de descarga")
    parser.add_argument("--playlist", action="store_true", help="Forzar modo playlist")
    parser.add_argument("--no-resume", action="store_true", help="Desactivar reanudación/skip archivo")
    args = parser.parse_args()

    run_youtube_downloader(args.url, args.mode, playlist=args.playlist, resume=not args.no_resume)


if __name__ == "__main__":
    main()

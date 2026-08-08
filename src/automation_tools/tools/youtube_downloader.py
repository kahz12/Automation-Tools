import os
import argparse
import subprocess
import sys

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.core.config import get_downloads_folder

# Wraps yt-dlp: single videos or whole playlists, video or audio-only, and it
# picks up interrupted downloads where they stopped.


def _is_playlist(url: str) -> bool:
    """Detects if a given URL points to a YouTube playlist."""
    return "playlist" in url.lower() or "list=" in url.lower()


def run_youtube_downloader(
    url: str,
    mode: str = 'video',
    playlist: bool = False,
    resume: bool = True,
) -> None:
    """Core download function:
    - Sets up the output directory (defaults to system Downloads).
    - Configures yt-dlp commands for video (MP4) or audio (MP3).
    - Handles playlist organization into subfolders.
    - Implements an archive file to skip previously downloaded content.
    """
    output_dir = get_downloads_folder()

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    is_playlist = playlist or _is_playlist(url)

    print_step(f"Preparing download in: [bold]{output_dir}[/bold]")
    if is_playlist:
        print_step("📚 Playlist mode activated.")

    # File naming template: 
    # For playlists, it creates a folder named after the playlist.
    if is_playlist:
        output_template = os.path.join(
            output_dir, '%(playlist_title)s', '%(playlist_index)03d - %(title)s.%(ext)s'
        )
    else:
        output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

    # Construct the yt-dlp command.
    cmd = [sys.executable, '-m', 'yt_dlp']

    # Configuration for resuming and skipping duplicates.
    if resume:
        cmd.extend(['--continue', '--no-overwrites'])
        # Archive file ensures that re-running the same URL skips videos that are already finished.
        archive = os.path.join(output_dir, '.yt_archive.txt')
        cmd.extend(['--download-archive', archive])

    if is_playlist:
        cmd.append('--yes-playlist')
    else:
        cmd.append('--no-playlist')

    if mode == 'audio':
        print_step("Mode: Audio (MP3)")
        cmd.extend([
            '-x',                       # Extract audio.
            '--audio-format', 'mp3',    # Set format to MP3.
            '--audio-quality', '0',     # Set to best quality.
        ])
    else:
        print_step("Mode: Video (Max Resolution)")
        # Request best MP4 video or best overall if MP4 isn't available.
        cmd.extend([
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        ])

    cmd.extend(['-o', output_template, url])

    console.print(f"[cyan]{'-' * 50}[/cyan]")
    try:
        # Run the command in a subprocess.
        subprocess.run(cmd, check=True)
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_success("Download completed successfully!")
    except subprocess.CalledProcessError as e:
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_error(f"Error during download (code {e.returncode})")
        if resume:
            console.print("[dim]💡 If the download was interrupted, run it again: "
                          "it will automatically resume where it left off.[/dim]")
    except FileNotFoundError:
        console.print(f"[cyan]{'-' * 50}[/cyan]")
        print_error("'yt-dlp' not found. Please ensure it is installed (pip install yt-dlp).")


def main():
    """CLI entry point for the YouTube Downloader."""
    parser = argparse.ArgumentParser(description="YouTube Downloader (Video/Audio)")
    parser.add_argument("url", help="URL of the video or playlist")
    parser.add_argument("--mode", choices=['video', 'audio'], default='video', help="Download format")
    parser.add_argument("--playlist", action="store_true", help="Force playlist mode")
    parser.add_argument("--no-resume", action="store_true", help="Disable resume/archive skip")
    args = parser.parse_args()

    run_youtube_downloader(args.url, args.mode, playlist=args.playlist, resume=not args.no_resume)


if __name__ == "__main__":
    main()

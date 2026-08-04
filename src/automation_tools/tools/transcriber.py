import os
import time
import argparse
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, _generate, PRIMARY_MODEL

# Upload polling: how long to wait for Gemini to finish processing a media file
# before giving up, and how often to re-check in the meantime.
UPLOAD_TIMEOUT = 600.0  # seconds
POLL_INTERVAL = 3.0     # seconds


def _wait_for_active(
    client,
    file_name: str,
    timeout: float = UPLOAD_TIMEOUT,
    poll_interval: float = POLL_INTERVAL,
) -> bool:
    """
    Polls an uploaded file until Gemini reports it as ACTIVE.

    Returns True once the file is ready to use. Returns False if Gemini reports
    the file as FAILED, or if `timeout` seconds go by first — a file stuck in
    PROCESSING or an API that keeps erroring must never hang the tool forever.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # genai state may be a string or an Enum; compare on its text form.
            state_str = str(client.files.get(name=file_name).state).upper()
            if "ACTIVE" in state_str:
                return True
            if "FAILED" in state_str:
                print_error("Gemini failed to process the media file.")
                return False
        except Exception as e:
            print_warning(f"Error checking file state: {e}")
        time.sleep(poll_interval)

    print_error(f"Gave up waiting for Gemini to process the file after {timeout:.0f}s.")
    return False


def run_transcriber(
    filepath: str,
    mode: str = "srt",
    out_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> bool:
    """
    Transcribes an audio or video file using Gemini multimodal capabilities.
    Outputs either in SRT format or plain text.

    Returns True only when a transcript was produced and written to disk.
    """
    if not os.path.exists(filepath):
        print_error(f"File '{filepath}' does not exist.")
        return False

    client = get_gemini_client(api_key)
    if not client:
        return False

    print_step(f"Uploading file '{os.path.basename(filepath)}' to Gemini...")
    try:
        uploaded_file = client.files.upload(file=filepath)
    except Exception as e:
        print_error(f"Failed to upload file: {e}")
        return False

    console.print(f"[dim]File uploaded. ID: {uploaded_file.name}. Waiting for processing...[/dim]")

    # Wait for the file to be processed (important for large audio/video).
    if not _wait_for_active(
        client, uploaded_file.name,
        timeout=UPLOAD_TIMEOUT, poll_interval=POLL_INTERVAL,
    ):
        # Don't leave the unusable upload sitting on the remote side.
        try:
            client.files.delete(name=uploaded_file.name)
        except Exception:
            pass
        return False

    print_step("Generating transcription...")

    if mode == "srt":
        prompt = "Transcribe the audio in this file and output it in strict SRT subtitle format. Only output the raw SRT content, nothing else (no markdown blocks)."
    else:
        prompt = "Transcribe the audio in this file. Provide a clean, readable transcript in paragraphs."

    response_text = None
    try:
        response_text = _generate(
            client=client,
            contents=[uploaded_file, prompt],
            model_name=PRIMARY_MODEL,
            allow_fallback=True
        )
    finally:
        # Cleanup remote file
        try:
            client.files.delete(name=uploaded_file.name)
            console.print("[dim]Remote file deleted.[/dim]")
        except Exception:
            pass

    if not response_text:
        return False

    # Some models wrap the answer in a markdown block; strip it for SRT.
    if mode == "srt" and response_text.startswith("```srt"):
        response_text = response_text[6:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

    console.print(f"\n[cyan]{'='*40}[/cyan]")
    console.print("[bold]TRANSCRIPTION[/bold]")
    console.print(f"[cyan]{'='*40}[/cyan]\n")
    console.print(response_text)

    if not out_path:
        ext = ".srt" if mode == "srt" else ".txt"
        out_path = os.path.splitext(filepath)[0] + ext

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(response_text)
    except OSError as e:
        print_error(f"Error saving file: {e}")
        return False

    console.print(f"\n[dim]Transcription saved to: {out_path}[/dim]")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Audio/Video Transcriber with Gemini")
    parser.add_argument("filepath", help="Path to the audio or video file")
    parser.add_argument("--mode", choices=["srt", "txt"], default="srt", help="Output format (srt or txt)")
    parser.add_argument("--out", help="Save output to this file")
    parser.add_argument("--key", help="Google API Key")
    args = parser.parse_args()

    ok = run_transcriber(args.filepath, args.mode, args.out, args.key)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

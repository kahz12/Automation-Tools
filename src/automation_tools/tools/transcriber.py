import os
import time
import argparse
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, _generate, PRIMARY_MODEL


def run_transcriber(
    filepath: str,
    mode: str = "srt",
    out_path: Optional[str] = None,
    api_key: Optional[str] = None
) -> None:
    """
    Transcribes an audio or video file using Gemini multimodal capabilities.
    Outputs either in SRT format or plain text.
    """
    if not os.path.exists(filepath):
        print_error(f"File '{filepath}' does not exist.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    print_step(f"Uploading file '{os.path.basename(filepath)}' to Gemini...")
    try:
        uploaded_file = client.files.upload(file=filepath)
    except Exception as e:
        print_error(f"Failed to upload file: {e}")
        return

    console.print(f"[dim]File uploaded. ID: {uploaded_file.name}. Waiting for processing...[/dim]")

    # Wait for the file to be processed (important for large audio/video)
    while True:
        try:
            f = client.files.get(name=uploaded_file.name)
            # genai state might be a string or Enum, check for 'ACTIVE' string representation
            state_str = str(f.state).upper()
            if "ACTIVE" in state_str:
                break
            elif "FAILED" in state_str:
                print_error("Gemini failed to process the media file.")
                return
            time.sleep(3)
        except Exception as e:
            print_warning(f"Error checking file state: {e}")
            time.sleep(5)

    print_step("Generating transcription...")

    if mode == "srt":
        prompt = "Transcribe the audio in this file and output it in strict SRT subtitle format. Only output the raw SRT content, nothing else (no markdown blocks)."
    else:
        prompt = "Transcribe the audio in this file. Provide a clean, readable transcript in paragraphs."

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

    if response_text:
        # Some models return markdown blocks, we can clean them up if mode == srt
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
            console.print(f"\n[dim]Transcription saved to: {out_path}[/dim]")
        except Exception as e:
            print_error(f"Error saving file: {e}")


def main():
    parser = argparse.ArgumentParser(description="Audio/Video Transcriber with Gemini")
    parser.add_argument("filepath", help="Path to the audio or video file")
    parser.add_argument("--mode", choices=["srt", "txt"], default="srt", help="Output format (srt or txt)")
    parser.add_argument("--out", help="Save output to this file")
    parser.add_argument("--key", help="Google API Key")
    args = parser.parse_args()

    run_transcriber(args.filepath, args.mode, args.out, args.key)


if __name__ == "__main__":
    main()

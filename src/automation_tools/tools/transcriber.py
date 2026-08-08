import os
import argparse
from typing import Optional

from automation_tools.ai import AIProviderError, Capability, get_provider
from automation_tools.core.logger import console, print_error, print_step

# Transcribes audio or video files, in SRT or plain-text form, using an
# audio-capable AI provider. The upload/polling dance some providers need
# (e.g. Gemini's Files API) lives inside their adapter, not here.


def run_transcriber(
    filepath: str,
    mode: str = "srt",
    out_path: Optional[str] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> bool:
    """Transcribes an audio or video file, in SRT or plain-text form.

    Returns True only when a transcript was produced and written to disk.
    """
    if not os.path.exists(filepath):
        print_error(f"File '{filepath}' does not exist.")
        return False

    try:
        ai = get_provider(Capability.AUDIO, name=provider, api_key=api_key, model=model)
    except AIProviderError as e:
        print_error(str(e))
        return False

    print_step(f"Transcribing '{os.path.basename(filepath)}' with {ai.name}…")
    response_text = ai.transcribe(filepath, mode=mode)
    if not response_text:
        return False

    # Some models wrap the answer in a markdown block; strip it for SRT.
    if mode == "srt" and response_text.startswith("```srt"):
        response_text = response_text[6:].strip()
        if response_text.endswith("```"):
            response_text = response_text[:-3].strip()

    console.print(f"\n[cyan]{'=' * 40}[/cyan]")
    console.print("[bold]TRANSCRIPTION[/bold]")
    console.print(f"[cyan]{'=' * 40}[/cyan]\n")
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
    parser = argparse.ArgumentParser(description="Audio/Video Transcriber")
    parser.add_argument("filepath", help="Path to the audio or video file")
    parser.add_argument("--mode", choices=["srt", "txt"], default="srt",
                        help="Output format (srt or txt)")
    parser.add_argument("--out", help="Save output to this file")
    parser.add_argument("--key", help="API key for the chosen provider (optional)")
    parser.add_argument("--provider",
                        help="AI provider (default: $AI_PROVIDER, or gemini)")
    parser.add_argument("--model", help="Override the provider's default model")
    args = parser.parse_args()

    ok = run_transcriber(args.filepath, args.mode, args.out, args.key,
                         provider=args.provider, model=args.model)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

import os
import argparse
import hashlib
from typing import List, Optional

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

# --- AI File Translator Tool ---
# This tool uses Gemini to translate text files, subtitles, and code comments
# while preserving the original file structure and formatting.

# Maximum characters per request to ensure reliability and stay within AI limits.
CHUNK_CHARS = 40000


def read_file(filepath: str) -> Optional[str]:
    """Reads the entire content of a text file (UTF-8)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print_error(f"Error reading file: {e}")
        return None


def _chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> List[str]:
    """
    Splits long text into manageable chunks.
    Prefers breaking at paragraph boundaries to maintain translation quality.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
        # Search for a clean break point (double newline, newline, or period).
        cut = remaining.rfind("\n\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = remaining.rfind("\n", 0, max_chars)
        if cut < max_chars // 2:
            cut = remaining.rfind(". ", 0, max_chars)
        if cut < max_chars // 2:
            cut = max_chars
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _chunk_cache_key(chunk: str, target_lang: str) -> str:
    """Generates a unique MD5 hash for a text chunk and its target language."""
    h = hashlib.md5(f"{target_lang}::{chunk}".encode("utf-8")).hexdigest()
    return h


def run_translator(filepath: str, target_lang: str, api_key: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """
    Core translation workflow:
    1. Validates file support and reads content.
    2. Chunks text if necessary.
    3. Translates each chunk using specialized system instructions to preserve formatting.
    4. Reassembles the translated parts.
    """
    if not os.path.exists(filepath):
        print_error(f"File '{filepath}' does not exist.")
        return

    # List of common text-based formats that the tool can process safely.
    supported = ('.txt', '.md', '.srt', '.py', '.json', '.csv', '.xml', '.html', '.css', '.js')
    ext = os.path.splitext(filepath)[1].lower()

    if ext not in supported:
        print_error(f"Unsupported format: {ext}. \nSupported: {', '.join(supported)}")
        return

    text = read_file(filepath)
    if not text:
        print_error("Could not read file content.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    # System instruction tailored for precise, formatting-aware translation.
    instruction = f"""You are a professional translator. Translate the following text to the language: {target_lang}.

Strict Rules:
- Preserve exactly the original format: line breaks, indentation, spaces, and structure.
- If the text contains source code, translate ONLY the comments and strings, not the code logic.
- If the text is a subtitle file (.srt), translate ONLY the dialogue, not the timestamps or sequence numbers.
- If the text is JSON, translate ONLY the string values, not the keys.
- If the text is Markdown, preserve all Markdown syntax (headers, lists, links, code blocks, etc).
- If you receive a fragment that seems incomplete, assume it is part of a larger text and translate it without adding continuations.
- Do not add explanations, notes, or additional text. Return only the translated text."""

    chunks = _chunk_text(text)
    if len(chunks) > 1:
        print_step(f"Large file: split into {len(chunks)} fragments.")

    print_step(f"Translating to {target_lang} with Gemini...")

    # Simple in-memory cache to avoid redundant translations of identical chunks.
    cache: dict = {}
    translated_parts: List[str] = []

    for i, chunk in enumerate(chunks, 1):
        key = _chunk_cache_key(chunk, target_lang)
        if key in cache:
            console.print(f"[dim]  • Fragment {i}/{len(chunks)}: reusing cached translation[/dim]")
            translated_parts.append(cache[key])
            continue

        if len(chunks) > 1:
            console.print(f"[dim]  • Fragment {i}/{len(chunks)} ({len(chunk)} chars)…[/dim]")

        prompt = f"Text to translate:\n{chunk}"
        result = generate_content(client, prompt, system_instruction=instruction)
        if not result:
            print_warning(f"Could not translate fragment {i}. Keeping original text.")
            translated_parts.append(chunk)
            continue
        cache[key] = result
        translated_parts.append(result)

    translation = "\n".join(translated_parts)

    # Preview the translation in the terminal.
    console.print(f"\n[cyan]{'=' * 40}[/cyan]")
    console.print("[bold]GENERATED TRANSLATION[/bold]")
    console.print(f"[cyan]{'=' * 40}[/cyan]\n")
    console.print(translation[:4000])
    if len(translation) > 4000:
        console.print(f"[dim]... (preview truncated · total {len(translation)} characters)[/dim]")

    # Save output if a path was provided.
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(translation)
            console.print(f"\n[dim]Translation saved to: {out_path}[/dim]")
        except Exception as e:
            print_error(f"Error saving file: {e}")


def main():
    """CLI entry point for the File Translator."""
    parser = argparse.ArgumentParser(description="File Translator with Gemini")
    parser.add_argument("filepath", help="Path to the file to translate")
    parser.add_argument("--lang", required=True, help="Target language")
    parser.add_argument("--key", help="Google API Key (optional)")
    parser.add_argument("--out", help="Save translation to this file")
    args = parser.parse_args()

    run_translator(args.filepath, args.lang, args.key, args.out)


if __name__ == "__main__":
    main()

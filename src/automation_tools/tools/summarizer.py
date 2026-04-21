import os
import argparse
from typing import List, Optional
import pypdf

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

# --- AI Document Summarizer Tool ---
# This tool extracts text from PDF or TXT files and uses the Gemini AI model
# to generate concise executive summaries and key bullet points.

# Maximum characters to process in a single Gemini request.
CHUNK_CHARS = 28000


def extract_text_from_pdf(filepath: str) -> Optional[str]:
    """Extracts all text from a PDF file using pypdf."""
    text = ""
    try:
        reader = pypdf.PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print_error(f"Error reading PDF: {e}")
        return None


def extract_text_from_txt(filepath: str) -> Optional[str]:
    """Reads text from a plain text file (UTF-8)."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print_error(f"Error reading text file: {e}")
        return None


def _chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> List[str]:
    """
    Splits long text into smaller chunks to fit within AI model limits.
    Attempts to break text at paragraph or sentence boundaries for better context.
    """
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
        # Try to find a clean break point (double newline, newline, or period).
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


def run_summarizer(filepath: str, api_key: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """
    Orchestrates the summarization workflow:
    1. Extracts text from the document.
    2. Chunks text if it is too long.
    3. Summarizes individual chunks (Map phase).
    4. Consolidates chunk summaries into a final report (Reduce phase).
    """

    if not os.path.exists(filepath):
        print_error(f"File '{filepath}' does not exist.")
        return

    # Determine extraction method based on file extension.
    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    if ext == ".pdf":
        text = extract_text_from_pdf(filepath)
    elif ext in [".txt", ".md", ".py", ".json"]:
        text = extract_text_from_txt(filepath)
    else:
        print_error(f"Unsupported format: {ext}")
        return

    if not text:
        print_error("Could not extract text from file.")
        return

    # Initialize Gemini client.
    client = get_gemini_client(api_key)
    if not client:
        return

    chunks = _chunk_text(text)

    # Prompt instructions for chunk summarization.
    chunk_instruction = (
        "You are an expert analyst. Read this fragment and extract:\n"
        "1. 3-5 concise key points.\n"
        "2. Any relevant numerical data, dates, or proper names.\n"
        "Preserve the structure of the original (titles/sections if they exist). "
        "Respond in Spanish in bullet list format."
    )
    # Prompt instructions for consolidating partial summaries.
    final_instruction = (
        "You are an expert analyst. Synthesize the following partial summaries "
        "(each covering a part of the document in order) into:\n"
        "1. A 1-2 paragraph executive summary.\n"
        "2. A consolidated list of key bullet points.\n"
        "Preserve titles/sections from the original if identifiable."
    )

    partials: List[str] = []
    if len(chunks) == 1:
        # Simple case: Document fits in one request.
        print_step("Generating summary with Gemini...")
        summary = generate_content(
            client,
            f"Text:\n{chunks[0]}",
            system_instruction=(
                "You are an expert analyst. Please read the following text and generate:\n"
                "1. A 1-paragraph executive summary.\n"
                "2. A list of key points (bullet points).\n"
                "Preserve main titles or sections if they exist."
            ),
        )
    else:
        # Complex case: Multi-part summarization (Map-Reduce).
        print_step(f"Long document: processing {len(chunks)} fragments (map-reduce).")
        for i, chunk in enumerate(chunks, 1):
            console.print(f"[dim]  • Fragment {i}/{len(chunks)}…[/dim]")
            part = generate_content(
                client,
                f"Fragment {i}/{len(chunks)}:\n{chunk}",
                system_instruction=chunk_instruction,
            )
            if part:
                partials.append(f"### Fragment {i}\n{part}")
            else:
                print_warning(f"Could not summarize fragment {i}.")

        if not partials:
            print_error("No partial summaries were generated.")
            return

        print_step("Consolidating final summary…")
        combined = "\n\n".join(partials)
        summary = generate_content(
            client,
            f"Partial summaries:\n{combined}",
            system_instruction=final_instruction,
        )

    # Output the result.
    if summary:
        console.print(f"\n[cyan]{'='*40}[/cyan]")
        console.print("[bold]GENERATED SUMMARY[/bold]")
        console.print(f"[cyan]{'='*40}[/cyan]\n")
        console.print(summary)

        # Optionally save to file.
        if out_path:
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(summary)
                console.print(f"\n[dim]Summary saved to: {out_path}[/dim]")
            except Exception as e:
                print_error(f"Error saving file: {e}")


def main():
    """CLI entry point for the Document Summarizer."""
    parser = argparse.ArgumentParser(description="Document Summarizer with Gemini")
    parser.add_argument("filepath", help="Path to the PDF or TXT file")
    parser.add_argument("--key", help="Google API Key (optional)")
    parser.add_argument("--out", help="Save summary to this file")
    args = parser.parse_args()

    run_summarizer(args.filepath, args.key, args.out)


if __name__ == "__main__":
    main()

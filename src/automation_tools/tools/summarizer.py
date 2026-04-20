import os
import argparse
from typing import List, Optional
import pypdf

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

CHUNK_CHARS = 28000  # per-request budget


def extract_text_from_pdf(filepath: str) -> Optional[str]:
    """Extrae texto de un archivo PDF."""
    text = ""
    try:
        reader = pypdf.PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        print_error(f"Error al leer PDF: {e}")
        return None


def extract_text_from_txt(filepath: str) -> Optional[str]:
    """Lee texto de un archivo plano."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print_error(f"Error al leer archivo de texto: {e}")
        return None


def _chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> List[str]:
    """Split text into chunks, preferring paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
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
    """Core function to summarize a document (map-reduce over chunks when large)."""

    if not os.path.exists(filepath):
        print_error(f"El archivo '{filepath}' no existe.")
        return

    ext = os.path.splitext(filepath)[1].lower()
    text = ""
    if ext == ".pdf":
        text = extract_text_from_pdf(filepath)
    elif ext in [".txt", ".md", ".py", ".json"]:
        text = extract_text_from_txt(filepath)
    else:
        print_error(f"Formato no soportado: {ext}")
        return

    if not text:
        print_error("No se pudo extraer texto del archivo.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    chunks = _chunk_text(text)

    chunk_instruction = (
        "Eres un analista experto. Lee este fragmento y extrae:\n"
        "1. 3-5 puntos clave concisos.\n"
        "2. Cualquier dato numérico, fecha o nombre propio relevante.\n"
        "Preserva la estructura del original (títulos/secciones si existen). "
        "Responde en español en formato bullet list."
    )
    final_instruction = (
        "Eres un analista experto. Sintetiza los siguientes resúmenes parciales "
        "(cada uno cubre un fragmento del documento en orden) en:\n"
        "1. Un resumen ejecutivo de 1-2 párrafos.\n"
        "2. Una lista consolidada de puntos clave (bullet points).\n"
        "Conserva títulos/secciones del original si son identificables."
    )

    partials: List[str] = []
    if len(chunks) == 1:
        print_step("Generando resumen con Gemini...")
        summary = generate_content(
            client,
            f"Texto:\n{chunks[0]}",
            system_instruction=(
                "Eres un experto analista. Por favor lee el siguiente texto y genera:\n"
                "1. Un resumen ejecutivo de 1 párrafo.\n"
                "2. Una lista de los puntos clave (bullet points).\n"
                "Preserva títulos o secciones principales si existen."
            ),
        )
    else:
        print_step(f"Documento largo: procesando {len(chunks)} fragmentos (map-reduce).")
        for i, chunk in enumerate(chunks, 1):
            console.print(f"[dim]  • Fragmento {i}/{len(chunks)}…[/dim]")
            part = generate_content(
                client,
                f"Fragmento {i}/{len(chunks)}:\n{chunk}",
                system_instruction=chunk_instruction,
            )
            if part:
                partials.append(f"### Fragmento {i}\n{part}")
            else:
                print_warning(f"No se pudo resumir el fragmento {i}.")

        if not partials:
            print_error("No se generó ningún resumen parcial.")
            return

        print_step("Consolidando resumen final…")
        combined = "\n\n".join(partials)
        summary = generate_content(
            client,
            f"Resúmenes parciales:\n{combined}",
            system_instruction=final_instruction,
        )

    if summary:
        console.print(f"\n[cyan]{'='*40}[/cyan]")
        console.print("[bold]RESUMEN GENERADO[/bold]")
        console.print(f"[cyan]{'='*40}[/cyan]\n")
        console.print(summary)

        if out_path:
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(summary)
                console.print(f"\n[dim]Resumen guardado en: {out_path}[/dim]")
            except Exception as e:
                print_error(f"Error al guardar archivo: {e}")


def main():
    parser = argparse.ArgumentParser(description="Resumidor de Documentos con Gemini")
    parser.add_argument("filepath", help="Ruta al archivo PDF o TXT")
    parser.add_argument("--key", help="API Key de Google (opcional)")
    parser.add_argument("--out", help="Guardar resumen en este archivo")
    args = parser.parse_args()

    run_summarizer(args.filepath, args.key, args.out)


if __name__ == "__main__":
    main()

import os
import argparse
import hashlib
from typing import List, Optional

from automation_tools.core.logger import console, print_error, print_step, print_warning
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

CHUNK_CHARS = 40000  # per-request budget (well under Gemini limits, headroom for instructions)


def read_file(filepath: str) -> Optional[str]:
    """Lee el contenido de un archivo de texto."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print_error(f"Error al leer el archivo: {e}")
        return None


def _chunk_text(text: str, max_chars: int = CHUNK_CHARS) -> List[str]:
    """Split text into chunks under `max_chars`, preferring paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_chars:
        # Try to cut at last paragraph/sentence boundary within budget.
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
    h = hashlib.md5(f"{target_lang}::{chunk}".encode("utf-8")).hexdigest()
    return h


def run_translator(filepath: str, target_lang: str, api_key: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Core function to translate a file (with chunking + caching)."""
    if not os.path.exists(filepath):
        print_error(f"El archivo '{filepath}' no existe.")
        return

    supported = ('.txt', '.md', '.srt', '.py', '.json', '.csv', '.xml', '.html', '.css', '.js')
    ext = os.path.splitext(filepath)[1].lower()

    if ext not in supported:
        print_error(f"Formato no soportado: {ext}. \nSoportados: {', '.join(supported)}")
        return

    text = read_file(filepath)
    if not text:
        print_error("No se pudo leer el contenido del archivo.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    instruction = f"""Eres un traductor profesional. Traduce el siguiente texto al idioma {target_lang}.

Reglas estrictas:
- Preserva exactamente el formato original: saltos de linea, indentacion, espacios, y estructura.
- Si el texto contiene codigo fuente, traduce SOLO los comentarios y cadenas de texto, no el codigo.
- Si el texto es un archivo de subtitulos (.srt), traduce SOLO el texto, no los timestamps ni los numeros de secuencia.
- Si el texto es JSON, traduce SOLO los valores de texto, no las claves.
- Si el texto es Markdown, preserva toda la sintaxis Markdown (encabezados, listas, enlaces, bloques de codigo, etc).
- Si recibes un fragmento que parece incompleto, asume que es parte de un texto mayor y traducelo sin agregar continuaciones.
- No agregues explicaciones, notas ni texto adicional. Devuelve unicamente el texto traducido."""

    chunks = _chunk_text(text)
    if len(chunks) > 1:
        print_step(f"Archivo grande: dividido en {len(chunks)} fragmentos.")

    print_step(f"Traduciendo a {target_lang} con Gemini...")

    cache: dict = {}
    translated_parts: List[str] = []

    for i, chunk in enumerate(chunks, 1):
        key = _chunk_cache_key(chunk, target_lang)
        if key in cache:
            console.print(f"[dim]  • Fragmento {i}/{len(chunks)}: reutilizando traducción en caché[/dim]")
            translated_parts.append(cache[key])
            continue

        if len(chunks) > 1:
            console.print(f"[dim]  • Fragmento {i}/{len(chunks)} ({len(chunk)} chars)…[/dim]")

        prompt = f"Texto a traducir:\n{chunk}"
        result = generate_content(client, prompt, system_instruction=instruction)
        if not result:
            print_warning(f"No se pudo traducir el fragmento {i}. Se conserva el original.")
            translated_parts.append(chunk)
            continue
        cache[key] = result
        translated_parts.append(result)

    translation = "\n".join(translated_parts)

    console.print(f"\n[cyan]{'=' * 40}[/cyan]")
    console.print("[bold]TRADUCCIÓN GENERADA[/bold]")
    console.print(f"[cyan]{'=' * 40}[/cyan]\n")
    console.print(translation[:4000])
    if len(translation) > 4000:
        console.print(f"[dim]... (vista previa truncada · total {len(translation)} caracteres)[/dim]")

    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(translation)
            console.print(f"\n[dim]Traducción guardada en: {out_path}[/dim]")
        except Exception as e:
            print_error(f"Error al guardar archivo: {e}")


def main():
    parser = argparse.ArgumentParser(description="Traductor de Archivos con Gemini")
    parser.add_argument("filepath", help="Ruta al archivo a traducir")
    parser.add_argument("--lang", required=True, help="Idioma destino")
    parser.add_argument("--key", help="API Key de Google (opcional)")
    parser.add_argument("--out", help="Guardar traduccion en este archivo")
    args = parser.parse_args()

    run_translator(args.filepath, args.lang, args.key, args.out)


if __name__ == "__main__":
    main()

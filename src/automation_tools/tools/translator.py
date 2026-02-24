import os
import argparse
from typing import Optional

from automation_tools.core.logger import console, print_error, print_step
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

def read_file(filepath: str) -> Optional[str]:
    """Lee el contenido de un archivo de texto."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print_error(f"Error al leer el archivo: {e}")
        return None

def run_translator(filepath: str, target_lang: str, api_key: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Core function to translate a file."""
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

    print_step(f"Traduciendo a {target_lang} con Gemini...")

    instruction = f"""Eres un traductor profesional. Traduce el siguiente texto al idioma {target_lang}.

Reglas estrictas:
- Preserva exactamente el formato original: saltos de linea, indentacion, espacios, y estructura.
- Si el texto contiene codigo fuente, traduce SOLO los comentarios y cadenas de texto, no el codigo.
- Si el texto es un archivo de subtitulos (.srt), traduce SOLO el texto, no los timestamps ni los numeros de secuencia.
- Si el texto es JSON, traduce SOLO los valores de texto, no las claves.
- Si el texto es Markdown, preserva toda la sintaxis Markdown (encabezados, listas, enlaces, bloques de codigo, etc).
- No agregues explicaciones, notas ni texto adicional. Devuelve unicamente el texto traducido."""

    prompt = f"Texto a traducir:\n{text[:50000]}"
    
    translation = generate_content(client, prompt, system_instruction=instruction)

    if translation:
        console.print(f"\n[cyan]{'=' * 40}[/cyan]")
        console.print("[bold]TRADUCCIÓN GENERADA[/bold]")
        console.print(f"[cyan]{'=' * 40}[/cyan]\n")
        console.print(translation)

        if out_path:
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(translation)
                console.print(f"\n[dim]Traducción guardada en: {out_path}[/dim]")
            except Exception as e:
                print_error(f"Error al guardar archivo: {e}")
    else:
        print_error("No se pudo generar la traducción.")

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

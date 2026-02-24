import os
import argparse
from typing import Optional
import pypdf

from automation_tools.core.logger import console, print_error, print_step
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

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

def run_summarizer(filepath: str, api_key: Optional[str] = None, out_path: Optional[str] = None) -> None:
    """Core function to summarize a document."""
    
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

    print_step(f"Generando resumen con Gemini...")
    
    prompt = f"Texto:\n{text[:30000]}"
    instruction = "Eres un experto analista. Por favor lee el siguiente texto y genera:\n1. Un resumen ejecutivo de 1 párrafo.\n2. Una lista de los puntos clave (bullet points)."
    
    summary = generate_content(client, prompt, system_instruction=instruction)
    
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

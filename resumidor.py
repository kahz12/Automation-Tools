import os
import sys
import argparse
from google import genai
from google.genai import types
import pypdf

# Intentar cargar variables de entorno desde .env si existe python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def extract_text_from_pdf(filepath):
    """Extrae texto de un archivo PDF."""
    text = ""
    try:
        reader = pypdf.PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    except Exception as e:
        print(f"Error al leer PDF: {e}")
        return None
    return text

def extract_text_from_txt(filepath):
    """Lee texto de un archivo plano."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error al leer archivo de texto: {e}")
        return None

def summarize_text(text, api_key, model_name="gemini-2.5-flash"):
    """Envía el texto a la API de Gemini para resumirlo."""
    if not text:
        return None

    print(f"Generando resumen con Gemini ({model_name})...")
    
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Eres un experto analista. Por favor lee el siguiente texto y genera:
        1. Un resumen ejecutivo de 1 párrafo.
        2. Una lista de los puntos clave (bullet points).
        
        Texto:
        {text[:30000]}  # Limitamos caracteres por seguridad/tokens
        """
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Error en la API de Gemini: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Resumidor de Documentos con Gemini")
    parser.add_argument("filepath", help="Ruta al archivo PDF o TXT")
    parser.add_argument("--key", help="API Key de Google (opcional si está en env GOOGLE_API_KEY)")
    parser.add_argument("--out", help="Guardar resumen en este archivo")
    
    args = parser.parse_args()

    api_key = args.key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: No se encontró la API Key. Usa --key o define GOOGLE_API_KEY.")
        return

    if not os.path.exists(args.filepath):
        print(f"Error: El archivo '{args.filepath}' no existe.")
        return

    # Extraer texto
    ext = os.path.splitext(args.filepath)[1].lower()
    text = ""
    if ext == ".pdf":
        text = extract_text_from_pdf(args.filepath)
    elif ext in [".txt", ".md", ".py", ".json"]:
        text = extract_text_from_txt(args.filepath)
    else:
        print(f"Formato no soportado: {ext}")
        return

    if not text:
        print("No se pudo extraer texto del archivo.")
        return

    # Resumir
    summary = summarize_text(text, api_key)
    
    if summary:
        print("\n" + "="*40)
        print("RESUMEN GENERADO")
        print("="*40 + "\n")
        print(summary)
        
        if args.out:
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(summary)
                print(f"\nResumen guardado en: {args.out}")
            except Exception as e:
                print(f"Error al guardar archivo: {e}")

if __name__ == "__main__":
    main()

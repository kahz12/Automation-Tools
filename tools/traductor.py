# ─── Imports ───
import os
import sys
import argparse
from google import genai
from google.genai import types

# Intentar cargar variables de entorno desde .env si existe python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─── Funciones ───
def read_file(filepath):
    """Lee el contenido de un archivo de texto."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error al leer el archivo: {e}")
        return None


def translate_text(text, target_lang, api_key, model_name="gemini-2.5-flash"):
    """Envía el texto a la API de Gemini para traducirlo."""
    if not text:
        return None

    print(f"Traduciendo a {target_lang} con Gemini ({model_name})...")

    try:
        client = genai.Client(api_key=api_key)

        prompt = f"""Eres un traductor profesional. Traduce el siguiente texto al idioma {target_lang}.

Reglas estrictas:
- Preserva exactamente el formato original: saltos de linea, indentacion, espacios, y estructura.
- Si el texto contiene codigo fuente, traduce SOLO los comentarios y cadenas de texto, no el codigo.
- Si el texto es un archivo de subtitulos (.srt), traduce SOLO el texto, no los timestamps ni los numeros de secuencia.
- Si el texto es JSON, traduce SOLO los valores de texto, no las claves.
- Si el texto es Markdown, preserva toda la sintaxis Markdown (encabezados, listas, enlaces, bloques de codigo, etc).
- No agregues explicaciones, notas ni texto adicional. Devuelve unicamente el texto traducido.

Texto a traducir:
{text[:50000]}"""

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"Error en la API de Gemini: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Traductor de Archivos con Gemini")
    parser.add_argument("filepath", help="Ruta al archivo a traducir")
    parser.add_argument("--lang", required=True, help="Idioma destino (ej: ingles, frances, portugues)")
    parser.add_argument("--key", help="API Key de Google (opcional si esta en env GOOGLE_API_KEY)")
    parser.add_argument("--out", help="Guardar traduccion en este archivo")

    args = parser.parse_args()

    api_key = args.key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("Error: No se encontro la API Key. Usa --key o define GOOGLE_API_KEY.")
        return

    if not os.path.exists(args.filepath):
        print(f"Error: El archivo '{args.filepath}' no existe.")
        return

    supported = ('.txt', '.md', '.srt', '.py', '.json', '.csv', '.xml', '.html', '.css', '.js')
    ext = os.path.splitext(args.filepath)[1].lower()
    if ext not in supported:
        print(f"Formato no soportado: {ext}")
        print(f"Formatos soportados: {', '.join(supported)}")
        return

    # Leer archivo
    text = read_file(args.filepath)
    if not text:
        print("No se pudo leer el contenido del archivo.")
        return

    # Traducir
    translation = translate_text(text, args.lang, api_key)

    if translation:
        print("\n" + "=" * 40)
        print("TRADUCCION GENERADA")
        print("=" * 40 + "\n")
        print(translation)

        if args.out:
            try:
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(translation)
                print(f"\nTraduccion guardada en: {args.out}")
            except Exception as e:
                print(f"Error al guardar archivo: {e}")
    else:
        print("No se pudo generar la traduccion.")


# ─── Entry point ───
if __name__ == "__main__":
    main()

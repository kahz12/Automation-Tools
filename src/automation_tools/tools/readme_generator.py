import os
import argparse
from typing import Optional, List

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content

def get_project_tree(directory: str, ignore_dirs: Optional[List[str]] = None) -> str:
    """Genera una representacion en texto del arbol de directorios."""
    if ignore_dirs is None:
        ignore_dirs = ['.git', '__pycache__', 'venv', 'env', 'node_modules', '.idea', '.vscode', '.venv']
        
    tree_str = f"{os.path.basename(os.path.abspath(directory))}/\n"
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        level = root.replace(directory, '').count(os.sep)
        indent = '│   ' * level
        subindent = '│   ' * (level + 1)
        
        if level > 0:
            tree_str += f"{indent}├── {os.path.basename(root)}/\n"
            
        for f in files:
            tree_str += f"{subindent}├── {f}\n"
            
    return tree_str

def read_key_files(directory: str, max_files: int = 10) -> str:
    """Lee el contenido de archivos clave para entender el proyecto."""
    key_extensions = ['.py', '.js', '.html', '.md', '.json', '.txt', '.sh', '.yml', '.yaml', '.ts', '.go', '.rs', '.cpp', '.h', '.java']
    important_files = ['requirements.txt', 'package.json', 'Dockerfile', 'main.py', 'app.py', 'index.js', 'cargo.toml', 'go.mod']
    
    content = ""
    files_read = 0
    
    for root, dirs, files in os.walk(directory):
        if any(ignored in root for ignored in ['.git', 'venv', 'node_modules', '__pycache__', '.venv']):
            continue
            
        for f in files:
            filepath = os.path.join(root, f)
            ext = os.path.splitext(f)[1].lower()
            
            if f in important_files or ext in key_extensions:
                if files_read >= max_files:
                    break
                    
                try:
                    with open(filepath, 'r', encoding='utf-8') as file:
                        file_content = file.read(10240) 
                        content += f"\n--- Contenido de {f} ---\n{file_content}\n"
                        files_read += 1
                except Exception:
                    pass
                    
        if files_read >= max_files:
            break
            
    return content

def run_readme_generator(directory: str, api_key: Optional[str] = None, out_path: str = "README_generado.md") -> None:
    """Analiza el proyecto y usa Gemini para generar el README."""
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    print_step(f"Analizando proyecto en: {directory}...")
    tree = get_project_tree(directory)
    code_context = read_key_files(directory)
    
    print_step("Enviando contexto a Gemini...")
    
    instruction = """Eres un desarrollador experto. Escribe un README.md completo, profesional y bien estructurado (en español) para el siguiente proyecto.

Usa la estructura de carpetas y los fragmentos de código para entender de qué se trata, qué hace, cómo se instala y cómo se usa.

El README debe contener:
1. Título y descripción corta (qué hace el proyecto)
2. Características principales (viñetas)
3. Requisitos previos e instalación (comandos paso a paso)
4. Uso (con ejemplos de comandos)
5. Estructura del proyecto (usando un árbol)

Instrucciones finales:
- Devuelve ÚNICAMENTE el código Markdown del README.
- No incluyas comentarios iniciales introductorios.
- NO envuelvas tu respuesta en un bloque ```markdown (solo entrega el Markdown raw)."""

    prompt = f"Estructura de Carpetas (arbol real):\n{tree}\n\nCódigo y Archivos Clave:\n{code_context[:50000]}"
    
    readme_content = generate_content(client, prompt, system_instruction=instruction)
    
    if readme_content:
        if readme_content.startswith("```markdown"):
            readme_content = readme_content[11:]
        elif readme_content.startswith("```"):
            readme_content = readme_content[3:]
            
        if readme_content.endswith("```"):
            readme_content = readme_content[:-3]
            
        readme_content = readme_content.strip()
        
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(readme_content)
            print_success(f"README generado y guardado en: {out_path}")
        except Exception as e:
            print_error(f"Error al guardar el archivo: {e}")

def main():
    parser = argparse.ArgumentParser(description="Generador Automatico de README con IA")
    parser.add_argument("directory", help="Directorio del proyecto a analizar")
    parser.add_argument("--key", help="API Key de Google (opcional si esta en env GOOGLE_API_KEY)")
    parser.add_argument("--out", default="README_generado.md", help="Archivo de salida")
    args = parser.parse_args()
    
    run_readme_generator(args.directory, args.key, args.out)

if __name__ == "__main__":
    main()

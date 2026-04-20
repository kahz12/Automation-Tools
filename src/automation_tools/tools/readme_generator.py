import os
import argparse
import re
from collections import Counter
from typing import Dict, Optional, List, Tuple

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content


# File extensions → language name.
LANG_EXTENSIONS: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".swift": "Swift",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Bash",
    ".lua": "Lua",
    ".dart": "Dart",
    ".scala": "Scala",
    ".clj": "Clojure",
}

# Signal files that indicate a specific stack (stronger than extensions).
STACK_MARKERS: List[Tuple[str, str]] = [
    ("pyproject.toml", "Python"),
    ("requirements.txt", "Python"),
    ("setup.py", "Python"),
    ("package.json", "Node.js / JavaScript"),
    ("tsconfig.json", "TypeScript"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java / Kotlin (Gradle)"),
    ("Gemfile", "Ruby"),
    ("composer.json", "PHP"),
    ("pubspec.yaml", "Dart / Flutter"),
]


def detect_primary_language(directory: str) -> Optional[str]:
    """Detect the dominant language by counting source files + stack markers."""
    stack_hits: List[str] = []
    ext_counter: Counter = Counter()

    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in ('.git', 'venv', '.venv', 'node_modules', '__pycache__', 'dist', 'build')]
        for f in files:
            if any(f == marker for marker, _ in STACK_MARKERS):
                for marker, lang in STACK_MARKERS:
                    if f == marker:
                        stack_hits.append(lang)
            ext = os.path.splitext(f)[1].lower()
            if ext in LANG_EXTENSIONS:
                ext_counter[LANG_EXTENSIONS[ext]] += 1

    if stack_hits:
        return Counter(stack_hits).most_common(1)[0][0]
    if ext_counter:
        return ext_counter.most_common(1)[0][0]
    return None


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


def generate_toc(markdown: str) -> str:
    """Build a GitHub-flavored TOC from ## / ### headings in the markdown."""
    lines = markdown.splitlines()
    toc: List[str] = []
    for line in lines:
        m = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        if title.lower() in ("tabla de contenidos", "tabla de contenido", "contents", "toc"):
            continue
        slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
        indent = "  " * (level - 2)
        toc.append(f"{indent}- [{title}](#{slug})")
    if not toc:
        return ""
    return "## Tabla de contenidos\n\n" + "\n".join(toc) + "\n"


def _inject_toc(markdown: str) -> str:
    """Insert a TOC right after the first H1 title (or at the top)."""
    toc = generate_toc(markdown)
    if not toc:
        return markdown
    lines = markdown.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i + 1
            break
    # Skip a blank line after H1 if present.
    if insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    return "\n".join(lines[:insert_at] + ["", toc] + lines[insert_at:])


def run_readme_generator(directory: str, api_key: Optional[str] = None, out_path: str = "README_generado.md") -> None:
    """Analiza el proyecto y usa Gemini para generar el README con TOC."""
    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    print_step(f"Analizando proyecto en: {directory}...")
    language = detect_primary_language(directory) or "no identificado"
    console.print(f"[dim]Lenguaje principal detectado: [bold]{language}[/bold][/dim]")

    tree = get_project_tree(directory)
    code_context = read_key_files(directory)

    print_step("Enviando contexto a Gemini...")

    lang_hint = ""
    if language.lower().startswith("python"):
        lang_hint = "Incluye sección de entorno virtual (venv) y `pip install -r requirements.txt`."
    elif "node" in language.lower() or "javascript" in language.lower() or "typescript" in language.lower():
        lang_hint = "Incluye comandos `npm install` / `npm run` según los scripts de package.json."
    elif "rust" in language.lower():
        lang_hint = "Incluye comandos `cargo build` y `cargo run`."
    elif "go" in language.lower():
        lang_hint = "Incluye comandos `go build` y `go run ./...`."
    elif "java" in language.lower():
        lang_hint = "Incluye comandos de Maven/Gradle según corresponda."

    instruction = f"""Eres un desarrollador experto. Escribe un README.md completo, profesional y bien estructurado (en español) para el siguiente proyecto.

El lenguaje principal del proyecto es: {language}. {lang_hint}

Usa la estructura de carpetas y los fragmentos de código para entender de qué se trata, qué hace, cómo se instala y cómo se usa.

El README debe contener:
1. Título y descripción corta (qué hace el proyecto)
2. Características principales (viñetas)
3. Requisitos previos e instalación (comandos paso a paso, adaptados al lenguaje)
4. Uso (con ejemplos de comandos)
5. Estructura del proyecto (usando un árbol)

Instrucciones finales:
- Devuelve ÚNICAMENTE el código Markdown del README.
- No incluyas comentarios iniciales introductorios.
- NO envuelvas tu respuesta en un bloque ```markdown (solo entrega el Markdown raw).
- NO incluyas una tabla de contenidos: se agregará automáticamente después."""

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
        readme_content = _inject_toc(readme_content)

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

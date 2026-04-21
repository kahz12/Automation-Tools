import os
import argparse
import re
from collections import Counter
from typing import Dict, Optional, List, Tuple

from automation_tools.core.logger import console, print_error, print_step, print_success
from automation_tools.tools.gemini_utils import get_gemini_client, generate_content


# Mapping of file extensions to their respective programming languages
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

# Signal files that indicate a specific project stack (stronger indicator than extensions)
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
    """
    Detects the dominant programming language by counting source files and checking stack markers.
    
    Args:
        directory (str): The project root directory.
        
    Returns:
        Optional[str]: The detected language name or None.
    """
    stack_hits: List[str] = []
    ext_counter: Counter = Counter()

    for root, dirs, files in os.walk(directory):
        # Prune common non-source directories
        dirs[:] = [d for d in dirs if d not in ('.git', 'venv', '.venv', 'node_modules', '__pycache__', 'dist', 'build')]
        for f in files:
            # Check for stack markers (like package.json)
            if any(f == marker for marker, _ in STACK_MARKERS):
                for marker, lang in STACK_MARKERS:
                    if f == marker:
                        stack_hits.append(lang)
            # Count extensions
            ext = os.path.splitext(f)[1].lower()
            if ext in LANG_EXTENSIONS:
                ext_counter[LANG_EXTENSIONS[ext]] += 1

    # Stack markers have priority over file counts
    if stack_hits:
        return Counter(stack_hits).most_common(1)[0][0]
    if ext_counter:
        return ext_counter.most_common(1)[0][0]
    return None


def get_project_tree(directory: str, ignore_dirs: Optional[List[str]] = None) -> str:
    """
    Generates a text-based tree representation of the directory structure.
    
    Args:
        directory (str): The directory to map.
        ignore_dirs (Optional[List[str]]): List of directories to skip.
        
    Returns:
        str: A string representing the project tree.
    """
    if ignore_dirs is None:
        ignore_dirs = ['.git', '__pycache__', 'venv', 'env', 'node_modules', '.idea', '.vscode', '.venv']

    tree_str = f"{os.path.basename(os.path.abspath(directory))}/\n"

    for root, dirs, files in os.walk(directory):
        # Filter out ignored directories
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
    """
    Reads the content of key files to provide context for project analysis.
    
    Args:
        directory (str): Project root directory.
        max_files (int): Maximum number of files to read to avoid hitting token limits.
        
    Returns:
        str: Concatenated content of key project files.
    """
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
                        # Read up to 10KB per file
                        file_content = file.read(10240)
                        content += f"\n--- Content of {f} ---\n{file_content}\n"
                        files_read += 1
                except Exception:
                    pass

        if files_read >= max_files:
            break

    return content


def generate_toc(markdown: str) -> str:
    """
    Builds a GitHub-flavored Table of Contents (TOC) from ## and ### headings.
    
    Args:
        markdown (str): The README content.
        
    Returns:
        str: A markdown string containing the TOC.
    """
    lines = markdown.splitlines()
    toc: List[str] = []
    for line in lines:
        m = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        # Skip self-referencing TOC titles
        if title.lower() in ("tabla de contenidos", "tabla de contenido", "contents", "toc"):
            continue
        slug = re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "-")
        indent = "  " * (level - 2)
        toc.append(f"{indent}- [{title}](#{slug})")
    if not toc:
        return ""
    return "## Table of Contents\n\n" + "\n".join(toc) + "\n"


def _inject_toc(markdown: str) -> str:
    """
    Inserts a Table of Contents right after the first H1 title.
    """
    toc = generate_toc(markdown)
    if not toc:
        return markdown
    lines = markdown.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            insert_at = i + 1
            break
    # Add a blank line if necessary
    if insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    return "\n".join(lines[:insert_at] + ["", toc] + lines[insert_at:])


def run_readme_generator(directory: str, api_key: Optional[str] = None, out_path: str = "README_generado.md") -> None:
    """
    Analyzes a project and uses Gemini AI to generate a comprehensive README.md.
    
    Args:
        directory (str): The project directory.
        api_key (Optional[str]): Google API key.
        out_path (str): The destination file path.
    """
    if not os.path.isdir(directory):
        print_error(f"The directory '{directory}' does not exist.")
        return

    client = get_gemini_client(api_key)
    if not client:
        return

    print_step(f"Analyzing project at: {directory}...")
    language = detect_primary_language(directory) or "unidentified"
    console.print(f"[dim]Primary language detected: [bold]{language}[/bold][/dim]")

    tree = get_project_tree(directory)
    code_context = read_key_files(directory)

    print_step("Sending context to Gemini...")

    # Language-specific setup hints
    lang_hint = ""
    if language.lower().startswith("python"):
        lang_hint = "Include virtual environment (venv) and `pip install -r requirements.txt` section."
    elif "node" in language.lower() or "javascript" in language.lower() or "typescript" in language.lower():
        lang_hint = "Include `npm install` / `npm run` commands based on package.json scripts."
    elif "rust" in language.lower():
        lang_hint = "Include `cargo build` and `cargo run` commands."
    elif "go" in language.lower():
        lang_hint = "Include `go build` and `go run ./...` commands."
    elif "java" in language.lower():
        lang_hint = "Include Maven/Gradle commands as appropriate."

    instruction = f"""You are an expert developer. Write a complete, professional, and well-structured README.md (in Spanish) for the following project.

Primary language: {language}. {lang_hint}

Use the folder structure and code snippets to understand the project's purpose, functionality, installation, and usage.

The README must contain:
1. Title and short description (what the project does)
2. Main features (bullet points)
3. Prerequisites and installation (step-by-step commands)
4. Usage (with command examples)
5. Project structure (using a tree)

Final instructions:
- Return ONLY the Markdown code for the README.
- Do not include introductory comments.
- DO NOT wrap your response in ```markdown blocks (just raw Markdown).
- DO NOT include a table of contents; it will be added automatically."""

    prompt = f"Folder Structure (real tree):\n{tree}\n\nCode and Key Files:\n{code_context[:50000]}"

    readme_content = generate_content(client, prompt, system_instruction=instruction)

    if readme_content:
        # Clean up potential markdown blocks if AI ignored instructions
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
            print_success(f"README generated and saved at: {out_path}")
        except Exception as e:
            print_error(f"Error saving file: {e}")


def main():
    """
    Main entry point for the README generator CLI.
    """
    parser = argparse.ArgumentParser(description="AI-powered Automatic README Generator")
    parser.add_argument("directory", help="Project directory to analyze")
    parser.add_argument("--key", help="Google API Key (optional if in GOOGLE_API_KEY env)")
    parser.add_argument("--out", default="README_generado.md", help="Output file path")
    args = parser.parse_args()

    run_readme_generator(args.directory, args.key, args.out)


if __name__ == "__main__":
    main()

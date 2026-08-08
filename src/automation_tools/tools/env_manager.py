import os
import argparse
from typing import List, Optional, Tuple

from automation_tools.core.logger import console, print_error, print_step, print_warning

# Generate a .env.example template, find .env files that should never be
# committed, and check a .env against its template.
#
# Exit contract:
#   generate → True when the template was written.
#   validate → True only when the .env matches the template. Here the verdict is
#              the result, so it is what drives the exit code.
#   scan     → True when the scan completed. Finding .env files is the expected
#              output of the report, not a failure.

# Skipped when scanning: vendored trees are full of other people's .env files.
IGNORE_DIRS = {"node_modules", "venv", ".venv", "__pycache__", ".git", "env"}


def _parse_env_file(filepath: str) -> List[Tuple[Optional[str], Optional[str], str]]:
    """Parses a .env file into (key, value, original_line) tuples.

    Comments, blank lines and anything without an '=' come back with key and
    value set to None, so the original line can still be reproduced verbatim.
    """
    lines_parsed: List[Tuple[Optional[str], Optional[str], str]] = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#') or '=' not in stripped:
                    lines_parsed.append((None, None, line.rstrip('\n')))
                    continue
                key, val = stripped.split('=', 1)
                lines_parsed.append((key.strip(), val.strip(), line.rstrip('\n')))
    except OSError as e:
        print_error(f"Failed to read {filepath}: {e}")
        return []

    return lines_parsed


def generate_example(env_path: str, out_path: Optional[str] = None) -> bool:
    """Writes a copy of `env_path` with every value blanked out."""
    print_step(f"Generating template from '{env_path}'...")
    parsed = _parse_env_file(env_path)
    if not parsed:
        print_warning("No readable content found or file is empty.")
        return False

    out_lines = []
    keys_found = 0
    for key, _val, original in parsed:
        if key is not None:
            out_lines.append(f"{key}=")
            keys_found += 1
        else:
            out_lines.append(original)

    if not out_path:
        out_path = env_path + ".example"

    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(out_lines) + "\n")
    except OSError as e:
        print_error(f"Failed to write template: {e}")
        return False

    console.print(f"[bold green]✓ Successfully created template with {keys_found} keys.[/]")
    console.print(f"[dim]Saved to: {out_path}[/dim]")
    return True


def scan_envs(directory: str) -> bool:
    """Reports every .env-style file under `directory`, skipping vendored trees."""
    print_step(f"Scanning '{directory}' for exposed .env files...")
    found_files = []

    for root, dirs, files in os.walk(directory):
        # Mutate dirs in place to skip ignored directories.
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file == '.env' or file.endswith('.env.local') or file.endswith('.env.development'):
                found_files.append(os.path.join(root, file))

    if not found_files:
        console.print("[green]✓ No exposed .env files found in the scanned paths.[/green]")
        return True

    console.print(f"\n[bold red]⚠ Found {len(found_files)} potential environment files:[/]")
    for f in found_files:
        console.print(f"  [dim]•[/] {f}")
    console.print("\n[dim]Make sure these files are included in your .gitignore![/dim]")
    return True


def validate_env(env_path: str, example_path: str) -> bool:
    """Compares the keys in `env_path` against `example_path`."""
    print_step(f"Validating '{env_path}' against '{example_path}'...")

    env_parsed = _parse_env_file(env_path)
    example_parsed = _parse_env_file(example_path)

    if not example_parsed:
        print_error("Example file could not be read or is empty.")
        return False

    env_keys = {k for k, _v, _orig in env_parsed if k is not None}
    example_keys = {k for k, _v, _orig in example_parsed if k is not None}

    missing_keys = example_keys - env_keys
    extra_keys = env_keys - example_keys

    if not missing_keys and not extra_keys:
        console.print("[bold green]✓ The .env file is fully synchronized with the template.[/]")
        return True

    if missing_keys:
        console.print("\n[bold red]✗ Missing keys in your .env:[/]")
        for k in sorted(missing_keys):
            console.print(f"  [dim]-[/] {k}")

    if extra_keys:
        console.print("\n[bold yellow]⚠ Extra keys in your .env (not in template):[/]")
        for k in sorted(extra_keys):
            console.print(f"  [dim]+[/] {k}")

    return False


def run_env_manager(
    action: str,
    target_path: str,
    example_path: Optional[str] = None,
    out_path: Optional[str] = None
) -> bool:
    """Dispatches to the requested action. See the module docstring for the contract."""
    if not os.path.exists(target_path):
        print_error(f"Path '{target_path}' does not exist.")
        return False

    if action == "generate":
        if not os.path.isfile(target_path):
            print_error("Target path must be a file to generate a template.")
            return False
        return generate_example(target_path, out_path)

    if action == "scan":
        if not os.path.isdir(target_path):
            print_error("Target path must be a directory to scan.")
            return False
        return scan_envs(target_path)

    if action == "validate":
        if not os.path.isfile(target_path):
            print_error("Target path must be a file to validate.")
            return False
        if not example_path or not os.path.exists(example_path):
            print_error("A valid template/example path is required for validation.")
            return False
        return validate_env(target_path, example_path)

    print_error(f"Unknown action: {action}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Dotenv & Config Manager")
    parser.add_argument("action", choices=["generate", "scan", "validate"], help="Action to perform")
    parser.add_argument("target_path", help="Path to a .env file or directory (for scanning)")
    parser.add_argument("--example", help="Path to .env.example (required for validate)")
    parser.add_argument("--out", help="Output path for the generated template (for generate)")

    args = parser.parse_args()
    ok = run_env_manager(args.action, args.target_path, args.example, args.out)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

import difflib
import importlib
import io
import json
import pkgutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from typing import List, Optional

from rich.markup import escape

from automation_tools import tools as tools_package
from automation_tools.core.cli import exit_code
from automation_tools.core.logger import console, print_error, setup_logger

# One command that reaches every tool: `atools vault ./docs encrypt`.
#
# Each tool module already has its own argparse `main()`, but there was no way
# to reach it once the package was installed. Running the file by path only
# works from a checkout, and even then only if `src` happens to be on the path,
# so the documented examples failed with ModuleNotFoundError. This forwards the
# rest of the command line to the tool's own parser, which keeps every flag and
# help text exactly where it already was.

USAGE = "atools <tool> [options]    ·    atools --list    ·    atools <tool> --help"


def available_tools() -> List[str]:
    """Every tool module that ships in the package, discovered, not hardcoded."""
    return sorted(
        module.name for module in pkgutil.iter_modules(tools_package.__path__)
        if not module.name.startswith("_")
    )


def _print_catalogue() -> None:
    names = available_tools()
    console.print(f"[bold #22d3ee]{escape(USAGE)}[/]\n")
    console.print(f"[dim]{len(names)} tools:[/dim]")
    width = max(len(n) for n in names) + 2
    columns = max(1, 76 // width)
    for row in range(0, len(names), columns):
        console.print("  " + "".join(n.ljust(width) for n in names[row:row + columns]))
    console.print("\n[dim]The interactive menu is `automation-tools`.[/dim]")


def _json_requested(args: List[str]) -> tuple[bool, List[str]]:
    """Extract the machine-output switch without exposing it to tool parsers."""
    json_mode = any(flag in args for flag in ("--json", "--json-output"))
    if not json_mode:
        return False, args
    return True, [arg for arg in args if arg not in ("--json", "--json-output")]


def _print_json(payload: dict[str, object], code: int) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    raise SystemExit(code)


def _run_json(name: str, entry: object, rest: List[str]) -> None:
    """Run a tool while keeping stdout a single valid JSON document."""
    output = io.StringIO()
    errors = io.StringIO()
    old_argv = sys.argv
    sys.argv = [f"atools {name}"] + rest
    code = 0
    error: Optional[str] = None
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            assert callable(entry)
            result = entry()
            code = exit_code(result)
    except SystemExit as exc:
        value = exc.code
        code = value if isinstance(value, int) else (0 if value is None else 1)
    except KeyboardInterrupt:
        code = 130
        error = "Operation cancelled by user"
    except Exception as exc:  # pragma: no cover - defensive boundary
        code = 1
        error = str(exc) or exc.__class__.__name__
    finally:
        sys.argv = old_argv

    text = output.getvalue()
    stderr = errors.getvalue().strip()
    payload: dict[str, object] = {
        "tool": name,
        "ok": code == 0,
        "exit_code": code,
        "output": text,
    }
    if stderr:
        payload["error"] = stderr
    elif error:
        payload["error"] = error
    _print_json(payload, code)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the `atools` command."""
    args = list(sys.argv[1:] if argv is None else argv)
    json_mode, args = _json_requested(args)

    if not args or args[0] in ("-h", "--help", "--list", "-l", "help", "list"):
        if json_mode:
            _print_json({"tools": available_tools()}, 0)
        _print_catalogue()
        raise SystemExit(0)

    name, rest = args[0], args[1:]
    if name not in available_tools():
        if json_mode:
            close = difflib.get_close_matches(name, available_tools(), n=3)
            hint = f"Unknown tool '{name}'."
            if close:
                hint += f" Did you mean: {', '.join(close)}?"
            _print_json({"tool": name, "ok": False, "exit_code": 2,
                         "output": "", "error": hint}, 2)
        print_error(f"There is no tool called '{name}'.")
        close = difflib.get_close_matches(name, available_tools(), n=3)
        if close:
            console.print(f"[dim]Did you mean: {', '.join(close)}?[/dim]")
        console.print(f"[dim]{escape(USAGE)}[/dim]")
        raise SystemExit(2)

    setup_logger()
    module = importlib.import_module(f"automation_tools.tools.{name}")
    entry = getattr(module, "main", None)
    if entry is None:
        print_error(f"'{name}' has no command line of its own; use the menu instead.")
        raise SystemExit(2)

    if json_mode:
        _run_json(name, entry, rest)

    # The tool parses sys.argv itself, so the program name has to read like the
    # command the user actually typed for its --help to make sense.
    old_argv = sys.argv
    sys.argv = [f"atools {name}"] + rest
    try:
        result = entry()
        # A tool may either retain the historical ``raise SystemExit`` style
        # or return a bool/int.  Normalize both forms at the dispatcher
        # boundary so console-script invocations never mask a failed run.
        raise SystemExit(exit_code(result))
    except KeyboardInterrupt:
        console.print()
        raise SystemExit(130)
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    main()

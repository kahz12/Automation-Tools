import difflib
import importlib
import pkgutil
import sys
from typing import List, Optional

from rich.markup import escape

from automation_tools import tools as tools_package
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


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the `atools` command."""
    args = list(sys.argv[1:] if argv is None else argv)

    if not args or args[0] in ("-h", "--help", "--list", "-l", "help", "list"):
        _print_catalogue()
        raise SystemExit(0)

    name, rest = args[0], args[1:]
    if name not in available_tools():
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

    # The tool parses sys.argv itself, so the program name has to read like the
    # command the user actually typed for its --help to make sense.
    sys.argv = [f"atools {name}"] + rest
    try:
        entry()
    except KeyboardInterrupt:
        console.print()
        raise SystemExit(130)


if __name__ == "__main__":
    main()

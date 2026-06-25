"""Structural regression guards for the TUI wiring.

These catch the kind of mistakes that only blow up at runtime: a menu entry
with no screen, a screen calling a tool function that doesn't exist, etc.
"""
import ast
import importlib

from automation_tools.cli.menu import MENU_ENTRIES
from automation_tools.cli.tui import TOOL_INFO
from automation_tools.cli.screens import SCREEN_MAP, ToolScreen
import automation_tools.cli.screens as screens_mod

MENU_LABELS = [label for _, entries in MENU_ENTRIES for label, _ in entries]


def test_menu_labels_unique():
    assert len(MENU_LABELS) == len(set(MENU_LABELS))


def test_every_menu_label_has_screen_and_info():
    info_keys = {k.strip() for k in TOOL_INFO}
    for label in MENU_LABELS:
        assert label in SCREEN_MAP, f"{label!r} missing from SCREEN_MAP"
        assert label.strip() in info_keys, f"{label!r} missing from TOOL_INFO"


def test_screen_map_values_are_tool_screens():
    for cls in SCREEN_MAP.values():
        assert issubclass(cls, ToolScreen)


def test_screen_tool_calls_resolve():
    """Every `<tool_module>.<func>(...)` reference in screens.py must exist."""
    tree = ast.parse(open(screens_mod.__file__).read())

    tool_aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "automation_tools.tools":
            for alias in node.names:
                tool_aliases.add(alias.asname or alias.name)

    missing = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in tool_aliases):
            mod = importlib.import_module(f"automation_tools.tools.{node.value.id}")
            if not callable(getattr(mod, node.attr, None)):
                missing.append(f"{node.value.id}.{node.attr}")

    assert not missing, f"screens.py references non-existent tool callables: {missing}"

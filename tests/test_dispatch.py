"""Tests for the `atools` command.

The point of this entry point is that a tool is reachable after `pip install`,
which is exactly what running the module file by path never was.
"""
import sys

import pytest

from automation_tools.cli import dispatch


def test_every_tool_module_is_listed():
    names = dispatch.available_tools()
    assert "vault" in names and "pdf_builder" in names
    assert not any(n.startswith("_") for n in names)


def test_every_listed_tool_can_actually_be_dispatched():
    """A name in the catalogue with no main() would be a dead menu entry."""
    import importlib

    missing = [
        name for name in dispatch.available_tools()
        if not hasattr(importlib.import_module(f"automation_tools.tools.{name}"), "main")
    ]
    assert missing == []


def test_no_arguments_prints_the_catalogue(capsys):
    with pytest.raises(SystemExit) as excinfo:
        dispatch.main([])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "vault" in out
    # `[options]` is rich markup unless it is escaped, and it used to vanish.
    assert "[options]" in out


def test_an_unknown_tool_suggests_the_closest_name(capsys):
    with pytest.raises(SystemExit) as excinfo:
        dispatch.main(["vaul"])
    assert excinfo.value.code == 2
    assert "vault" in capsys.readouterr().out


def test_arguments_reach_the_tool_and_the_program_name_reads_right(monkeypatch):
    seen = {}

    def fake_main():
        seen["argv"] = list(sys.argv)
        raise SystemExit(0)

    from automation_tools.tools import vault
    monkeypatch.setattr(vault, "main", fake_main)

    with pytest.raises(SystemExit) as excinfo:
        dispatch.main(["vault", "/tmp/x", "encrypt", "--shred"])
    assert excinfo.value.code == 0
    assert seen["argv"] == ["atools vault", "/tmp/x", "encrypt", "--shred"]


def test_interrupting_a_tool_exits_the_conventional_way(monkeypatch):
    def fake_main():
        raise KeyboardInterrupt

    from automation_tools.tools import vault
    monkeypatch.setattr(vault, "main", fake_main)

    with pytest.raises(SystemExit) as excinfo:
        dispatch.main(["vault"])
    assert excinfo.value.code == 130

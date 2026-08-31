"""Tests for the confirmation indirection.

The TUI used to answer these by overwriting `questionary.confirm` for the whole
process. That worked until something escaped the restore, and it meant a
third-party module carried the app's state.
"""
import io

import pytest

from automation_tools.core import logger, prompt


def test_confirm_goes_to_questionary_by_default(monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, message, default):
            seen["message"], seen["default"] = message, default

        def ask(self):
            return True

    monkeypatch.setattr(prompt.questionary, "confirm",
                        lambda message, default=True: Fake(message, default))
    assert prompt.confirm("¿seguro?", default=False) is True
    assert seen == {"message": "¿seguro?", "default": False}


def test_a_backend_takes_over_while_it_is_installed():
    asked = []

    def backend(message, default):
        asked.append((message, default))
        return True

    with prompt.confirm_backend(backend):
        assert prompt.confirm("borro?", default=False) is True
    assert asked == [("borro?", False)]


def test_the_backend_is_removed_even_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with prompt.confirm_backend(lambda m, d: True):
            raise RuntimeError("boom")
    assert prompt._backend is None


def test_backends_nest_and_unwind_in_order():
    called = []
    with prompt.confirm_backend(lambda m, d: called.append("outer") or True):
        with prompt.confirm_backend(lambda m, d: called.append("inner") or True):
            prompt.confirm("x")
        prompt.confirm("x")
    assert called == ["inner", "outer"]


# ── console redirection ─────────────────────────────────────────────────────
def test_redirect_console_captures_what_the_tools_print():
    sink = io.StringIO()
    with logger.redirect_console(sink, width=40):
        logger.print_success("hola")
    assert "hola" in sink.getvalue()


def test_redirect_console_puts_the_console_back():
    """The tools hold the console object itself, so it is reconfigured in place."""
    before = (logger.console.file, logger.console.width, logger.console.is_terminal)
    with logger.redirect_console(io.StringIO()):
        assert logger.console.width == 100
        assert logger.console.is_terminal is True
    assert (logger.console.file, logger.console.width, logger.console.is_terminal) == before


def test_the_console_is_restored_even_when_the_tool_blows_up():
    original = logger.console.file
    with pytest.raises(ValueError):
        with logger.redirect_console(io.StringIO()):
            raise ValueError("boom")
    assert logger.console.file is original

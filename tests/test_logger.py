import io
import logging

import pytest
from rich.text import Text

from automation_tools.core import logger
from automation_tools.core.logger import PALETTE, ASCII_TITLE, _gradient_text


def test_setup_logger_returns_logger():
    lg = logger.setup_logger()
    assert isinstance(lg, logging.Logger)
    assert lg.name == "automation_tools"


def test_palette_has_core_colors():
    for key in ("primary", "accent", "danger", "success", "warning"):
        assert PALETTE[key].startswith("#")


def test_gradient_text_nonempty():
    out = _gradient_text(ASCII_TITLE, PALETTE["primary"], PALETTE["accent"])
    # Rich Text object whose plain content mirrors the banner.
    assert out.plain.strip() != ""


def test_gradient_text_empty_input():
    out = _gradient_text("", "#000000", "#ffffff")
    assert out.plain == ""


def test_print_helpers_do_not_crash():
    # They render to the shared console; just ensure no exception.
    logger.print_error("e")
    logger.print_success("s")
    logger.print_warning("w")
    logger.print_step("step")


# ── the log file is the entry point's business ──────────────────────────────
# Importing a tool used to open the log as a side effect, which meant a library
# import created files and the first module in wins the whole logging config.

def test_get_logger_touches_no_files(monkeypatch, tmp_path, data_dir):
    lg = logger.get_logger()
    assert lg.name == "automation_tools"
    assert not any(data_dir.rglob("*.log"))


def test_setup_logger_writes_into_the_data_directory(monkeypatch, tmp_path, data_dir):
    lg = logger.get_logger()
    monkeypatch.setattr(lg, "handlers", [])

    logger.setup_logger("probe.log").info("hola")
    log_file = data_dir / "probe.log"
    assert "hola" in log_file.read_text(encoding="utf-8")


def test_setup_logger_is_idempotent(monkeypatch, tmp_path, data_dir):
    lg = logger.get_logger()
    monkeypatch.setattr(lg, "handlers", [])

    logger.setup_logger("probe.log")
    logger.setup_logger("probe.log")
    assert len([h for h in logger.get_logger().handlers
                if isinstance(h, logging.FileHandler)]) == 1


def test_setup_logger_survives_an_unwritable_home(monkeypatch, tmp_path, data_dir):
    lg = logger.get_logger()
    monkeypatch.setattr(lg, "handlers", [])

    def refuse(*a, **k):
        raise OSError("read-only file system")

    monkeypatch.setattr(logging, "FileHandler", refuse)
    # No log is better than no app.
    assert logger.setup_logger("probe.log").name == "automation_tools"


def _printed(text):
    out = io.StringIO()
    logger.SafeConsole(file=out, width=200, color_system=None).print(text)
    return out.getvalue().rstrip("\n")


@pytest.mark.parametrize("text", [
    "dups/a [copy].txt",             # used to print as "dups/a .txt"
    "[www.site.com] movie.mkv",
    "/tmp/[/x].jpg",                 # used to raise MarkupError
    "[@click(].txt",
    "[/]",                           # a real tag, but with nothing to close
    "[/bold]",
])
def test_outside_text_is_printed_as_written(text):
    assert _printed(text) == text


def test_the_print_helpers_survive_a_hostile_path(capsys):
    logger.print_error("The file '/tmp/[/x].jpg' does not exist.")
    assert "/tmp/[/x].jpg" in capsys.readouterr().out


def test_real_markup_still_works():
    console = logger.SafeConsole(file=io.StringIO(), width=80)
    text = console.render_str("[bold #22d3ee]x[/] [dim]y[/dim] [copy]")
    assert text.plain == "x y [copy]"
    assert {"bold #22d3ee", "dim"} <= {str(span.style) for span in text.spans}


def test_an_escaped_tag_stays_escaped():
    assert _printed("\\[options] and \\[/x]") == "[options] and [/x]"


def test_markup_false_is_left_alone():
    out = io.StringIO()
    logger.SafeConsole(file=out, width=80, color_system=None).print("[copy]", markup=False)
    assert out.getvalue().rstrip("\n") == "[copy]"


def test_redirecting_keeps_the_safe_console():
    out = io.StringIO()
    with logger.redirect_console(out) as console:
        console.print("a [copy].txt")
    assert "a [copy].txt" in Text.from_ansi(out.getvalue()).plain
    assert isinstance(logger.console, logger.SafeConsole)

import logging

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

import logging
import os
import re
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.errors import MarkupError, StyleError
from rich.text import Text

# What rich's parser takes for a tag, including any backslashes escaping it.
_TAG_RE = re.compile(r"(\\*)\[([a-z#/@][^\[]*?)\]")


class SafeConsole(Console):
    """A console where text from the outside world cannot act as markup.

    Nearly every message here is an f-string with a path, a URL or an exception
    dropped into it, and rich parses the finished string. A file called
    "a [copy].txt" was printed as "a .txt", right before asking whether to
    delete it, and a stray "[/x]" raised MarkupError and took the tool down
    with it. Escaping every value at every call site is what nobody remembers
    to do, so it happens here instead: a bracketed word that is not a real
    style is shown as written.

    A value that happens to spell a style, like "[red]", still reads as one.
    Anything that must be shown exactly, such as a password, has to be passed
    as a `Text`.
    """

    def _is_style(self, tag: str) -> bool:
        name = tag[1:] if tag.startswith("/") else tag
        if not name:  # "[/]" closes whatever is open.
            return True
        try:
            self.get_style(name)
        except StyleError:
            return False
        return True

    def _escape_foreign_tags(self, text: str) -> str:
        def fix(match: "re.Match[str]") -> str:
            slashes, tag = match.groups()
            if len(slashes) % 2 or self._is_style(tag):
                return match.group(0)
            return f"{slashes}\\[{tag}]"
        return _TAG_RE.sub(fix, text)

    def render_str(self, text: str, **kwargs: Any) -> Text:
        if kwargs.get("markup") is False:
            return super().render_str(text, **kwargs)
        try:
            return super().render_str(self._escape_foreign_tags(text), **kwargs)
        except MarkupError:
            # A real style word closing nothing, such as a lone "[/bold]".
            return super().render_str(text, **{**kwargs, "markup": False})


console = SafeConsole()


@contextmanager
def redirect_console(file, width: int = 100):
    """Sends everything the tools print into `file` while the block runs.

    Every tool holds a reference to the console object itself, so the TUI
    cannot simply hand them a different one; the object has to be reconfigured
    in place. Re-running `__init__` is how rich's own `reconfigure()` does
    that, which beats reaching into `_file`, `_force_terminal`, `_color_system`
    and `_width` one by one and hoping they keep those names.
    """
    # Re-running __init__ on a live instance is what rich's own reconfigure()
    # does; type checkers dislike it on principle.
    console.__init__(file=file, force_terminal=True,  # type: ignore[misc]
                     color_system="truecolor", width=width)
    try:
        yield console
    finally:
        console.__init__()  # type: ignore[misc]

# Every colour the project uses, in one place so the CLI and the TUI agree.
PALETTE = {
    "primary": "#7c3aed",      # Purple: Main theme color.
    "primary_soft": "#a78bfa",  # Soft Purple: Used for dividers and secondary UI.
    "accent": "#22d3ee",       # Cyan: Highlights and primary actions.
    "accent_soft": "#67e8f9",   # Soft Cyan: Secondary highlights.
    "success": "#22c55e",      # Green: Success messages and indicators.
    "warning": "#f59e0b",      # Amber: Warnings and cautions.
    "danger": "#ef4444",       # Red: Error messages.
    "muted": "#94a3b8",        # Slate: Secondary text and metadata.
    "text": "#e2e8f0",         # Light Slate: Primary text color.
}

# ASCII Art banner rendered by the Textual launcher (see cli/tui.py).
ASCII_TITLE = r"""
   _____          __                        __  _
  /  _  \  __ ___/  |_  ____   _____ _____ _/  |_(_)____   ____
 /  /_\  \|  |  \   __\/  _ \ /     \\__  \\   __\/  ___\ /    \
/    |    \  |  /|  | (  <_> )  Y Y  \/ __ \|  | |  /_/  >   |  \
\____|__  /____/ |__|  \____/|__|_|  (____  /__| \___  /|___|  /
        \/                         \/     \/    /_____/      \/
"""


LOGGER_NAME = "automation_tools"


def get_logger() -> logging.Logger:
    """The shared logger, without touching the filesystem.

    Modules take this one at import time. Opening the log file is the entry
    point's job (`setup_logger`), so importing a tool to use it as a library
    creates no files and steals nobody's logging config.
    """
    return logging.getLogger(LOGGER_NAME)


def setup_logger(log_file: str = "automation_tools.log", level: int = logging.INFO) -> logging.Logger:
    """Attaches the file handler. Called once, by whatever starts the app.

    The log goes to the user data directory, not next to the source: installed
    with pip there is nothing writable next to the source to begin with. It
    configures our own logger rather than the root one, so a library that logs
    does not end up in our file, and calling it twice does not double every line.
    """
    from automation_tools.core.config import user_data_dir

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        return logger

    log_path = os.path.join(user_data_dir(), log_file)
    try:
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        # A read-only home is not a reason to refuse to run.
        return logger
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return logger


def _gradient_text(text: str, start: str, end: str) -> Text:
    """Creates a vertical color gradient effect for ASCII art.
    Interpolates between two hex colors across lines.
    """
    from rich.color import Color
    from rich.color_triplet import ColorTriplet

    lines = text.strip("\n").splitlines()
    if not lines:
        return Text(text)

    def _parse(hex_color: str) -> ColorTriplet:
        c = Color.parse(hex_color).triplet
        return c if c else ColorTriplet(255, 255, 255)

    a, b = _parse(start), _parse(end)
    out = Text()
    n = max(len(lines) - 1, 1)
    for i, line in enumerate(lines):
        t = i / n
        r = int(a.red + (b.red - a.red) * t)
        g = int(a.green + (b.green - a.green) * t)
        bl = int(a.blue + (b.blue - a.blue) * t)
        out.append(line + "\n", style=f"bold #{r:02x}{g:02x}{bl:02x}")
    return out


def print_error(msg: str) -> None:
    """Displays an error message with a consistent style."""
    console.print(f"[bold {PALETTE['danger']}]✗ Error:[/] {msg}")


def print_success(msg: str) -> None:
    """Displays a success message with a consistent style."""
    console.print(f"[bold {PALETTE['success']}]✓ Success:[/] {msg}")


def print_warning(msg: str) -> None:
    """Displays a warning message with a consistent style."""
    console.print(f"[bold {PALETTE['warning']}]⚠ Warning:[/] {msg}")


def print_step(msg: str) -> None:
    """Displays an progress step indicator."""
    console.print(f"[bold {PALETTE['accent']}]➜[/] {msg}")

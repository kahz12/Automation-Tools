import logging
import os

from rich.console import Console
from rich.text import Text

# --- Logging & UI Utilities Module ---
# Central application logger plus small helpers for consistent, styled terminal
# output using the 'rich' library.

# Global console instance for rendering all project output.
console = Console()

# Visual palette: Centralized color scheme for a consistent look and feel.
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


def setup_logger(log_file: str = "automation_tools.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns the application's central logger.
    Logs are saved to a file in the project root.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    log_path = os.path.join(project_root, log_file)

    logging.basicConfig(
        filename=log_path,
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("automation_tools")


def _gradient_text(text: str, start: str, end: str) -> Text:
    """
    Creates a vertical color gradient effect for ASCII art.
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

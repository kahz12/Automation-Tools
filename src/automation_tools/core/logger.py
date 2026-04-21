import logging
import os
from datetime import datetime
from typing import Optional

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# --- Logging & UI Utilities Module ---
# This module provides stylized terminal output using the 'rich' library.
# It handles the visual layout, banners, section headers, and consistent styling for the CLI.

try:
    from questionary import Style as QuestionaryStyle
except ImportError:
    QuestionaryStyle = None

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

# ASCII Art banner displayed at startup.
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
    if not :
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


def print_banner(clear: bool = True) -> None:
    """
    Renders the main application banner with a gradient title and subtitle.
    Optionally clears the terminal screen before rendering.
    """
    if clear:
        os.system("cls" if os.name == "nt" else "clear")

    title = _gradient_text(ASCII_TITLE, PALETTE["primary"], PALETTE["accent"])
    subtitle = Text(
        "Automation Kit  •  Your terminal toolbox",
        style=f"italic {PALETTE['accent_soft']}",
        justify="center",
    )
    meta = Text(
        f"  v1.0  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}  ·  by Ale  ",
        style=f"dim {PALETTE['muted']}",
        justify="center",
    )

    body = Group(Align.center(title), subtitle, Text(""), meta)
    console.print(
        Panel(
            body,
            border_style=PALETTE["primary"],
            padding=(1, 2),
        )
    )


def print_section(title: str, subtitle: str = "", icon: str = "🛠️") -> None:
    """
    Standardized header for individual tool screens.
    Clears the screen and displays the tool's name and description.
    """
    os.system("cls" if os.name == "nt" else "clear")
    print_banner(clear=False)

    heading = Text()
    heading.append(f"  {icon}  ", style="bold")
    heading.append(title, style=f"bold {PALETTE['accent']}")
    if subtitle:
        heading.append(f"\n      {subtitle}", style=f"italic {PALETTE['muted']}")

    console.print(Panel(heading, border_style=PALETTE["accent"], padding=(0, 1)))
    console.print()


def print_footer_tip(text: str) -> None:
    """Displays a helpful tip or hint at the bottom of the screen."""
    console.print(f"[dim {PALETTE['muted']}]💡 {text}[/]")


def print_rule(label: str = "") -> None:
    """Draws a horizontal line to separate visual sections."""
    console.print(Rule(label, style=PALETTE["primary_soft"]))


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


def question_style():
    """
    Defines the theme for 'questionary' interactive prompts.
    Ensures that input fields, selections, and menus align with the project palette.
    """
    if QuestionaryStyle is None:
        return None
    return QuestionaryStyle(
        [
            ("qmark", f"fg:{PALETTE['accent']} bold"),
            ("question", f"fg:{PALETTE['text']} bold"),
            ("answer", f"fg:{PALETTE['success']} bold"),
            ("pointer", f"fg:{PALETTE['primary_soft']} bold"),
            ("highlighted", f"fg:{PALETTE['accent']} bold"),
            ("selected", f"fg:{PALETTE['success']}"),
            ("separator", f"fg:{PALETTE['muted']}"),
            ("instruction", f"fg:{PALETTE['muted']} italic"),
            ("text", f"fg:{PALETTE['text']}"),
            ("disabled", f"fg:{PALETTE['muted']} italic"),
        ]
    )

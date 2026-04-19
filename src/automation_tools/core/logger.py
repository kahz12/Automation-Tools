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

try:
    from questionary import Style as QuestionaryStyle
except ImportError:  # questionary is always present but keep it defensive
    QuestionaryStyle = None

# Global console instance shared across the package.
console = Console()

# Visual palette (single source of truth for colors across the CLI).
PALETTE = {
    "primary": "#7c3aed",     # purple 600
    "primary_soft": "#a78bfa",  # purple 400
    "accent": "#22d3ee",      # cyan 400
    "accent_soft": "#67e8f9",  # cyan 300
    "success": "#22c55e",     # green 500
    "warning": "#f59e0b",     # amber 500
    "danger": "#ef4444",      # red 500
    "muted": "#94a3b8",       # slate 400
    "text": "#e2e8f0",        # slate 200
}

ASCII_TITLE = r"""
   _____          __                        __  _
  /  _  \  __ ___/  |_  ____   _____ _____ _/  |_(_)____   ____
 /  /_\  \|  |  \   __\/  _ \ /     \\__  \\   __\/  ___\ /    \
/    |    \  |  /|  | (  <_> )  Y Y  \/ __ \|  | |  /_/  >   |  \
\____|__  /____/ |__|  \____/|__|_|  (____  /__| \___  /|___|  /
        \/                         \/     \/    /_____/      \/
"""


def setup_logger(log_file: str = "automation_tools.log", level: int = logging.INFO) -> logging.Logger:
    """Configures and returns the central logger for the application."""
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
    """Returns Text with a two-color vertical gradient across lines."""
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


def print_banner(clear: bool = True) -> None:
    """Renders the main application banner with gradient ASCII art."""
    if clear:
        os.system("cls" if os.name == "nt" else "clear")

    title = _gradient_text(ASCII_TITLE, PALETTE["primary"], PALETTE["accent"])
    subtitle = Text(
        "Kit de Automatización  •  Tu caja de herramientas en la terminal",
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
    """Header shown at the top of each tool screen — replaces ad-hoc titles."""
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
    """Small helper hint, usually shown near prompts."""
    console.print(f"[dim {PALETTE['muted']}]💡 {text}[/]")


def print_rule(label: str = "") -> None:
    """Thin horizontal divider for visual rhythm."""
    console.print(Rule(label, style=PALETTE["primary_soft"]))


def print_error(msg: str) -> None:
    console.print(f"[bold {PALETTE['danger']}]✗ Error:[/] {msg}")


def print_success(msg: str) -> None:
    console.print(f"[bold {PALETTE['success']}]✓ Éxito:[/] {msg}")


def print_warning(msg: str) -> None:
    console.print(f"[bold {PALETTE['warning']}]⚠ Aviso:[/] {msg}")


def print_step(msg: str) -> None:
    console.print(f"[bold {PALETTE['accent']}]➜[/] {msg}")


def question_style():
    """Shared prompt_toolkit style for questionary prompts.

    Applied via `questionary.xxx(..., style=question_style())` so every
    interactive prompt matches the palette.
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

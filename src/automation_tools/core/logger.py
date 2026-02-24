import logging
import os
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Global console instance to be shared across the package
console = Console()

def setup_logger(log_file: str = "automation_tools.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configures and returns the central logger for the application.
    Also ensures the log file is placed in the project root.
    """
    # Assuming the project root is 3 levels up from this file: src/automation_tools/core/logger.py
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

def print_banner(clear: bool = True) -> None:
    """Prints the application banner using Rich."""
    if clear:
        os.system("cls" if os.name == "nt" else "clear")
    title = Text("🚀 KIT DE AUTOMATIZACIÓN 🚀", style="bold white on blue", justify="center")
    subtitle = Text("Herramientas de Python", style="italic cyan", justify="center")
    console.print(Panel(title, subtitle=subtitle, border_style="blue", padding=(1, 2)))

def print_error(msg: str) -> None:
    """Standardized error printing."""
    console.print(f"[bold red]Error:[/bold red] {msg}")

def print_success(msg: str) -> None:
    """Standardized success printing."""
    console.print(f"[bold green]Éxito:[/bold green] {msg}")

def print_warning(msg: str) -> None:
    """Standardized warning printing."""
    console.print(f"[bold yellow]Advertencia:[/bold yellow] {msg}")

def print_step(msg: str) -> None:
    """Standardized step/info printing."""
    console.print(f"[cyan]{msg}[/cyan]")

# ─── Imports ───
import os
import sys
import subprocess
import logging
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import questionary

# ─── Logging ───
logging.basicConfig(
    filename="automation_tools.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─── Rutas ───
ROOT_DIR  = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(ROOT_DIR, "tools")
CONFIG_FILE = os.path.join(ROOT_DIR, "productos_a_monitorear.json")

console = Console()


# ─── Helpers ───
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_banner():
    clear_screen()
    title    = Text("🚀 KIT DE AUTOMATIZACIÓN 🚀", style="bold white on blue", justify="center")
    subtitle = Text("Herramientas de Python", style="italic cyan", justify="center")
    console.print(Panel(title, subtitle=subtitle, border_style="blue", padding=(1, 2)))


def run_script(script_name: str, args: list = None):
    """Lanza un script desde la carpeta /tools via subprocess."""
    args = args or []
    script_path = os.path.join(TOOLS_DIR, script_name)

    if not os.path.exists(script_path):
        console.print(f"[bold red]Error:[/bold red] No se encuentra tools/{script_name}")
        logging.error(f"Script no encontrado: {script_path}")
        questionary.press_any_key_to_continue().ask()
        return

    cmd = [sys.executable, script_path] + args
    logging.info(f"Ejecutando: {' '.join(cmd)}")

    console.print(f"[yellow]Ejecutando: tools/{script_name}...[/yellow]")
    console.print("-" * 50)

    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        console.print("\n[bold red]Ejecución interrumpida.[/bold red]")
        logging.warning(f"Interrumpido por usuario: {script_name}")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        logging.error(f"Error ejecutando {script_name}: {e}")

    console.print("-" * 50)
    questionary.press_any_key_to_continue().ask()


# ─── Submenús ───
def menu_renombrador():
    print_banner()
    console.print("[bold green]Renombrador Masivo[/bold green]")

    directory = questionary.path("¿Qué carpeta quieres procesar?").ask()
    if not directory:
        return

    mode = questionary.select(
        "¿Qué modo quieres usar?",
        choices=[
            "Patrón (ej: foto_001.jpg)",
            "Fecha (ej: 2024-01-01_archivo.jpg)",
            "Reemplazo (ej: borrar 'copia de')",
        ],
    ).ask()

    args = [directory]

    if "Patrón" in mode:
        pattern = questionary.text("Ingresa el patrón (ej: 'viaje_{:03d}'):").ask()
        if not pattern:
            return
        args.extend(["--mode", "patron", "--pattern", pattern])

    elif "Fecha" in mode:
        keep = questionary.confirm("¿Mantener nombre original?").ask()
        args.extend(["--mode", "fecha"])
        if keep:
            args.append("--keep-name")

    elif "Reemplazo" in mode:
        old = questionary.text("Texto a buscar:").ask()
        new = questionary.text("Texto nuevo (deja vacío para borrar):").ask()
        if not old:
            return
        args.extend(["--mode", "reemplazo", "--old-text", old, "--new-text", new or ""])

    ext = questionary.text("Filtrar por extensión (opcional, ej: .jpg):").ask()
    if ext:
        args.extend(["--ext", ext])

    apply_changes = questionary.confirm("¿Aplicar cambios reales? (No = Solo simulación)").ask()
    if apply_changes:
        args.append("--aplicar")

    run_script("renombrador_masivo.py", args)


def menu_monitor():
    print_banner()
    console.print("[bold green]Monitor de Precios[/bold green]")

    action = questionary.select(
        "¿Qué quieres hacer?",
        choices=[
            "Ejecutar un chequeo ahora mismo",
            "Iniciar monitoreo continuo (cada hora)",
            "Ver configuración (archivo)",
        ],
    ).ask()

    if "ahora" in action:
        run_script("monitor_precios.py", ["--now"])
    elif "continuo" in action:
        run_script("monitor_precios.py")
    elif "configuración" in action:
        console.print(f"Archivo de configuración: [link=file://{CONFIG_FILE}]{CONFIG_FILE}[/link]")
        questionary.press_any_key_to_continue().ask()


def menu_resumidor():
    print_banner()
    console.print("[bold green]Resumidor de Documentos[/bold green]")

    filepath = questionary.path("Selecciona el archivo PDF o TXT:").ask()
    if not filepath:
        return

    args = [filepath]

    if not os.environ.get("GOOGLE_API_KEY"):
        console.print("[yellow]No se detectó GOOGLE_API_KEY en variables de entorno.[/yellow]")
        key_input = questionary.password(
            "Ingresa tu Google API Key (opcional si la configuras en .env):"
        ).ask()
        if key_input:
            args.extend(["--key", key_input])

    if questionary.confirm("¿Guardar resumen en archivo?").ask():
        out_path = os.path.splitext(filepath)[0] + "_resumen.txt"
        args.extend(["--out", out_path])
        console.print(f"[dim]Se guardará en: {out_path}[/dim]")

    run_script("resumidor.py", args)


def menu_convertir():
    print_banner()
    console.print("[bold green]Convertidor de Imágenes[/bold green]")

    img_path = questionary.path("Selecciona la imagen o carpeta a convertir:").ask()
    if not img_path:
        return

    fmt = questionary.select(
        "Selecciona el formato de salida:",
        choices=["png", "jpg", "webp", "tiff", "bmp", "gif"],
    ).ask()
    if fmt:
        run_script("convertir_imagen.py", [img_path, fmt])


def menu_convertir_pdf():
    print_banner()
    console.print("[bold green]Convertir a PDF[/bold green]")

    filepath = questionary.path("Selecciona el archivo a convertir (ej: .docx, .odt, .pptx):").ask()
    if not filepath:
        return

    run_script("convertor_pdf.py", [filepath])


def menu_traductor():
    print_banner()
    console.print("[bold green]Traductor de Archivos[/bold green]")

    filepath = questionary.path("Selecciona el archivo a traducir:").ask()
    if not filepath:
        return

    lang = questionary.select(
        "Idioma destino:",
        choices=["Ingles", "Espanol", "Frances", "Portugues", "Aleman", "Italiano", "Otro"],
    ).ask()
    if not lang:
        return

    if lang == "Otro":
        lang = questionary.text("Escribe el idioma destino:").ask()
        if not lang:
            return

    args = [filepath, "--lang", lang.lower()]

    if not os.environ.get("GOOGLE_API_KEY"):
        console.print("[yellow]No se detecto GOOGLE_API_KEY en variables de entorno.[/yellow]")
        key_input = questionary.password(
            "Ingresa tu Google API Key (opcional si la configuras en .env):"
        ).ask()
        if key_input:
            args.extend(["--key", key_input])

    if questionary.confirm("Guardar traduccion en archivo?").ask():
        base = os.path.splitext(filepath)[0]
        ext = os.path.splitext(filepath)[1]
        out_path = f"{base}_{lang.lower()}{ext}"
        args.extend(["--out", out_path])
        console.print(f"[dim]Se guardara en: {out_path}[/dim]")

    run_script("traductor.py", args)


# ─── Menú principal ───
def main_menu():
    while True:
        print_banner()

        choice = questionary.select(
            "Selecciona una herramienta:",
            choices=[
                "1. Renombrador Masivo",
                "2. Monitor de Precios",
                "3. Resumidor con IA",
                "4. Organizar Descargas",
                "5. Convertir Imagen",
                "6. Convertir a PDF",
                "7. Traductor de Archivos",
                "8. Salir",
            ],
            use_indicator=True,
        ).ask()

        if choice is None or "Salir" in choice:
            console.print("[bold blue]¡Hasta luego![/bold blue] 👋")
            break

        actions = {
            "Renombrador": menu_renombrador,
            "Monitor":     menu_monitor,
            "Resumidor":   menu_resumidor,
            "Convertir Imagen": menu_convertir,
            "Convertir a PDF":  menu_convertir_pdf,
            "Traductor":        menu_traductor,
            "Organizar":        lambda: run_script("organizar_descargas.py"),
        }

        for key, action in actions.items():
            if key in choice:
                action()
                break


# ─── Entry point ───
if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nSaliendo...")
    except Exception as e:
        console.print(f"[bold red]Error fatal:[/bold red] {e}")
        logging.critical(f"Error fatal en main_menu: {e}")

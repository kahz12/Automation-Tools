import os
import sys
import subprocess
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.layout import Layout
import questionary

console = Console()

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    clear_screen()
    
    title = Text("🚀 KIT DE AUTOMATIZACIÓN 🚀", style="bold white on blue", justify="center")
    
    subtitle = Text("Herramientas de Python", style="italic cyan", justify="center")
    
    console.print(Panel(
        title,
        subtitle=subtitle,
        border_style="blue",
        padding=(1, 2)
    ))

def run_script(script_name, args=[]):
    script_path = os.path.join(TOOLS_DIR, script_name)
    if not os.path.exists(script_path):
        console.print(f"[bold red]Error:[/bold red] No se encuentra {script_name}")
        questionary.press_any_key_to_continue().ask()
        return

    cmd = [sys.executable, script_path] + args
    
    console.print(f"[yellow]Ejecutando: {script_name}...[/yellow]")
    print("-" * 50)
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        console.print("\n[bold red]Ejecución interrumpida.[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
    
    print("-" * 50)
    questionary.press_any_key_to_continue().ask()

def menu_renombrador():
    print_banner()
    console.print("[bold green]Renombrador Masivo[/bold green]")
    
    directory = questionary.path("¿Qué carpeta quieres procesar?").ask()
    if not directory: return

    mode = questionary.select(
        "¿Qué modo quieres usar?",
        choices=[
            "Patrón (ej: foto_001.jpg)",
            "Fecha (ej: 2024-01-01_archivo.jpg)",
            "Reemplazo (ej: borrar 'copia de')",
        ]
    ).ask()

    args = [directory]

    if "Patrón" in mode:
        pattern = questionary.text("Ingresa el patrón (ej: 'viaje_{:03d}'):").ask()
        if not pattern: return
        args.extend(["--mode", "patron", "--pattern", pattern])
    elif "Fecha" in mode:
        keep = questionary.confirm("¿Mantener nombre original?").ask()
        args.extend(["--mode", "fecha"])
        if keep: args.append("--keep-name")
    elif "Reemplazo" in mode:
        old = questionary.text("Texto a buscar:").ask()
        new = questionary.text("Texto nuevo (deja vacío para borrar):").ask()
        if not old: return
        args.extend(["--mode", "reemplazo", "--old-text", old, "--new-text", new])

    ext = questionary.text("Filtrar por extensión (opcional, ej: .jpg):").ask()
    if ext: args.extend(["--ext", ext])

    apply = questionary.confirm("¿Aplicar cambios reales? (No = Solo simulación)").ask()
    if apply: args.append("--aplicar")

    run_script("renombrador_masivo.py", args)

def menu_monitor():
    print_banner()
    console.print("[bold green]Monitor de Precios[/bold green]")
    
    action = questionary.select(
        "¿Qué quieres hacer?",
        choices=[
            "Ejecutar un chequeo ahora mismo",
            "Iniciar monitoreo continuo (cada hora)",
            "Ver configuración (archivo)"
        ]
    ).ask()

    if "ahora" in action:
        run_script("monitor_precios.py", ["--now"])
    elif "continuo" in action:
        run_script("monitor_precios.py")
    elif "configuración" in action:
        config_path = os.path.join(TOOLS_DIR, "productos_a_monitorear.json")
        console.print(f"Archivo de configuración: [link=file://{config_path}]{config_path}[/link]")
        questionary.press_any_key_to_continue().ask()

def menu_resumidor():
    print_banner()
    console.print("[bold green]Resumidor de Documentos[/bold green]")
    
    filepath = questionary.path("Selecciona el archivo PDF o TXT:").ask()
    if not filepath: return
    
    key = os.environ.get("GOOGLE_API_KEY")
    args = [filepath]
    
    if not key:
        console.print("[yellow]No se detectó GOOGLE_API_KEY en variables de entorno.[/yellow]")
        key_input = questionary.password("Ingresa tu Google API Key (opcional si la configuras en .env):").ask()
        if key_input:
            args.extend(["--key", key_input])
    
    save = questionary.confirm("¿Guardar resumen en archivo?").ask()
    if save:
        out_path = os.path.splitext(filepath)[0] + "_resumen.txt"
        args.extend(["--out", out_path])

    run_script("resumidor.py", args)

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
                "6. Salir"
            ],
            use_indicator=True
        ).ask()

        if choice is None or "Salir" in choice:
            console.print("[bold blue]¡Hasta luego![/bold blue] 👋")
            break
        
        if "Renombrador" in choice:
            menu_renombrador()
        elif "Monitor" in choice:
            menu_monitor()
        elif "Resumidor" in choice:
            menu_resumidor()
        elif "Organizar Descargas" in choice:
            console.print("[yellow]Este script no tiene opciones interactivas, ejecutando directamente...[/yellow]")
            run_script("organizar_descargas.py")
        elif "Convertir Imagen" in choice:
            console.print("[bold green]Convertidor de Imágenes[/bold green]")
            img_path = questionary.path("Selecciona la imagen o carpeta a convertir:").ask()
            if img_path:
                fmt = questionary.select(
                    "Selecciona el formato de salida:",
                    choices=["png", "jpg", "webp", "pdf", "tiff", "bmp"]
                ).ask()
                if fmt:
                    run_script("convertir_imagen.py", [img_path, fmt])

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nSaliendo...")
    except Exception as e:
        console.print(f"[bold red]Error fatal:[/bold red] {e}")

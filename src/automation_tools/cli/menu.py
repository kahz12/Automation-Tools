import os
import argparse
from typing import Optional

import questionary
from rich.console import Console

from automation_tools.core.logger import console, print_banner, print_error, print_success, print_warning
from automation_tools.core.config import load_environment, get_env_var, get_project_root

# Import all tools
from automation_tools.tools import (
    renamer,
    monitor,
    summarizer,
    converter,
    translator,
    duplicate_finder,
    youtube_downloader,
    readme_generator,
    metadata,
    organizer
)

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def error_boundary(func):
    """Decorator to catch exceptions gracefully in menu selections."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except KeyboardInterrupt:
            console.print("\n[bold red]Ejecución interrumpida.[/bold red]")
        except Exception as e:
            print_error(f"Ocurrió un error inesperado: {e}")
        finally:
            console.print("-" * 50)
            questionary.press_any_key_to_continue().ask()
    return wrapper

@error_boundary
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
    
    if not mode: return

    mode_id = "patron" if "Patrón" in mode else "fecha" if "Fecha" in mode else "reemplazo"
    pattern, old_text, new_text = None, None, ""
    keep = False

    if mode_id == "patron":
        pattern = questionary.text("Ingresa el patrón (ej: 'viaje_{:03d}'):").ask()
        if not pattern: return
    elif mode_id == "fecha":
        keep = questionary.confirm("¿Mantener nombre original?").ask()
    elif mode_id == "reemplazo":
        old_text = questionary.text("Texto a buscar:").ask()
        if not old_text: return
        new_text = questionary.text("Texto nuevo (deja vacío para borrar):").ask()

    ext = questionary.text("Filtrar por extensión (opcional, ej: .jpg):").ask()
    apply_changes = questionary.confirm("¿Aplicar cambios reales? (No = Solo simulación)").ask()

    renamer.run_massive_rename(
        directory=directory,
        mode=mode_id,
        apply_changes=apply_changes,
        ext_filter=ext,
        pattern=pattern,
        keep_name=keep,
        old_text=old_text,
        new_text=new_text
    )

@error_boundary
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
    
    if not action: return

    if "ahora" in action:
        monitor.run_price_monitor_job()
    elif "continuo" in action:
        monitor.run_continuous_monitor()
    elif "configuración" in action:
        config_path = os.path.join(get_project_root(), "productos_a_monitorear.json")
        console.print(f"Archivo de configuración: [link=file://{config_path}]{config_path}[/link]")

def check_api_key() -> Optional[str]:
    api_key = get_env_var("GOOGLE_API_KEY")
    if not api_key:
        print_warning("No se detectó GOOGLE_API_KEY en variables de entorno.")
        api_key = questionary.password("Ingresa tu Google API Key:").ask()
    return api_key

@error_boundary
def menu_resumidor():
    print_banner()
    console.print("[bold green]Resumidor de Documentos[/bold green]")

    filepath = questionary.path("Selecciona el archivo PDF o TXT:").ask()
    if not filepath: return

    api_key = check_api_key()
    if not api_key: return

    out_path = None
    if questionary.confirm("¿Guardar resumen en archivo?").ask():
        out_path = os.path.splitext(filepath)[0] + "_resumen.txt"
        console.print(f"[dim]Se guardará en: {out_path}[/dim]")

    summarizer.run_summarizer(filepath=filepath, api_key=api_key, out_path=out_path)

@error_boundary
def menu_convertir():
    print_banner()
    console.print("[bold green]Convertidor de Imágenes[/bold green]")

    img_path = questionary.path("Selecciona la imagen o carpeta a convertir:").ask()
    if not img_path: return

    fmt = questionary.select(
        "Selecciona el formato de salida:",
        choices=["png", "jpg", "webp", "tiff", "bmp", "gif"],
    ).ask()
    
    if fmt:
        converter.run_image_converter(img_path, fmt)

@error_boundary
def menu_convertir_pdf():
    print_banner()
    console.print("[bold green]Convertir a PDF[/bold green]")

    filepath = questionary.path("Selecciona el archivo a convertir (ej: .docx, .odt, .pptx):").ask()
    if filepath:
        converter.run_pdf_converter(filepath)

@error_boundary
def menu_traductor():
    print_banner()
    console.print("[bold green]Traductor de Archivos[/bold green]")

    filepath = questionary.path("Selecciona el archivo a traducir:").ask()
    if not filepath: return

    lang = questionary.select(
        "Idioma destino:",
        choices=["Ingles", "Espanol", "Frances", "Portugues", "Aleman", "Italiano", "Otro"],
    ).ask()
    if not lang: return

    if lang == "Otro":
        lang = questionary.text("Escribe el idioma destino:").ask()
        if not lang: return

    api_key = check_api_key()
    if not api_key: return

    out_path = None
    if questionary.confirm("¿Guardar traducción en archivo?").ask():
        base = os.path.splitext(filepath)[0]
        ext = os.path.splitext(filepath)[1]
        out_path = f"{base}_{lang.lower()}{ext}"
        console.print(f"[dim]Se guardará en: {out_path}[/dim]")

    translator.run_translator(filepath=filepath, target_lang=lang.lower(), api_key=api_key, out_path=out_path)

@error_boundary
def menu_detector_duplicados():
    print_banner()
    console.print("[bold green]Detector de Duplicados[/bold green]")
    directory = questionary.path("¿Qué carpeta quieres escanear?").ask()
    if not directory: return
    
    delete = questionary.confirm("¿Eliminar duplicados automáticamente (conservando el original)?").ask()
    duplicate_finder.run_duplicate_finder(directory, auto_delete=delete)

@error_boundary
def menu_descargador_youtube():
    print_banner()
    console.print("[bold green]Descargador de YouTube[/bold green]")
    url = questionary.text("URL del video:").ask()
    if not url: return
    
    mode = questionary.select(
        "¿Qué deseas descargar?",
        choices=["Video (MP4 alta calidad)", "Audio (MP3)"]
    ).ask()
    if not mode: return
    
    mode_id = "audio" if "Audio" in mode else "video"
    youtube_downloader.run_youtube_downloader(url, mode_id)

@error_boundary
def menu_generador_readme():
    print_banner()
    console.print("[bold green]Generador de README con IA[/bold green]")
    directory = questionary.path("¿Carpeta del proyecto a analizar?").ask()
    if not directory: return
    
    api_key = check_api_key()
    if not api_key: return
    
    readme_generator.run_readme_generator(directory, api_key)

@error_boundary
def menu_extractor_metadata():
    print_banner()
    console.print("[bold green]Extractor de Metadatos[/bold green]")
    filepath = questionary.path("¿Archivo a escrutar (PDF, JPG, PNG, etc)?").ask()
    if filepath:
        metadata.run_metadata_extractor(filepath)

@error_boundary
def menu_organizar_descargas():
    print_banner()
    console.print("[bold green]Organizar Descargas[/bold green]")
    if questionary.confirm("¿Organizar la carpeta de descargas del sistema ahora?").ask():
        organizer.run_download_organizer()

def main_menu():
    load_environment()
    
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
                "8. Detector de Duplicados",
                "9. Descargar de YouTube",
                "10. Generador de README (IA)",
                "11. Extractor de Metadata",
                "12. Salir",
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
            "Detector":         menu_detector_duplicados,
            "YouTube":          menu_descargador_youtube,
            "Generador":        menu_generador_readme,
            "Extractor":        menu_extractor_metadata,
            "Organizar":        menu_organizar_descargas,
        }

        for key, action in actions.items():
            if key in choice:
                action()
                break

if __name__ == "__main__":
    main_menu()

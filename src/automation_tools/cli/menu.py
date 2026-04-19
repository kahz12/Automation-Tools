import os
from typing import Optional

import questionary
from questionary import Choice, Separator

from automation_tools.core.logger import (
    console,
    print_banner,
    print_error,
    print_footer_tip,
    print_rule,
    print_section,
    print_success,
    print_warning,
    question_style,
)
from automation_tools.core.config import load_environment, get_env_var, get_project_root

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
    organizer,
    password_generator,
    space_cleaner,
)


# ---------------------------------------------------------------------------
# Shared questionary helpers (every prompt uses the same palette/style).
# ---------------------------------------------------------------------------
QSTYLE = question_style()


def ask_select(message, choices, **kwargs):
    return questionary.select(message, choices=choices, style=QSTYLE, **kwargs).ask()


def ask_text(message, **kwargs):
    return questionary.text(message, style=QSTYLE, **kwargs).ask()


def ask_path(message, **kwargs):
    return questionary.path(message, style=QSTYLE, **kwargs).ask()


def ask_confirm(message, default=False, **kwargs):
    return questionary.confirm(message, default=default, style=QSTYLE, **kwargs).ask()


def ask_password(message, **kwargs):
    return questionary.password(message, style=QSTYLE, **kwargs).ask()


def press_any_key():
    print_rule()
    questionary.press_any_key_to_continue(style=QSTYLE).ask()


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
            press_any_key()
    return wrapper


# ---------------------------------------------------------------------------
# Tool screens
# ---------------------------------------------------------------------------
@error_boundary
def menu_renombrador():
    print_section("Renombrador Masivo", "Renombra lotes de archivos con patrones, fechas o reemplazos", "✂️")

    directory = ask_path("¿Qué carpeta quieres procesar?")
    if not directory:
        return

    mode = ask_select(
        "¿Qué modo quieres usar?",
        choices=[
            Choice("🔢  Patrón (ej: foto_001.jpg)", "patron"),
            Choice("📅  Fecha (ej: 2024-01-01_archivo.jpg)", "fecha"),
            Choice("🔁  Reemplazo de texto (ej: borrar 'copia de')", "reemplazo"),
        ],
    )
    if not mode:
        return

    pattern, old_text, new_text = None, None, ""
    keep = False

    if mode == "patron":
        print_footer_tip("Usa '{:03d}' para numeración con ceros a la izquierda (001, 002...)")
        pattern = ask_text("Ingresa el patrón (ej: 'viaje_{:03d}'):")
        if not pattern:
            return
    elif mode == "fecha":
        keep = ask_confirm("¿Mantener nombre original como sufijo?")
    elif mode == "reemplazo":
        old_text = ask_text("Texto a buscar:")
        if not old_text:
            return
        new_text = ask_text("Texto nuevo (deja vacío para borrar):")

    ext = ask_text("Filtrar por extensión (opcional, ej: .jpg):")
    apply_changes = ask_confirm("¿Aplicar cambios reales? (No = solo simulación)")

    renamer.run_massive_rename(
        directory=directory,
        mode=mode,
        apply_changes=apply_changes,
        ext_filter=ext,
        pattern=pattern,
        keep_name=keep,
        old_text=old_text,
        new_text=new_text,
    )


@error_boundary
def menu_monitor():
    print_section("Monitor de Precios", "Rastrea precios en MercadoLibre y Amazon", "💰")

    action = ask_select(
        "¿Qué quieres hacer?",
        choices=[
            Choice("⚡  Ejecutar un chequeo ahora mismo", "now"),
            Choice("🔁  Iniciar monitoreo continuo (cada hora)", "loop"),
            Choice("📝  Ver configuración (archivo)", "config"),
        ],
    )
    if not action:
        return

    if action == "now":
        monitor.run_price_monitor_job()
    elif action == "loop":
        monitor.run_continuous_monitor()
    elif action == "config":
        config_path = os.path.join(get_project_root(), "productos_a_monitorear.json")
        console.print(f"📄 Archivo de configuración: [link=file://{config_path}]{config_path}[/link]")


def check_api_key() -> Optional[str]:
    api_key = get_env_var("GOOGLE_API_KEY")
    if not api_key:
        print_warning("No se detectó GOOGLE_API_KEY en variables de entorno.")
        api_key = ask_password("Ingresa tu Google API Key:")
    return api_key


@error_boundary
def menu_resumidor():
    print_section("Resumidor con IA", "Genera un resumen ejecutivo de PDF o TXT con Gemini", "📝")

    filepath = ask_path("Selecciona el archivo PDF o TXT:")
    if not filepath:
        return

    api_key = check_api_key()
    if not api_key:
        return

    out_path = None
    if ask_confirm("¿Guardar resumen en archivo?"):
        out_path = os.path.splitext(filepath)[0] + "_resumen.txt"
        console.print(f"[dim]Se guardará en: {out_path}[/dim]")

    summarizer.run_summarizer(filepath=filepath, api_key=api_key, out_path=out_path)


@error_boundary
def menu_convertir():
    print_section("Convertidor de Imágenes", "Cambia de formato (png, jpg, webp, …)", "🖼️")

    img_path = ask_path("Selecciona la imagen o carpeta a convertir:")
    if not img_path:
        return

    fmt = ask_select(
        "Selecciona el formato de salida:",
        choices=["png", "jpg", "webp", "tiff", "bmp", "gif"],
    )
    if fmt:
        converter.run_image_converter(img_path, fmt)


@error_boundary
def menu_convertir_pdf():
    print_section("Convertir a PDF", "Transforma documentos Office a PDF con LibreOffice", "📄")

    filepath = ask_path("Selecciona el archivo a convertir (ej: .docx, .odt, .pptx):")
    if filepath:
        converter.run_pdf_converter(filepath)


@error_boundary
def menu_traductor():
    print_section("Traductor de Archivos", "Traduce texto, subtítulos o código con Gemini", "🌐")

    filepath = ask_path("Selecciona el archivo a traducir:")
    if not filepath:
        return

    lang = ask_select(
        "Idioma destino:",
        choices=["Ingles", "Espanol", "Frances", "Portugues", "Aleman", "Italiano", "Otro"],
    )
    if not lang:
        return

    if lang == "Otro":
        lang = ask_text("Escribe el idioma destino:")
        if not lang:
            return

    api_key = check_api_key()
    if not api_key:
        return

    out_path = None
    if ask_confirm("¿Guardar traducción en archivo?"):
        base = os.path.splitext(filepath)[0]
        ext = os.path.splitext(filepath)[1]
        out_path = f"{base}_{lang.lower()}{ext}"
        console.print(f"[dim]Se guardará en: {out_path}[/dim]")

    translator.run_translator(filepath=filepath, target_lang=lang.lower(), api_key=api_key, out_path=out_path)


@error_boundary
def menu_detector_duplicados():
    print_section("Detector de Duplicados", "Encuentra archivos idénticos por contenido (MD5)", "🧬")
    directory = ask_path("¿Qué carpeta quieres escanear?")
    if not directory:
        return

    delete = ask_confirm("¿Eliminar duplicados automáticamente (conservando el original)?")
    duplicate_finder.run_duplicate_finder(directory, auto_delete=delete)


@error_boundary
def menu_descargador_youtube():
    print_section("Descargador de YouTube", "Descarga videos y audios en máxima calidad", "📺")
    url = ask_text("URL del video:")
    if not url:
        return

    mode = ask_select(
        "¿Qué deseas descargar?",
        choices=[
            Choice("🎬  Video (MP4 alta calidad)", "video"),
            Choice("🎵  Audio (MP3)", "audio"),
        ],
    )
    if not mode:
        return

    youtube_downloader.run_youtube_downloader(url, mode)


@error_boundary
def menu_generador_readme():
    print_section("Generador de README (IA)", "Analiza un proyecto y redacta su README con Gemini", "📘")
    directory = ask_path("¿Carpeta del proyecto a analizar?")
    if not directory:
        return

    api_key = check_api_key()
    if not api_key:
        return

    readme_generator.run_readme_generator(directory, api_key)


@error_boundary
def menu_extractor_metadata():
    print_section("Extractor de Metadatos", "Revela EXIF de imágenes e info de PDFs", "🔎")
    filepath = ask_path("¿Archivo a escrutar (PDF, JPG, PNG, etc)?")
    if filepath:
        metadata.run_metadata_extractor(filepath)


@error_boundary
def menu_organizar_descargas():
    print_section("Organizar Descargas", "Mueve archivos de Downloads en subcarpetas por tipo", "📦")
    if ask_confirm("¿Organizar la carpeta de descargas del sistema ahora?", default=True):
        organizer.run_download_organizer()


@error_boundary
def menu_password_generator():
    print_section("Gestor de Contraseñas", "Genera contraseñas, frases y evalúa fortaleza", "🔐")

    action = ask_select(
        "¿Qué quieres hacer?",
        choices=[
            Choice("🎲  Generar contraseña segura", "secure"),
            Choice("🧠  Generar frase memorable", "passphrase"),
            Choice("🛡️   Evaluar fortaleza de contraseña", "strength"),
        ],
    )
    if not action:
        return

    if action == "secure":
        length_str = ask_text("Longitud de la contraseña:", default="16")
        if not length_str:
            return
        try:
            length = int(length_str)
            if length < 4:
                print_warning("Longitud mínima ajustada a 4.")
                length = 4
            elif length > 128:
                print_warning("Longitud máxima ajustada a 128.")
                length = 128
        except ValueError:
            print_error("Longitud no válida.")
            return

        use_special = ask_confirm("¿Incluir símbolos (!@#$%...)?", default=True)
        exclude_ambiguous = ask_confirm("¿Excluir ambiguos (I/l/1, O/0)?", default=False)

        count_str = ask_text("¿Cuántas generar?", default="5")
        count = min(max(int(count_str or "5"), 1), 20)

        password_generator.run_generate_password(
            length=length,
            use_special=use_special,
            exclude_ambiguous=exclude_ambiguous,
            count=count,
        )

    elif action == "passphrase":
        words_str = ask_text("¿Cuántas palabras?", default="4")
        num_words = min(max(int(words_str or "4"), 2), 10)

        separator = ask_select("Separador:", choices=["-", ".", "_", " "]) or "-"

        capitalize = ask_confirm("¿Capitalizar palabras?", default=True)
        add_number = ask_confirm("¿Agregar número al final?", default=True)
        add_special = ask_confirm("¿Agregar símbolo al final?", default=False)

        count_str = ask_text("¿Cuántas generar?", default="5")
        count = min(max(int(count_str or "5"), 1), 20)

        password_generator.run_generate_passphrase(
            num_words=num_words,
            separator=separator,
            capitalize=capitalize,
            add_number=add_number,
            add_special=add_special,
            count=count,
        )

    elif action == "strength":
        pwd = ask_password("Ingresa la contraseña a evaluar:")
        if pwd:
            password_generator.run_evaluate_strength(pwd)


@error_boundary
def menu_limpiador_espacio():
    print_section("Limpiador de Espacio", "Detecta caché, archivos grandes y antiguos (dry-run por defecto)", "🧹")

    directory = ask_path("¿Qué carpeta quieres analizar?")
    if not directory:
        return

    find_junk = ask_confirm(
        "¿Buscar caché/basura (__pycache__, node_modules, .DS_Store, etc.)?", default=True
    )

    find_large = ask_confirm("¿Buscar archivos grandes?", default=True)
    large_mb = space_cleaner.DEFAULT_LARGE_MB
    if find_large:
        raw = ask_text("Umbral de archivo grande (MB):", default=str(space_cleaner.DEFAULT_LARGE_MB))
        try:
            large_mb = max(1, int(raw or space_cleaner.DEFAULT_LARGE_MB))
        except ValueError:
            print_warning("Valor no válido, usando 100 MB.")

    find_old = ask_confirm("¿Buscar archivos antiguos?", default=True)
    old_days = space_cleaner.DEFAULT_OLD_DAYS
    if find_old:
        raw = ask_text(
            "Umbral de antigüedad (días desde la última modificación):",
            default=str(space_cleaner.DEFAULT_OLD_DAYS),
        )
        try:
            old_days = max(1, int(raw or space_cleaner.DEFAULT_OLD_DAYS))
        except ValueError:
            print_warning("Valor no válido, usando 365 días.")

    apply = ask_confirm("¿Aplicar eliminación? (No = solo simulación)", default=False)

    delete_all = False
    if apply:
        delete_all = ask_confirm(
            "¿Incluir archivos grandes/antiguos en la eliminación? (solo caché si respondes No)",
            default=False,
        )

    space_cleaner.run_space_cleaner(
        directory=directory,
        large_mb=large_mb,
        old_days=old_days,
        find_junk=find_junk,
        find_large=find_large,
        find_old=find_old,
        apply=apply,
        delete_large_and_old=delete_all,
    )


# ---------------------------------------------------------------------------
# Main menu — grouped by category with icons and separators.
# ---------------------------------------------------------------------------
MENU_ENTRIES = [
    ("📂  Archivos", [
        ("✂️   Renombrador Masivo",      menu_renombrador),
        ("📦  Organizar Descargas",      menu_organizar_descargas),
        ("🧬  Detector de Duplicados",   menu_detector_duplicados),
        ("🧹  Limpiador de Espacio",     menu_limpiador_espacio),
    ]),
    ("🔄  Conversión", [
        ("🖼️   Convertir Imagen",         menu_convertir),
        ("📄  Convertir a PDF",           menu_convertir_pdf),
    ]),
    ("🧠  IA (Gemini)", [
        ("📝  Resumidor de Documentos",   menu_resumidor),
        ("🌐  Traductor de Archivos",     menu_traductor),
        ("📘  Generador de README",       menu_generador_readme),
    ]),
    ("🌐  Web & Multimedia", [
        ("💰  Monitor de Precios",        menu_monitor),
        ("📺  Descargar de YouTube",      menu_descargador_youtube),
    ]),
    ("🔧  Utilidades", [
        ("🔎  Extractor de Metadatos",    menu_extractor_metadata),
        ("🔐  Gestor de Contraseñas",     menu_password_generator),
    ]),
]


def _build_menu_choices():
    choices = []
    for group_label, entries in MENU_ENTRIES:
        choices.append(Separator(f"── {group_label} ──"))
        for label, action in entries:
            choices.append(Choice(f"  {label}", value=action))
    choices.append(Separator(" "))
    choices.append(Choice("  🚪  Salir", value="exit"))
    return choices


def main_menu():
    load_environment()

    while True:
        print_banner()
        print_footer_tip("Usa ↑/↓ para navegar, Enter para seleccionar, Ctrl+C para cancelar.")
        console.print()

        selection = ask_select(
            "¿Qué quieres hacer hoy?",
            choices=_build_menu_choices(),
            use_indicator=True,
            qmark="▸",
        )

        if selection is None or selection == "exit":
            console.print()
            console.print("[bold #a78bfa]¡Hasta luego![/] 👋")
            break

        selection()


if __name__ == "__main__":
    main_menu()

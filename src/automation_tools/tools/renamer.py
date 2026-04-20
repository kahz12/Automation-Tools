import os
import re
import datetime
import argparse
from typing import Optional, List, Tuple

from automation_tools.core.logger import console, print_error, print_success, print_warning, print_step

try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def get_file_date(filepath: str) -> datetime.datetime:
    """Gets the original creation date of the file, prefering EXIF if available."""
    date_taken = None
    if HAS_PILLOW:
        try:
            with Image.open(filepath) as img:
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        if tag in ExifTags.TAGS and ExifTags.TAGS[tag] == 'DateTimeOriginal':
                            date_taken = datetime.datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                            break
        except Exception:
            pass 

    if not date_taken:
        timestamp = os.path.getmtime(filepath)
        date_taken = datetime.datetime.fromtimestamp(timestamp)
    
    return date_taken


def _build_pattern_regex(pattern: str) -> Optional[re.Pattern]:
    """Build a regex from a format pattern like 'viaje_{:03d}' that captures the numeric index."""
    placeholder_re = re.compile(r'\{[^}]*\}')
    if not placeholder_re.search(pattern):
        return None
    parts = placeholder_re.split(pattern)
    escaped = [re.escape(p) for p in parts]
    return re.compile(r'^' + r'(\d+)'.join(escaped) + r'$')


def _split_pattern_files(files: List[str], pattern: str) -> Tuple[List[str], List[str], int]:
    """Split files into (already_matching, to_rename) and return the max existing index."""
    regex = _build_pattern_regex(pattern)
    if regex is None:
        return [], files, 0

    matching: List[str] = []
    pending: List[str] = []
    max_index = 0
    for f in files:
        name, _ = os.path.splitext(f)
        m = regex.match(name)
        if m:
            try:
                max_index = max(max_index, int(m.group(1)))
                matching.append(f)
                continue
            except (ValueError, IndexError):
                pass
        pending.append(f)
    return matching, pending, max_index


def detect_existing_sequence(
    directory: str,
    pattern: str,
    ext_filter: Optional[str] = None,
) -> Tuple[int, int]:
    """Return (count, max_index) of files in `directory` already matching `pattern`."""
    if not pattern or not os.path.isdir(directory):
        return 0, 0
    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter.lower())]
    matching, _, max_index = _split_pattern_files(files, pattern)
    return len(matching), max_index


def detect_dominant_pattern(
    directory: str,
    ext_filter: Optional[str] = None,
    min_count: int = 2,
) -> Tuple[Optional[str], int, int]:
    """Auto-detect a dominant naming pattern like '<prefix><digits>'.

    Looks at file names (without extension) ending in digits, groups by
    (prefix, digit_width), and returns the most populated group as a
    format pattern, e.g. 'viaje_{:03d}'. Requires at least `min_count` files
    in the group.

    Returns (pattern, count, max_index) or (None, 0, 0) if no dominant pattern.
    """
    if not os.path.isdir(directory):
        return None, 0, 0

    files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter.lower())]

    trailing = re.compile(r'^(.*?)(\d+)$')
    groups: dict = {}
    for f in files:
        name, _ = os.path.splitext(f)
        m = trailing.match(name)
        if not m:
            continue
        prefix, digits = m.group(1), m.group(2)
        key = (prefix, len(digits))
        groups.setdefault(key, []).append(int(digits))

    if not groups:
        return None, 0, 0

    (prefix, width), indices = max(groups.items(), key=lambda kv: len(kv[1]))
    if len(indices) < min_count:
        return None, 0, 0

    pattern = f"{prefix}{{:0{width}d}}" if width > 1 else f"{prefix}{{}}"
    return pattern, len(indices), max(indices)


def generate_new_name(
    filename: str, 
    directory: str,
    mode: str,
    index: int = 0,
    pattern: Optional[str] = None,
    date_format: str = "%Y-%m-%d",
    keep_name: bool = False,
    old_text: Optional[str] = None,
    new_text: str = ""
) -> str:
    """Generates a new name based on the chosen mode."""
    name, ext = os.path.splitext(filename)
    
    if mode == 'patron':
        if not pattern:
            return filename
        try:
            new_name = pattern.format(index) + ext
        except ValueError:
             new_name = f"{pattern}_{index:03d}{ext}"
        return new_name

    elif mode == 'fecha':
        filepath = os.path.join(directory, filename)
        date = get_file_date(filepath)
        date_str = date.strftime(date_format)
        
        if keep_name:
            new_name = f"{date_str}_{name}{ext}"
        else:
            new_name = f"{date_str}_{index:03d}{ext}"
        return new_name

    elif mode == 'reemplazo':
        if not old_text:
            return filename
        new_base = name.replace(old_text, new_text)
        return new_base + ext

    return filename


def _auto_version_name(directory: str, desired: str, reserved: set) -> str:
    """Return `desired` or `name_1.ext`, `name_2.ext`... until free."""
    dst = os.path.join(directory, desired)
    if not os.path.exists(dst) and desired not in reserved:
        return desired
    base, ext = os.path.splitext(desired)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(os.path.join(directory, candidate)) and candidate not in reserved:
            return candidate
        i += 1


def run_massive_rename(
    directory: str,
    mode: str,
    apply_changes: bool = False,
    ext_filter: Optional[str] = None,
    pattern: Optional[str] = None,
    date_format: str = "%Y-%m-%d",
    keep_name: bool = False,
    old_text: Optional[str] = None,
    new_text: str = "",
    continue_sequence: Optional[bool] = None,
    auto_version: bool = True,
    preview: bool = False,
) -> None:
    """Core function to execute massive rename without argparse dependency.

    `continue_sequence`:
        - True  → si hay archivos ya en secuencia, saltarlos y continuar desde el siguiente índice.
        - False → ignorar la secuencia existente y renumerar desde 1.
        - None  → comportamiento por defecto (equivale a True).
    """

    if not os.path.isdir(directory):
        print_error(f"El directorio '{directory}' no existe.")
        return

    files = sorted([f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))])

    if ext_filter:
        files = [f for f in files if f.lower().endswith(ext_filter.lower())]

    if not files:
        print_warning("No se encontraron archivos para procesar.")
        return

    count_start = 1
    if mode == 'patron' and pattern:
        matching, pending, max_index = _split_pattern_files(files, pattern)
        if matching:
            if continue_sequence is False:
                console.print(
                    f"[dim]Detectados {len(matching)} archivo(s) ya en secuencia "
                    f"(índice máx: {max_index}). Reiniciando numeración desde 1.[/dim]"
                )
            else:
                console.print(
                    f"[dim]Detectados {len(matching)} archivo(s) ya en secuencia "
                    f"(índice máx: {max_index}). Continuando desde {max_index + 1}.[/dim]"
                )
                files = pending
                count_start = max_index + 1

    if not files:
        print_warning("No hay archivos nuevos para renombrar.")
        return

    print_step(f"Procesando {len(files)} archivos en '{directory}'...")
    print_step(f"Modo: {mode}")

    if not apply_changes:
        console.print("[yellow]MODO SIMULACIÓN (DRY-RUN): No se harán cambios reales.[/yellow]\n")

    # Build the full plan first (source → destination) to allow preview and collision handling.
    plan: List[Tuple[str, str]] = []
    reserved: set = set()
    count = count_start
    for filename in files:
        new_name = generate_new_name(
            filename=filename,
            directory=directory,
            mode=mode,
            index=count,
            pattern=pattern,
            date_format=date_format,
            keep_name=keep_name,
            old_text=old_text,
            new_text=new_text,
        )

        if new_name == filename:
            count += 1
            continue

        if os.path.exists(os.path.join(directory, new_name)) or new_name in reserved:
            if auto_version:
                versioned = _auto_version_name(directory, new_name, reserved)
                console.print(
                    f"[yellow][!][/yellow] '{new_name}' ya existe; versionado a '{versioned}'"
                )
                new_name = versioned
            else:
                console.print(
                    f"[bold red][!][/bold red] Conflicto: '{new_name}' ya existe. Saltando '{filename}'."
                )
                count += 1
                continue

        plan.append((filename, new_name))
        reserved.add(new_name)
        count += 1

    if not plan:
        print_warning("No hay cambios que aplicar.")
        return

    for src_name, dst_name in plan:
        console.print(f"'{src_name}' -> '{dst_name}'")

    if preview and apply_changes:
        try:
            import questionary
            if not questionary.confirm(
                f"¿Aplicar estos {len(plan)} renombres?", default=True
            ).ask():
                print_warning("Cancelado por el usuario. No se aplicó nada.")
                return
        except ImportError:
            pass

    if apply_changes:
        applied = 0
        for src_name, dst_name in plan:
            try:
                os.rename(os.path.join(directory, src_name), os.path.join(directory, dst_name))
                applied += 1
            except Exception as e:
                print_error(f"Error al renombrar '{src_name}': {e}")
        print_success(f"Renombrado completado. {applied}/{len(plan)} archivos.")
    else:
        console.print("\n[dim]Para aplicar estos cambios, ejecuta con apply_changes=True[/dim]")


def main():
    """CLI Entry point for standalone execution."""
    parser = argparse.ArgumentParser(description="Renombrador Masivo Inteligente de Archivos")
    
    parser.add_argument("directory", help="Directorio donde están los archivos")
    parser.add_argument("--mode", choices=['patron', 'fecha', 'reemplazo'], required=True, help="Modo de renombrado")
    parser.add_argument("--ext", help="Filtrar por extensión (ej: .jpg)")
    parser.add_argument("--aplicar", action="store_true", help="Aplicar los cambios reales")
    
    parser.add_argument("--pattern", help="Patrón para el nuevo nombre (ej: 'viaje_{:03d}')")
    parser.add_argument("--date-format", default="%Y-%m-%d", help="Formato de fecha (default: YYYY-MM-DD)")
    parser.add_argument("--keep-name", action="store_true", help="Mantener nombre original")
    parser.add_argument("--old-text", help="Texto a buscar para reemplazar")
    parser.add_argument("--new-text", default="", help="Texto nuevo")
    seq_group = parser.add_mutually_exclusive_group()
    seq_group.add_argument("--continue-sequence", dest="continue_sequence", action="store_true",
                           help="Continuar una secuencia ya existente desde el siguiente índice")
    seq_group.add_argument("--restart-sequence", dest="continue_sequence", action="store_false",
                           help="Ignorar la secuencia existente y renumerar desde 1")
    parser.set_defaults(continue_sequence=None)

    args = parser.parse_args()

    run_massive_rename(
        directory=args.directory,
        mode=args.mode,
        apply_changes=args.aplicar,
        ext_filter=args.ext,
        pattern=args.pattern,
        date_format=args.date_format,
        keep_name=args.keep_name,
        old_text=args.old_text,
        new_text=args.new_text,
        continue_sequence=args.continue_sequence,
    )

if __name__ == "__main__":
    main()

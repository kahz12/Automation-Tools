"""Shared command-line conventions.

The project grew a few tools independently, so equivalent options had
different names (``--out`` versus ``--output`` and, in places, Spanish-only
flags).  ``ArgumentParser`` below keeps every historical spelling while also
exposing a predictable English/Spanish alias for new scripts.
"""

from __future__ import annotations

import argparse
from typing import Any


# Aliases are intentionally option-only.  Positional arguments and subcommand
# names remain unchanged, which avoids ambiguity and preserves old scripts.
_OPTION_ALIASES: dict[str, tuple[str, ...]] = {
    "--out": ("--output", "--salida"),
    "--output": ("--out", "--salida"),
    "--dest": ("--destination", "--destino"),
    "--export": ("--exportar",),
    "--key": ("--api-key", "--clave"),
    "--provider": ("--proveedor",),
    "--model": ("--modelo",),
    "--apply": ("--aplicar",),
    "--delete": ("--borrar", "--eliminar"),
    "--exclude": ("--excluir",),
    "--hidden": ("--ocultos",),
    "--overwrite": ("--sobrescribir",),
    "--format": ("--formato",),
    "--quality": ("--calidad",),
    "--timeout": ("--tiempo-espera",),
    "--interval": ("--intervalo",),
    "--recursive": ("--recursivo",),
    "--no-recursive": ("--no-recursivo", "--sin-recursivo"),
    "--lang": ("--language", "--idioma"),
    "--language": ("--lang", "--idioma"),
    "--password": ("--contrasena", "--contraseña"),
    "--password-file": ("--archivo-contrasena", "--archivo-contraseña"),
    "--out-dir": ("--output-dir", "--directorio-salida"),
    "--from-pdf": ("--desde-pdf",),
    "--dpi": ("--resolucion",),
    "--show-unknown": ("--mostrar-desconocidos",),
    "--case-sensitive": ("--sensible-mayusculas",),
    "--regex": ("--expresion-regular",),
    "--keywords": ("--palabras-clave",),
    "--mode": ("--modo",),
    "--playlist": ("--lista",),
    "--no-resume": ("--no-reanudar", "--sin-reanudar"),
    "--page-size": ("--tamano-pagina", "--tamaño-pagina"),
    "--no-libreoffice": ("--sin-libreoffice",),
    "--exact": ("--exacto",),
    "--op": ("--operation", "--operacion", "--operación"),
    "--max-size": ("--max-size-px", "--tamano-maximo", "--tamaño-maximo"),
    "--scale": ("--escala",),
    "--position": ("--posicion", "--posición"),
    "--opacity": ("--opacidad",),
    "--pattern": ("--patron", "--patrón"),
    "--date-format": ("--formato-fecha",),
    "--keep-name": ("--conservar-nombre",),
    "--old-text": ("--texto-antiguo",),
    "--new-text": ("--texto-nuevo",),
    "--continue-sequence": ("--continuar-secuencia",),
    "--restart-sequence": ("--reiniciar-secuencia",),
    "--no-md5": ("--sin-md5",),
    "--seconds": ("--segundos",),
    "--all": ("--todos",),
    "--text": ("--texto",),
    "--no-images": ("--sin-imagenes", "--sin-imágenes"),
    "--save": ("--guardar",),
    "--no-junk": ("--sin-basura",),
    "--no-large": ("--sin-grandes",),
    "--no-old": ("--sin-antiguos",),
    "--large": ("--grandes",),
    "--old": ("--antiguos",),
    "--threshold": ("--umbral",),
    "--algorithm": ("--algoritmo",),
    "--ext": ("--extension", "--extensión"),
    "--clean-exif": ("--limpiar-exif",),
    "--count": ("--cantidad",),
    "--example": ("--ejemplo",),
    "--extra": ("--extras",),
    "--length": ("--longitud",),
    "--manifest": ("--manifiesto",),
    "--markdown": ("--marcado",),
    "--pages": ("--paginas", "--páginas"),
    "--remove-originals": ("--eliminar-originales",),
    "--shred": ("--triturar",),
    "--special": ("--especial",),
    "--spectrograms": ("--espectrogramas",),
    "--words": ("--palabras",),
    "--no-upper": ("--sin-mayusculas", "--sin-mayúsculas"),
    "--no-digits": ("--sin-digitos", "--sin-dígitos"),
    "--no-special": ("--sin-especiales",),
    "--no-ambiguous": ("--sin-ambiguos",),
    "--no-capitalize": ("--sin-mayuscula-inicial",),
    "--no-number": ("--sin-numero", "--sin-número"),
    "--separator": ("--separador",),
    "--offline": ("--sin-conexion", "--sin-conexión"),
    "--aplicar": ("--apply",),
    "--historial": ("--history",),
    "--now": ("--ahora",),
}


class ArgumentParser(argparse.ArgumentParser):
    """Argument parser that registers compatible bilingual option aliases."""

    def add_argument(self, *option_strings: str, **kwargs: Any) -> argparse.Action:
        expanded = list(option_strings)
        known = set(expanded)
        for option in option_strings:
            aliases = list(_OPTION_ALIASES.get(option, ()))
            # Also expand a historical/translated spelling when it is the
            # spelling declared by a tool (e.g. renamer's --aplicar).
            aliases.extend(
                canonical
                for canonical, names in _OPTION_ALIASES.items()
                if option in names
            )
            for alias in aliases:
                if alias not in known:
                    expanded.append(alias)
                    known.add(alias)
        return super().add_argument(*expanded, **kwargs)


def exit_code(result: Any) -> int:
    """Convert a tool operation result to the common success/error contract."""
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    return 0 if result is not False else 1


__all__ = ["ArgumentParser", "exit_code"]

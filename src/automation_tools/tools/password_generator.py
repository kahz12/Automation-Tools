import hashlib
import shutil
import string
import subprocess
import secrets
import math
import re
from typing import Optional, List, Dict, Any

from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.progress_bar import ProgressBar

from automation_tools.core.logger import console, print_error, print_success, print_step, print_warning


def check_pwned(password: str, timeout: float = 5.0) -> Optional[int]:
    """Check a password against Have I Been Pwned (k-anonymity).

    Returns the number of times the password was seen in breaches,
    0 if not seen, None if the check could not be performed.
    Only the first 5 chars of the SHA-1 hash are sent — the password
    itself never leaves the machine.
    """
    try:
        import requests
    except ImportError:
        return None

    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        resp = requests.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            timeout=timeout,
            headers={"Add-Padding": "true"},
        )
        if resp.status_code != 200:
            return None
        for line in resp.text.splitlines():
            tail, _, count = line.partition(":")
            if tail.strip().upper() == suffix:
                try:
                    return int(count.strip())
                except ValueError:
                    return None
        return 0
    except Exception:
        return None


def copy_to_clipboard(text: str) -> bool:
    """Best-effort copy to clipboard across platforms (Termux, Linux, macOS, Windows)."""
    candidates = [
        ["termux-clipboard-set"],
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],  # macOS
        ["clip"],    # Windows
    ]
    for cmd in candidates:
        if not shutil.which(cmd[0]):
            continue
        try:
            p = subprocess.run(cmd, input=text.encode("utf-8"), check=True, timeout=3)
            if p.returncode == 0:
                return True
        except Exception:
            continue
    return False

# ─── Lista de palabras para frases memorables ───

WORD_LIST = [
    "aceite", "acero", "agua", "aguila", "aire", "alfa", "alma", "alto",
    "ambar", "amor", "angel", "anillo", "arbol", "arco", "arena", "arma",
    "astro", "atlas", "aurora", "avion", "azul", "bahia", "baile", "banco",
    "banda", "barco", "barro", "base", "beso", "beta", "bicho", "blanco",
    "bloque", "boca", "bolsa", "bomba", "bosque", "bravo", "brazo", "brisa",
    "bronce", "bruja", "buho", "cable", "cabra", "cacao", "cadena", "cafe",
    "calma", "cama", "campo", "canal", "canto", "capa", "carbon", "cargo",
    "carne", "carta", "casa", "casco", "causa", "caza", "cedro", "celda",
    "celta", "censo", "cerdo", "cerro", "chapa", "charco", "chico", "chispa",
    "cielo", "cifra", "cinco", "circo", "cisne", "clase", "clave", "clima",
    "cobre", "cofre", "cola", "color", "cometa", "conde", "conejo", "copa",
    "coral", "coro", "corona", "corte", "costa", "crema", "cruz", "cubo",
    "cuento", "cuero", "cueva", "cumbre", "cuna", "curso", "curva", "dardo",
    "delfin", "delta", "diana", "disco", "donde", "doble", "dragon", "duende",
    "duque", "eco", "elite", "enigma", "enlace", "enano", "era", "escudo",
    "esfera", "espada", "estrella", "extra", "faro", "fauna", "feria",
    "fibra", "fiera", "fiesta", "filo", "filtro", "final", "firme", "flama",
    "flash", "flecha", "flora", "fondo", "forma", "forja", "frase", "frente",
    "fruta", "fuego", "fuente", "fuerza", "gallo", "garra", "gato", "genio",
    "globo", "golpe", "gorila", "gota", "gracia", "grano", "gris", "gruta",
    "guante", "guia", "hacha", "halcon", "halo", "hierba", "hierro", "hilo",
    "hogar", "hoja", "hongo", "honor", "huella", "hueso", "icono", "idea",
    "imagen", "indio", "isla", "jabon", "jaguar", "jardin", "jarra", "jaula",
    "joven", "juego", "jugo", "jungla", "junco", "lago", "lanza", "largo",
    "laser", "lava", "leche", "lente", "leon", "letra", "libre", "liebre",
    "limon", "linea", "lince", "lira", "llama", "llave", "lobo", "loma",
    "loto", "lucero", "lumbre", "luna", "macro", "madre", "magia", "mango",
    "manto", "mapa", "marca", "marea", "marte", "masa", "media", "mente",
    "mesa", "metal", "metro", "miel", "mina", "mirlo", "mito", "molde",
    "monte", "mora", "motor", "muela", "muro", "musgo", "nardo", "nave",
    "nexo", "nido", "ninja", "noble", "noche", "norte", "nota", "nube",
    "nudo", "oasis", "obra", "ocaso", "omega", "once", "opera", "orden",
    "oro", "oruga", "oso", "padre", "palma", "panda", "panel", "pardo",
    "parte", "pasta", "patio", "pavo", "paz", "perla", "perro", "peso",
    "pico", "piedra", "pieza", "pino", "pinta", "pirata", "pista", "placa",
    "plano", "plata", "playa", "plaza", "pluma", "poeta", "polvo", "porta",
    "poste", "pozo", "prado", "presa", "primo", "proa", "prueba", "pulso",
    "puma", "punta", "punto", "queso", "radio", "raiz", "rama", "rango",
    "rayo", "red", "reina", "reloj", "remo", "resto", "retro", "ritmo",
    "rival", "roble", "roca", "rocio", "rojo", "rombo", "rosa", "rostro",
    "rubi", "rueda", "runa", "ruta", "sabio", "sal", "salto", "salva",
    "samba", "sauce", "selva", "serie", "sierra", "sigma", "sirena", "sitio",
    "solar", "sombra", "soplo", "suelo", "surco", "tabla", "talon", "tango",
    "tarde", "tea", "techo", "tela", "templo", "tigre", "timbre", "tinta",
    "titan", "tonel", "toque", "torre", "tramo", "tren", "tribu", "trigo",
    "trozo", "trueno", "tumba", "turbo", "turno", "ultra", "umbral", "unica",
    "vaca", "vacio", "valle", "vapor", "vela", "venda", "verde", "verso",
    "viaje", "vida", "vidrio", "viento", "vincha", "vino", "viola", "virus",
    "vital", "vuelo", "yate", "yerba", "zafiro", "zarpa", "zona", "zorro",
]


# ─── Generador de Contraseñas ───

def generate_password(
    length: int = 16,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_special: bool = True,
    exclude_ambiguous: bool = False,
) -> Optional[str]:
    """Genera una contraseña aleatoria segura usando secrets."""
    charset = ""
    required = []

    ambiguous = "Il1O0o" if exclude_ambiguous else ""

    if use_lowercase:
        pool = string.ascii_lowercase
        if exclude_ambiguous:
            pool = "".join(c for c in pool if c not in ambiguous)
        charset += pool
        required.append(secrets.choice(pool))

    if use_uppercase:
        pool = string.ascii_uppercase
        if exclude_ambiguous:
            pool = "".join(c for c in pool if c not in ambiguous)
        charset += pool
        required.append(secrets.choice(pool))

    if use_digits:
        pool = string.digits
        if exclude_ambiguous:
            pool = "".join(c for c in pool if c not in ambiguous)
        charset += pool
        required.append(secrets.choice(pool))

    if use_special:
        pool = "!@#$%^&*()-_=+[]{}|;:,.<>?"
        charset += pool
        required.append(secrets.choice(pool))

    if not charset:
        print_error("Debes seleccionar al menos un tipo de caracter.")
        return None

    if length < len(required):
        length = len(required)

    remaining = length - len(required)
    password_chars = required + [secrets.choice(charset) for _ in range(remaining)]

    # Mezclar de forma segura
    result = list(password_chars)
    for i in range(len(result) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        result[i], result[j] = result[j], result[i]

    return "".join(result)


# ─── Generador de Frases Memorables ───

def generate_passphrase(
    num_words: int = 4,
    separator: str = "-",
    capitalize: bool = True,
    add_number: bool = True,
    add_special: bool = False,
) -> str:
    """Genera una frase memorable con palabras aleatorias."""
    words = [secrets.choice(WORD_LIST) for _ in range(num_words)]

    if capitalize:
        words = [w.capitalize() for w in words]

    phrase = separator.join(words)

    if add_number:
        phrase += separator + str(secrets.randbelow(900) + 100)

    if add_special:
        symbols = "!@#$%&*?"
        phrase += secrets.choice(symbols)

    return phrase


# ─── Evaluador de Fortaleza ───

COMMON_PASSWORDS = {
    "password", "123456", "12345678", "qwerty", "abc123", "letmein",
    "admin", "welcome", "monkey", "master", "dragon", "login",
    "password1", "123456789", "1234567890", "000000", "111111",
    "contraseña", "usuario", "acceso", "hola1234", "123abc",
}


def calculate_entropy(password: str) -> float:
    """Calcula la entropia en bits de una contraseña."""
    charset_size = 0
    if re.search(r"[a-z]", password):
        charset_size += 26
    if re.search(r"[A-Z]", password):
        charset_size += 26
    if re.search(r"\d", password):
        charset_size += 10
    if re.search(r"[^a-zA-Z0-9]", password):
        charset_size += 32

    if charset_size == 0:
        return 0.0
    return len(password) * math.log2(charset_size)


def evaluate_strength(password: str) -> Dict[str, Any]:
    """Evalua la fortaleza de una contraseña y devuelve un reporte detallado."""
    score = 0
    feedback: List[str] = []
    details: Dict[str, str] = {}
    length = len(password)

    # ── Longitud (0-35 pts) ──
    if length < 6:
        score += 5
        feedback.append("Muy corta — usa al menos 8 caracteres")
    elif length < 8:
        score += 12
        feedback.append("Corta — considera usar 12+ caracteres")
    elif length < 12:
        score += 22
    elif length < 16:
        score += 30
    else:
        score += 35
    details["Longitud"] = f"{length} caracteres"

    # ── Variedad de caracteres (0-40 pts) ──
    has_lower = bool(re.search(r"[a-z]", password))
    has_upper = bool(re.search(r"[A-Z]", password))
    has_digit = bool(re.search(r"\d", password))
    has_special = bool(re.search(r"[^a-zA-Z0-9]", password))

    variety = sum([has_lower, has_upper, has_digit, has_special])
    score += variety * 10

    types_present = []
    if has_lower:
        types_present.append("minusculas")
    if has_upper:
        types_present.append("MAYUSCULAS")
    if has_digit:
        types_present.append("numeros")
    if has_special:
        types_present.append("simbolos")
    details["Tipos de caracter"] = ", ".join(types_present) if types_present else "ninguno"

    if variety < 3:
        feedback.append("Agrega mas tipos de caracteres (mayusculas, numeros, simbolos)")

    # ── Entropia (0-25 pts) ──
    entropy = calculate_entropy(password)
    details["Entropia"] = f"{entropy:.1f} bits"

    if entropy >= 70:
        score += 25
    elif entropy >= 50:
        score += 18
    elif entropy >= 35:
        score += 10
    elif entropy >= 20:
        score += 5

    # ── Penalizaciones ──

    # Caracteres repetidos consecutivos (aaa, 111)
    if re.search(r"(.)\1{2,}", password):
        score -= 10
        feedback.append("Evita 3+ caracteres repetidos consecutivos")

    # Secuencias comunes
    sequences = [
        "abcdef", "123456", "qwerty", "asdfgh", "zxcvbn",
        "abcde", "12345", "qwert",
    ]
    pw_lower = password.lower()
    for seq in sequences:
        if seq in pw_lower or seq[::-1] in pw_lower:
            score -= 15
            feedback.append("Contiene secuencias predecibles")
            break

    # Contraseñas comunes
    if pw_lower in COMMON_PASSWORDS:
        score = 3
        feedback = ["Esta es una de las contraseñas mas comunes del mundo — cambiala inmediatamente"]

    # Solo un tipo de caracter y corta
    if variety == 1 and length < 10:
        score -= 10
        feedback.append("Usa una combinacion de tipos de caracteres")

    score = max(0, min(100, score))

    # ── Nivel ──
    if score >= 80:
        level, color, bar_color = "Muy fuerte", "bold green", "green"
    elif score >= 60:
        level, color, bar_color = "Fuerte", "green", "green"
    elif score >= 40:
        level, color, bar_color = "Moderada", "yellow", "yellow"
    elif score >= 20:
        level, color, bar_color = "Debil", "red", "red"
    else:
        level, color, bar_color = "Muy debil", "bold red", "red"

    if not feedback:
        feedback.append("Buena contraseña")

    return {
        "score": score,
        "level": level,
        "color": color,
        "bar_color": bar_color,
        "entropy": entropy,
        "details": details,
        "feedback": feedback,
    }


# ─── Funciones de visualizacion ───

def display_strength(result: Dict[str, Any]) -> None:
    """Muestra el resultado del analisis de fortaleza con Rich."""
    score = result["score"]
    filled = int(score / 100 * 30)
    empty = 30 - filled
    bar = f"[{result['bar_color']}]{'█' * filled}[/{result['bar_color']}][dim]{'░' * empty}[/dim]"

    console.print()
    console.print(Panel(
        f"{bar}  [{result['color']}]{score}/100 — {result['level']}[/{result['color']}]",
        title="Fortaleza",
        border_style="cyan",
        padding=(0, 2),
    ))

    # Detalles
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")

    for key, val in result["details"].items():
        table.add_row(key, val)

    console.print(table)

    # Recomendaciones
    if result["feedback"]:
        console.print()
        for tip in result["feedback"]:
            icon = "+" if "Buena" in tip else "!"
            style = "green" if "Buena" in tip else "yellow"
            console.print(f"  [{style}][{icon}][/{style}] {tip}")
    console.print()


def display_passwords(passwords: List[str], title: str = "Contraseñas Generadas") -> None:
    """Muestra una lista de contraseñas generadas con su fortaleza."""
    table = Table(title=title, title_style="bold magenta", border_style="cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Contraseña", style="bold white")
    table.add_column("Fortaleza", justify="center")
    table.add_column("Entropia", justify="right", style="dim")

    for i, pwd in enumerate(passwords, 1):
        result = evaluate_strength(pwd)
        score = result["score"]
        label = f"[{result['color']}]{result['level']}[/{result['color']}]"
        table.add_row(str(i), pwd, label, f"{result['entropy']:.0f} bits")

    console.print()
    console.print(table)
    console.print()


# ─── Funciones de entrada publica ───

def run_generate_password(
    length: int = 16,
    use_uppercase: bool = True,
    use_lowercase: bool = True,
    use_digits: bool = True,
    use_special: bool = True,
    exclude_ambiguous: bool = False,
    count: int = 5,
) -> None:
    """Genera y muestra multiples contraseñas seguras."""
    passwords = []
    for _ in range(count):
        pwd = generate_password(
            length=length,
            use_uppercase=use_uppercase,
            use_lowercase=use_lowercase,
            use_digits=use_digits,
            use_special=use_special,
            exclude_ambiguous=exclude_ambiguous,
        )
        if pwd:
            passwords.append(pwd)

    if passwords:
        display_passwords(passwords, title=f"Contraseñas ({length} caracteres)")
        print_success(f"{len(passwords)} contraseñas generadas.")


def run_generate_passphrase(
    num_words: int = 4,
    separator: str = "-",
    capitalize: bool = True,
    add_number: bool = True,
    add_special: bool = False,
    count: int = 5,
) -> None:
    """Genera y muestra multiples frases memorables."""
    phrases = []
    for _ in range(count):
        phrase = generate_passphrase(
            num_words=num_words,
            separator=separator,
            capitalize=capitalize,
            add_number=add_number,
            add_special=add_special,
        )
        phrases.append(phrase)

    if phrases:
        display_passwords(phrases, title=f"Frases Memorables ({num_words} palabras)")
        bits = num_words * math.log2(len(WORD_LIST))
        console.print(f"  [dim]Palabras en diccionario: {len(WORD_LIST)} | Entropia base: ~{bits:.0f} bits[/dim]\n")
        print_success(f"{len(phrases)} frases generadas.")


def run_evaluate_strength(password: str, check_breach: bool = True) -> None:
    """Evalua y muestra la fortaleza de una contraseña, opcionalmente consulta HIBP."""
    if not password:
        print_error("No se proporciono ninguna contraseña.")
        return

    result = evaluate_strength(password)
    display_strength(result)

    if check_breach:
        console.print("[dim]🔍 Consultando HaveIBeenPwned (k-anonymity, no se envía tu contraseña)…[/dim]")
        count = check_pwned(password)
        if count is None:
            print_warning("No se pudo verificar contra HaveIBeenPwned (sin red / sin requests).")
        elif count == 0:
            print_success("✓ No aparece en filtraciones conocidas.")
        else:
            print_error(
                f"⚠ Apareció en {count:,} filtraciones. ¡No uses esta contraseña!"
            )


def run_copy_password(password: str) -> None:
    """Copy a generated password to the clipboard."""
    if copy_to_clipboard(password):
        print_success("Contraseña copiada al portapapeles.")
    else:
        print_warning(
            "No se pudo copiar al portapapeles (instala 'termux-api', 'xclip', 'wl-copy', 'pbcopy' o 'clip')."
        )

import json
import time
import random
import sqlite3
import os
import re
import argparse
from datetime import datetime
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from automation_tools.core.logger import setup_logger, console, print_error, print_success, print_warning, print_step
from automation_tools.core.config import load_json_config, get_project_root

# Get logger specific to this tool
logger = setup_logger()

# ─── Rutas ───
DB_FILE = os.path.join(get_project_root(), "historial_precios.db")

# ─── Rate limiting por dominio ───
# Tiempo mínimo entre requests al mismo host (segundos).
MIN_INTERVAL_PER_HOST = 3.5
_LAST_REQUEST: Dict[str, float] = {}


def _throttle(url: str) -> None:
    """Ensure at least MIN_INTERVAL_PER_HOST seconds between requests per host."""
    host = urlparse(url).netloc.lower()
    now = time.monotonic()
    last = _LAST_REQUEST.get(host, 0.0)
    wait = MIN_INTERVAL_PER_HOST - (now - last)
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    _LAST_REQUEST[host] = time.monotonic()

# ─── User-Agents para rotación ───
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

# ─── Base de Datos — SQLite ───

def init_db() -> None:
    """Inicializa la base de datos y crea las tablas si no existen."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre      TEXT    NOT NULL,
            url         TEXT    NOT NULL,
            precio      REAL    NOT NULL,
            moneda      TEXT,
            fecha       TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            url         TEXT    PRIMARY KEY,
            disponible  INTEGER NOT NULL,
            fecha       TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def get_last_stock(url: str) -> Optional[bool]:
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("SELECT disponible FROM stock WHERE url = ?", (url,)).fetchone()
    conn.close()
    return bool(row[0]) if row else None


def save_stock(url: str, available: bool) -> None:
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO stock (url, disponible, fecha) VALUES (?, ?, ?)",
        (url, 1 if available else 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()


def guardar_precio(nombre: str, url: str, precio: float, moneda: str) -> None:
    """Guarda una lectura de precio en el historial."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO historial (nombre, url, precio, moneda, fecha) VALUES (?, ?, ?, ?, ?)",
        (nombre, url, precio, moneda, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    logger.info(f"Precio guardado: {nombre} → {precio} {moneda}")


def obtener_ultimo_precio(url: str) -> Optional[float]:
    """Devuelve el precio más reciente registrado para una URL."""
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT precio FROM historial WHERE url = ? ORDER BY fecha DESC LIMIT 1",
        (url,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def mostrar_historial() -> None:
    """Imprime el historial completo en consola."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT nombre, precio, moneda, fecha FROM historial ORDER BY fecha DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if not rows:
        print_warning("No hay historial registrado aún.")
        return

    console.print(f"\n[cyan]{'─'*60}[/cyan]")
    console.print(f"[bold]{'PRODUCTO':<25} {'PRECIO':>12}  {'FECHA'}[/bold]")
    console.print(f"[cyan]{'─'*60}[/cyan]")
    for nombre, precio, moneda, fecha in rows:
        precio_str = f"{precio:.2f} {moneda or ''}"
        console.print(f"{nombre:<25} {precio_str:>12}  {fecha}")
    console.print(f"[cyan]{'─'*60}[/cyan]\n")


# ─── Notificaciones — Telegram ───

def send_telegram(token: str, chat_id: str, message: str) -> None:
    """Envía un mensaje por Telegram."""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        logger.info(f"Telegram enviado: {message[:60]}...")
    except Exception as e:
        logger.error(f"Error Telegram: {e}")


def send_notification(title: str, message: str, settings: Dict[str, Any]) -> None:
    """Notificación por Telegram + consola."""
    full_msg = f"<b>{title}</b>\n{message}"
    console.print(f"\n[bold yellow]🔔 {title}:[/bold yellow] {message}")

    token   = settings.get("telegram_token", "")
    chat_id = settings.get("telegram_chat_id", "")
    send_telegram(token, chat_id, full_msg)


# ─── Utilidades de Precio ───

def clean_price(price_str: str, settings: Dict[str, Any]) -> Optional[float]:
    if not price_str:
        return None
    dec_sep = settings.get("decimal_separator", ".")
    tho_sep = settings.get("thousands_separator", ",")
    clean = re.sub(r"[^\d" + re.escape(dec_sep) + re.escape(tho_sep) + r"-]", "", price_str)
    clean = clean.replace(tho_sep, "").replace(dec_sep, ".")
    try:
        return float(clean)
    except ValueError:
        return None


def format_price(value: float, settings: Dict[str, Any]) -> str:
    currency = settings.get("currency_code", "$")
    return f"{value:,.2f} {currency}"


def get_headers() -> Dict[str, str]:
    """Headers con User-Agent rotativo para evitar bloqueos."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
    }


# ─── Scrapers ───

def check_mercadolibre_api(item_id: str, access_token: str) -> Optional[float]:
    """Consulta el precio vía API oficial de MercadoLibre."""
    try:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        url = f"https://api.mercadolibre.com/items/{item_id}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            price = data.get("price") or data.get("sale_price", {}).get("amount")
            return float(price) if price else None
    except Exception as e:
        logger.warning(f"ML API falló para {item_id}: {e}")
    return None


def extract_ml_item_id(url: str) -> Optional[str]:
    """Extrae el ID del item de una URL de MercadoLibre."""
    match = re.search(r"/(MC[A-Z]-\d+)", url, re.IGNORECASE)
    return match.group(1).replace("-", "") if match else None


def check_mercadolibre(url: str, soup: BeautifulSoup, settings: Dict[str, Any], access_token: str = "") -> Optional[float]:
    item_id = extract_ml_item_id(url)
    if item_id and access_token:
        price = check_mercadolibre_api(item_id, access_token)
        if price:
            logger.info(f"ML precio via API: {price}")
            return price

    selectors = [
        ("meta", {"itemprop": "price"}, "content"),
        ("span", {"class": "andes-money-amount__fraction"}, "text"),
        ("span", {"class": "price-tag-fraction"}, "text"),
    ]
    for tag, attrs, prop in selectors:
        el = soup.find(tag, attrs)
        if el:
            val = el.get("content") if prop == "content" else el.text
            price = clean_price(str(val), settings)
            if price:
                return price
    return None


def check_amazon(soup: BeautifulSoup, settings: Dict[str, Any]) -> Optional[float]:
    selectors = [
        "span.a-price-whole",
        ".a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "span[data-a-color='price'] .a-offscreen",
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            price = clean_price(el.text, settings)
            if price:
                return price
    return None


# ─── Logica de Alertas ───

def evaluar_alertas(product: Dict[str, Any], precio_actual: float, settings: Dict[str, Any]) -> None:
    nombre       = product.get("name", "Producto")
    url          = product.get("url", "")
    target_price = product.get("target_price")
    alert_drop   = product.get("alert_drop_percent")
    
    precio_fmt = format_price(precio_actual, settings)

    if target_price and precio_actual <= target_price:
        target_fmt = format_price(target_price, settings)
        send_notification(
            "🎯 ¡Precio objetivo alcanzado!",
            f"{nombre}\nPrecio actual: {precio_fmt}\nObjetivo: {target_fmt}\n🔗 {url}",
            settings,
        )

    if alert_drop:
        ultimo = obtener_ultimo_precio(url)
        if ultimo and ultimo > 0:
            variacion = ((ultimo - precio_actual) / ultimo) * 100
            if variacion >= alert_drop:
                send_notification(
                    f"📉 Bajó {variacion:.1f}% de precio",
                    f"{nombre}\nAntes: {format_price(ultimo, settings)}\nAhora: {precio_fmt}\n🔗 {url}",
                    settings,
                )
            elif variacion < 0:
                logger.info(f"{nombre} subió {abs(variacion):.1f}% → {precio_fmt}")


# ─── Check Principal ───

def detect_stock(url: str, soup: BeautifulSoup, price: Optional[float]) -> bool:
    """Heurística simple para disponibilidad: precio presente + sin señales de agotado."""
    page_text = soup.get_text(" ", strip=True).lower()
    signals_out = [
        "out of stock", "sin stock", "agotado", "no disponible",
        "currently unavailable", "producto no disponible", "sin existencias",
    ]
    if any(s in page_text for s in signals_out):
        return False
    return price is not None


def evaluar_stock(product: Dict[str, Any], disponible: bool, settings: Dict[str, Any]) -> None:
    """Notifica cambios de stock (disponible ↔ agotado) y persiste el estado."""
    url = product.get("url", "")
    nombre = product.get("name", "Producto")
    anterior = get_last_stock(url)
    if anterior is None:
        save_stock(url, disponible)
        return
    if anterior != disponible:
        if disponible:
            send_notification(
                "🟢 ¡Volvió a estar disponible!",
                f"{nombre}\n🔗 {url}",
                settings,
            )
        else:
            send_notification(
                "🔴 Se agotó",
                f"{nombre}\n🔗 {url}",
                settings,
            )
        save_stock(url, disponible)


def check_price(product: Dict[str, Any], settings: Dict[str, Any]) -> None:
    url    = product.get("url", "")
    nombre = product.get("name", "Producto")
    moneda = settings.get("currency_code", "$")

    console.print(f"  [dim]🔍 Verificando:[/dim] {nombre}...")

    try:
        _throttle(url)

        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200:
            console.print(f"     [yellow]⚠️  HTTP {response.status_code}[/yellow]")
            logger.warning(f"{nombre}: HTTP {response.status_code}")
            return

        soup         = BeautifulSoup(response.content, "html.parser")
        access_token = settings.get("ml_access_token", "")
        price        = None

        if "mercadolibre" in url:
            price = check_mercadolibre(url, soup, settings, access_token)
        elif "amazon" in url:
            price = check_amazon(soup, settings)

        disponible = detect_stock(url, soup, price)
        evaluar_stock(product, disponible, settings)

        if price is None:
            if not disponible:
                console.print(f"     [yellow]🚫 Producto no disponible[/yellow]")
            else:
                console.print(f"     [red]❌ No se pudo detectar el precio.[/red]")
            logger.warning(f"{nombre}: precio no detectado en {url}")
            return

        console.print(f"     [green]💰 Precio:[/green] {format_price(price, settings)}")

        guardar_precio(nombre, url, price, moneda)
        evaluar_alertas(product, price, settings)

    except requests.Timeout:
        console.print(f"     [red]⏱️  Timeout al acceder a {nombre}[/red]")
        logger.error(f"{nombre}: timeout")
    except Exception as e:
        console.print(f"     [red]❌ Error:[/red] {e}")
        logger.error(f"{nombre}: {e}")


def run_price_monitor_job() -> None:
    """Ejecuta una sola ronda del monitor de precios."""
    init_db()
    
    console.print(f"\n[cyan]{'═'*50}[/cyan]")
    console.print(f"  [bold]Chequeo:[/bold] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"[cyan]{'═'*50}[/cyan]")

    data     = load_json_config()
    products = data.get("products", [])
    settings = data.get("settings", {})

    if not products:
        print_warning("No hay productos configurados en productos_a_monitorear.json")
        return

    for product in products:
        check_price(product, settings)

    print_success(f"Chequeo completo — {len(products)} producto(s)\n")


def run_continuous_monitor(interval_minutes: int = 60) -> None:
    """Ejecuta el monitor en un loop continuo."""
    console.print(f"[bold green]🟢 Monitor iniciado.[/bold green] Verificando cada {interval_minutes} minuto(s)...")
    try:
        run_price_monitor_job()
        while True:
            time.sleep(interval_minutes * 60)
            run_price_monitor_job()
    except KeyboardInterrupt:
        console.print("\n[yellow]Monitor detenido por el usuario.[/yellow]")


def main():
    parser = argparse.ArgumentParser(description="Monitor de Precios v2.0")
    parser.add_argument("--now",       action="store_true", help="Ejecutar un chequeo inmediato")
    parser.add_argument("--historial", action="store_true", help="Ver historial de precios")
    parser.add_argument("--interval",  type=int, default=60, help="Intervalo en minutos (default: 60)")
    args = parser.parse_args()

    if args.historial:
        mostrar_historial()
    elif args.now:
        run_price_monitor_job()
    else:
        run_continuous_monitor(args.interval)

if __name__ == "__main__":
    main()

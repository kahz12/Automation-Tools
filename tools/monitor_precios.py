# ─── Imports ─── 
import json
import time
import random
import sqlite3
import logging
import os
import re
import argparse
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ─── Logging ───
logging.basicConfig(
    filename=os.path.join(os.path.dirname(__file__), "..", "automation_tools.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ─── Rutas ───
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "..", "productos_a_monitorear.json")
DB_FILE     = os.path.join(BASE_DIR, "..", "historial_precios.db")

# ─── User-Agents para rotación ───
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

DEFAULT_SETTINGS = {
    "currency_code": "$",
    "decimal_separator": ".",
    "thousands_separator": ",",
    "telegram_token": "",
    "telegram_chat_id": "",
    "ml_access_token": "",          # Token de MercadoLibre API oficial (opcional)
}


# ─── Base de Datos — SQLite ───

def init_db():
    """Inicializa la base de datos y crea la tabla si no existe."""
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
    conn.commit()
    conn.close()


def guardar_precio(nombre: str, url: str, precio: float, moneda: str):
    """Guarda una lectura de precio en el historial."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO historial (nombre, url, precio, moneda, fecha) VALUES (?, ?, ?, ?, ?)",
        (nombre, url, precio, moneda, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    logging.info(f"Precio guardado: {nombre} → {precio} {moneda}")


def obtener_ultimo_precio(url: str) -> float | None:
    """Devuelve el precio más reciente registrado para una URL."""
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute(
        "SELECT precio FROM historial WHERE url = ? ORDER BY fecha DESC LIMIT 1",
        (url,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def obtener_historial(url: str, limite: int = 10) -> list[dict]:
    """Devuelve las últimas N lecturas de precio para una URL."""
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT precio, moneda, fecha FROM historial WHERE url = ? ORDER BY fecha DESC LIMIT ?",
        (url, limite)
    ).fetchall()
    conn.close()
    return [{"precio": r[0], "moneda": r[1], "fecha": r[2]} for r in rows]


def mostrar_historial():
    """Imprime el historial completo en consola."""
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT nombre, precio, moneda, fecha FROM historial ORDER BY fecha DESC LIMIT 50"
    ).fetchall()
    conn.close()

    if not rows:
        print("No hay historial registrado aún.")
        return

    print(f"\n{'─'*60}")
    print(f"{'PRODUCTO':<25} {'PRECIO':>12}  {'FECHA'}")
    print(f"{'─'*60}")
    for nombre, precio, moneda, fecha in rows:
        print(f"{nombre:<25} {precio:>10.2f} {moneda or ''}  {fecha}")
    print(f"{'─'*60}\n")


# ─── Notificaciones — Telegram ───

def send_telegram(token: str, chat_id: str, message: str):
    """Envía un mensaje por Telegram."""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        logging.info(f"Telegram enviado: {message[:60]}...")
    except Exception as e:
        logging.error(f"Error Telegram: {e}")


def send_notification(title: str, message: str, settings: dict):
    """Notificación por Telegram + consola."""
    full_msg = f"<b>{title}</b>\n{message}"
    print(f"\n🔔 {title}: {message}")

    token   = settings.get("telegram_token", "")
    chat_id = settings.get("telegram_chat_id", "")
    send_telegram(token, chat_id, full_msg)



# ─── Config ───

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {"settings": DEFAULT_SETTINGS, "products": []}
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {"settings": DEFAULT_SETTINGS, "products": data}
        # Merge con defaults para keys faltantes
        settings = {**DEFAULT_SETTINGS, **data.get("settings", {})}
        data["settings"] = settings
        return data
    except Exception as e:
        logging.error(f"Error cargando config: {e}")
        return {"settings": DEFAULT_SETTINGS, "products": []}


# ─── Utilidades de Precio ───

def clean_price(price_str: str, settings: dict) -> float | None:
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


def format_price(value: float, settings: dict) -> str:
    currency = settings.get("currency_code", "$")
    return f"{value:,.2f} {currency}"


def get_headers() -> dict:
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

def check_mercadolibre_api(item_id: str, access_token: str) -> float | None:
    """
    Consulta el precio vía API oficial de MercadoLibre.
    Más confiable que scraping, no se rompe con cambios de HTML.
    item_id: ej. 'MCO-123456789'
    """
    try:
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        url = f"https://api.mercadolibre.com/items/{item_id}"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            price = data.get("price") or data.get("sale_price", {}).get("amount")
            return float(price) if price else None
    except Exception as e:
        logging.warning(f"ML API falló para {item_id}: {e}")
    return None


def extract_ml_item_id(url: str) -> str | None:
    """Extrae el ID del item de una URL de MercadoLibre. Ej: MCO-123456789"""
    match = re.search(r"/(MC[A-Z]-\d+)", url, re.IGNORECASE)
    return match.group(1).replace("-", "") if match else None


def check_mercadolibre(url: str, soup: BeautifulSoup, settings: dict, access_token: str = "") -> float | None:
    # Intentar primero con API oficial
    item_id = extract_ml_item_id(url)
    if item_id and access_token:
        price = check_mercadolibre_api(item_id, access_token)
        if price:
            logging.info(f"ML precio via API: {price}")
            return price

    # Fallback: scraping con múltiples selectores
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


def check_amazon(soup: BeautifulSoup, settings: dict) -> float | None:
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

def evaluar_alertas(product: dict, precio_actual: float, settings: dict):
    """
    Evalúa y dispara alertas por:
    - Precio objetivo alcanzado
    - Caída porcentual desde última lectura
    """
    nombre       = product.get("name", "Producto")
    url          = product.get("url", "")
    target_price = product.get("target_price")
    alert_drop   = product.get("alert_drop_percent")   # ej: 5 → alerta si baja 5%
    moneda       = settings.get("currency_code", "$")

    precio_fmt = format_price(precio_actual, settings)

    # Alerta 1: precio objetivo
    if target_price and precio_actual <= target_price:
        target_fmt = format_price(target_price, settings)
        send_notification(
            "🎯 ¡Precio objetivo alcanzado!",
            f"{nombre}\nPrecio actual: {precio_fmt}\nObjetivo: {target_fmt}\n🔗 {url}",
            settings,
        )

    # Alerta 2: caída porcentual
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
                logging.info(f"{nombre} subió {abs(variacion):.1f}% → {precio_fmt}")


# ─── Check Principal ───

def check_price(product: dict, settings: dict):
    url    = product.get("url", "")
    nombre = product.get("name", "Producto")
    moneda = settings.get("currency_code", "$")

    print(f"  🔍 Verificando: {nombre}...")

    try:
        # Delay aleatorio entre requests para no levantar sospechas
        time.sleep(random.uniform(1.5, 4.0))

        response = requests.get(url, headers=get_headers(), timeout=15)
        if response.status_code != 200:
            print(f"     ⚠️  HTTP {response.status_code}")
            logging.warning(f"{nombre}: HTTP {response.status_code}")
            return

        soup         = BeautifulSoup(response.content, "html.parser")
        access_token = settings.get("ml_access_token", "")
        price        = None

        if "mercadolibre" in url:
            price = check_mercadolibre(url, soup, settings, access_token)
        elif "amazon" in url:
            price = check_amazon(soup, settings)

        if price is None:
            print(f"     ❌ No se pudo detectar el precio.")
            logging.warning(f"{nombre}: precio no detectado en {url}")
            return

        print(f"     💰 Precio: {format_price(price, settings)}")

        # Guardar en historial
        guardar_precio(nombre, url, price, moneda)

        # Evaluar alertas
        evaluar_alertas(product, price, settings)

    except requests.Timeout:
        print(f"     ⏱️  Timeout al acceder a {nombre}")
        logging.error(f"{nombre}: timeout")
    except Exception as e:
        print(f"     ❌ Error: {e}")
        logging.error(f"{nombre}: {e}")


def job():
    print(f"\n{'═'*50}")
    print(f"  Chequeo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*50}")

    data     = load_config()
    products = data.get("products", [])
    settings = data.get("settings", DEFAULT_SETTINGS)

    if not products:
        print("  ⚠️  No hay productos configurados en productos_a_monitorear.json")
        return

    for product in products:
        check_price(product, settings)

    print(f"\n  ✅ Chequeo completo — {len(products)} producto(s)\n")


# ─── Entry Point ───

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor de Precios v2.0")
    parser.add_argument("--now",       action="store_true", help="Ejecutar un chequeo inmediato")
    parser.add_argument("--historial", action="store_true", help="Ver historial de precios")
    parser.add_argument("--interval",  type=int, default=60, help="Intervalo en minutos (default: 60)")
    args = parser.parse_args()

    init_db()

    if args.historial:
        mostrar_historial()

    elif args.now:
        job()

    else:
        print(f"🟢 Monitor iniciado. Verificando cada {args.interval} minuto(s)...")
        job()
        while True:
            time.sleep(args.interval * 60)
            job()
import json
import time
import requests
from bs4 import BeautifulSoup
from plyer import notification
import schedule
import os
import re

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'productos_a_monitorear.json')

# Configuración predeterminada si falta el archivo de config o tiene formato antiguo
DEFAULT_SETTINGS = {
    "currency_code": "$",
    "decimal_separator": ".",
    "thousands_separator": ","
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"settings": DEFAULT_SETTINGS, "products": []}
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            
            # Soporte para formato antiguo (lista de productos)
            if isinstance(data, list):
                return {"settings": DEFAULT_SETTINGS, "products": data}
            
            return data
    except Exception as e:
        print(f"Error al cargar configuración: {e}")
        return {"settings": DEFAULT_SETTINGS, "products": []}

def send_notification(title, message):
    try:
        notification.notify(
            title=title,
            message=message,
            app_name='Monitor de Precios',
            timeout=10
        )
        print(f"[NOTIFICACIÓN] {title}: {message}")
    except Exception as e:
        print(f"Error al enviar notificación: {e}")

def clean_price(price_str, settings):
    """
    Convierte string de precio a float usando la configuración regional.
    Ejemplos:
      - "$ 1,234.56" (US/MX) -> 1234.56
      - "1.234,56 €" (ES/CO) -> 1234.56
    """
    if not price_str:
        return None

    dec_sep = settings.get("decimal_separator", ".")
    tho_sep = settings.get("thousands_separator", ",")
    
    # 1. Eliminar todo excepto dígitos, separadores y signo negativo
    clean = re.sub(r'[^\d' + re.escape(dec_sep) + re.escape(tho_sep) + r'-]', '', price_str)
    
    # 2. Eliminar separador de miles
    clean = clean.replace(tho_sep, '')
    
    # 3. Reemplazar separador decimal por punto (para Python)
    clean = clean.replace(dec_sep, '.')
    
    try:
        return float(clean)
    except ValueError:
        return None

def format_price(value, settings):
    currency = settings.get("currency_code", "$")
    return f"{value} {currency}"

def check_mercadolibre(soup, settings):
    # Meta tag (formato generalmente consistente, a menudo solo dígitos o formato US)
    meta_price = soup.find("meta", itemprop="price")
    if meta_price:
        try:
            return float(meta_price["content"])
        except ValueError:
            pass
    
    # Selector visual
    price_span = soup.find("span", class_="andes-money-amount__fraction")
    if price_span:
        return clean_price(price_span.text, settings)
        
    return None

def check_amazon(soup, settings):
    selectors = ["span.a-price-whole", ".a-offscreen"]
    for selector in selectors:
        element = soup.select_one(selector)
        if element:
            # Amazon a menudo separa entero/fracción en HTML, manejado por extracción de texto
            # Pero la lógica de "clean_price" es suficientemente para cadenas simples
            return clean_price(element.text, settings)
    return None

def check_price(product, settings):
    url = product.get('url')
    target_price = product.get('target_price')
    name = product.get('name', 'Producto')

    print(f"Verificando: {name}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"  Error {response.status_code} al acceder a {url}")
            return

        soup = BeautifulSoup(response.content, 'html.parser')
        price = None

        if "mercadolibre" in url:
            price = check_mercadolibre(soup, settings)
        elif "amazon" in url:
            price = check_amazon(soup, settings)
        
        if price is None:
            print(f"  No se pudo detectar el precio.")
            return

        formatted_price = format_price(price, settings)
        formatted_target = format_price(target_price, settings)
        print(f"  Precio actual: {formatted_price} (Objetivo: {formatted_target})")

        if price <= target_price:
            send_notification(
                f"¡Oferta detectada!",
                f"{name} está a {formatted_price} (Objetivo: {formatted_target})"
            )
            
    except Exception as e:
        print(f"  Error al verificar {name}: {e}")

def job():
    print(f"\n--- Iniciando chequeo: {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    data = load_config()
    products = data.get("products", [])
    settings = data.get("settings", DEFAULT_SETTINGS)

    if not products:
        print("No hay productos configurados.")
        return

    print(f"Configuración: Moneda={settings.get('currency_code')}, Dec={settings.get('decimal_separator')}")

    for product in products:
        check_price(product, settings)
        time.sleep(2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monitor de Precios")
    parser.add_argument("--now", action="store_true", help="Ejecutar una vez ahora mismo")
    args = parser.parse_args()

    if args.now:
        job()
    else:
        print("Monitor iniciado. Verificando precios cada hora...")
        schedule.every(1).hours.do(job)
        job()
        while True:
            schedule.run_pending()
            time.sleep(60)

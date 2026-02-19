# Guía de Configuración — `productos_a_monitorear.json`

Este archivo controla todo el comportamiento del monitor de precios.
Se divide en dos secciones: `settings` (configuración global) y `products` (lista de productos).

---

## `settings` — Configuración Global

```json
"settings": {
    "currency_code": "COP",
    "decimal_separator": ".",
    "thousands_separator": ",",
    "telegram_token": "",
    "telegram_chat_id": "",
    "ml_access_token": ""
}
```

| Campo | Descripción | Ejemplos válidos |
|---|---|---|
| `currency_code` | Código o símbolo de moneda que aparece en consola y notificaciones | `"COP"`, `"USD"`, `"EUR"`, `"$"` |
| `decimal_separator` | Carácter que separa los decimales en los precios de la tienda | `"."` (Colombia, USA) · `","` (España, Europa) |
| `thousands_separator` | Carácter que separa los miles en los precios de la tienda | `","` (Colombia, USA) · `"."` (España, Europa) |
| `telegram_token` | Token del bot de Telegram para recibir notificaciones en el celular | Ver sección Telegram abajo |
| `telegram_chat_id` | Tu ID de chat personal en Telegram | Ver sección Telegram abajo |
| `ml_access_token` | Token de la API oficial de MercadoLibre (opcional pero recomendado) | Ver sección MercadoLibre abajo |

### Error común
No pongas el precio del producto en `decimal_separator`. Este campo solo acepta **un carácter**: el punto `.` o la coma `,`.

** Mal:**
```json
"decimal_separator": "75.490"
```
** Bien:**
```json
"decimal_separator": "."
```

---

## `products` — Lista de Productos

```json
"products": [
    {
        "name": "Nombre del producto",
        "url": "https://articulo.mercadolibre.com.co/MCO-XXXXXXXXX-...",
        "target_price": 75490,
        "alert_drop_percent": 5
    }
]
```

| Campo | Requerido | Descripción |
|---|---|---|
| `name` | ✅ Sí | Nombre descriptivo. Aparece en consola y en las notificaciones. |
| `url` | ✅ Sí | URL directa del producto. Ver notas abajo. |
| `target_price` | ⬜ Opcional | Precio objetivo en números enteros, sin puntos ni comas. Si el precio actual llega o baja de este valor, recibes una alerta. |
| `alert_drop_percent` | ⬜ Opcional | Porcentaje de caída desde la última lectura que dispara una alerta. `5` significa: avísame si el precio baja 5% o más respecto al chequeo anterior. |

### Notas sobre las URLs

**MercadoLibre:** Usa la URL limpia del producto, sin parámetros de tracking.

** Con tracking (puede interferir):**
```
https://articulo.mercadolibre.com.co/MCO-123456789-..._JM?matt_tool=15401541#origin=share&sid=share
```
** Limpia:**
```
https://articulo.mercadolibre.com.co/MCO-123456789-..._JM
```

**Amazon:** Puedes usar la URL corta con el ID del producto (formato `/dp/XXXXXXXXXX`).

---

## Configurar Telegram (notificaciones al celular)

Es gratis y llega instantáneo. Solo necesitas hacerlo una vez.

**Paso 1 — Crear el bot:**
1. Abre Telegram y busca `@BotFather`
2. Escribe `/newbot`
3. Ponle un nombre y un username (debe terminar en `bot`)
4. BotFather te dará el **token** — cópialo en `telegram_token`

**Paso 2 — Obtener tu chat ID:**
1. Busca `@userinfobot` en Telegram
2. Escribe `/start`
3. Te responde con tu **ID** — cópialo en `telegram_chat_id`

**Paso 3 — Activar el bot:**
Busca tu bot por su username en Telegram y escríbele `/start` una vez.
Sin este paso el bot no puede enviarte mensajes.

---

## Configurar MercadoLibre API (opcional pero recomendado)

La API oficial es más estable que el scraping. No se rompe cuando ML cambia su HTML.

1. Ve a [developers.mercadolibre.com](https://developers.mercadolibre.com)
2. Inicia sesión con tu cuenta de MercadoLibre
3. Crea una nueva aplicación (el nombre es libre)
4. En la sección **Credentials** copia el `Access Token`
5. Pégalo en `ml_access_token` del JSON

> El access token gratuito tiene límite de requests pero es más que suficiente para monitoreo personal.

---

## Ejemplo completo funcional

```json
{
    "settings": {
        "currency_code": "COP",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "telegram_token": "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ",
        "telegram_chat_id": "987654321",
        "ml_access_token": ""
    },
    "products": [
        {
            "name": "Botas Mujer",
            "url": "https://articulo.mercadolibre.com.co/MCO-886072080-bota-de-caucho-impermeable-dama-moto-mujer-color-_JM",
            "target_price": 70000,
            "alert_drop_percent": 5
        },
        {
            "name": "Teclado Mecánico",
            "url": "https://articulo.mercadolibre.com.co/MCO-XXXXXXXXX-...",
            "target_price": 150000,
            "alert_drop_percent": 10
        }
    ]
}
```

---

## Comandos disponibles

```bash
# Chequeo inmediato
python3 tools/monitor_precios.py --now

# Ver historial de precios guardados
python3 tools/monitor_precios.py --historial

# Monitoreo continuo cada 30 minutos
python3 tools/monitor_precios.py --interval 30

# Monitoreo continuo cada hora (por defecto)
python3 tools/monitor_precios.py
```

---

Desarrollado con ❤️ por Ale.
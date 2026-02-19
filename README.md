# Kit de Automatizacion de Tareas

Coleccion de scripts en Python para automatizar tareas cotidianas: organizacion de archivos, monitoreo de precios, resumen de documentos con IA, conversion de imagenes y generacion de PDFs.

## Instalacion

1. Asegurate de tener Python 3 instalado.
2. Crea y activa un entorno virtual (recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

## Menu Principal

La forma recomendada de usar estas herramientas es a traves del menu interactivo:

```bash
python3 menu_herramientas.py
```

El menu permite navegar con las flechas del teclado y ejecutar cualquier herramienta sin necesidad de recordar comandos.

---

## Herramientas

Cada script tambien puede ejecutarse de forma independiente desde la terminal. A continuacion se documenta cada herramienta con sus opciones y ejemplos de uso.

---

### 1. Renombrador Masivo

**Script:** `tools/renombrador_masivo.py`

Renombra multiples archivos en una carpeta usando tres modos: patron secuencial, fecha de creacion o reemplazo de texto.

> [!NOTE]
> Por defecto se ejecuta en modo simulacion (dry-run) para previsualizar los cambios. Agrega `--aplicar` para confirmar los cambios.

**Opciones:**

| Opcion | Descripcion |
|---|---|
| `directory` | Carpeta donde estan los archivos (obligatorio) |
| `--mode` | Modo de renombrado: `patron`, `fecha` o `reemplazo` (obligatorio) |
| `--ext` | Filtrar archivos por extension (ej: `.jpg`) |
| `--aplicar` | Aplicar los cambios realmente |

**Ejemplos:**

- **Modo patron** -- Renombra archivos secuencialmente:
  ```bash
  python3 tools/renombrador_masivo.py /ruta/fotos --mode patron --pattern "viaje_{:03d}" --ext .jpg
  python3 tools/renombrador_masivo.py /ruta/fotos --mode patron --pattern "viaje_{:03d}" --ext .jpg --aplicar
  ```
  Resultado: `viaje_001.jpg`, `viaje_002.jpg`, `viaje_003.jpg`...

- **Modo fecha** -- Agrega la fecha de creacion (EXIF o del sistema) al nombre:
  ```bash
  python3 tools/renombrador_masivo.py /ruta/docs --mode fecha --keep-name --aplicar
  python3 tools/renombrador_masivo.py /ruta/docs --mode fecha --aplicar
  ```
  Con `--keep-name`: `2024-02-17_documento.pdf`
  Sin `--keep-name`: `2024-02-17_001.pdf`

- **Modo reemplazo** -- Busca y reemplaza texto en nombres de archivos:
  ```bash
  python3 tools/renombrador_masivo.py /ruta/archivos --mode reemplazo --old-text "Copia de " --new-text "" --aplicar
  ```

---

### 2. Monitor de Precios

**Script:** `tools/monitor_precios.py`

Rastrea precios en MercadoLibre y Amazon. Cuando el precio alcanza el objetivo configurado o registra una caida porcentual, envia una alerta por consola y opcionalmente por Telegram.

**Configuracion:** Edita el archivo `productos_a_monitorear.json`:

```json
{
    "settings": {
        "currency_code": "COP",
        "decimal_separator": ".",
        "thousands_separator": ","
    },
    "products": [
        {
            "name": "Nintendo Switch",
            "url": "https://articulo.mercadolibre.com.co/MCO-XXXXXXX",
            "target_price": 1200000
        }
    ]
}
```

**Ejemplos:**

```bash
# Chequeo unico inmediato
python3 tools/monitor_precios.py --now

# Monitoreo continuo (verifica cada hora por defecto)
python3 tools/monitor_precios.py

# Monitoreo con intervalo personalizado (cada 30 minutos)
python3 tools/monitor_precios.py --interval 30

# Ver historial de precios registrados
python3 tools/monitor_precios.py --historial
```

| Opcion | Descripcion |
|---|---|
| `--now` | Ejecutar un solo chequeo y terminar |
| `--interval` | Intervalo en minutos entre chequeos (default: 60) |
| `--historial` | Mostrar el historial de precios registrados |

---

### 3. Resumidor con IA

**Script:** `tools/resumidor.py`

Utiliza la API de Google Gemini para leer archivos PDF o de texto plano y generar un resumen ejecutivo con puntos clave.

**Requisito:** Se necesita una API Key de Google, configurable de dos formas:
- Variable de entorno: `export GOOGLE_API_KEY=tu_clave`
- Archivo `.env` en la raiz del proyecto con `GOOGLE_API_KEY=tu_clave`

**Formatos soportados:** `.pdf`, `.txt`, `.md`, `.py`, `.json`

**Ejemplos:**

```bash
# Resumir un PDF (la API Key se toma del entorno)
python3 tools/resumidor.py documento.pdf

# Guardar el resumen en un archivo
python3 tools/resumidor.py reporte.pdf --out resumen.txt

# Pasar la API Key directamente
python3 tools/resumidor.py contrato.pdf --key TU_API_KEY
```

| Opcion | Descripcion |
|---|---|
| `filepath` | Ruta al archivo PDF o TXT (obligatorio) |
| `--key` | API Key de Google (opcional si esta en el entorno) |
| `--out` | Guardar el resumen en un archivo de salida |

---

### 4. Organizador de Descargas

**Script:** `tools/organizar_descargas.py`

Mueve automaticamente los archivos de la carpeta `~/Descargas` a subcarpetas organizadas por tipo segun su extension. No requiere argumentos.

**Categorias predeterminadas:**

| Categoria | Extensiones |
|---|---|
| Imagenes | `.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp` |
| Documentos | `.pdf`, `.doc`, `.docx`, `.txt`, `.xls`, `.xlsx`, `.ppt`, `.pptx` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.flv`, `.wmv` |
| Audio | `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg` |
| Comprimidos | `.zip`, `.rar`, `.7z`, `.tar`, `.gz` |
| Ejecutables | `.exe`, `.dmg`, `.app`, `.deb`, `.rpm` |
| Programacion | `.py`, `.js`, `.html`, `.css`, `.json`, `.xml` |
| Otros | Cualquier otra extension |

```bash
python3 tools/organizar_descargas.py
```

> [!TIP]
> Las categorias y extensiones se pueden personalizar editando el diccionario `CATEGORIES` dentro del script.

---

### 5. Convertidor de Imagenes

**Script:** `tools/convertir_imagen.py`

Convierte imagenes entre diferentes formatos. Funciona con archivos individuales y con carpetas completas (conversion masiva).

**Formatos soportados:** `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif`

**Ejemplos:**

```bash
# Convertir una imagen individual a JPG
python3 tools/convertir_imagen.py /ruta/imagen.png jpg

# Convertir una imagen a WebP
python3 tools/convertir_imagen.py /ruta/foto.jpg webp

# Convertir todas las imagenes de una carpeta a PNG
python3 tools/convertir_imagen.py /ruta/carpeta/ png
```

| Opcion | Descripcion |
|---|---|
| `input_path` | Ruta al archivo de imagen o carpeta (obligatorio) |
| `output_format` | Formato de salida: `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif` (obligatorio) |

> [!NOTE]
> Las imagenes con transparencia (PNG con canal alfa) se convierten automaticamente a RGB al exportar como JPG.

---

### 6. Convertir a PDF

**Script:** `tools/convertor_pdf.py`

Convierte documentos de oficina (`.docx`, `.odt`, `.pptx`, entre otros) a formato PDF utilizando LibreOffice en modo headless.

**Requisito:** LibreOffice debe estar instalado en el sistema.

**Ejemplo:**

```bash
python3 tools/convertor_pdf.py /ruta/documento.docx
```

| Opcion | Descripcion |
|---|---|
| `input_path` | Ruta al archivo a convertir (obligatorio) |

El archivo PDF resultante se guarda en la misma carpeta que el archivo de entrada.

---

### 7. Traductor de Archivos

**Script:** `tools/traductor.py`

Traduce archivos de texto completos a otro idioma usando la API de Google Gemini. Preserva el formato original del archivo: para codigo fuente traduce solo comentarios y cadenas de texto, para subtitulos (.srt) solo el texto, para JSON solo los valores.

**Requisito:** API Key de Google (misma configuracion que el Resumidor).

**Formatos soportados:** `.txt`, `.md`, `.srt`, `.py`, `.json`, `.csv`, `.xml`, `.html`, `.css`, `.js`

**Ejemplos:**

```bash
# Traducir un archivo de texto a ingles
python3 tools/traductor.py documento.txt --lang ingles

# Traducir subtitulos a portugues y guardar resultado
python3 tools/traductor.py pelicula.srt --lang portugues --out pelicula_pt.srt

# Traducir un archivo Markdown a frances con API Key explicita
python3 tools/traductor.py notas.md --lang frances --key TU_API_KEY
```

| Opcion | Descripcion |
|---|---|
| `filepath` | Ruta al archivo a traducir (obligatorio) |
| `--lang` | Idioma destino (obligatorio, ej: `ingles`, `frances`) |
| `--key` | API Key de Google (opcional si esta en el entorno) |
| `--out` | Guardar la traduccion en un archivo de salida |

---

## Estructura del Proyecto

```
Automation-Tools/
├── menu_herramientas.py          # Menu interactivo principal
├── requirements.txt              # Dependencias del proyecto
├── productos_a_monitorear.json   # Configuracion del monitor de precios
├── historial_precios.db          # Base de datos SQLite de precios
├── automation_tools.log          # Registro de actividad
└── tools/
    ├── renombrador_masivo.py     # Herramienta 1
    ├── monitor_precios.py        # Herramienta 2
    ├── resumidor.py              # Herramienta 3
    ├── organizar_descargas.py    # Herramienta 4
    ├── convertir_imagen.py       # Herramienta 5
    ├── convertor_pdf.py          # Herramienta 6
    └── traductor.py              # Herramienta 7
```

---

## Licencia

Desarrollado con ❤️ por Ale.
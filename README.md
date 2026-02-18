# 🚀 Kit de Automatización de Tareas

Este repositorio contiene una colección de scripts en Python diseñados para automatizar tareas cotidianas como organizar archivos, monitorear precios, resumir documentos con IA y convertir imágenes.

## 📦 Instalación

1.  Asegúrate de tener Python 3 instalado.
2.  Instala las dependencias necesarias:
    ```bash
    pip install -r requirements.txt
    ```

## 🖥️ Menú Principal (Recomendado)

La forma más fácil de usar estas herramientas es a través del menú interactivo:

```bash
python3 menu_herramientas.py
```

Desde aquí podrás navegar con las flechas del teclado y lanzar cualquiera de los scripts sin necesidad de recordar comandos.

---

## 🛠️ Herramientas Individuales

Cada script se puede ejecutar de forma independiente desde la terminal. A continuación se documenta cada herramienta con sus opciones y ejemplos de uso.

---

### 1. Renombrador Masivo (`renombrador_masivo.py`)

Renombra múltiples archivos en una carpeta usando tres modos diferentes: patrón secuencial, fecha de creación o reemplazo de texto.

> **Nota:** Por defecto se ejecuta en **modo simulación** (dry-run) para previsualizar los cambios. Agrega `--aplicar` para hacer los cambios reales.

**Opciones generales:**
| Opción | Descripción |
|---|---|
| `directory` | Carpeta donde están los archivos (obligatorio) |
| `--mode` | Modo de renombrado: `patron`, `fecha` o `reemplazo` (obligatorio) |
| `--ext` | Filtrar archivos por extensión (ej: `.jpg`) |
| `--aplicar` | Aplicar los cambios realmente |

**Ejemplos:**

*   **Modo Patrón** — Renombra archivos secuencialmente con un patrón personalizado:
    ```bash
    # Simulación (ver qué cambiaría)
    python3 renombrador_masivo.py /ruta/fotos --mode patron --pattern "viaje_{:03d}" --ext .jpg

    # Aplicar cambios
    python3 renombrador_masivo.py /ruta/fotos --mode patron --pattern "viaje_{:03d}" --ext .jpg --aplicar
    ```
    *Resultado*: `viaje_001.jpg`, `viaje_002.jpg`, `viaje_003.jpg`...

*   **Modo Fecha** — Añade la fecha de creación (EXIF o del sistema) al nombre del archivo:
    ```bash
    # Mantener nombre original con fecha al inicio
    python3 renombrador_masivo.py /ruta/docs --mode fecha --keep-name --aplicar

    # Solo fecha + número secuencial
    python3 renombrador_masivo.py /ruta/docs --mode fecha --aplicar
    ```
    *Resultado con `--keep-name`*: `2024-02-17_documento.pdf`
    *Resultado sin `--keep-name`*: `2024-02-17_001.pdf`

*   **Modo Reemplazo** — Busca y reemplaza texto en nombres de archivos:
    ```bash
    # Eliminar "Copia de " del nombre
    python3 renombrador_masivo.py /ruta/archivos --mode reemplazo --old-text "Copia de " --new-text "" --aplicar

    # Reemplazar texto
    python3 renombrador_masivo.py /ruta/archivos --mode reemplazo --old-text "borrador" --new-text "final" --aplicar
    ```

---

### 2. Monitor de Precios (`monitor_precios.py`)

Rastrea precios en **MercadoLibre** y **Amazon**. Si el precio baja de tu objetivo, envía una notificación de escritorio.

**Configuración:** Edita el archivo `productos_a_monitorear.json` con tus productos y la configuración regional:

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
# Chequeo único inmediato
python3 monitor_precios.py --now

# Modo continuo: verifica precios cada hora
python3 monitor_precios.py
```

| Opción | Descripción |
|---|---|
| `--now` | Ejecutar un solo chequeo y terminar |
| *(sin opciones)* | Iniciar monitoreo continuo cada hora |

---

### 3. Resumidor con IA (`resumidor.py`)

Usa la API de **Google Gemini** para leer archivos PDF o de texto plano y generar un resumen ejecutivo con puntos clave.

**Requisito:** Necesitas una API Key de Google. Puedes configurarla de dos formas:
- Variable de entorno: `export GOOGLE_API_KEY=tu_clave`
- Archivo `.env` en el directorio del proyecto con `GOOGLE_API_KEY=tu_clave`

**Formatos soportados:** `.pdf`, `.txt`, `.md`, `.py`, `.json`

**Ejemplos:**

```bash
# Resumir un PDF (la API Key se toma del entorno)
python3 resumidor.py documento.pdf

# Resumir un archivo de texto
python3 resumidor.py notas.txt

# Guardar el resumen en un archivo
python3 resumidor.py reporte.pdf --out resumen.txt

# Pasar la API Key directamente
python3 resumidor.py contrato.pdf --key TU_API_KEY
```

| Opción | Descripción |
|---|---|
| `filepath` | Ruta al archivo PDF o TXT (obligatorio) |
| `--key` | API Key de Google (opcional si está en el entorno) |
| `--out` | Guardar el resumen en este archivo |

---

### 4. Organizador de Descargas (`organizar_descargas.py`)

Mueve automáticamente los archivos de la carpeta `~/Descargas` a subcarpetas organizadas por tipo según su extensión. No requiere argumentos.

**Categorías predeterminadas:**

| Categoría | Extensiones |
|---|---|
| Imágenes | `.jpg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp` |
| Documentos | `.pdf`, `.doc`, `.docx`, `.txt`, `.xls`, `.xlsx`, `.ppt`, `.pptx` |
| Videos | `.mp4`, `.mov`, `.avi`, `.mkv`, `.flv`, `.wmv` |
| Audio | `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg` |
| Comprimidos | `.zip`, `.rar`, `.7z`, `.tar`, `.gz` |
| Ejecutables | `.exe`, `.dmg`, `.app`, `.deb`, `.rpm` |
| Programación | `.py`, `.js`, `.html`, `.css`, `.json`, `.xml` |
| Otros | Cualquier otra extensión |

**Ejemplo:**

```bash
python3 organizar_descargas.py
```

> **Nota:** Las categorías y extensiones se pueden personalizar editando el diccionario `CATEGORIES` dentro del script.

---

### 5. Convertidor de Imágenes (`convertir_imagen.py`)

Convierte imágenes entre diferentes formatos. Funciona tanto con archivos individuales como con carpetas completas (conversión masiva).

**Formatos soportados:** `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif`

**Ejemplos:**

```bash
# Convertir una imagen individual a JPG
python3 convertir_imagen.py /ruta/imagen.png jpg

# Convertir una imagen a WebP
python3 convertir_imagen.py /ruta/foto.jpg webp

# Convertir todas las imágenes de una carpeta a PNG
python3 convertir_imagen.py /ruta/carpeta/ png
```

| Opción | Descripción |
|---|---|
| `input_path` | Ruta al archivo de imagen o carpeta (obligatorio) |
| `output_format` | Formato de salida: `jpg`, `png`, `webp`, `bmp`, `tiff`, `gif` (obligatorio) |

> **Nota:** Las imágenes con transparencia (PNG con canal alfa) se convierten automáticamente a RGB al guardar como JPG.

---
Desarrollado con ❤️ por Ale
---
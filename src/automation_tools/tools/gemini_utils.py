import time
from typing import Optional

from google import genai

from automation_tools.core.logger import console, print_error, print_warning, setup_logger
from automation_tools.core.config import get_env_var

logger = setup_logger()

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-1.5-flash"
MAX_RETRIES = 4
BASE_BACKOFF = 2.0  # seconds; doubled each retry


def get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Inicializa y devuelve el cliente de Gemini."""
    key = api_key or get_env_var("GOOGLE_API_KEY")
    if not key:
        print_error("No se encontró la API Key de Google. Proporciona una válida o define GOOGLE_API_KEY.")
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        print_error(f"Error al inicializar cliente Gemini: {e}")
        return None


def _is_rate_limit(err: Exception) -> bool:
    msg = str(err).lower()
    return any(code in msg for code in ("429", "503", "resource_exhausted", "unavailable", "overloaded"))


def _log_usage(response, model_name: str) -> None:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return
    prompt = getattr(usage, "prompt_token_count", None)
    out = getattr(usage, "candidates_token_count", None)
    total = getattr(usage, "total_token_count", None)
    logger.info(f"Gemini tokens | model={model_name} prompt={prompt} out={out} total={total}")
    if total:
        console.print(f"[dim]🧮 Tokens: {total} (prompt {prompt} + salida {out}) · {model_name}[/dim]")


def generate_content(
    client: genai.Client,
    prompt: str,
    model_name: str = PRIMARY_MODEL,
    system_instruction: Optional[str] = None,
    allow_fallback: bool = True,
) -> Optional[str]:
    """Envía un prompt a Gemini con retry/backoff y fallback de modelo.

    - Reintenta ante 429/503/Unavailable con backoff exponencial.
    - Si el modelo primario sigue limitado, cae a `FALLBACK_MODEL`.
    - Loggea el consumo de tokens por llamada.
    """
    if system_instruction:
        prompt = f"{system_instruction}\n\n{prompt}"

    models_to_try = [model_name]
    if allow_fallback and model_name != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    last_err: Optional[Exception] = None
    for current_model in models_to_try:
        backoff = BASE_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(model=current_model, contents=prompt)
                _log_usage(response, current_model)
                return response.text
            except Exception as e:
                last_err = e
                if _is_rate_limit(e) and attempt < MAX_RETRIES:
                    print_warning(
                        f"Gemini ocupado ({current_model}). Reintento {attempt}/{MAX_RETRIES - 1} en {backoff:.1f}s…"
                    )
                    logger.warning(f"Retry {attempt} on {current_model}: {e}")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                break  # non-retriable or retries exhausted → try next model
        if last_err and _is_rate_limit(last_err) and current_model != models_to_try[-1]:
            print_warning(f"Cambiando a modelo de respaldo: {FALLBACK_MODEL}")
            continue
        break

    print_error(f"Error en la API de Gemini: {last_err}")
    return None

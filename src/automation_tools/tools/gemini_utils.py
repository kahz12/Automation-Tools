import time
from typing import Optional

from google import genai

from automation_tools.core.logger import console, print_error, print_warning, setup_logger
from automation_tools.core.config import get_env_var

logger = setup_logger()

# Configuration for AI models and retry logic
PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-1.5-flash"
MAX_RETRIES = 4
BASE_BACKOFF = 2.0  # seconds; doubled each retry


def get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """
    Initializes and returns a Gemini API client.
    
    Args:
        api_key (Optional[str]): The Google API key. If not provided, it will try to get it from environment variables.
        
    Returns:
        Optional[genai.Client]: The initialized Gemini client, or None if initialization fails.
    """
    key = api_key or get_env_var("GOOGLE_API_KEY")
    if not key:
        print_error("Google API Key not found. Provide a valid key or define GOOGLE_API_KEY in your environment.")
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        print_error(f"Error initializing Gemini client: {e}")
        return None


def _is_rate_limit(err: Exception) -> bool:
    """
    Checks if an exception is related to rate limiting or service unavailability.
    
    Args:
        err (Exception): The exception to check.
        
    Returns:
        bool: True if it's a rate limit or transient error, False otherwise.
    """
    msg = str(err).lower()
    return any(code in msg for code in ("429", "503", "resource_exhausted", "unavailable", "overloaded"))


def _log_usage(response, model_name: str) -> None:
    """
    Logs token usage metadata from a Gemini API response.
    
    Args:
        response: The response object from Gemini.
        model_name (str): The name of the model used.
    """
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return
    prompt = getattr(usage, "prompt_token_count", None)
    out = getattr(usage, "candidates_token_count", None)
    total = getattr(usage, "total_token_count", None)
    logger.info(f"Gemini tokens | model={model_name} prompt={prompt} out={out} total={total}")
    if total:
        console.print(f"[dim]🧮 Tokens: {total} (prompt {prompt} + output {out}) · {model_name}[/dim]")


def generate_content(
    client: genai.Client,
    prompt: str,
    model_name: str = PRIMARY_MODEL,
    system_instruction: Optional[str] = None,
    allow_fallback: bool = True,
) -> Optional[str]:
    """
    Sends a prompt to Gemini with retry/backoff logic and model fallback.
    
    - Retries on 429/503/Unavailable errors with exponential backoff.
    - If the primary model remains limited, falls back to `FALLBACK_MODEL`.
    - Logs token consumption for each call.
    
    Args:
        client (genai.Client): The Gemini client.
        prompt (str): The main prompt text.
        model_name (str): The primary model to use.
        system_instruction (Optional[str]): Optional system instruction to prepend.
        allow_fallback (bool): Whether to allow falling back to a secondary model.
        
    Returns:
        Optional[str]: The generated text content, or None if it fails.
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
                        f"Gemini busy ({current_model}). Retrying {attempt}/{MAX_RETRIES - 1} in {backoff:.1f}s…"
                    )
                    logger.warning(f"Retry {attempt} on {current_model}: {e}")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                break  # Non-retriable error or retries exhausted for this model
        
        # If we hit a rate limit and have a fallback model available, try the next one
        if last_err and _is_rate_limit(last_err) and current_model != models_to_try[-1]:
            print_warning(f"Switching to fallback model: {FALLBACK_MODEL}")
            continue
        break

    print_error(f"Gemini API Error: {last_err}")
    return None

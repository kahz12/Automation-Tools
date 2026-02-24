from typing import Optional

from google import genai

from automation_tools.core.logger import console, print_error, print_step
from automation_tools.core.config import get_env_var

def get_gemini_client(api_key: Optional[str] = None) -> Optional[genai.Client]:
    """Inicializa y devuelve el cliente de Gemini."""
    key = api_key or get_env_var("GOOGLE_API_KEY")
    if not key:
        print_error("No se encontró la API Key de Google. Proporciona una válidad o define GOOGLE_API_KEY.")
        return None
    try:
        return genai.Client(api_key=key)
    except Exception as e:
        print_error(f"Error al inicializar cliente Gemini: {e}")
        return None

def generate_content(client: genai.Client, prompt: str, model_name: str = "gemini-2.5-flash", system_instruction: Optional[str] = None) -> Optional[str]:
    """Envía un prompt a Gemini y devuelve el texto generado."""
    try:
        if system_instruction:
            prompt = f"{system_instruction}\n\n{prompt}"
            
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except Exception as e:
        print_error(f"Error en la API de Gemini: {e}")
        return None

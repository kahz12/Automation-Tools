import os
import json
from typing import Dict, Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from automation_tools.core.logger import print_error

def load_environment() -> None:
    """Loads environment variables from .env file if python-dotenv is available."""
    if load_dotenv:
        load_dotenv()

def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Safely retrieves an environment variable."""
    return os.environ.get(key, default)

def get_project_root() -> str:
    """Returns the absolute path to the project root directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", "..", ".."))

def get_downloads_folder() -> str:
    """Gets the path to the system's Downloads folder."""
    if os.name == 'nt':
        import winreg
        sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        downloads_guid = '{374DE290-123F-4565-9164-39C4925E467B}'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return location
    else:
        downloads_path = os.path.join(os.path.expanduser('~'), 'Descargas')
        if not os.path.exists(downloads_path):
            downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        return downloads_path

def load_json_config(filename: str = "productos_a_monitorear.json") -> Dict[str, Any]:
    """Loads a JSON configuration file from the project root."""
    root = get_project_root()
    filepath = os.path.join(root, filename)
    
    default_settings = {
        "currency_code": "$",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "telegram_token": "",
        "telegram_chat_id": "",
        "ml_access_token": "",
    }
    
    if not os.path.exists(filepath):
        return {"settings": default_settings, "products": []}
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if isinstance(data, list):
            return {"settings": default_settings, "products": data}
            
        settings = {**default_settings, **data.get("settings", {})}
        data["settings"] = settings
        return data
    except Exception as e:
        print_error(f"Failed to load config file {filename}: {e}")
        return {"settings": default_settings, "products": []}

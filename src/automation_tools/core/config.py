import os
import json
from typing import Dict, Any, Optional

# --- Configuration & Environment Module ---
# This module handles environment variable loading, project path resolution,
# and JSON configuration file management.

try:
    # Attempt to import python-dotenv to support .env files.
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from automation_tools.core.logger import print_error

def load_environment() -> None:
    """
    Loads environment variables from a .env file if the python-dotenv package is installed.
    Used for sensitive data like API keys.
    """
    if load_dotenv:
        load_dotenv()

def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Safely retrieves an environment variable from the system.
    Returns the value or a default value if the key is not found.
    """
    return os.environ.get(key, default)

def get_project_root() -> str:
    """
    Calculates and returns the absolute path to the project's root directory.
    Uses the location of this file as a reference point.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", "..", ".."))

def get_downloads_folder() -> str:
    """
    Determines the system's Downloads folder path.
    Supports Windows (via registry) and Linux/Android/Termux (via common paths).
    """
    if os.name == 'nt':
        import winreg
        sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        downloads_guid = '{374DE290-123F-4565-9164-39C4925E467B}'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return location
    else:
        # For Android/Termux: try the shared storage Downloads folder first.
        android_downloads = '/storage/emulated/0/Download'
        if os.path.isdir(android_downloads):
            return android_downloads

        # Fallback to standard Linux HOME-based paths.
        downloads_path = os.path.join(os.path.expanduser('~'), 'Descargas')
        if not os.path.exists(downloads_path):
            downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        return downloads_path

def load_json_config(filename: str = "productos_a_monitorear.json") -> Dict[str, Any]:
    """
    Loads a JSON configuration file from the project root.
    If the file doesn't exist, it returns a default configuration structure.
    Specifically used for the price monitor tool.
    """
    root = get_project_root()
    filepath = os.path.join(root, filename)
    
    # Default settings for the monitor tool.
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
            
        # Handle cases where the file might just be a list of products.
        if isinstance(data, list):
            return {"settings": default_settings, "products": data}
            
        # Merge existing settings with defaults.
        settings = {**default_settings, **data.get("settings", {})}
        data["settings"] = settings
        return data
    except Exception as e:
        print_error(f"Failed to load config file {filename}: {e}")
        return {"settings": default_settings, "products": []}

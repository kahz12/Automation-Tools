import os
import json
import shutil
import sys
from typing import Dict, Any, List, Optional

try:
    # python-dotenv is optional; without it, .env files are simply ignored.
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

from automation_tools.core.logger import print_error

def load_environment() -> None:
    """Loads a .env file into the environment, if python-dotenv is installed."""
    if HAS_DOTENV:
        load_dotenv()

def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Reads an environment variable, or `default` when it is not set."""
    return os.environ.get(key, default)

def get_project_root() -> str:
    """Absolute path to the project root, worked out from this file's location.

    Only meaningful when running from a checkout. Installed with pip the package
    sits in site-packages and this points at its parent, so it is good for
    finding files that ship with the source and never for writing.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, "..", "..", ".."))


APP_DIRNAME = "automation-tools"


def user_data_dir() -> str:
    """Where the tool keeps what it writes: history, the price database, the log.

    Not the project root. Once installed with pip that resolves to somewhere
    inside the interpreter's lib directory, which is either unwritable or a
    place nobody would look. Falls back to the project root if the real one
    cannot be created, so a checkout still works on a locked-down system.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")

    path = os.path.join(base, APP_DIRNAME)
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return get_project_root()
    return path


def _is_checkout(root: str) -> bool:
    return (os.path.isfile(os.path.join(root, "pyproject.toml"))
            and os.path.isdir(os.path.join(root, "src", "automation_tools")))


def state_path(name: str) -> str:
    """Absolute path for one piece of state, moved out of the checkout once.

    Earlier versions wrote next to the source. If that copy is still there and
    the new location is free, it moves rather than starting empty, so nobody
    loses their price history to an upgrade. Never overwrites, and keeps using
    the old path if the move fails.
    """
    target = os.path.join(user_data_dir(), name)
    legacy = os.path.join(get_project_root(), name)
    # Only ever migrate out of a real checkout. Installed, `get_project_root`
    # points into the interpreter's lib directory, and a file that happens to
    # share a name there belongs to somebody else.
    if not _is_checkout(get_project_root()):
        return target
    if not os.path.exists(target) and os.path.exists(legacy):
        try:
            shutil.move(legacy, target)
        except OSError:
            return legacy
    return target


def config_search_paths(filename: str) -> List[str]:
    """Where a hand-edited config file is looked for, in order.

    The working directory comes first so a config can sit next to whatever it
    describes; the data directory is where it belongs once installed; the
    project root is last, for checkouts that already have one there.
    """
    return [
        os.path.join(os.getcwd(), filename),
        os.path.join(user_data_dir(), filename),
        os.path.join(get_project_root(), filename),
    ]


def find_config_file(filename: str) -> Optional[str]:
    """The first existing config file with that name, or None."""
    for candidate in config_search_paths(filename):
        if os.path.isfile(candidate):
            return candidate
    return None

def get_downloads_folder() -> str:
    """The system Downloads folder: the registry on Windows, known paths elsewhere."""
    # sys.platform rather than os.name so a type checker knows the winreg
    # import below only happens where winreg exists.
    if sys.platform == 'win32':
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
    """Loads a JSON configuration file from the project root.
    If the file doesn't exist, it returns a default configuration structure.
    Specifically used for the price monitor tool.
    """
    filepath = find_config_file(filename)

    # Default settings for the monitor tool.
    default_settings = {
        "currency_code": "$",
        "decimal_separator": ".",
        "thousands_separator": ",",
        "telegram_token": "",
        "telegram_chat_id": "",
        "ml_access_token": "",
    }
    
    if not filepath:
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

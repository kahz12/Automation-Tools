import sys
import os

# Agrega la carpeta /src al path para permitir importar 'automation_tools'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from automation_tools.cli.menu import main_menu

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nSaliendo...")
    except Exception as e:
        print(f"Error fatal: {e}")

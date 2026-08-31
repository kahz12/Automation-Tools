import os
import sys

# Lets `python3 run.py` work straight from a checkout: the package lives under
# src/, which is not on the path when you run a loose file.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from automation_tools.cli.menu import main_menu

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        # The menu handles its own Ctrl+C; this is the backstop for anything
        # that slips past it. 130 is what a shell expects for an interrupt.
        raise SystemExit(130)

import sys
import os

# --- Entry Point for the Automation Tools Project ---
# This script initializes the application by setting up the module search path
# and launching the main command-line interface menu.

# Add the /src directory to the system path to allow importing the 'automation_tools' package.
# This ensures that internal modules can be resolved correctly regardless of where the script is run from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from automation_tools.cli.menu import main_menu

if __name__ == "__main__":
    try:
        # Start the interactive main menu.
        main_menu()
    except KeyboardInterrupt:
        # Gracefully handle user interruption (e.g., Ctrl+C).
        print("\nExiting...")
    except Exception as e:
        # Catch and display any fatal errors that occur during execution.
        print(f"Fatal error: {e}")

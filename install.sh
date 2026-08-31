#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Automation-Tools one-line installer
# ---------------------------------------------------------------------------

REPO_URL="https://github.com/kahz12/Automation-Tools.git"
INSTALL_DIR="${AUTOMATION_TOOLS_DIR:-$HOME/Automation-Tools}"
PYTHON_BIN="python3"

# ANSI colors
readonly C_GREEN='\033[0;32m'
readonly C_YELLOW='\033[0;33m'
readonly C_RED='\033[0;31m'
readonly C_RESET='\033[0m'

info()  { printf "${C_GREEN}[+]${C_RESET} %s\n" "$*"; }
warn()  { printf "${C_YELLOW}[!]${C_RESET} %s\n" "$*"; }
error() { printf "${C_RED}[x]${C_RESET} %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Environment detection: Termux vs regular Linux
# ---------------------------------------------------------------------------
IS_TERMUX=0
if [ -n "${TERMUX_VERSION:-}" ]; then
    IS_TERMUX=1
    LAUNCHER_DIR="${PREFIX}/bin"
else
    LAUNCHER_DIR="${HOME}/.local/bin"
fi
LAUNCHER_PATH="${LAUNCHER_DIR}/automation-tools"

# ---------------------------------------------------------------------------
# Package manager detection (for user-facing install hints only)
# ---------------------------------------------------------------------------
detect_pkg_hint() {
    local pkg="$1"
    if [ "$IS_TERMUX" -eq 1 ]; then
        printf "pkg install %s" "$pkg"
    elif command -v apt-get >/dev/null 2>&1; then
        printf "sudo apt-get install %s" "$pkg"
    elif command -v pacman >/dev/null 2>&1; then
        printf "sudo pacman -S %s" "$pkg"
    elif command -v dnf >/dev/null 2>&1; then
        printf "sudo dnf install %s" "$pkg"
    else
        printf "install %s with your system package manager" "$pkg"
    fi
}

# ---------------------------------------------------------------------------
# System dependency checks
# ---------------------------------------------------------------------------
info "Checking system dependencies..."

if ! command -v git >/dev/null 2>&1; then
    error "git is required. Install it with: $(detect_pkg_hint git)"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    error "python3 is required. Install it with: $(detect_pkg_hint python)"
fi

# Verify that the venv module is available
if ! "$PYTHON_BIN" -c "import venv" >/dev/null 2>&1; then
    if [ "$IS_TERMUX" -eq 1 ]; then
        hint="pkg install python"
    elif command -v apt-get >/dev/null 2>&1; then
        hint="sudo apt-get install python3-venv"
    elif command -v pacman >/dev/null 2>&1; then
        hint="sudo pacman -S python"
    elif command -v dnf >/dev/null 2>&1; then
        hint="sudo dnf install python3-virtualenv"
    else
        hint="install the Python venv module with your system package manager"
    fi
    error "Python venv module is missing. Install it with: ${hint}"
fi

info "All required system dependencies are present."

# ---------------------------------------------------------------------------
# Optional enhancement: LibreOffice. The PDF Builder works without it, on a
# pure-Python engine that recovers the text of a document but not its layout.
# When LibreOffice is present it is used instead and keeps images and tables.
# ---------------------------------------------------------------------------
if ! command -v libreoffice >/dev/null 2>&1 && ! command -v soffice >/dev/null 2>&1; then
    if [ "$IS_TERMUX" -eq 1 ]; then
        lo_hint="not available on Termux, so office files convert as text only"
    else
        lo_hint="for full-layout conversion install it with: $(detect_pkg_hint libreoffice)"
    fi
    info "LibreOffice not detected. The PDF Builder still works: ${lo_hint}"
fi

# ---------------------------------------------------------------------------
# Clone or update the repository (idempotent)
# ---------------------------------------------------------------------------
if [ -d "${INSTALL_DIR}/.git" ]; then
    info "Repository already present at ${INSTALL_DIR}. Pulling latest changes..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning repository into ${INSTALL_DIR}..."
    git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi

# ---------------------------------------------------------------------------
# Python virtual environment setup
# ---------------------------------------------------------------------------
VENV_DIR="${INSTALL_DIR}/venv"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    info "Virtual environment already exists, reusing it."
fi

info "Installing Python dependencies..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
# Installs the package itself (and its dependencies) from pyproject.toml.
pip install --quiet -e "${INSTALL_DIR}"
deactivate

# ---------------------------------------------------------------------------
# Global launcher script
# ---------------------------------------------------------------------------
info "Installing global launcher at ${LAUNCHER_PATH}..."
mkdir -p "$LAUNCHER_DIR"

cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
# Automation-Tools launcher (auto-generated by install.sh)
set -e
cd "${INSTALL_DIR}"
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
exec python3 run.py "\$@"
EOF

chmod 755 "$LAUNCHER_PATH"

# ---------------------------------------------------------------------------
# PATH check
# ---------------------------------------------------------------------------
case ":${PATH}:" in
    *":${LAUNCHER_DIR}:"*)
        PATH_OK=1
        ;;
    *)
        PATH_OK=0
        ;;
esac

# ---------------------------------------------------------------------------
# Final message
# ---------------------------------------------------------------------------
echo
info "Automation-Tools installed successfully!"
echo

if [ "$PATH_OK" -eq 0 ]; then
    warn "${LAUNCHER_DIR} is not in your PATH."
    echo "    Add it by appending this line to your ~/.bashrc or ~/.zshrc:"
    echo
    echo "        export PATH=\"${LAUNCHER_DIR}:\$PATH\""
    echo
    echo "    Then reload your shell: source ~/.bashrc   (or ~/.zshrc)"
    echo
fi

echo "Run the interactive menu with:"
echo
echo "    automation-tools"
echo
echo "Or run it manually:"
echo
echo "    cd ${INSTALL_DIR} && source venv/bin/activate && python3 run.py"
echo

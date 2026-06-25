import argparse
import base64
import os
import struct
from typing import Dict, List, Optional, Tuple

import questionary

from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# --- Encryption Vault Tool ---
# Encrypt or decrypt any file (or a whole folder) with a password, using only
# the `cryptography` library so it runs the same on Linux, Windows and
# Termux/Android (no external binaries).
#
# Scheme (per file):
#   key   = PBKDF2-HMAC-SHA256(password, salt, iterations)  → 32 bytes
#   token = Fernet(key).encrypt(plaintext)                  → AES-128-CBC + HMAC-SHA256
#
# Each encrypted file is self-describing: a small header stores the salt and the
# iteration count, so any file can be decrypted standalone later with the right
# password. Fernet is authenticated, so a wrong password or any tampering is
# detected and reported instead of producing garbage output.

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# File header: MAGIC(8) + iterations(4, big-endian uint32) + salt(16)
MAGIC = b"ATVAULT1"
SALT_LEN = 16
HEADER_LEN = len(MAGIC) + 4 + SALT_LEN
# OWASP-recommended PBKDF2-HMAC-SHA256 work factor. Derived once per batch.
DEFAULT_ITERATIONS = 600_000
ENC_SUFFIX = ".enc"


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derives a 32-byte url-safe Fernet key from a password via PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def _unique_path(path: str) -> str:
    """Returns `path` or, if it already exists, the same name with a _1, _2… suffix."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        candidate = f"{base}_{i}{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _collect_files(path: str, action: str, recursive: bool) -> List[str]:
    """
    Gathers the files to process.

    - encrypt: every file except ones we already produced (*.enc).
    - decrypt: only *.enc files.
    """
    def _wanted(name: str) -> bool:
        is_enc = name.lower().endswith(ENC_SUFFIX)
        return is_enc if action == "decrypt" else not is_enc

    if os.path.isfile(path):
        return [path] if _wanted(os.path.basename(path)) else []

    files: List[str] = []
    if recursive:
        for root, _, names in os.walk(path):
            for name in sorted(names):
                if _wanted(name):
                    files.append(os.path.join(root, name))
    else:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full) and _wanted(name):
                files.append(full)
    return files


def _out_path(src: str, action: str, output_dir: Optional[str]) -> str:
    """Computes the destination path for one file, avoiding collisions."""
    if action == "encrypt":
        name = os.path.basename(src) + ENC_SUFFIX
    else:  # decrypt → strip the .enc suffix (or add .dec if it has none)
        base = os.path.basename(src)
        name = base[: -len(ENC_SUFFIX)] if base.lower().endswith(ENC_SUFFIX) else base + ".dec"

    target_dir = output_dir if output_dir else os.path.dirname(src) or "."
    return _unique_path(os.path.join(target_dir, name))


def encrypt_file(input_path: str, key: bytes, salt: bytes, iterations: int, output_path: str) -> None:
    """Encrypts one file and writes the self-describing header + token."""
    with open(input_path, "rb") as f:
        data = f.read()
    token = Fernet(key).encrypt(data)
    header = MAGIC + struct.pack(">I", iterations) + salt
    with open(output_path, "wb") as f:
        f.write(header + token)


def decrypt_file(input_path: str, password: str, output_path: str, key_cache: Dict[Tuple[bytes, int], bytes]) -> None:
    """
    Decrypts one vault file. Raises:
        ValueError    — not a vault file (bad/short header).
        InvalidToken  — wrong password or tampered/corrupted data.
    """
    with open(input_path, "rb") as f:
        raw = f.read()

    if len(raw) < HEADER_LEN or raw[: len(MAGIC)] != MAGIC:
        raise ValueError("not a vault file (missing header)")

    iterations = struct.unpack(">I", raw[len(MAGIC): len(MAGIC) + 4])[0]
    salt = raw[len(MAGIC) + 4: HEADER_LEN]
    token = raw[HEADER_LEN:]

    cache_key = (salt, iterations)
    key = key_cache.get(cache_key)
    if key is None:
        key = _derive_key(password, salt, iterations)
        key_cache[cache_key] = key

    data = Fernet(key).decrypt(token)  # raises InvalidToken if wrong password / tampered
    with open(output_path, "wb") as f:
        f.write(data)


def run_vault(
    path: str,
    action: str,
    password: str,
    output_dir: Optional[str] = None,
    remove_originals: bool = False,
    recursive: bool = True,
) -> bool:
    """
    Core workflow: encrypt or decrypt a file or a folder of files.

    Returns True only if at least one file was processed and none failed.

    Args:
        path: A file or a folder.
        action: "encrypt" or "decrypt".
        password: The password used to derive the key.
        output_dir: Where to write results (defaults to alongside each source file).
        remove_originals: Delete each source file after it is processed successfully.
        recursive: Recurse into subfolders when `path` is a directory.
    """
    if not HAS_CRYPTO:
        print_error("The 'cryptography' library is not installed. Install it with 'pip install cryptography'.")
        return False
    if action not in ("encrypt", "decrypt"):
        print_error(f"Unknown action: '{action}'. Use 'encrypt' or 'decrypt'.")
        return False
    if not password:
        print_error("A password is required.")
        return False
    if not os.path.exists(path):
        print_error(f"The path '{path}' does not exist.")
        return False

    files = _collect_files(path, action, recursive)
    if not files:
        what = "*.enc files" if action == "decrypt" else "files"
        print_error(f"No {what} found to {action}.")
        return False

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Confirm before deleting plaintext/originals — this step is irreversible.
    if remove_originals:
        confirm = questionary.confirm(
            f"Delete the {len(files)} original file(s) after {action}ing? This cannot be undone.",
            default=False,
        ).ask()
        if not confirm:
            remove_originals = False
            print_warning("Originals will be kept.")

    verb = "Encrypting" if action == "encrypt" else "Decrypting"
    print_step(f"{verb} {len(files)} file(s)…")

    # For encryption the whole batch shares one salt/key (derived once); each
    # file still gets a unique IV from Fernet, so ciphertexts stay distinct.
    enc_salt = os.urandom(SALT_LEN)
    enc_key = _derive_key(password, enc_salt, DEFAULT_ITERATIONS) if action == "encrypt" else b""
    dec_cache: Dict[Tuple[bytes, int], bytes] = {}

    done = 0
    failed = 0
    for src in files:
        out = _out_path(src, action, output_dir)
        rel = os.path.basename(src)
        try:
            if action == "encrypt":
                encrypt_file(src, enc_key, enc_salt, DEFAULT_ITERATIONS, out)
            else:
                decrypt_file(src, password, out, dec_cache)

            if remove_originals:
                os.remove(src)
            console.print(f"  ✓ {rel} → '{os.path.basename(out)}'")
            done += 1
        except InvalidToken:
            print_error(f"{rel}: wrong password or the file is corrupted/tampered.")
            failed += 1
        except ValueError as e:
            print_error(f"{rel}: {e}")
            failed += 1
        except Exception as e:
            print_error(f"{rel}: {e}")
            failed += 1

    if done:
        past = "Encrypted" if action == "encrypt" else "Decrypted"
        print_success(f"{past} {done}/{len(files)} file(s).")
        if action == "encrypt":
            console.print("[dim]🔑 Keep your password safe — without it the files cannot be recovered.[/dim]")
    if failed:
        print_warning(f"{failed} file(s) could not be processed.")

    return failed == 0 and done > 0


def main() -> None:
    """CLI entry point for the Encryption Vault."""
    parser = argparse.ArgumentParser(description="Encrypt or decrypt files/folders with a password (AES via Fernet).")
    parser.add_argument("path", help="File or folder to process.")
    parser.add_argument("action", choices=["encrypt", "decrypt"], help="Operation to perform.")
    parser.add_argument("--password", help="Password (you will be prompted if omitted).")
    parser.add_argument("--out-dir", help="Output folder (default: alongside each source file).")
    parser.add_argument("--remove-originals", action="store_true",
                        help="Delete each source file after processing (asks for confirmation).")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Do not recurse into subfolders.")
    args = parser.parse_args()

    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("Password: ")

    ok = run_vault(
        path=args.path,
        action=args.action,
        password=password,
        output_dir=args.out_dir,
        remove_originals=args.remove_originals,
        recursive=not args.no_recursive,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

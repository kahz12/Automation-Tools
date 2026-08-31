import argparse
import base64
import getpass
import os
import re
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO, Callable, Dict, List, Optional, Tuple


from automation_tools.core import fs

from automation_tools.core import prompt
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Encrypt or decrypt any file (or a whole folder) with a password, using only
# the `cryptography` library so it runs the same on Linux, Windows and
# Termux/Android (no external binaries).
#
# Scheme (per file), format ATVAULT2:
#   master = scrypt(password, kdf_salt, N, r, p)          -> 32 bytes
#   key    = HKDF-SHA256(master, salt=file_salt)          -> 32 bytes, per file
#   body   = AES-256-GCM over 1 MiB chunks, each chunk authenticated
#            together with the header, its index and whether it is the last one
#
# Why it is built this way:
#
# scrypt instead of PBKDF2. PBKDF2 is pure arithmetic, so a GPU or an ASIC runs
# thousands of guesses in parallel for the price of one. scrypt forces 128 MiB
# of random access per guess, which is exactly what that hardware does not have
# per core, so an offline attack against a stolen .enc file costs orders of
# magnitude more.
#
# AES-256-GCM instead of Fernet. Fernet is AES-128-CBC plus HMAC and only works
# on a whole buffer, which means a 3 GB video has to fit in RAM twice. GCM lets
# us authenticate chunk by chunk, so memory stays flat and the key is 256 bits.
#
# The header is authenticated as associated data, so the KDF parameters cannot
# be edited. The chunk index is too, so chunks cannot be reordered, and each
# chunk records whether it is the last one, so cutting the tail off a file is
# detected instead of silently returning a shorter document.
#
# A per-file key derived with HKDF keeps the expensive scrypt step to once per
# batch while guaranteeing that no two files ever share an AES key, which is
# what GCM needs to stay safe.
#
# Files written by the previous format (ATVAULT1: PBKDF2 + Fernet) are still
# decrypted, so an existing vault keeps working after the upgrade.

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    HAS_CRYPTO = True
    # Wrong password and tampered data surface differently in each format.
    AUTH_ERRORS: Tuple[type, ...] = (InvalidTag, InvalidToken)
except ImportError:
    HAS_CRYPTO = False
    AUTH_ERRORS = ()

MAGIC = b"ATVAULT2"
MAGIC_V1 = b"ATVAULT1"
VERSION = 2
KDF_SCRYPT = 1
CIPHER_AES256GCM = 1

SALT_LEN = 16
NONCE_PREFIX_LEN = 8
TAG_LEN = 16
ENC_SUFFIX = ".enc"
PART_SUFFIX = ".part"

# ATVAULT2 header, big-endian, no padding:
#   magic(8) version(1) kdf(1) cipher(1) chunk_log2(1)
#   scrypt_n(4) scrypt_r(1) scrypt_p(1) reserved(2)
#   kdf_salt(16) file_salt(16) nonce_prefix(8)
HEADER_FMT = ">8sBBBBIBB2x16s16s8s"
HEADER_LEN = struct.calcsize(HEADER_FMT)
# ATVAULT1 header: magic(8) iterations(4) salt(16)
V1_HEADER_LEN = len(MAGIC_V1) + 4 + SALT_LEN

# OWASP's recommended scrypt work factor. Measured on the ARM64 phone this is
# developed on: 0.4 s and 128 MiB per derivation, paid once per batch.
SCRYPT_N = 1 << 17
SCRYPT_R = 8
SCRYPT_P = 1

# 1 MiB chunks: small enough that memory stays flat on a phone, large enough
# that the 16-byte tag per chunk is noise (0.0015% overhead).
CHUNK_LOG2 = 20

# Ceilings applied to whatever a file's header asks for. Without them a hostile
# .enc could name parameters that pin the machine for hours or ask for 40 GiB
# of scratch memory, turning "open this file" into a denial of service.
MAX_KDF_MEMORY = 1 << 30      # 1 GiB
MAX_SCRYPT_N = 1 << 22
MAX_ITERATIONS = 50_000_000   # ATVAULT1 files only
MAX_CHUNK_LOG2 = 26           # 64 MiB

MIN_PASSWORD_LEN = 12


@dataclass(frozen=True)
class KdfParams:
    """scrypt cost parameters, stored in every file so it stays self-describing."""
    n: int
    r: int
    p: int

    @property
    def memory_bytes(self) -> int:
        return 128 * self.n * self.r * self.p


# ── Key derivation ───────────────────────────────────────────────────────────
def check_kdf_params(params: KdfParams) -> None:
    """Rejects cost parameters that would hang or exhaust the machine.

    Raises ValueError. Called on every file we read, never trusting the header.
    """
    if params.n < 2 or params.n > MAX_SCRYPT_N or params.n & (params.n - 1):
        raise ValueError(f"invalid scrypt cost N={params.n}")
    if not 1 <= params.r <= 32 or not 1 <= params.p <= 16:
        raise ValueError(f"invalid scrypt parameters r={params.r} p={params.p}")
    if params.memory_bytes > MAX_KDF_MEMORY:
        raise ValueError(
            f"header asks for {params.memory_bytes // (1 << 20)} MiB of memory to "
            "derive the key, refusing"
        )


def derive_master_key(password: str, salt: bytes, params: KdfParams) -> bytes:
    """Turns the password into a 32-byte master key with scrypt."""
    check_kdf_params(params)
    kdf = Scrypt(salt=salt, length=32, n=params.n, r=params.r, p=params.p)
    return kdf.derive(password.encode("utf-8"))


def file_key(master_key: bytes, file_salt: bytes) -> bytes:
    """Splits off a key for a single file, cheaply.

    GCM breaks badly if a key and a nonce are ever reused together, and the
    master key is shared by the whole batch, so each file gets its own key from
    its own random salt. HKDF is one HMAC, unlike the scrypt step it comes from.
    """
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=file_salt,
        info=b"ATVAULT2 file key",
    ).derive(master_key)


def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    """Derives a url-safe Fernet key via PBKDF2, to read ATVAULT1 files."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


# ── Header ───────────────────────────────────────────────────────────────────
def pack_header(params: KdfParams, chunk_log2: int, kdf_salt: bytes,
                file_salt: bytes, nonce_prefix: bytes) -> bytes:
    return struct.pack(
        HEADER_FMT, MAGIC, VERSION, KDF_SCRYPT, CIPHER_AES256GCM, chunk_log2,
        params.n, params.r, params.p, kdf_salt, file_salt, nonce_prefix,
    )


def parse_header(raw: bytes) -> Tuple[KdfParams, int, bytes, bytes, bytes]:
    """Reads and validates an ATVAULT2 header. Raises ValueError if unusable."""
    if len(raw) != HEADER_LEN:
        raise ValueError("not a vault file (truncated header)")
    (magic, version, kdf, cipher, chunk_log2,
     n, r, p, kdf_salt, file_salt, nonce_prefix) = struct.unpack(HEADER_FMT, raw)

    if magic != MAGIC:
        raise ValueError("not a vault file (missing header)")
    if version != VERSION:
        raise ValueError(f"vault format v{version} is newer than this tool understands")
    if kdf != KDF_SCRYPT or cipher != CIPHER_AES256GCM:
        raise ValueError("unsupported key derivation or cipher in header")
    if not 10 <= chunk_log2 <= MAX_CHUNK_LOG2:
        raise ValueError(f"invalid chunk size in header (2^{chunk_log2})")

    params = KdfParams(n, r, p)
    check_kdf_params(params)
    return params, chunk_log2, kdf_salt, file_salt, nonce_prefix


def _aad(header: bytes, counter: int, final: bool) -> bytes:
    """What every chunk is authenticated against, on top of its own contents.

    Binding the header stops the KDF parameters and salts being edited; binding
    the index stops chunks being swapped around; binding the final flag stops
    the tail of the file being cut off unnoticed.
    """
    return header + struct.pack(">I?", counter, final)


# ── Files ────────────────────────────────────────────────────────────────────
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


def _quiet_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@contextmanager
def _atomic_write(path: str):
    """Writes through a temporary file and renames it only once it is on disk.

    Two things go wrong without this. A crash halfway through leaves a
    half-written .enc that looks like a real one, and with --remove-originals
    the source is deleted right after, so the data is gone. And on decryption
    the output must not appear at its final name until every chunk has been
    authenticated, or a truncated file leaves behind plaintext that looks whole.
    """
    tmp = _unique_path(path + PART_SUFFIX)
    handle = open(tmp, "wb")
    try:
        # Best effort: on Android's shared storage the mode is fixed by the
        # mount, but wherever it works a decrypted secret is not world-readable.
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        yield handle
        handle.flush()
        os.fsync(handle.fileno())
    except BaseException:
        handle.close()
        _quiet_remove(tmp)
        raise
    else:
        handle.close()
        os.replace(tmp, path)


def shred_file(path: str, block: int = 1 << 20) -> None:
    """Overwrites a file with random bytes, then deletes it.

    Worth knowing: on flash storage (so, on any phone) the controller writes to
    fresh cells and remaps them, and a copy-on-write filesystem does the same by
    design, so the old contents can survive this. It raises the cost of casual
    recovery; it is not an erase guarantee.
    """
    size = os.path.getsize(path)
    with open(path, "r+b") as handle:
        remaining = size
        while remaining > 0:
            written = min(remaining, block)
            handle.write(os.urandom(written))
            remaining -= written
        handle.flush()
        os.fsync(handle.fileno())
    os.remove(path)


def _collect_files(path: str, action: str, recursive: bool,
                   exclude_dir: Optional[str] = None) -> List[str]:
    """Gathers the files to process.

    - encrypt: every file except ones we already produced (*.enc, *.part).
    - decrypt: only *.enc files.

    Symlinks are skipped. Following one would encrypt whatever it points at
    while --remove-originals deleted only the link, leaving the real file
    sitting there in plaintext.
    """
    def _wanted(name: str) -> bool:
        lower = name.lower()
        if lower.endswith(PART_SUFFIX):
            return False
        is_enc = lower.endswith(ENC_SUFFIX)
        return is_enc if action == "decrypt" else not is_enc

    # walk_files skips symlinks and never descends into the output folder, so
    # what is left here is the suffix rule, which has to stay case-insensitive.
    return [full for full in fs.walk_files(path, recursive=recursive,
                                           skip_dir=exclude_dir)
            if _wanted(os.path.basename(full))]


def _out_path(src: str, action: str, output_dir: Optional[str]) -> str:
    """Computes the destination path for one file, avoiding collisions."""
    if action == "encrypt":
        name = os.path.basename(src) + ENC_SUFFIX
    else:  # decrypt: strip the .enc suffix (or add .dec if it has none)
        base = os.path.basename(src)
        name = base[: -len(ENC_SUFFIX)] if base.lower().endswith(ENC_SUFFIX) else base + ".dec"

    target_dir = output_dir if output_dir else os.path.dirname(src) or "."
    return _unique_path(os.path.join(target_dir, name))


# ── Encryption ───────────────────────────────────────────────────────────────
def encrypt_file(input_path: str, master_key: bytes, kdf_salt: bytes,
                 params: KdfParams, output_path: str,
                 chunk_log2: int = CHUNK_LOG2) -> None:
    """Encrypts one file chunk by chunk, writing header + authenticated frames."""
    chunk_size = 1 << chunk_log2
    file_salt = os.urandom(SALT_LEN)
    nonce_prefix = os.urandom(NONCE_PREFIX_LEN)
    header = pack_header(params, chunk_log2, kdf_salt, file_salt, nonce_prefix)
    cipher = AESGCM(file_key(master_key, file_salt))

    with open(input_path, "rb") as source, _atomic_write(output_path) as out:
        out.write(header)
        counter = 0
        chunk = source.read(chunk_size)
        while True:
            # Read ahead so each chunk knows whether it is the last one, which
            # is what makes a truncated file detectable. An empty input still
            # produces one frame, so a file with no frames is never valid.
            following = source.read(chunk_size)
            final = not following
            token = cipher.encrypt(
                nonce_prefix + struct.pack(">I", counter),
                chunk,
                _aad(header, counter, final),
            )
            out.write(struct.pack(">I", len(token)))
            out.write(token)
            if final:
                break
            chunk = following
            counter += 1


# ── Decryption ───────────────────────────────────────────────────────────────
def _read_frame(handle: BinaryIO, max_len: int) -> Optional[bytes]:
    """Reads one length-prefixed frame, or None at a clean end of file."""
    prefix = handle.read(4)
    if not prefix:
        return None
    if len(prefix) < 4:
        raise ValueError("truncated frame header")
    length = struct.unpack(">I", prefix)[0]
    # The length comes from the file, so it is checked before it becomes a
    # multi-gigabyte read() on a hostile input.
    if length < TAG_LEN or length > max_len:
        raise ValueError("frame length is out of range")
    frame = handle.read(length)
    if len(frame) < length:
        raise ValueError("truncated frame")
    return frame


def _decrypt_v2(handle: BinaryIO, header: bytes, password: str,
                out: BinaryIO, key_cache: Dict[tuple, bytes]) -> None:
    params, chunk_log2, kdf_salt, file_salt, nonce_prefix = parse_header(header)

    cache_key = ("v2", kdf_salt, params.n, params.r, params.p)
    master = key_cache.get(cache_key)
    if master is None:
        master = derive_master_key(password, kdf_salt, params)
        key_cache[cache_key] = master

    cipher = AESGCM(file_key(master, file_salt))
    max_frame = (1 << chunk_log2) + TAG_LEN

    frame = _read_frame(handle, max_frame)
    if frame is None:
        raise ValueError("vault file carries no data")

    counter = 0
    while True:
        following = _read_frame(handle, max_frame)
        final = following is None
        # Each chunk is authenticated before a byte of it reaches the file, and
        # the file only takes its real name once the loop finishes.
        out.write(cipher.decrypt(
            nonce_prefix + struct.pack(">I", counter),
            frame,
            _aad(header, counter, final),
        ))
        if final:
            return
        frame = following
        counter += 1


def _decrypt_v1(raw: bytes, password: str, out: BinaryIO,
                key_cache: Dict[tuple, bytes]) -> None:
    """Reads a file written by the old PBKDF2 + Fernet format.

    Fernet has no streaming API, so this one holds the file in memory. New
    files do not go through here.
    """
    if len(raw) < V1_HEADER_LEN:
        raise ValueError("not a vault file (missing header)")
    iterations = struct.unpack(">I", raw[len(MAGIC_V1): len(MAGIC_V1) + 4])[0]
    if not 1 <= iterations <= MAX_ITERATIONS:
        raise ValueError(f"header asks for {iterations} PBKDF2 iterations, refusing")
    salt = raw[len(MAGIC_V1) + 4: V1_HEADER_LEN]

    cache_key = ("v1", salt, iterations)
    key = key_cache.get(cache_key)
    if key is None:
        key = _derive_key(password, salt, iterations)
        key_cache[cache_key] = key
    out.write(Fernet(key).decrypt(raw[V1_HEADER_LEN:]))


def decrypt_file(input_path: str, password: str, output_path: str,
                 key_cache: Dict[tuple, bytes]) -> None:
    """Decrypts one vault file, in either format. Raises:
        ValueError:              not a vault file, or a corrupt/hostile header.
        InvalidTag/InvalidToken: wrong password or tampered data.
    """
    with open(input_path, "rb") as handle:
        magic = handle.read(len(MAGIC))
        if magic == MAGIC:
            header = magic + handle.read(HEADER_LEN - len(MAGIC))
            with _atomic_write(output_path) as out:
                _decrypt_v2(handle, header, password, out, key_cache)
        elif magic == MAGIC_V1:
            raw = magic + handle.read()
            with _atomic_write(output_path) as out:
                _decrypt_v1(raw, password, out, key_cache)
        else:
            raise ValueError("not a vault file (missing header)")


# ── Passwords ────────────────────────────────────────────────────────────────
def password_problems(password: str) -> List[str]:
    """Lists what is weak about a password, empty when it looks fine.

    The KDF only buys time proportional to how much guessing an attacker has to
    do, and it cannot save a password that is in every wordlist.
    """
    problems = []
    if len(password) < MIN_PASSWORD_LEN:
        problems.append(f"it is shorter than {MIN_PASSWORD_LEN} characters")
    classes = sum(bool(re.search(pattern, password)) for pattern in
                  (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("it mixes fewer than three of lower/upper/digits/symbols")
    if re.fullmatch(r"(.)\1*", password) or password.lower() in (
        "password", "contrasena", "contraseña", "qwerty", "123456", "admin", "secret",
    ):
        problems.append("it is one of the first passwords anyone tries")
    return problems


def _accept_weak_password() -> bool:
    return prompt.confirm("Use it anyway?", default=False)


def _prompt_password(action: str, prompt: Callable[[str], str] = getpass.getpass,
                     accept_weak: Callable[[], bool] = _accept_weak_password) -> Optional[str]:
    """Asks the user for the vault password.

    Encrypting asks twice and requires both entries to match: a typo there seals
    the files under a password nobody knows, and the contents are gone for good.
    It also complains about a weak password while there is still time, since
    once the files are encrypted the password is the only thing protecting them.
    Decrypting asks once, since a wrong password is simply rejected.

    Returns None if the password is empty, the confirmation does not match, or
    a weak one is not confirmed.
    """
    password = prompt("Password: ")
    if not password:
        print_error("A password is required.")
        return None

    if action == "encrypt":
        confirmation = prompt("Confirm password: ")
        if confirmation != password:
            print_error("The passwords do not match. Nothing was encrypted.")
            return None

        problems = password_problems(password)
        if problems:
            print_warning("That password is weak: " + ", ".join(problems) + ".")
            console.print(
                "[dim]Anyone who copies an encrypted file can guess at it offline, "
                "for as long as they like.[/dim]"
            )
            if not accept_weak():
                print_error("Nothing was encrypted.")
                return None

    return password


def _password_from_args(args: argparse.Namespace) -> Optional[str]:
    """Resolves the password from the flags, the environment, or a prompt."""
    if args.password:
        print_warning(
            "--password is visible to every process on the machine (ps) and lands "
            "in your shell history. Prefer --password-file or the prompt."
        )
        return args.password
    if args.password_file:
        try:
            with open(args.password_file, "r", encoding="utf-8") as handle:
                password = handle.readline().rstrip("\r\n")
        except OSError as e:
            print_error(f"Could not read the password file: {e}")
            return None
        if not password:
            print_error("The password file is empty.")
            return None
        return password
    from_env = os.environ.get("AT_VAULT_PASSWORD")
    if from_env:
        return from_env
    return _prompt_password(args.action)


# ── Entry point ──────────────────────────────────────────────────────────────
def run_vault(
    path: str,
    action: str,
    password: str,
    output_dir: Optional[str] = None,
    remove_originals: bool = False,
    recursive: bool = True,
    shred: bool = False,
) -> bool:
    """Core workflow: encrypt or decrypt a file, or a folder of files.

    Returns True only if at least one file was processed and none failed.
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

    if shred:
        remove_originals = True

    files = _collect_files(path, action, recursive, exclude_dir=output_dir)
    if not files:
        what = "*.enc files" if action == "decrypt" else "files"
        print_error(f"No {what} found to {action}.")
        return False

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Confirm before destroying the originals; this step is irreversible.
    if remove_originals:
        how = "Shred (overwrite) and delete" if shred else "Delete"
        confirm = prompt.confirm(
            f"{how} the {len(files)} original file(s) after {action}ing? This cannot be undone.",
            default=False,
        )
        if not confirm:
            remove_originals = False
            print_warning("Originals will be kept.")

    verb = "Encrypting" if action == "encrypt" else "Decrypting"
    print_step(f"{verb} {len(files)} file(s)…")

    params = KdfParams(SCRYPT_N, SCRYPT_R, SCRYPT_P)
    kdf_salt = os.urandom(SALT_LEN)
    master_key = b""
    if action == "encrypt":
        console.print(
            f"[dim]Deriving the key with scrypt "
            f"(N=2^{params.n.bit_length() - 1}, {params.memory_bytes // (1 << 20)} MiB)…[/dim]"
        )
        master_key = derive_master_key(password, kdf_salt, params)
    # Decryption derives per (salt, parameters) found in the files themselves.
    key_cache: Dict[tuple, bytes] = {}

    done = 0
    failed = 0
    for src in files:
        out = _out_path(src, action, output_dir)
        rel = os.path.basename(src)
        try:
            if action == "encrypt":
                encrypt_file(src, master_key, kdf_salt, params, out)
            else:
                decrypt_file(src, password, out, key_cache)

            if remove_originals:
                shred_file(src) if shred else os.remove(src)
            console.print(f"  ✓ {rel} → '{os.path.basename(out)}'")
            done += 1
        except AUTH_ERRORS:
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
            console.print("[dim]🔑 Keep your password safe. Without it the files cannot be recovered.[/dim]")
    if failed:
        print_warning(f"{failed} file(s) could not be processed.")

    return failed == 0 and done > 0


def main() -> None:
    """CLI entry point for the Encryption Vault."""
    parser = argparse.ArgumentParser(
        description="Encrypt or decrypt files/folders with a password (scrypt + AES-256-GCM)."
    )
    parser.add_argument("path", help="File or folder to process.")
    parser.add_argument("action", choices=["encrypt", "decrypt"], help="Operation to perform.")
    parser.add_argument("--password", help="Password (insecure: visible in ps; you will be prompted if omitted).")
    parser.add_argument("--password-file", help="Read the password from the first line of this file.")
    parser.add_argument("--out-dir", help="Output folder (default: alongside each source file).")
    parser.add_argument("--remove-originals", action="store_true",
                        help="Delete each source file after processing (asks for confirmation).")
    parser.add_argument("--shred", action="store_true",
                        help="Overwrite each original before deleting it (implies --remove-originals).")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Do not recurse into subfolders.")
    args = parser.parse_args()

    password = _password_from_args(args)
    if not password:
        raise SystemExit(1)

    ok = run_vault(
        path=args.path,
        action=args.action,
        password=password,
        output_dir=args.out_dir,
        remove_originals=args.remove_originals,
        recursive=not args.no_recursive,
        shred=args.shred,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

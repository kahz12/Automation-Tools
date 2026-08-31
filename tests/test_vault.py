"""Tests for the Encryption Vault.

Most of these are adversarial on purpose: the interesting question for an
encryption tool is not whether a file survives a round trip, it is what happens
when the file that comes back has been edited, cut short, rearranged, or
written by an attacker who chose the header.
"""
import base64
import os
import struct
import sys
import types

import pytest

from conftest import needs_symlinks

# Skip the module rather than error out where the library loads but its Rust
# extension does not (Termux's Python 3.14 today). pytest.importorskip only
# covers a missing module, and this one is present and broken.
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as exc:
    pytest.skip(f"cryptography is not usable here: {exc}", allow_module_level=True)

from automation_tools.tools import vault

STRONG = "Corr3cta-Bateria-Grapa!"


@pytest.fixture(autouse=True)
def cheap_kdf(monkeypatch):
    """Runs the suite at a fraction of the real scrypt cost.

    The shipped parameters take 128 MiB and 0.4 s per derivation, which is the
    point of them; paying that in every test is not. Decryption reads the cost
    out of each file's own header, so the round trips stay honest.
    """
    monkeypatch.setattr(vault, "SCRYPT_N", 1 << 12)


@pytest.fixture
def accept_confirm(monkeypatch):
    def _set(answer):
        monkeypatch.setattr(vault.prompt, "confirm", lambda *a, **k: answer)
    return _set


def _encrypted(tmp_path, text="contenido confidencial áéí 🔐", password=STRONG, name="secret.txt"):
    """Writes a plaintext file, encrypts it, and returns the .enc path."""
    src = tmp_path / name
    src.write_text(text, encoding="utf-8")
    assert vault.run_vault(str(src), "encrypt", password, output_dir=str(tmp_path / "enc")) is True
    return tmp_path / "enc" / (name + ".enc")


# ── defaults ────────────────────────────────────────────────────────────────
def test_shipped_parameters_are_the_recommended_ones():
    # The cheap_kdf fixture lowers N for speed, so assert on the real constant.
    assert vault.KdfParams(1 << 17, 8, 1).memory_bytes == 128 * (1 << 20)
    assert (vault.SCRYPT_R, vault.SCRYPT_P) == (8, 1)
    assert vault.HEADER_LEN == 60


# ── round trips ─────────────────────────────────────────────────────────────
def test_encrypt_decrypt_roundtrip(tmp_path):
    enc_file = _encrypted(tmp_path)
    raw = enc_file.read_bytes()
    assert raw[:8] == vault.MAGIC
    assert b"confidencial" not in raw

    assert vault.run_vault(str(enc_file), "decrypt", STRONG, output_dir=str(tmp_path / "dec")) is True
    restored = (tmp_path / "dec" / "secret.txt").read_text(encoding="utf-8")
    assert restored == "contenido confidencial áéí 🔐"


def test_a_file_larger_than_one_chunk_streams_through_intact(tmp_path):
    # Two and a bit chunks at the real 1 MiB default, so the frame loop, the
    # counter and the final-chunk flag all get exercised as shipped.
    payload = os.urandom((2 << 20) + 4096)
    src = tmp_path / "big.bin"
    src.write_bytes(payload)

    assert vault.run_vault(str(src), "encrypt", STRONG, output_dir=str(tmp_path / "enc")) is True
    enc_file = tmp_path / "enc" / "big.bin.enc"
    assert vault.run_vault(str(enc_file), "decrypt", STRONG, output_dir=str(tmp_path / "dec")) is True
    assert (tmp_path / "dec" / "big.bin").read_bytes() == payload


@pytest.mark.parametrize("size", [0, 1, 1024, 1025, 4096])
def test_chunk_boundaries_round_trip(tmp_path, size):
    # 1 KiB chunks, so these sizes land exactly on, just past, and well past a
    # boundary. An empty file still has to produce a readable vault file.
    payload = os.urandom(size)
    src = tmp_path / "f.bin"
    src.write_bytes(payload)
    out = str(tmp_path / "f.enc")

    params = vault.KdfParams(1 << 12, 8, 1)
    salt = os.urandom(vault.SALT_LEN)
    master = vault.derive_master_key(STRONG, salt, params)
    vault.encrypt_file(str(src), master, salt, params, out, chunk_log2=10)

    back = str(tmp_path / "back.bin")
    vault.decrypt_file(out, STRONG, back, {})
    assert open(back, "rb").read() == payload


def test_two_files_never_share_a_key_or_a_nonce(tmp_path):
    # Same password, same batch, same contents: the ciphertexts must still
    # differ, or GCM would be reusing a key and nonce pair.
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("identical", encoding="utf-8")
    assert vault.run_vault(str(tmp_path), "encrypt", STRONG, output_dir=str(tmp_path / "enc")) is True

    a = (tmp_path / "enc" / "a.txt.enc").read_bytes()
    b = (tmp_path / "enc" / "b.txt.enc").read_bytes()
    assert a != b
    # Both carry the batch salt scrypt ran on, but the per-file HKDF salt and
    # the nonce prefix are drawn fresh for each one.
    assert a[20:36] == b[20:36]
    assert a[36:52] != b[36:52]
    assert a[52:60] != b[52:60]


def test_old_format_files_still_decrypt(tmp_path):
    """A vault encrypted before the scrypt/GCM upgrade must keep opening."""
    salt = b"0123456789abcdef"
    iterations = 1000
    key = base64.urlsafe_b64encode(
        PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                   iterations=iterations).derive(b"vieja")
    )
    legacy = tmp_path / "old.txt.enc"
    legacy.write_bytes(
        vault.MAGIC_V1 + struct.pack(">I", iterations) + salt
        + Fernet(key).encrypt("texto de antes".encode("utf-8"))
    )

    assert vault.run_vault(str(legacy), "decrypt", "vieja", output_dir=str(tmp_path / "dec")) is True
    assert (tmp_path / "dec" / "old.txt").read_text(encoding="utf-8") == "texto de antes"


# ── tampering ───────────────────────────────────────────────────────────────
def test_wrong_password_is_rejected_and_writes_nothing(tmp_path):
    enc_file = _encrypted(tmp_path, "data", password="right-Password-1", name="f.txt")
    assert vault.run_vault(str(enc_file), "decrypt", "wrong-Password-1",
                           output_dir=str(tmp_path / "dec")) is False
    assert not (tmp_path / "dec" / "f.txt").exists()


def test_a_flipped_bit_in_the_ciphertext_is_detected(tmp_path):
    enc_file = _encrypted(tmp_path, "data", name="f.txt")
    raw = bytearray(enc_file.read_bytes())
    raw[-1] ^= 0x01
    enc_file.write_bytes(bytes(raw))
    assert vault.run_vault(str(enc_file), "decrypt", STRONG, output_dir=str(tmp_path / "dec")) is False


@pytest.mark.parametrize("offset, label", [
    (12, "scrypt cost"),
    (20, "kdf salt"),
    (36, "file salt"),
    (52, "nonce prefix"),
])
def test_editing_the_header_is_detected(tmp_path, offset, label):
    """The header is in the clear, so it has to be authenticated, not trusted."""
    enc_file = _encrypted(tmp_path, "data", name="f.txt")
    raw = bytearray(enc_file.read_bytes())
    raw[offset] ^= 0x01
    enc_file.write_bytes(bytes(raw))
    assert vault.run_vault(str(enc_file), "decrypt", STRONG,
                           output_dir=str(tmp_path / "dec")) is False, label


def test_cutting_the_tail_off_a_file_is_detected(tmp_path):
    """Truncation must fail loudly instead of returning a shorter document."""
    src = tmp_path / "f.bin"
    src.write_bytes(b"A" * 3072)
    out = str(tmp_path / "f.enc")
    params = vault.KdfParams(1 << 12, 8, 1)
    salt = os.urandom(vault.SALT_LEN)
    vault.encrypt_file(str(src), vault.derive_master_key(STRONG, salt, params),
                       salt, params, out, chunk_log2=10)

    raw = open(out, "rb").read()
    frame_len = struct.unpack(">I", raw[vault.HEADER_LEN:vault.HEADER_LEN + 4])[0]
    # Keep the header and exactly one whole frame; drop the rest.
    open(out, "wb").write(raw[: vault.HEADER_LEN + 4 + frame_len])

    with pytest.raises(vault.AUTH_ERRORS):
        vault.decrypt_file(out, STRONG, str(tmp_path / "back.bin"), {})
    assert not (tmp_path / "back.bin").exists()


def test_reordering_chunks_is_detected(tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(b"A" * 1024 + b"B" * 1024)
    out = str(tmp_path / "f.enc")
    params = vault.KdfParams(1 << 12, 8, 1)
    salt = os.urandom(vault.SALT_LEN)
    vault.encrypt_file(str(src), vault.derive_master_key(STRONG, salt, params),
                       salt, params, out, chunk_log2=10)

    raw = open(out, "rb").read()
    body = raw[vault.HEADER_LEN:]
    size = struct.unpack(">I", body[:4])[0]
    first, rest = body[: 4 + size], body[4 + size:]
    second_size = struct.unpack(">I", rest[:4])[0]
    second = rest[: 4 + second_size]
    open(out, "wb").write(raw[: vault.HEADER_LEN] + second + first + rest[4 + second_size:])

    with pytest.raises(vault.AUTH_ERRORS):
        vault.decrypt_file(out, STRONG, str(tmp_path / "back.bin"), {})


def test_decrypt_rejects_a_file_that_is_not_a_vault(tmp_path):
    bad = tmp_path / "x.enc"
    bad.write_bytes(b"not a vault")
    assert vault.run_vault(str(bad), "decrypt", STRONG, output_dir=str(tmp_path / "o")) is False


def test_decrypt_rejects_a_header_that_stops_halfway(tmp_path):
    short = tmp_path / "x.enc"
    short.write_bytes(vault.MAGIC + b"\x02\x01\x01\x14")
    assert vault.run_vault(str(short), "decrypt", STRONG, output_dir=str(tmp_path / "o")) is False


def test_a_vault_file_with_no_frames_is_rejected(tmp_path):
    enc_file = _encrypted(tmp_path, "data", name="f.txt")
    enc_file.write_bytes(enc_file.read_bytes()[: vault.HEADER_LEN])
    assert vault.run_vault(str(enc_file), "decrypt", STRONG, output_dir=str(tmp_path / "o")) is False


# ── hostile headers ─────────────────────────────────────────────────────────
def test_absurd_kdf_parameters_are_refused_instead_of_run(tmp_path):
    """A header naming 40 GiB of scratch memory must not be obeyed."""
    hostile = vault.pack_header(
        vault.KdfParams(1 << 22, 16, 4), 20,
        os.urandom(16), os.urandom(16), os.urandom(8),
    )
    path = tmp_path / "bomb.enc"
    path.write_bytes(hostile + struct.pack(">I", 32) + b"\x00" * 32)

    with pytest.raises(ValueError, match="memory"):
        vault.decrypt_file(str(path), STRONG, str(tmp_path / "out"), {})


@pytest.mark.parametrize("params", [
    vault.KdfParams(3, 8, 1),          # not a power of two
    vault.KdfParams(1, 8, 1),          # below the floor
    vault.KdfParams(1 << 12, 0, 1),    # r out of range
    vault.KdfParams(1 << 12, 8, 99),   # p out of range
])
def test_check_kdf_params_rejects_nonsense(params):
    with pytest.raises(ValueError):
        vault.check_kdf_params(params)


def test_a_huge_frame_length_is_refused_before_it_is_allocated(tmp_path):
    """The length prefix comes from the file, so it cannot become a blind read."""
    header = vault.pack_header(
        vault.KdfParams(1 << 12, 8, 1), 10,
        os.urandom(16), os.urandom(16), os.urandom(8),
    )
    path = tmp_path / "greedy.enc"
    path.write_bytes(header + struct.pack(">I", 0xFFFFFFFF) + b"\x00" * 16)

    with pytest.raises(ValueError, match="out of range"):
        vault.decrypt_file(str(path), STRONG, str(tmp_path / "out"), {})


def test_a_future_format_version_is_reported_not_guessed(tmp_path):
    header = bytearray(vault.pack_header(
        vault.KdfParams(1 << 12, 8, 1), 20,
        os.urandom(16), os.urandom(16), os.urandom(8),
    ))
    header[8] = 9
    with pytest.raises(ValueError, match="newer"):
        vault.parse_header(bytes(header))


# ── partial writes ──────────────────────────────────────────────────────────
def test_atomic_write_leaves_nothing_behind_when_it_fails(tmp_path):
    target = tmp_path / "out.bin"
    with pytest.raises(RuntimeError):
        with vault._atomic_write(str(target)) as handle:
            handle.write(b"half a file")
            raise RuntimeError("boom")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_publishes_only_on_success(tmp_path):
    target = tmp_path / "out.bin"
    with vault._atomic_write(str(target)) as handle:
        handle.write(b"whole file")
        assert not target.exists()
    assert target.read_bytes() == b"whole file"
    assert [p.name for p in tmp_path.iterdir()] == ["out.bin"]


def test_no_part_files_survive_a_normal_run(tmp_path):
    enc_dir = tmp_path / "enc"
    _encrypted(tmp_path, "data", name="f.txt")
    assert not any(p.name.endswith(".part") for p in enc_dir.iterdir())


def test_a_leftover_part_file_is_never_encrypted(tmp_path):
    (tmp_path / "real.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "stale.enc.part").write_bytes(b"junk")
    targets = vault._collect_files(str(tmp_path), "encrypt", recursive=False)
    assert [os.path.basename(p) for p in targets] == ["real.txt"]


# ── what gets collected ─────────────────────────────────────────────────────
def test_collect_files_filters_by_action(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.enc").write_text("b")
    enc_targets = vault._collect_files(str(tmp_path), "encrypt", recursive=False)
    dec_targets = vault._collect_files(str(tmp_path), "decrypt", recursive=False)
    assert any(p.endswith("a.txt") for p in enc_targets)
    assert all(not p.endswith(".enc") for p in enc_targets)
    assert all(p.endswith(".enc") for p in dec_targets)


@needs_symlinks
def test_symlinks_are_skipped(tmp_path):
    """Encrypting through a link then deleting the link leaves the real file bare."""
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    inside = tmp_path / "box"
    inside.mkdir()
    (inside / "own.txt").write_text("mine", encoding="utf-8")
    os.symlink(str(outside), str(inside / "link.txt"))

    targets = vault._collect_files(str(inside), "encrypt", recursive=True)
    assert [os.path.basename(p) for p in targets] == ["own.txt"]


def test_the_output_folder_is_not_swept_up_when_it_sits_inside_the_source(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    out_dir = tmp_path / "enc"
    out_dir.mkdir()
    (out_dir / "already.txt").write_text("previous output", encoding="utf-8")

    targets = vault._collect_files(str(tmp_path), "encrypt", recursive=True,
                                   exclude_dir=str(out_dir))
    assert [os.path.basename(p) for p in targets] == ["a.txt"]


# ── originals ───────────────────────────────────────────────────────────────
def test_remove_originals_only_after_confirmation(tmp_path, accept_confirm):
    src = tmp_path / "f.txt"
    src.write_text("data")
    accept_confirm(True)
    vault.run_vault(str(src), "encrypt", STRONG, output_dir=str(tmp_path / "enc"),
                    remove_originals=True)
    assert not src.exists()
    assert (tmp_path / "enc" / "f.txt.enc").exists()


def test_declining_the_confirmation_keeps_the_originals(tmp_path, accept_confirm):
    src = tmp_path / "f.txt"
    src.write_text("data")
    accept_confirm(False)
    vault.run_vault(str(src), "encrypt", STRONG, output_dir=str(tmp_path / "enc"),
                    remove_originals=True)
    assert src.read_text() == "data"


def test_shred_overwrites_the_bytes_before_unlinking(tmp_path, monkeypatch):
    src = tmp_path / "f.txt"
    src.write_bytes(b"S" * 4096)
    seen = {}

    real_remove = os.remove

    def spy(path):
        seen["content"] = open(path, "rb").read()
        real_remove(path)

    monkeypatch.setattr(vault.os, "remove", spy)
    vault.shred_file(str(src))

    assert not src.exists()
    assert len(seen["content"]) == 4096
    assert b"SSSS" not in seen["content"]


def test_shred_implies_removing_the_originals(tmp_path, accept_confirm, monkeypatch):
    src = tmp_path / "f.txt"
    src.write_text("data")
    accept_confirm(True)
    shredded = []
    monkeypatch.setattr(vault, "shred_file", lambda p: (shredded.append(p), os.remove(p)))

    vault.run_vault(str(src), "encrypt", STRONG, output_dir=str(tmp_path / "enc"), shred=True)
    assert shredded == [str(src)]
    assert not src.exists()


# ── paths ───────────────────────────────────────────────────────────────────
def test_unique_path(tmp_path):
    p = tmp_path / "a.txt"
    assert vault._unique_path(str(p)) == str(p)
    p.write_text("x")
    assert vault._unique_path(str(p)) == str(tmp_path / "a_1.txt")


def test_out_path_encrypt_and_decrypt(tmp_path):
    src = str(tmp_path / "f.txt")
    open(src, "w").close()
    enc = vault._out_path(src, "encrypt", None)
    assert enc.endswith("f.txt.enc")
    # Decrypt in a clean dir so the restored name doesn't collide with anything.
    sub = tmp_path / "sub"
    sub.mkdir()
    src_enc = str(sub / "g.txt.enc")
    open(src_enc, "w").close()
    dec = vault._out_path(src_enc, "decrypt", None)
    assert dec.endswith("g.txt")


def test_decrypting_next_to_an_existing_file_never_overwrites_it(tmp_path):
    enc_file = _encrypted(tmp_path, "nuevo", name="f.txt")
    kept = tmp_path / "enc" / "f.txt"
    kept.write_text("no me pises", encoding="utf-8")

    assert vault.run_vault(str(enc_file), "decrypt", STRONG) is True
    assert kept.read_text(encoding="utf-8") == "no me pises"
    assert (tmp_path / "enc" / "f_1.txt").read_text(encoding="utf-8") == "nuevo"


def test_run_vault_validation_errors(tmp_path):
    assert vault.run_vault(str(tmp_path), "encrypt", "") is False          # no password
    assert vault.run_vault(str(tmp_path), "bogus", "pw") is False          # bad action
    assert vault.run_vault("/no/such/path", "encrypt", "pw") is False      # missing path


# ── passwords ───────────────────────────────────────────────────────────────
def test_derive_key_deterministic_and_salt_sensitive():
    salt = b"0123456789abcdef"
    k1 = vault._derive_key("pw", salt, 1000)
    k2 = vault._derive_key("pw", salt, 1000)
    k3 = vault._derive_key("pw", b"fedcba9876543210", 1000)
    assert k1 == k2
    assert k1 != k3


def test_the_same_password_gives_a_different_key_each_batch(tmp_path):
    params = vault.KdfParams(1 << 12, 8, 1)
    a = vault.derive_master_key(STRONG, os.urandom(16), params)
    b = vault.derive_master_key(STRONG, os.urandom(16), params)
    assert a != b and len(a) == 32


@pytest.mark.parametrize("password, weak", [
    ("Corr3cta-Bateria-Grapa!", False),
    ("corta1A!", True),
    ("todoenminusculasylargo", True),
    ("password", True),
    ("aaaaaaaaaaaaaaaa", True),
])
def test_password_problems_flags_the_weak_ones(password, weak):
    assert bool(vault.password_problems(password)) is weak


def _scripted_prompt(answers):
    """Returns a getpass-like callable that yields `answers` in order."""
    remaining = list(answers)
    calls = []

    def _prompt(label=""):
        calls.append(label)
        return remaining.pop(0)

    _prompt.calls = calls
    return _prompt


def test_prompt_password_encrypt_requires_confirmation():
    prompt = _scripted_prompt([STRONG, STRONG])
    assert vault._prompt_password("encrypt", prompt=prompt) == STRONG
    assert len(prompt.calls) == 2


def test_prompt_password_encrypt_rejects_mismatch():
    prompt = _scripted_prompt([STRONG, STRONG + "x"])
    assert vault._prompt_password("encrypt", prompt=prompt) is None
    assert len(prompt.calls) == 2


def test_prompt_password_decrypt_asks_once_and_does_not_judge():
    # A weak password on the way in is a problem; on the way out it is just
    # whatever the file was locked with.
    prompt = _scripted_prompt(["pw"])
    assert vault._prompt_password("decrypt", prompt=prompt) == "pw"
    assert len(prompt.calls) == 1


def test_prompt_password_rejects_empty():
    prompt = _scripted_prompt(["", ""])
    assert vault._prompt_password("encrypt", prompt=prompt) is None


def test_a_weak_password_has_to_be_confirmed(capsys):
    prompt = _scripted_prompt(["corta", "corta"])
    assert vault._prompt_password("encrypt", prompt=prompt, accept_weak=lambda: False) is None
    assert "weak" in capsys.readouterr().out


def test_a_weak_password_is_accepted_when_the_user_insists():
    prompt = _scripted_prompt(["corta", "corta"])
    assert vault._prompt_password("encrypt", prompt=prompt, accept_weak=lambda: True) == "corta"


def test_password_comes_from_a_file_when_asked(tmp_path):
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text(STRONG + "\n", encoding="utf-8")
    args = types.SimpleNamespace(password=None, password_file=str(pw_file), action="encrypt")
    assert vault._password_from_args(args) == STRONG


def test_an_empty_password_file_is_an_error(tmp_path):
    pw_file = tmp_path / "pw.txt"
    pw_file.write_text("\n", encoding="utf-8")
    args = types.SimpleNamespace(password=None, password_file=str(pw_file), action="encrypt")
    assert vault._password_from_args(args) is None


def test_password_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("AT_VAULT_PASSWORD", STRONG)
    args = types.SimpleNamespace(password=None, password_file=None, action="encrypt")
    assert vault._password_from_args(args) == STRONG


def test_passing_the_password_as_a_flag_warns_about_it(capsys):
    args = types.SimpleNamespace(password=STRONG, password_file=None, action="encrypt")
    assert vault._password_from_args(args) == STRONG
    assert "ps" in capsys.readouterr().out


def test_main_aborts_without_encrypting_when_confirmation_fails(tmp_path, monkeypatch, capsys):
    """A mistyped confirmation must exit non-zero and leave no .enc behind."""
    src = tmp_path / "f.txt"
    src.write_text("data")
    out_dir = tmp_path / "enc"

    monkeypatch.setattr(vault, "_prompt_password", lambda action, **kw: None)
    monkeypatch.setattr(
        sys, "argv",
        ["vault", str(src), "encrypt", "--out-dir", str(out_dir)],
    )

    with pytest.raises(SystemExit) as excinfo:
        vault.main()

    assert excinfo.value.code == 1
    assert not out_dir.exists()
    assert src.read_text() == "data"
    # The prompt already said what went wrong. Falling through into run_vault
    # would tack on a contradictory "A password is required." after it.
    assert "A password is required" not in capsys.readouterr().out

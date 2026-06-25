import os
import types

import pytest

from automation_tools.tools import vault


def test_derive_key_deterministic_and_salt_sensitive():
    salt = b"0123456789abcdef"
    k1 = vault._derive_key("pw", salt, 1000)
    k2 = vault._derive_key("pw", salt, 1000)
    k3 = vault._derive_key("pw", b"fedcba9876543210", 1000)
    assert k1 == k2
    assert k1 != k3


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


def test_collect_files_filters_by_action(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.enc").write_text("b")
    enc_targets = vault._collect_files(str(tmp_path), "encrypt", recursive=False)
    dec_targets = vault._collect_files(str(tmp_path), "decrypt", recursive=False)
    assert any(p.endswith("a.txt") for p in enc_targets)
    assert all(not p.endswith(".enc") for p in enc_targets)
    assert all(p.endswith(".enc") for p in dec_targets)


def test_encrypt_decrypt_roundtrip(tmp_path):
    src = tmp_path / "secret.txt"
    src.write_text("contenido confidencial áéí 🔐", encoding="utf-8")

    assert vault.run_vault(str(src), "encrypt", "pw123", output_dir=str(tmp_path / "enc")) is True
    enc_file = tmp_path / "enc" / "secret.txt.enc"
    assert enc_file.exists()
    # Plaintext must not leak into the ciphertext, and the header is present.
    raw = enc_file.read_bytes()
    assert raw[:8] == vault.MAGIC
    assert b"confidencial" not in raw

    assert vault.run_vault(str(enc_file), "decrypt", "pw123", output_dir=str(tmp_path / "dec")) is True
    restored = (tmp_path / "dec" / "secret.txt").read_text(encoding="utf-8")
    assert restored == "contenido confidencial áéí 🔐"


def test_decrypt_wrong_password_fails(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("data")
    vault.run_vault(str(src), "encrypt", "right", output_dir=str(tmp_path / "enc"))
    enc_file = tmp_path / "enc" / "f.txt.enc"
    ok = vault.run_vault(str(enc_file), "decrypt", "wrong", output_dir=str(tmp_path / "dec"))
    assert ok is False
    # No plaintext file produced on failure.
    assert not (tmp_path / "dec" / "f.txt").exists()


def test_decrypt_detects_tampering(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("data")
    vault.run_vault(str(src), "encrypt", "pw", output_dir=str(tmp_path / "enc"))
    enc_file = tmp_path / "enc" / "f.txt.enc"
    b = bytearray(enc_file.read_bytes())
    b[-1] ^= 0x01  # flip a bit in the ciphertext
    enc_file.write_bytes(bytes(b))
    assert vault.run_vault(str(enc_file), "decrypt", "pw", output_dir=str(tmp_path / "dec")) is False


def test_decrypt_non_vault_file(tmp_path):
    bad = tmp_path / "x.enc"
    bad.write_bytes(b"not a vault")
    assert vault.run_vault(str(bad), "decrypt", "pw", output_dir=str(tmp_path / "o")) is False


def test_run_vault_validation_errors(tmp_path):
    assert vault.run_vault(str(tmp_path), "encrypt", "") is False          # no password
    assert vault.run_vault(str(tmp_path), "bogus", "pw") is False          # bad action
    assert vault.run_vault("/no/such/path", "encrypt", "pw") is False      # missing path


def test_remove_originals_confirmed(tmp_path, monkeypatch):
    src = tmp_path / "f.txt"
    src.write_text("data")
    # questionary.confirm(...).ask() -> True
    monkeypatch.setattr(
        vault.questionary, "confirm",
        lambda *a, **k: types.SimpleNamespace(ask=lambda: True),
    )
    vault.run_vault(str(src), "encrypt", "pw", output_dir=str(tmp_path / "enc"), remove_originals=True)
    assert not src.exists()
    assert (tmp_path / "enc" / "f.txt.enc").exists()

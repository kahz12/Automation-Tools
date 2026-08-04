import sys
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


# ── password prompting ──────────────────────────────────────────────────────
# Encrypting with a mistyped password makes the data permanently unrecoverable,
# so the prompt must ask twice and require a match. Decrypting is harmless to
# get wrong (Fernet just rejects it), so it stays a single prompt.

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
    prompt = _scripted_prompt(["hunter2", "hunter2"])
    assert vault._prompt_password("encrypt", prompt=prompt) == "hunter2"
    assert len(prompt.calls) == 2


def test_prompt_password_encrypt_rejects_mismatch():
    prompt = _scripted_prompt(["hunter2", "hunter3"])
    assert vault._prompt_password("encrypt", prompt=prompt) is None
    assert len(prompt.calls) == 2


def test_prompt_password_decrypt_asks_once():
    prompt = _scripted_prompt(["hunter2"])
    assert vault._prompt_password("decrypt", prompt=prompt) == "hunter2"
    assert len(prompt.calls) == 1


def test_prompt_password_rejects_empty():
    prompt = _scripted_prompt(["", ""])
    assert vault._prompt_password("encrypt", prompt=prompt) is None


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

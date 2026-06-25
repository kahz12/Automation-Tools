import re

import pytest

from automation_tools.tools import password_generator as pg


def test_generate_password_length_and_charset():
    pw = pg.generate_password(length=20)
    assert len(pw) == 20
    assert re.search(r"[a-z]", pw)
    assert re.search(r"[A-Z]", pw)
    assert re.search(r"\d", pw)


def test_generate_password_respects_min_required_length():
    # All four types required; even length 2 must include the 4 required chars.
    pw = pg.generate_password(length=2)
    assert len(pw) == 4


def test_generate_password_no_charset_returns_none():
    assert pg.generate_password(
        use_uppercase=False, use_lowercase=False,
        use_digits=False, use_special=False,
    ) is None


def test_generate_password_exclude_ambiguous():
    pw = pg.generate_password(length=40, use_special=False, exclude_ambiguous=True)
    assert not any(c in pw for c in "Il1O0o")


def test_generate_passphrase_structure():
    phrase = pg.generate_passphrase(num_words=4, separator="-", add_number=True)
    parts = phrase.split("-")
    # 4 words + 1 trailing number group
    assert len(parts) == 5
    assert parts[-1].isdigit()


def test_calculate_entropy():
    assert pg.calculate_entropy("") == 0.0
    assert pg.calculate_entropy("aaaa") > 0
    # More variety => more entropy for same length.
    assert pg.calculate_entropy("Ab1!Ab1!") > pg.calculate_entropy("abababab")


def test_evaluate_strength_common_password():
    # Known-breached password must be rated at the bottom of the scale.
    res = pg.evaluate_strength("password")
    assert res["level"] == "Very Weak"
    assert res["score"] < 20
    assert any("common" in tip.lower() for tip in res["feedback"])


def test_evaluate_strength_strong_password():
    res = pg.evaluate_strength("Tr0ub4dor&3xKqz!Lm")
    assert res["score"] >= 60
    assert res["entropy"] > 0


def test_check_pwned_parses_k_anonymity(monkeypatch):
    import hashlib

    pwd = "hunter2"
    suffix = hashlib.sha1(pwd.encode()).hexdigest().upper()[5:]

    class FakeResp:
        status_code = 200
        text = f"{suffix}:42\r\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:1"

    # check_pwned imports `requests` locally, so patch the real module's get.
    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())
    assert pg.check_pwned(pwd) == 42


def test_check_pwned_not_found(monkeypatch):
    class FakeResp:
        status_code = 200
        text = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:1"

    monkeypatch.setattr("requests.get", lambda *a, **k: FakeResp())
    assert pg.check_pwned("whatever") == 0

"""Tests for the Dotenv & Config Manager.

Exit contract for the three actions:
  generate → True when the template was written.
  validate → True only when the .env actually matches the template. Here the
             verdict *is* the result, so it drives the exit code.
  scan     → True when the scan completed; finding .env files is the expected
             output of the report, not a failure.
"""
import sys

import pytest

from automation_tools.tools import env_manager


# ── parsing ─────────────────────────────────────────────────────────────────
def test_parse_env_file_splits_keys_and_keeps_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "API_KEY=secret123\n"
        "EMPTY=\n"
        "not a pair\n"
        "URL=https://example.com/a=b\n",
        encoding="utf-8",
    )

    parsed = env_manager._parse_env_file(str(env))
    pairs = {k: v for k, v, _ in parsed if k is not None}

    assert pairs == {
        "API_KEY": "secret123",
        "EMPTY": "",
        "URL": "https://example.com/a=b",  # only the first '=' splits
    }
    # Comments, blanks and junk lines survive as originals for reconstruction.
    originals = [orig for k, _, orig in parsed if k is None]
    assert "# a comment" in originals
    assert "not a pair" in originals


def test_parse_env_file_returns_empty_for_a_missing_file(tmp_path):
    assert env_manager._parse_env_file(str(tmp_path / "nope.env")) == []


# ── generate ────────────────────────────────────────────────────────────────
def test_generate_example_blanks_values_and_keeps_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# config\nAPI_KEY=secret123\nDB_PASS=hunter2\n", encoding="utf-8")

    assert env_manager.generate_example(str(env)) is True

    template = (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert "# config" in template
    assert "API_KEY=" in template
    assert "secret123" not in template
    assert "hunter2" not in template


def test_generate_example_honours_an_explicit_output_path(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    out = tmp_path / "custom.example"

    assert env_manager.generate_example(str(env), out_path=str(out)) is True
    assert out.read_text(encoding="utf-8").strip() == "A="


def test_generate_example_returns_false_for_an_empty_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    assert env_manager.generate_example(str(env)) is False


# ── validate ────────────────────────────────────────────────────────────────
def test_validate_returns_true_when_synchronized(tmp_path):
    (tmp_path / ".env").write_text("A=1\nB=2\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=\nB=\n", encoding="utf-8")

    assert env_manager.validate_env(str(tmp_path / ".env"), str(tmp_path / ".env.example")) is True


def test_validate_returns_false_when_a_key_is_missing(tmp_path):
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=\nB=\n", encoding="utf-8")

    assert env_manager.validate_env(str(tmp_path / ".env"), str(tmp_path / ".env.example")) is False


def test_validate_returns_false_on_an_unreadable_template(tmp_path):
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    assert env_manager.validate_env(str(tmp_path / ".env"), str(tmp_path / "nope")) is False


# ── scan ────────────────────────────────────────────────────────────────────
def test_scan_finds_env_files_and_skips_vendor_directories(tmp_path, capsys):
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    nested = tmp_path / "service"
    nested.mkdir()
    (nested / ".env.local").write_text("B=2\n", encoding="utf-8")
    vendored = tmp_path / "node_modules" / "pkg"
    vendored.mkdir(parents=True)
    (vendored / ".env").write_text("C=3\n", encoding="utf-8")

    assert env_manager.scan_envs(str(tmp_path)) is True

    out = capsys.readouterr().out
    assert "node_modules" not in out
    assert "Found 2" in out


def test_scan_reports_a_clean_tree(tmp_path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert env_manager.scan_envs(str(tmp_path)) is True


# ── dispatch ────────────────────────────────────────────────────────────────
def test_run_env_manager_rejects_a_missing_path(tmp_path):
    assert env_manager.run_env_manager("generate", str(tmp_path / "nope")) is False


def test_run_env_manager_rejects_an_unknown_action(tmp_path):
    assert env_manager.run_env_manager("explode", str(tmp_path)) is False


def test_run_env_manager_requires_a_file_for_generate(tmp_path):
    assert env_manager.run_env_manager("generate", str(tmp_path)) is False


def test_run_env_manager_requires_a_directory_for_scan(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    assert env_manager.run_env_manager("scan", str(env)) is False


def test_run_env_manager_requires_a_template_for_validate(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    assert env_manager.run_env_manager("validate", str(env)) is False


def test_main_exits_nonzero_when_validation_fails(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("A=\nB=\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "env_manager", "validate", str(tmp_path / ".env"),
        "--example", str(tmp_path / ".env.example"),
    ])

    with pytest.raises(SystemExit) as excinfo:
        env_manager.main()
    assert excinfo.value.code == 1


def test_main_exits_zero_on_success(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["env_manager", "generate", str(tmp_path / ".env")])

    with pytest.raises(SystemExit) as excinfo:
        env_manager.main()
    assert excinfo.value.code == 0

"""Shared CLI spelling and exit-code contracts."""

import pytest

from automation_tools.core.cli import ArgumentParser, exit_code, int_range


def test_parser_accepts_english_and_spanish_output_aliases():
    parser = ArgumentParser()
    parser.add_argument("--out")

    assert parser.parse_args(["--out", "a.txt"]).out == "a.txt"
    assert parser.parse_args(["--output", "b.txt"]).out == "b.txt"
    assert parser.parse_args(["--salida", "c.txt"]).out == "c.txt"


def test_parser_accepts_legacy_spanish_flag_and_english_alias():
    parser = ArgumentParser()
    parser.add_argument("--aplicar", action="store_true")

    assert parser.parse_args(["--aplicar"]).aplicar is True
    assert parser.parse_args(["--apply"]).aplicar is True


def test_parser_aliases_are_inherited_by_subcommands():
    parser = ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--export")

    assert parser.parse_args(["create", "--exportar", "report.csv"]).export == "report.csv"


@pytest.mark.parametrize(
    ("result", "expected"),
    [(None, 0), (True, 0), (False, 1), (0, 0), (1, 1), (130, 130)],
)
def test_exit_code_contract(result, expected):
    assert exit_code(result) == expected


def test_aliases_reach_options_declared_on_a_mutually_exclusive_group():
    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--continue-sequence", dest="seq", action="store_true")
    group.add_argument("--restart-sequence", dest="seq", action="store_false")
    parser.set_defaults(seq=None)

    assert parser.parse_args(["--continuar-secuencia"]).seq is True
    assert parser.parse_args(["--reiniciar-secuencia"]).seq is False
    with pytest.raises(SystemExit):
        parser.parse_args(["--continue-sequence", "--reiniciar-secuencia"])


def test_renamer_accepts_its_documented_spanish_flags(tmp_path, monkeypatch):
    from automation_tools.tools import renamer

    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr("sys.argv", ["renamer", str(tmp_path), "--mode", "patron",
                                     "--pattern", "f_{}", "--reiniciar-secuencia"])
    with pytest.raises(SystemExit) as excinfo:
        renamer.main()
    assert excinfo.value.code == 0


@pytest.mark.parametrize("bad", ["0", "-5", "101", "abc", "1.5"])
def test_int_range_makes_a_bad_value_a_usage_error(bad, capsys):
    parser = ArgumentParser()
    parser.add_argument("--quality", type=int_range(1, 100))

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--quality", bad])
    assert excinfo.value.code == 2
    assert "--quality" in capsys.readouterr().err


def test_int_range_accepts_its_bounds():
    parser = ArgumentParser()
    parser.add_argument("--quality", type=int_range(1, 100))
    parser.add_argument("--open-ended", type=int_range(1))

    assert parser.parse_args(["--quality", "1"]).quality == 1
    assert parser.parse_args(["--quality", "100"]).quality == 100
    assert parser.parse_args(["--open-ended", "99999"]).open_ended == 99999


@pytest.mark.parametrize("tool, argv", [
    ("monitor", ["--interval", "0"]),
    ("monitor", ["--interval", "-1"]),
    ("password_generator", ["generate", "--length", "0"]),
    ("password_generator", ["generate", "--count", "0"]),
    ("password_generator", ["passphrase", "--words", "0"]),
    ("image_processor", ["x", "--scale", "-5"]),
    ("image_processor", ["x", "--quality", "500"]),
    ("image_processor", ["x", "--opacity", "101"]),
    ("converter", ["x", "webp", "--quality", "500"]),
    ("space_cleaner", ["x", "--large", "-1"]),
    ("space_cleaner", ["x", "--old", "0"]),
    ("flac_check", ["x", "--seconds", "0"]),
    ("web_clipper", ["x", "--timeout", "0"]),
])
def test_out_of_range_numbers_are_refused_before_anything_runs(tool, argv, monkeypatch):
    import importlib

    module = importlib.import_module(f"automation_tools.tools.{tool}")
    monkeypatch.setattr("sys.argv", [tool, *argv])
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == 2

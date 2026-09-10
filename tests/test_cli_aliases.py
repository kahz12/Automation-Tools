"""Shared CLI spelling and exit-code contracts."""

import pytest

from automation_tools.core.cli import ArgumentParser, exit_code


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

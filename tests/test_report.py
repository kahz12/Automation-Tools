"""Tests for the shared report writer.

Four tools used to carry their own copy of this, with different ideas about
which errors to catch. These are the guarantees they all relied on.
"""
import csv

from automation_tools.core import report


def test_export_rows_writes_a_header_and_every_row(tmp_path):
    out = tmp_path / "r.csv"
    assert report.export_rows(str(out), ["a", "b"], [[1, 2], [3, 4]]) is True
    assert list(csv.reader(open(out, encoding="utf-8"))) == [
        ["a", "b"], ["1", "2"], ["3", "4"],
    ]


def test_export_rows_accepts_a_generator(tmp_path):
    out = tmp_path / "r.csv"
    report.export_rows(str(out), ["n"], ([i] for i in range(3)))
    assert out.read_text(encoding="utf-8").count("\n") == 4


def test_export_rows_writes_no_stray_blank_lines(tmp_path):
    """Without newline="" the csv module doubles the line ending on Windows."""
    out = tmp_path / "r.csv"
    report.export_rows(str(out), ["a"], [["x"], ["y"]])
    raw = out.read_bytes()
    assert b"\r\r" not in raw and b"\n\n" not in raw
    assert list(csv.reader(open(out, encoding="utf-8"))) == [["a"], ["x"], ["y"]]


def test_export_rows_reports_a_bad_destination(tmp_path, capsys):
    assert report.export_rows(str(tmp_path / "missing" / "r.csv"), ["a"], []) is False
    assert "Could not export" in capsys.readouterr().out


def test_export_json_round_trips(tmp_path):
    import json
    out = tmp_path / "r.json"
    assert report.export_json(str(out), {"k": "áé", "n": 1}) is True
    assert json.loads(out.read_text(encoding="utf-8")) == {"k": "áé", "n": 1}


def test_export_json_reports_unserialisable_data(tmp_path, capsys):
    assert report.export_json(str(tmp_path / "r.json"), {"k": object()}) is False
    assert "Could not export" in capsys.readouterr().out


def test_is_csv_looks_at_the_extension():
    assert report.is_csv("/tmp/a.CSV") is True
    assert report.is_csv("/tmp/a.json") is False

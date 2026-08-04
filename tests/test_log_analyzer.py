"""Tests for the Log Analyzer.

Log files are routinely gigabytes in size, so the analyzer has to stream: the
memory it uses must depend on the size of a single line, not on how many
matches it finds.
"""
import tracemalloc

from automation_tools.tools import log_analyzer


# ── behaviour ───────────────────────────────────────────────────────────────
def test_reports_matching_lines(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("all good\nERROR disk full\nstill fine\nERROR again\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords="ERROR", out_path=str(out))

    report = out.read_text(encoding="utf-8")
    assert "Total matches found: 2" in report
    assert "disk full" in report
    assert "ERROR again" in report
    assert "all good" not in report


def test_ignore_case_can_be_disabled(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("error lowercase\nERROR uppercase\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords="ERROR", ignore_case=False, out_path=str(out))

    assert "Total matches found: 1" in out.read_text(encoding="utf-8")


def test_multiple_keywords_are_comma_separated(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("WARN slow\nERROR bad\nINFO fine\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords="ERROR,WARN", out_path=str(out))

    assert "Total matches found: 2" in out.read_text(encoding="utf-8")


def test_a_line_matching_two_patterns_counts_once(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("ERROR and WARN on one line\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords="ERROR,WARN", out_path=str(out))

    assert "Total matches found: 1" in out.read_text(encoding="utf-8")


def test_regex_mode(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("code=404 missing\ncode=200 ok\ncode=500 boom\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords=r"code=[45]\d\d", use_regex=True, out_path=str(out))

    report = out.read_text(encoding="utf-8")
    assert "Total matches found: 2" in report
    assert "code=200" not in report


def test_invalid_regex_is_reported_and_writes_nothing(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("anything\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(log), keywords="([unclosed", use_regex=True, out_path=str(out))

    assert not out.exists()


def test_scans_log_files_in_a_directory(tmp_path):
    (tmp_path / "a.log").write_text("ERROR one\n", encoding="utf-8")
    (tmp_path / "b.log").write_text("ERROR two\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ERROR ignored\n", encoding="utf-8")
    out = tmp_path / "report.txt"

    log_analyzer.run_log_analyzer(str(tmp_path), keywords="ERROR", out_path=str(out))

    report = out.read_text(encoding="utf-8")
    assert "Total matches found: 2" in report
    assert "ignored" not in report


# ── the actual defect ───────────────────────────────────────────────────────
def test_memory_does_not_grow_with_the_number_of_matches(tmp_path):
    """A log with many matches must not be buffered whole in memory."""
    log = tmp_path / "big.log"
    line = "2026-01-01 12:00:00 ERROR something went wrong in the subsystem\n"
    log.write_text(line * 50_000, encoding="utf-8")
    out = tmp_path / "report.txt"

    tracemalloc.start()
    try:
        log_analyzer.run_log_analyzer(str(log), keywords="ERROR", out_path=str(out))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    # Buffering 50k matches twice (console list + report list) costs several MB.
    # Streaming keeps the working set to roughly one line at a time.
    assert peak < 1_000_000, f"peak memory was {peak} bytes — matches are still being buffered"
    # …and streaming must not lose anything.
    assert "Total matches found: 50000" in out.read_text(encoding="utf-8")

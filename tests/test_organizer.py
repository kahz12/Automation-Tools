import pytest

from automation_tools.tools import organizer


def test_get_target_category():
    assert organizer.get_target_category("photo.JPG") == "Imágenes"
    assert organizer.get_target_category("doc.pdf") == "Documentos"
    assert organizer.get_target_category("clip.mp4") == "Videos"
    assert organizer.get_target_category("mystery.xyz") == "Otros"


def test_resolve_collision(tmp_path):
    dst = tmp_path / "f.txt"
    # No collision -> returned as-is.
    assert organizer._resolve_collision(str(dst), "rename") == str(dst)
    dst.write_text("x")
    assert organizer._resolve_collision(str(dst), "skip") is None
    assert organizer._resolve_collision(str(dst), "overwrite") == str(dst)
    assert organizer._resolve_collision(str(dst), "rename") == str(tmp_path / "f_1.txt")


def test_run_download_organizer_and_undo(tmp_path, monkeypatch):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    history = tmp_path / "history"
    monkeypatch.setattr(organizer, "get_downloads_folder", lambda: str(downloads))
    monkeypatch.setattr(organizer, "HISTORY_DIR", str(history))

    (downloads / "pic.jpg").write_text("x")
    (downloads / "notes.pdf").write_text("y")

    organizer.run_download_organizer()
    assert (downloads / "Imágenes" / "pic.jpg").exists()
    assert (downloads / "Documentos" / "notes.pdf").exists()
    assert not (downloads / "pic.jpg").exists()

    # A history file was recorded; undo restores the originals.
    files = organizer.list_history()
    assert files
    organizer.undo_last()
    assert (downloads / "pic.jpg").exists()
    assert not (downloads / "Imágenes" / "pic.jpg").exists()


def test_partial_undo_keeps_history_for_retry(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    monkeypatch.setattr(organizer, "HISTORY_DIR", str(history_dir))

    first_src = tmp_path / "first.txt"
    second_src = tmp_path / "second.txt"
    first_dst = tmp_path / "moved-first.txt"
    second_dst = tmp_path / "moved-second.txt"
    first_dst.write_text("first")
    second_src.write_text("blocking destination")
    second_dst.write_text("second")
    history = organizer._save_history(
        [
            {"from": str(first_src), "to": str(first_dst)},
            {"from": str(second_src), "to": str(second_dst)},
        ],
        str(tmp_path),
    )
    assert history is not None

    # The first move succeeds; the second is blocked by an existing source.
    first_dst.rename(first_src)
    organizer.undo_from_file(history)

    assert first_src.exists()
    assert second_dst.exists()
    assert organizer.list_history() == [history]


def _with_a_full_folder(tmp_path, monkeypatch):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "report.pdf").write_text("x")
    monkeypatch.setattr(organizer, "get_downloads_folder", lambda: str(downloads))
    monkeypatch.setattr(organizer, "HISTORY_DIR", str(tmp_path / "history"))
    return downloads


@pytest.mark.parametrize("flag, code", [("--help", 0), ("--no-such-flag", 2), ("-x", 2)])
def test_a_flag_it_does_not_run_on_never_moves_anything(tmp_path, monkeypatch, flag, code):
    """`atools organizer --help` used to reorganize the whole Downloads folder."""
    downloads = _with_a_full_folder(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.argv", ["atools organizer", flag])

    with pytest.raises(SystemExit) as excinfo:
        organizer.main()

    assert excinfo.value.code == code
    assert sorted(p.name for p in downloads.iterdir()) == ["report.pdf"]


def test_the_command_line_can_undo_a_run(tmp_path, monkeypatch):
    downloads = _with_a_full_folder(tmp_path, monkeypatch)

    monkeypatch.setattr("sys.argv", ["atools organizer"])
    with pytest.raises(SystemExit) as excinfo:
        organizer.main()
    assert excinfo.value.code == 0
    assert (downloads / "Documentos" / "report.pdf").exists()

    monkeypatch.setattr("sys.argv", ["atools organizer", "--undo"])
    with pytest.raises(SystemExit) as excinfo:
        organizer.main()
    assert excinfo.value.code == 0
    assert (downloads / "report.pdf").exists()


def test_the_policy_flag_reaches_the_tool(tmp_path, monkeypatch):
    downloads = _with_a_full_folder(tmp_path, monkeypatch)
    (downloads / "Documentos").mkdir()
    (downloads / "Documentos" / "report.pdf").write_text("already here")

    monkeypatch.setattr("sys.argv", ["atools organizer", "--policy", "skip"])
    with pytest.raises(SystemExit):
        organizer.main()

    assert (downloads / "report.pdf").exists()
    assert (downloads / "Documentos" / "report.pdf").read_text() == "already here"


def test_a_failed_move_is_a_failed_run(tmp_path, monkeypatch):
    _with_a_full_folder(tmp_path, monkeypatch)

    def refuse(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(organizer.shutil, "move", refuse)
    assert organizer.run_download_organizer() is False


def test_undo_reports_whether_everything_came_back(tmp_path, monkeypatch):
    downloads = _with_a_full_folder(tmp_path, monkeypatch)
    assert organizer.run_download_organizer() is True
    (downloads / "report.pdf").write_text("a new file took the old name")

    assert organizer.undo_last() is False

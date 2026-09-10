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

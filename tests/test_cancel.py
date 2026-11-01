"""Cancel has to stop the tool and leave things consistent.

The first half tests the mechanism. The second runs each tool for real on real
files and looks at what is on disk afterwards, because stopping is the easy
part: the bugs live in what a run leaves behind when it stops halfway.
"""
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import zipfile

import pytest
from PIL import Image

from automation_tools.ai.gemini import GeminiProvider
from automation_tools.ai.registry import PROVIDERS
from automation_tools.ai.retry import with_retry
from automation_tools.core import cancel
from automation_tools.tools import (
    archiver,
    converter,
    duplicate_finder,
    env_manager,
    file_type,
    flac_check,
    image_processor,
    integrity,
    log_analyzer,
    monitor,
    ocr,
    organizer,
    pdf_builder,
    pdf_toolkit,
    readme_generator,
    renamer,
    similar_images,
    space_cleaner,
    summarizer,
    translator,
    vault,
    web_clipper,
    youtube_downloader,
)

posix_only = pytest.mark.skipif(os.name != "posix", reason="needs POSIX process groups")


@pytest.fixture
def event():
    return threading.Event()


@pytest.fixture
def stop_after(monkeypatch):
    """Arms a cancel that fires once `points` cancellation points have passed."""
    def arm(points):
        trigger = threading.Event()
        passed = [0]
        real = cancel.check

        def counting():
            passed[0] += 1
            if passed[0] > points:
                trigger.set()
            real()

        monkeypatch.setattr(cancel, "check", counting)
        return cancel.scope(trigger)
    return arm


def _fires_soon(event, delay=0.1):
    timer = threading.Timer(delay, event.set)
    timer.daemon = True
    timer.start()
    return timer


def _fires_once(signal, event):
    """Cancels as soon as `signal` says the tool has reached the blocking part."""
    def wait():
        if signal.wait(30):
            event.set()

    threading.Thread(target=wait, daemon=True).start()


def _quick(started, limit=4.0):
    assert time.monotonic() - started < limit


# ── The mechanism ────────────────────────────────────────────────────────────
def test_with_no_front_end_everything_is_a_plain_call():
    assert cancel.active() is False
    assert cancel.requested() is False
    cancel.check()
    cancel.sleep(0)
    assert cancel.interruptible(threading.get_ident) == threading.get_ident()


def test_check_raises_only_once_asked(event):
    with cancel.scope(event):
        assert cancel.active() is True
        cancel.check()
        event.set()
        assert cancel.requested() is True
        with pytest.raises(cancel.Cancelled):
            cancel.check()


def test_a_cancel_goes_straight_through_except_exception(event):
    """Every per-file try block in the toolkit is written like this one."""
    event.set()
    reached = []
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        try:
            cancel.check()
        except Exception:
            reached.append("swallowed as one more bad file")
    assert reached == []


def test_the_scope_is_undone_on_the_way_out(event):
    outer = threading.Event()
    with cancel.scope(outer):
        with cancel.scope(event):
            event.set()
            assert cancel.requested() is True
        assert cancel.requested() is False
    assert cancel.active() is False


def test_sleep_is_cut_short(event):
    _fires_soon(event)
    started = time.monotonic()
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        cancel.sleep(60)
    _quick(started)


def test_sleep_runs_its_course_when_nothing_cancels(event):
    with cancel.scope(event):
        cancel.sleep(0.01)


def test_a_read_through_checked_is_a_cancellation_point(event, tmp_path):
    path = tmp_path / "data"
    path.write_bytes(b"12345678")
    with open(path, "rb") as handle, cancel.scope(event):
        wrapped = cancel.checked(handle)
        assert wrapped.read(4) == b"1234"
        event.set()
        with pytest.raises(cancel.Cancelled):
            wrapped.read(4)


def test_interruptible_hands_back_the_result_and_the_error(event):
    with cancel.scope(event):
        assert cancel.interruptible(lambda: 5) == 5
        with pytest.raises(KeyError):
            cancel.interruptible(lambda: {}["missing"])


def test_interruptible_never_starts_once_cancelled(event):
    """A batch of AI requests must not send, and pay for, the next one."""
    event.set()
    started = []
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        cancel.interruptible(lambda: started.append(1))
    assert started == []


def test_interruptible_walks_away_and_tidies_up_what_arrives_late(event):
    release = threading.Event()
    tidied = []
    done = threading.Event()

    def blocked():
        release.wait(30)
        return "late result"

    def tidy(result):
        tidied.append(result)
        done.set()

    _fires_soon(event)
    started = time.monotonic()
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        cancel.interruptible(blocked, on_abandoned=tidy)
    _quick(started)
    assert tidied == []

    release.set()
    assert done.wait(5)
    assert tidied == ["late result"]


def test_run_is_subprocess_run_on_the_command_line(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return "finished"

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert cancel.run(["x"], check=True, on_line=print) == "finished"
    # The terminal stays with the child: nothing about its stdio is touched.
    assert seen == {"command": ["x"], "check": True, "timeout": None}


def test_run_returns_what_subprocess_run_would(event):
    with cancel.scope(event):
        done = cancel.run([sys.executable, "-c", "print('out')"],
                          stdout=subprocess.PIPE, text=True)
    assert (done.returncode, done.stdout.strip()) == (0, "out")


def test_run_keeps_the_check_and_timeout_contracts(event):
    with cancel.scope(event):
        with pytest.raises(subprocess.CalledProcessError) as excinfo:
            cancel.run([sys.executable, "-c", "raise SystemExit(3)"], check=True)
        assert excinfo.value.returncode == 3

        with pytest.raises(subprocess.TimeoutExpired):
            cancel.run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=0.3)


def test_run_gives_the_child_no_keyboard(event):
    """It would otherwise read the keys meant for the app."""
    with cancel.scope(event):
        done = cancel.run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
                          stdout=subprocess.PIPE, text=True)
    assert done.stdout.strip() == "''"


def test_run_streams_output_through_the_app(event):
    lines = []
    script = "import sys; print('one'); print(); print('two', file=sys.stderr)"
    with cancel.scope(event):
        cancel.run([sys.executable, "-c", script], on_line=lines.append)
    assert sorted(lines) == ["one", "two"]


def test_run_kills_the_process_when_cancelled(event):
    _fires_soon(event, 0.3)
    started = time.monotonic()
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        cancel.run([sys.executable, "-c", "import time; time.sleep(60)"])
    _quick(started)


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:  # An orphan nobody reaped yet is a zombie, and a zombie is not running.
        return pathlib.Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


@posix_only
def test_run_takes_the_children_with_it(event, tmp_path):
    """yt-dlp's ffmpeg, LibreOffice behind its launcher."""
    pidfile = tmp_path / "child.pid"
    script = (
        "import subprocess, sys, time, pathlib\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pidfile)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )

    def fire_once_written():
        while not pidfile.exists() or not pidfile.read_text():
            time.sleep(0.02)
        event.set()

    threading.Thread(target=fire_once_written, daemon=True).start()
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        cancel.run([sys.executable, "-c", script])

    child = int(pidfile.read_text())
    deadline = time.monotonic() + 5
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(child)


def test_nothing_new_blocks_where_cancel_cannot_reach():
    """Anything that waits has to go through core.cancel, or Cancel hangs on it.

    The two exceptions are not waits worth interrupting: the clipboard helper
    returns at once, and Instagram watches its own process.
    """
    allowed = {"password_generator.py", "instagram_downloader.py"}
    pattern = re.compile(r"\bsubprocess\.run\(|\btime\.sleep\(")
    tools = pathlib.Path(archiver.__file__).parent
    offenders = [
        path.name for path in tools.glob("*.py")
        if path.name not in allowed and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


# ── Files: nothing half-written, nothing lost ────────────────────────────────
@pytest.mark.parametrize("fmt, name", [("zip", "backup.zip"), ("tar.gz", "backup.tar.gz")])
def test_a_cancelled_archive_keeps_the_backup_already_there(tmp_path, stop_after, fmt, name):
    """Opening an archive empties it, so this used to cost the previous backup."""
    source = tmp_path / "data"
    source.mkdir()
    # Random, and big enough to be read in several chunks: this stops mid-file.
    (source / "big.bin").write_bytes(os.urandom(4 * 1024 * 1024))
    output = tmp_path / name
    output.write_bytes(b"last night's backup")
    entries = archiver.collect_entries([str(source)])

    with stop_after(1), pytest.raises(cancel.Cancelled):
        archiver.create_archive(entries, str(output), fmt)

    assert output.read_bytes() == b"last night's backup"
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(["data", name])


def _archive_with(tmp_path, content):
    path = tmp_path / "in.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("first.bin", content)
        zf.writestr("second.txt", "second")
    return path


def test_a_cancelled_extraction_cannot_ruin_the_file_it_was_replacing(tmp_path, stop_after):
    archive = _archive_with(tmp_path, os.urandom(1024 * 1024))
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "first.bin").write_bytes(b"precious")

    with stop_after(2), pytest.raises(cancel.Cancelled):
        archiver.extract_archive(str(archive), str(dest), overwrite=True)

    assert (dest / "first.bin").read_bytes() == b"precious"
    assert [p.name for p in dest.iterdir()] == ["first.bin"]


def test_a_cancelled_extraction_says_how_far_it_got(tmp_path, stop_after, capsys):
    archive = _archive_with(tmp_path, b"small")

    # Past the first member (one check for it, two reads), then stop on the next.
    with stop_after(4), pytest.raises(cancel.Cancelled):
        archiver.extract_archive(str(archive), str(tmp_path / "out"))

    assert "1 file(s) had already been extracted" in capsys.readouterr().out.replace("\n", " ")


def _downloads(tmp_path, monkeypatch, count=4):
    folder = tmp_path / "downloads"
    folder.mkdir()
    for index in range(count):
        (folder / f"file{index}.pdf").write_text("x")
    monkeypatch.setattr(organizer, "get_downloads_folder", lambda: str(folder))
    monkeypatch.setattr(organizer, "HISTORY_DIR", str(tmp_path / "history"))
    return folder


def test_a_cancelled_organize_can_still_be_undone(tmp_path, monkeypatch, event):
    """Files that have moved with no history have no way back."""
    folder = _downloads(tmp_path, monkeypatch)
    real_move = organizer.shutil.move

    def move_then_cancel(src, dst):
        real_move(src, dst)
        event.set()

    monkeypatch.setattr(organizer.shutil, "move", move_then_cancel)
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        organizer.run_download_organizer()
    monkeypatch.setattr(organizer.shutil, "move", real_move)

    assert len(list((folder / "Documentos").iterdir())) == 1
    assert organizer.undo_last() is True
    assert len(list(folder.glob("*.pdf"))) == 4


def test_a_ctrl_c_during_organize_can_be_undone_too(tmp_path, monkeypatch):
    folder = _downloads(tmp_path, monkeypatch)
    real_move = organizer.shutil.move
    moved = []

    def move_then_interrupt(src, dst):
        if moved:
            raise KeyboardInterrupt
        moved.append(src)
        real_move(src, dst)

    monkeypatch.setattr(organizer.shutil, "move", move_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        organizer.run_download_organizer()
    monkeypatch.setattr(organizer.shutil, "move", real_move)

    assert organizer.undo_last() is True
    assert len(list(folder.glob("*.pdf"))) == 4


def test_undoing_can_be_cancelled_and_finished_later(tmp_path, monkeypatch, event):
    folder = _downloads(tmp_path, monkeypatch)
    assert organizer.run_download_organizer() is True
    real_move = organizer.shutil.move

    def move_then_cancel(src, dst):
        real_move(src, dst)
        event.set()

    monkeypatch.setattr(organizer.shutil, "move", move_then_cancel)
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        organizer.undo_last()
    monkeypatch.setattr(organizer.shutil, "move", real_move)

    assert len(list(folder.glob("*.pdf"))) == 1
    organizer.undo_last()
    assert len(list(folder.glob("*.pdf"))) == 4


def test_planning_a_rename_can_be_cancelled(tmp_path, stop_after):
    """Reading EXIF dates off a big folder is slow long before anything moves."""
    (tmp_path / "a.txt").write_text("x")

    with stop_after(0), pytest.raises(cancel.Cancelled):
        renamer.run_massive_rename(str(tmp_path), mode="fecha")


def test_a_cancelled_rename_stops_and_says_where(tmp_path, monkeypatch, event, capsys):
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("x")
    real_rename = os.rename

    def rename_then_cancel(src, dst):
        real_rename(src, dst)
        event.set()

    monkeypatch.setattr(renamer.os, "rename", rename_then_cancel)
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        renamer.run_massive_rename(str(tmp_path), mode="patron", pattern="f_{}",
                                   apply_changes=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.txt", "c.txt", "f_1.txt"]
    assert "1/3 files had already been renamed" in capsys.readouterr().out


def _delete_then_cancel(module, monkeypatch, event):
    real_remove = os.remove

    def remove(path):
        real_remove(path)
        event.set()

    monkeypatch.setattr(module.os, "remove", remove)


def test_duplicate_deletion_stops_between_files(tmp_path, monkeypatch, event):
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("same")
    _delete_then_cancel(duplicate_finder, monkeypatch, event)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        duplicate_finder.run_duplicate_finder(str(tmp_path), auto_delete=True)

    assert len(list(tmp_path.iterdir())) == 2


def test_hashing_a_large_duplicate_stops_mid_file(tmp_path, stop_after):
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * (1024 * 1024))

    with stop_after(1), pytest.raises(cancel.Cancelled):
        duplicate_finder.hash_file(str(path))


def test_similar_image_deletion_stops_between_files(tmp_path, monkeypatch, event):
    for name in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (64, 64), (200, 10, 10)).save(tmp_path / name)
    _delete_then_cancel(similar_images, monkeypatch, event)
    monkeypatch.setattr(similar_images.prompt, "confirm", lambda *_a, **_k: True)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        similar_images.run_similar_images(str(tmp_path), apply=True)

    assert len(list(tmp_path.iterdir())) == 2


def test_comparing_many_photos_can_be_cancelled(stop_after):
    images = [similar_images.ImageInfo(f"{index}.png", 1 << index, 1, 1, 1)
              for index in range(6)]

    with stop_after(2), pytest.raises(cancel.Cancelled):
        similar_images.group_similar(images, threshold=1)


def test_space_cleaner_stops_between_items(tmp_path, monkeypatch, event):
    for name in ("a.tmp", "b.tmp", "c.tmp"):
        (tmp_path / name).write_text("x")
    _delete_then_cancel(space_cleaner, monkeypatch, event)
    monkeypatch.setattr(space_cleaner.prompt, "confirm", lambda *_a, **_k: True)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        space_cleaner.run_space_cleaner(str(tmp_path), find_large=False, find_old=False,
                                        apply=True)

    assert len(list(tmp_path.iterdir())) == 2


def test_a_cancelled_scan_stops_early(tmp_path, stop_after):
    for index in range(20):
        (tmp_path / f"{index}.txt").write_text("x")

    for scan in (
        lambda: space_cleaner.scan(str(tmp_path)),
        lambda: file_type.run_file_type_check(str(tmp_path)),
        lambda: env_manager.scan_envs(str(tmp_path)),
        lambda: flac_check.run_flac_check(str(tmp_path)),
        lambda: readme_generator.get_project_tree(str(tmp_path)),
    ):
        with stop_after(0), pytest.raises(cancel.Cancelled):
            scan()


# ── The vault: the original survives until its copy is whole ─────────────────
@pytest.fixture
def fast_vault(monkeypatch):
    monkeypatch.setattr(vault, "SCRYPT_N", 1 << 4)
    monkeypatch.setattr(vault.prompt, "confirm", lambda *_a, **_k: True)


def test_a_file_cancelled_mid_encryption_stays_as_it_was(tmp_path, stop_after, fast_vault):
    source = tmp_path / "video.bin"
    source.write_bytes(os.urandom(3 * (1 << 20)))
    before = source.read_bytes()
    params = vault.KdfParams(vault.SCRYPT_N, vault.SCRYPT_R, vault.SCRYPT_P)
    salt = os.urandom(vault.SALT_LEN)
    key = vault.derive_master_key("password", salt, params)

    with stop_after(1), pytest.raises(cancel.Cancelled):
        vault.encrypt_file(str(source), key, salt, params, str(source) + ".enc")

    assert source.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["video.bin"]


def test_the_vault_starts_no_new_file_once_cancelled(tmp_path, monkeypatch, event, fast_vault):
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(name)
    started = []

    def encrypt(src, *_args):
        started.append(src)
        event.set()

    monkeypatch.setattr(vault, "encrypt_file", encrypt)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        vault.run_vault(str(tmp_path), "encrypt", "password")

    assert len(started) == 1


def test_a_cancelled_vault_never_deletes_an_unencrypted_original(tmp_path, monkeypatch, event, fast_vault):
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text(name)
    _delete_then_cancel(vault, monkeypatch, event)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        vault.run_vault(str(tmp_path), "encrypt", "password", remove_originals=True)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.txt.enc", "b.txt"]


def test_a_file_cancelled_mid_decryption_leaves_no_plaintext(tmp_path, stop_after, fast_vault):
    source = tmp_path / "secret.bin"
    source.write_bytes(os.urandom(3 * (1 << 20)))
    assert vault.run_vault(str(source), "encrypt", "password", remove_originals=True)
    sealed = tmp_path / "secret.bin.enc"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        vault.decrypt_file(str(sealed), "password", str(source), {})

    assert [p.name for p in tmp_path.iterdir()] == ["secret.bin.enc"]


# ── Conversions ──────────────────────────────────────────────────────────────
def _images(folder, count=3):
    folder.mkdir()
    for index in range(count):
        Image.new("RGB", (32, 32), (index * 40, 0, 0)).save(folder / f"{index}.png")
    return folder


def test_a_conversion_stops_between_images(tmp_path, stop_after):
    folder = _images(tmp_path / "in")

    with stop_after(1), pytest.raises(cancel.Cancelled):
        converter.run_image_converter(str(folder), "jpg")

    assert len(list(folder.glob("*.jpg"))) == 1


def test_rendering_a_pdf_stops_between_pages(tmp_path, monkeypatch, stop_after):
    pages = _images(tmp_path / "staging")
    source = tmp_path / "doc.pdf"
    source.write_bytes(b"%PDF")
    module = type(sys)("pdf2image")
    module.convert_from_path = lambda *_a, **_k: sorted(str(p) for p in pages.iterdir())
    monkeypatch.setitem(sys.modules, "pdf2image", module)

    with stop_after(2), pytest.raises(cancel.Cancelled):
        converter.run_pdf_to_image(str(source))

    assert len(list((tmp_path / "doc_pages").iterdir())) == 1


def test_a_batch_of_images_stops_between_images(tmp_path, stop_after):
    folder = _images(tmp_path / "in")

    with stop_after(5), pytest.raises(cancel.Cancelled):
        image_processor.run_batch_image_processor(str(folder), max_size=8)

    # The scan took the first checks; the batch got through fewer than all three.
    assert len(list((folder / "processed").iterdir())) < 3


def test_a_cancelled_merge_writes_no_output(tmp_path, stop_after, make_pdf):
    one = make_pdf(tmp_path / "one.pdf")
    two = make_pdf(tmp_path / "two.pdf")
    out = tmp_path / "merged.pdf"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        pdf_toolkit.run_pdf_merge(f"{one},{two}", str(out))

    assert not out.exists()


def test_a_cancelled_split_stops_between_pages(tmp_path, stop_after, make_pdf):
    source = make_pdf(tmp_path / "doc.pdf", pages=5)
    out = tmp_path / "pages"

    with stop_after(2), pytest.raises(cancel.Cancelled):
        pdf_toolkit.run_pdf_split(source, output_dir=str(out))

    assert len(list(out.iterdir())) == 2


@pytest.mark.parametrize("operation", ["extract", "rotate"])
def test_cancelled_page_operations_write_no_output(tmp_path, stop_after, make_pdf, operation):
    source = make_pdf(tmp_path / "doc.pdf", pages=5)
    out = tmp_path / "out.pdf"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        if operation == "extract":
            pdf_toolkit.run_pdf_extract(source, "1-5", output_path=str(out))
        else:
            pdf_toolkit.run_pdf_rotate(source, 90, output_path=str(out))

    assert not out.exists()


def test_a_cancelled_pdf_build_writes_no_output(tmp_path, stop_after):
    folder = _images(tmp_path / "in")
    out = tmp_path / "album.pdf"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        pdf_builder.images_to_pdf(sorted(str(p) for p in folder.iterdir()), str(out))

    assert not out.exists()


def test_a_cancelled_pdf_merge_writes_no_output(tmp_path, stop_after):
    one, two = tmp_path / "a.txt", tmp_path / "b.txt"
    one.write_text("uno")
    two.write_text("dos")
    out = tmp_path / "joined.pdf"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        pdf_builder.merge_to_pdf([str(one), str(two)], str(out), use_libreoffice=False)

    assert not out.exists()


def test_merging_ready_made_pdfs_stops_between_inputs(tmp_path, stop_after, make_pdf):
    """Nothing is rendered here, so only the loop itself can notice."""
    one = make_pdf(tmp_path / "one.pdf")
    two = make_pdf(tmp_path / "two.pdf")
    out = tmp_path / "joined.pdf"

    with stop_after(1), pytest.raises(cancel.Cancelled):
        pdf_builder.merge_to_pdf([one, two], str(out), use_libreoffice=False)

    assert not out.exists()


def test_a_long_document_stops_between_blocks(tmp_path, stop_after):
    blocks = [pdf_builder.Block("p", "paragraph") for _ in range(10)]
    out = tmp_path / "long.pdf"

    with stop_after(3), pytest.raises(cancel.Cancelled):
        pdf_builder.render_pdf(blocks, str(out))

    assert not out.exists()


def _fake_program(path, body="sleep 60"):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return str(path)


@posix_only
def test_a_stuck_libreoffice_is_killed(tmp_path, event):
    binary = _fake_program(tmp_path / "soffice")
    source = tmp_path / "doc.docx"
    source.write_text("x")
    _fires_soon(event, 0.2)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        pdf_builder.convert_with_libreoffice(binary, str(source), str(tmp_path / "o.pdf"))

    _quick(started)


# ── Hashing and logs ─────────────────────────────────────────────────────────
def test_a_cancelled_manifest_is_not_written(tmp_path, stop_after):
    for index in range(5):
        (tmp_path / f"{index}.txt").write_text("x")

    # Five for the walk, then stopped partway through hashing the files.
    with stop_after(7), pytest.raises(cancel.Cancelled):
        integrity.run_integrity("create", str(tmp_path))

    assert not (tmp_path / "checksums.sha256").exists()


def test_hashing_a_large_file_stops_mid_file(tmp_path, stop_after):
    path = tmp_path / "big.bin"
    path.write_bytes(b"x" * (1024 * 1024))

    with stop_after(1), pytest.raises(cancel.Cancelled):
        integrity.hash_file(str(path), "sha256")


def test_a_cancelled_verify_stops(tmp_path, stop_after):
    (tmp_path / "a.txt").write_text("x")
    assert integrity.run_integrity("create", str(tmp_path))

    with stop_after(0), pytest.raises(cancel.Cancelled):
        integrity.run_integrity("verify", str(tmp_path))


def test_a_cancelled_log_report_is_marked_incomplete(tmp_path, stop_after):
    log = tmp_path / "app.log"
    log.write_text("ERROR one\nERROR two\nERROR three\n")
    report = tmp_path / "report.txt"

    with stop_after(2), pytest.raises(cancel.Cancelled):
        log_analyzer.run_log_analyzer(str(log), "ERROR", out_path=str(report))

    text = report.read_text()
    assert "ERROR one" in text
    assert "ERROR three" not in text
    assert "incomplete" in text


# ── Audio: ffmpeg does the work, so ffmpeg has to die ────────────────────────
@posix_only
def test_a_stuck_ffmpeg_is_killed_while_measuring(tmp_path, event):
    ffmpeg = _fake_program(tmp_path / "ffmpeg")
    source = tmp_path / "a.flac"
    source.write_bytes(b"x")
    _fires_soon(event, 0.2)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        flac_check.write_spectrogram(str(source), str(tmp_path / "a.png"), ffmpeg)

    _quick(started)


@posix_only
def test_a_stuck_ffmpeg_is_killed_while_decoding(tmp_path, event):
    pidfile = tmp_path / "pid"
    ffmpeg = _fake_program(tmp_path / "ffmpeg", f"echo $$ > {pidfile}\nexec sleep 60")
    source = tmp_path / "a.flac"
    source.write_bytes(b"x")
    stream = flac_check.StreamInfo(44100, 2, 16, 44100, "d41d8cd98f00b204e9800998ecf8427e")
    _fires_soon(event, 0.3)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        flac_check.verify_md5(str(source), stream, ffmpeg)

    _quick(started)
    assert not _alive(int(pidfile.read_text()))


# ── AI: walk away from the request, never start the next one ─────────────────
class _SlowProvider:
    """Answers the way a real adapter does, through `with_retry`."""

    name = "slow"

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.requests = 0
        self.stuck = threading.Event()
        self.release = threading.Event()

    def _ask(self):
        self.requests += 1
        if self.answers:
            return self.answers.pop(0)
        self.stuck.set()
        self.release.wait(30)
        return "too late"

    def generate_text(self, _prompt, system=None):
        return with_retry(self._ask, label="Slow")

    def generate_vision(self, _prompt, _image, _mime):
        return with_retry(self._ask, label="Slow")


def test_reading_a_long_pdf_for_a_summary_can_be_cancelled(tmp_path, stop_after, make_pdf):
    source = make_pdf(tmp_path / "long.pdf", pages=5)

    with stop_after(2), pytest.raises(cancel.Cancelled):
        summarizer.extract_text_from_pdf(source)


def test_reading_a_project_for_its_readme_can_be_cancelled(tmp_path, stop_after):
    (tmp_path / "main.py").write_text("print('x')")

    with stop_after(0), pytest.raises(cancel.Cancelled):
        readme_generator.read_key_files(str(tmp_path))


def test_a_cancel_interrupts_the_backoff_between_retries(event):
    def busy():
        event.set()
        raise RuntimeError("429 rate limit")

    started = time.monotonic()
    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        with_retry(busy, label="Test", base_backoff=60)
    _quick(started)


def test_a_summary_stops_waiting_on_the_model(tmp_path, monkeypatch, event):
    source = tmp_path / "notes.txt"
    source.write_text("texto " * 50)
    out = tmp_path / "summary.txt"
    provider = _SlowProvider()
    monkeypatch.setattr(summarizer, "get_provider", lambda *_a, **_k: provider)
    _fires_once(provider.stuck, event)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        summarizer.run_summarizer(str(source), out_path=str(out))

    _quick(started)
    provider.release.set()
    assert not out.exists()


def test_a_translation_keeps_no_half_translated_file(tmp_path, monkeypatch, event):
    source = tmp_path / "book.txt"
    # Every sentence different: identical chunks are served from a cache.
    source.write_text(" ".join(f"Frase numero {index}." for index in range(40000)))
    out = tmp_path / "book_es.txt"
    provider = _SlowProvider(answers=["uno"])
    monkeypatch.setattr(translator, "get_provider", lambda *_a, **_k: provider)
    _fires_once(provider.stuck, event)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        translator.run_translator(str(source), "spanish", out_path=str(out))

    provider.release.set()
    assert provider.requests == 2
    assert not out.exists()


def test_ocr_keeps_what_it_finished_and_stops_paying(tmp_path, monkeypatch, event):
    folder = _images(tmp_path / "in")
    provider = _SlowProvider(answers=["text of the first"])
    monkeypatch.setattr(ocr, "get_provider", lambda *_a, **_k: provider)
    _fires_once(provider.stuck, event)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        ocr.run_ocr(str(folder))

    provider.release.set()
    assert provider.requests == 2
    assert len(list(folder.glob("*.txt"))) == 1


class _Uploaded:
    name = "files/abc"
    state = "PROCESSING"


class _Files:
    def __init__(self):
        self.deleted = []
        self.deleted_late = threading.Event()
        self.uploading = threading.Event()
        self.polling = threading.Event()
        self.release = threading.Event()
        self.slow_upload = False

    def upload(self, file):
        self.uploading.set()
        if self.slow_upload:
            self.release.wait(30)
        return _Uploaded()

    def get(self, name):
        self.polling.set()
        return _Uploaded()

    def delete(self, name):
        self.deleted.append(name)
        self.deleted_late.set()


def _gemini():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.spec = PROVIDERS["gemini"]
    provider.name = "gemini"
    provider._client = type("Client", (), {"files": _Files()})()
    provider._model_override = None
    return provider, provider._client.files


def test_a_cancelled_transcription_still_deletes_the_upload(tmp_path, event):
    media = tmp_path / "talk.mp3"
    media.write_bytes(b"x")
    provider, files = _gemini()
    _fires_once(files.polling, event)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        provider.transcribe(str(media), poll_interval=60)

    _quick(started)
    assert files.deleted == ["files/abc"]


def test_an_upload_abandoned_midway_is_deleted_if_it_lands(tmp_path, event):
    media = tmp_path / "talk.mp3"
    media.write_bytes(b"x")
    provider, files = _gemini()
    files.slow_upload = True
    _fires_once(files.uploading, event)

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        provider.transcribe(str(media))

    assert files.deleted == []
    files.release.set()
    assert files.deleted_late.wait(5)


# ── Network ──────────────────────────────────────────────────────────────────
def test_the_price_monitor_stops_waiting_on_a_shop(monkeypatch, event):
    release = threading.Event()

    def stuck(*_args, **_kwargs):
        release.wait(30)

    monkeypatch.setattr(monitor.requests, "get", stuck)
    monkeypatch.setattr(monitor, "_throttle", lambda _url: None)
    _fires_soon(event)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        monitor.check_price({"url": "https://example.com", "name": "x"}, {})

    _quick(started)
    release.set()


def test_the_clipper_stops_waiting_on_the_page(tmp_path, monkeypatch, event):
    release = threading.Event()

    def stuck(_url, _timeout):
        release.wait(30)
        return "<html></html>"

    monkeypatch.setattr(web_clipper, "_fetch", stuck)
    out = tmp_path / "page.md"
    _fires_soon(event)
    started = time.monotonic()

    with cancel.scope(event), pytest.raises(cancel.Cancelled):
        web_clipper.run_web_clipper("https://example.com", out_path=str(out))

    _quick(started)
    release.set()
    assert not out.exists()


def _capture_download(monkeypatch, tmp_path):
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, **kwargs)

    monkeypatch.setattr(youtube_downloader.cancel, "run", fake_run)
    monkeypatch.setattr(youtube_downloader, "get_downloads_folder", lambda: str(tmp_path))
    return seen


def test_youtube_output_goes_through_the_app_in_the_tui(tmp_path, monkeypatch, event):
    seen = _capture_download(monkeypatch, tmp_path)

    with cancel.scope(event):
        youtube_downloader.run_youtube_downloader("https://youtu.be/x")

    assert "--no-progress" in seen["command"]
    assert callable(seen["on_line"])
    # The URL has to stay last, after the `--` that stops it being read as a flag.
    assert seen["command"][-2:] == ["--", "https://youtu.be/x"]


def test_youtube_keeps_its_progress_bar_on_the_command_line(tmp_path, monkeypatch):
    seen = _capture_download(monkeypatch, tmp_path)

    youtube_downloader.run_youtube_downloader("https://youtu.be/x")

    assert "--no-progress" not in seen["command"]


def test_a_cancelled_download_is_not_reported_as_a_failure(tmp_path, monkeypatch, capsys):
    def killed(_command, **_kwargs):
        raise cancel.Cancelled()

    monkeypatch.setattr(youtube_downloader.cancel, "run", killed)
    monkeypatch.setattr(youtube_downloader, "get_downloads_folder", lambda: str(tmp_path))

    with pytest.raises(cancel.Cancelled):
        youtube_downloader.run_youtube_downloader("https://youtu.be/x")

    assert "Error during download" not in capsys.readouterr().out

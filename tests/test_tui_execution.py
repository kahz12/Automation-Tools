"""Regression tests for the TUI execution view's progress/cancel contract."""

import threading
import time
import asyncio

from textual.app import App
from textual.widgets import Button, ProgressBar, Static

from automation_tools.cli.screens import ConfirmModal, ExecutionScreen
from automation_tools.core import cancel, prompt
from automation_tools.core.logger import console


def test_execution_view_exposes_progress_and_cancel_controls():
    async def noop(self):
        return None

    async def go():
        # Avoid starting the real to_thread worker here; this test only checks
        # the mounted chrome and the callback update path.
        old_execute = ExecutionScreen._execute
        ExecutionScreen._execute = noop
        try:
            class Harness(App):
                def on_mount(self):
                    self.push_screen(ExecutionScreen("Demo", lambda: None, {}))

            app = Harness()
            async with app.run_test() as pilot:
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen.query_one("#exec-progress"), ProgressBar)
                assert isinstance(screen.query_one("#exec-cancel-btn"), Button)
                assert screen.query_one("#back-btn", Button).disabled
                screen._request_cancel()
                assert screen.cancel_event.is_set()
                assert screen.query_one("#exec-cancel-btn", Button).disabled
        finally:
            ExecutionScreen._execute = old_execute

    asyncio.run(go())


def test_optional_hooks_are_injected_without_changing_legacy_callables():
    seen = {}

    def cooperative(cancel_event, progress_callback):
        seen["cancel_event"] = cancel_event
        seen["progress_callback"] = progress_callback

    screen = ExecutionScreen("Demo", cooperative, {})
    screen._run_sync()

    assert isinstance(seen["cancel_event"], threading.Event)
    assert callable(seen["progress_callback"])

    called = []
    legacy = ExecutionScreen("Demo", lambda value: called.append(value), {"value": 3})
    legacy._run_sync()
    assert called == [3]


# ── The run itself, end to end ───────────────────────────────────────────────
class _Harness(App):
    def __init__(self, screen):
        super().__init__()
        self._first = screen

    def on_mount(self):
        self.push_screen(self._first)


async def _until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.01)
    return False


def _status(screen):
    return str(screen.query_one("#exec-status", Static).render())


def _finish(fn):
    """Runs `fn` to the end on an execution screen and returns the final status."""
    async def go():
        screen = ExecutionScreen("Demo", fn, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(lambda: screen._done)
            await pilot.pause()
            return _status(screen)

    return asyncio.run(go())


def test_a_tool_that_reports_failure_does_not_end_in_done():
    assert "Finished with errors" in _finish(lambda: False)


def test_a_tool_that_raises_does_not_end_in_done():
    def explode():
        raise RuntimeError("kaboom")

    assert "Finished with errors" in _finish(explode)


def test_a_tool_that_succeeds_ends_in_done():
    assert "Done" in _finish(lambda: True)
    assert "Done" in _finish(lambda: None)


def test_an_exception_that_looks_like_markup_cannot_take_the_app_down():
    """It reached rich as markup, the handler itself raised, and the TUI died."""
    def explode():
        raise ValueError("bad value [/oops] and data[/]")

    assert "Finished with errors" in _finish(explode)


def test_a_confirm_message_is_shown_as_written():
    message = "'/tmp/[/x] [copy].pdf' already exists. Overwrite it?"
    seen = {}

    def ask():
        seen["answer"] = prompt.confirm(message, default=False)

    async def go():
        app = _Harness(ExecutionScreen("Demo", ask, {}))
        async with app.run_test() as pilot:
            assert await _until(lambda: isinstance(app.screen, ConfirmModal))
            await pilot.pause()
            seen["shown"] = str(app.screen.query_one("#confirm-msg", Static).render())
            await pilot.press("n")
            assert await _until(lambda: "answer" in seen)

    asyncio.run(go())
    assert message in seen["shown"]
    assert seen["answer"] is False


def test_a_question_asked_after_cancel_stops_the_tool_instead_of_answering():
    """The renamer asks with default=True: Cancel used to apply the renames."""
    planning = threading.Event()
    proceed = threading.Event()
    seen = {}

    def tool():
        planning.set()
        proceed.wait(5)
        seen["answer"] = prompt.confirm("Apply these 3 renames?", default=True)

    async def go():
        screen = ExecutionScreen("Demo", tool, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(planning.is_set)
            screen._request_cancel()
            proceed.set()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            seen["modal_left_open"] = isinstance(app.screen, ConfirmModal)
            seen["status"] = _status(screen)

    asyncio.run(go())
    assert "answer" not in seen
    assert seen["modal_left_open"] is False
    assert "Canceled safely" in seen["status"]


def test_cancelling_an_open_question_closes_it_and_stops_the_tool():
    seen = {}

    def tool():
        seen["answer"] = prompt.confirm("Apply?", default=True)

    async def go():
        screen = ExecutionScreen("Demo", tool, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(lambda: isinstance(app.screen, ConfirmModal))
            screen._request_cancel()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            assert not isinstance(app.screen, ConfirmModal)
            seen["status"] = _status(screen)

    asyncio.run(go())
    assert "answer" not in seen
    assert "Canceled safely" in seen["status"]


def test_cancelling_the_vault_at_its_question_encrypts_nothing(tmp_path, monkeypatch):
    """A declined "delete the originals?" only keeps them, and carries on.

    So answering that question "no" on a cancel would have gone straight on to
    encrypt the whole folder after the user asked it to stop.
    """
    from automation_tools.tools import vault

    monkeypatch.setattr(vault, "SCRYPT_N", 1 << 4)
    (tmp_path / "secret.txt").write_text("plain")

    async def go():
        screen = ExecutionScreen("Vault", vault.run_vault, {
            "path": str(tmp_path), "action": "encrypt", "password": "x",
            "remove_originals": True,
        })
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(lambda: isinstance(app.screen, ConfirmModal))
            screen._request_cancel()
            assert await _until(lambda: screen._done)
            await pilot.pause()

    asyncio.run(go())
    assert [p.name for p in tmp_path.iterdir()] == ["secret.txt"]


def test_a_real_tool_stops_when_cancelled(tmp_path):
    """The whole path: button, event, scope, and a batch that never finishes."""
    from automation_tools.tools import integrity

    for index in range(4000):
        (tmp_path / f"{index}.txt").write_text("x")

    async def go():
        screen = ExecutionScreen("Integrity", integrity.run_integrity, {
            "action": "create", "directory": str(tmp_path),
        })
        app = _Harness(screen)
        async with app.run_test() as pilot:
            screen._request_cancel()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            return _status(screen)

    assert "Canceled safely" in asyncio.run(go())
    assert not (tmp_path / "checksums.sha256").exists()


def test_a_tool_that_finishes_anyway_does_not_claim_to_be_canceled():
    release = threading.Event()
    started = threading.Event()

    def stubborn():
        started.set()
        release.wait(5)

    async def go():
        screen = ExecutionScreen("Demo", stubborn, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(started.is_set)
            screen._request_cancel()
            await pilot.pause()
            during = _status(screen)
            release.set()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            return during, _status(screen)

    during, after = asyncio.run(go())
    assert "stopping at the next safe point" in during
    assert "Canceled" not in after
    assert "finished before the cancel" in after


def test_a_cooperative_tool_is_reported_as_canceled():
    def careful(cancel_event):
        cancel_event.wait(5)

    async def go():
        screen = ExecutionScreen("Demo", careful, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._request_cancel()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            return _status(screen)

    assert "Canceled safely" in asyncio.run(go())


def test_the_continuous_monitor_can_be_cancelled_and_left(monkeypatch):
    """It looped forever: Cancel did nothing and BACK stayed disabled."""
    from automation_tools.tools import monitor

    monkeypatch.setattr(monitor, "run_price_monitor_job", lambda: True)

    async def go():
        screen = ExecutionScreen("Monitor", monitor.run_continuous_monitor,
                                 {"interval_minutes": 60})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._request_cancel()
            assert await _until(lambda: screen._done)
            await pilot.pause()
            assert not screen.query_one("#back-btn", Button).disabled
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is not screen

    asyncio.run(go())


def test_quitting_mid_run_tells_the_tool_to_stop():
    """asyncio waits for the worker thread on exit, so it has to end too."""
    stopped = threading.Event()

    def forever():
        try:
            cancel.sleep(30)
        finally:
            stopped.set()

    async def go():
        app = _Harness(ExecutionScreen("Demo", forever, {}))
        async with app.run_test() as pilot:
            await pilot.pause()
            app.exit()
            await pilot.pause()

    asyncio.run(asyncio.wait_for(go(), 15))
    assert stopped.wait(5)


def test_printed_lines_do_not_move_a_bar_with_a_real_total():
    """Each output line ticked the bar, so it ran ahead of the actual work."""
    def tool(progress_callback):
        progress_callback(current=1, total=10, message="1 of 10")
        for _ in range(5):
            console.print("noise")

    async def go():
        screen = ExecutionScreen("Demo", tool, {})
        app = _Harness(screen)
        async with app.run_test() as pilot:
            assert await _until(lambda: screen._done)
            await pilot.pause()
            return screen.query_one("#exec-progress", ProgressBar).progress

    assert asyncio.run(go()) == 1

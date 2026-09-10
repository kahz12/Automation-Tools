"""Regression tests for the TUI execution view's progress/cancel contract."""

import threading
import asyncio

from textual.app import App
from textual.widgets import Button, ProgressBar

from automation_tools.cli.screens import (
    ExecutionScreen,
    tui_cancelled,
    tui_check_cancelled,
)
from automation_tools.cli.screens import base as base_mod


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


def test_cooperative_cancellation_helper_raises_at_safe_boundary():
    previous = base_mod._CURRENT_EXECUTOR
    screen = ExecutionScreen("Demo", lambda: None, {})
    base_mod._CURRENT_EXECUTOR = screen
    try:
        assert not tui_cancelled()
        screen.cancel_event.set()
        assert tui_cancelled()
        try:
            tui_check_cancelled()
        except base_mod.TuiCancelled:
            pass
        else:
            raise AssertionError("tui_check_cancelled did not stop a canceled task")
    finally:
        base_mod._CURRENT_EXECUTOR = previous

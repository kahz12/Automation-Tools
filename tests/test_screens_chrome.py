"""Every tool screen must mount and carry the same chrome.

`test_cli_wiring` checks the maps line up; this actually mounts each screen in a
headless Textual app, which is what catches a screen that references a widget it
never composes. It is also the safety net for refactoring the shared layout out
of the 25 individual `compose()` methods.
"""
import asyncio

import pytest
from textual.app import App
from textual.widgets import Button

from automation_tools.cli.screens import SCREEN_MAP

from screens_golden import SCREEN_WIDGETS


class _Harness(App):
    """Bare app whose only job is to push one tool screen."""

    def __init__(self, screen_cls):
        super().__init__()
        self._screen_cls = screen_cls

    def on_mount(self) -> None:
        self.push_screen(self._screen_cls())


def _mount(screen_cls):
    """Mounts the screen headless and returns (button_ids, panel_text, error_slot)."""

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            buttons = {b.id for b in screen.query(Button)}
            # Static.render() gives the plain text, with the markup resolved.
            panels = [str(p.render()) for p in screen.query(".tool-panel")]
            has_error_slot = bool(list(screen.query("#error-msg")))
            return buttons, panels, has_error_slot

    return asyncio.run(go())


def _inventory(screen_cls):
    """Mounts the screen headless and returns its widget ids and classes."""

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            widgets = list(app.screen.query("*"))
            ids = sorted(w.id for w in widgets if w.id)
            classes = sorted({c for w in widgets for c in w.classes
                              if not c.startswith("-")})
            return ids, classes

    return asyncio.run(go())


@pytest.mark.parametrize("label,screen_cls", sorted(SCREEN_MAP.items()))
def test_every_screen_mounts_with_the_standard_chrome(label, screen_cls):
    buttons, panels, has_error_slot = _mount(screen_cls)

    assert "run-btn" in buttons, f"{screen_cls.__name__} has no RUN button"
    assert "back-btn" in buttons, f"{screen_cls.__name__} has no BACK button"
    assert has_error_slot, f"{screen_cls.__name__} has no #error-msg slot"
    assert panels, f"{screen_cls.__name__} has no .tool-panel header"


@pytest.mark.parametrize("label,screen_cls", sorted(SCREEN_MAP.items()))
def test_every_screen_header_shows_its_title(label, screen_cls):
    _buttons, panels, _slot = _mount(screen_cls)

    title = screen_cls.TOOL_TITLE.strip()
    joined = "\n".join(panels)
    assert title in joined, (
        f"{screen_cls.__name__} header does not show its TOOL_TITLE "
        f"({title!r} not in {joined!r})"
    )


@pytest.mark.parametrize("label,screen_cls", sorted(SCREEN_MAP.items()))
def test_every_screen_still_composes_the_same_widgets(label, screen_cls):
    """Guards the shared-chrome refactor: no field may silently disappear."""
    expected = SCREEN_WIDGETS.get(screen_cls.__name__)
    assert expected is not None, (
        f"{screen_cls.__name__} is not in screens_golden.py — add it deliberately"
    )

    ids, classes = _inventory(screen_cls)

    missing = sorted(set(expected["ids"]) - set(ids))
    added = sorted(set(ids) - set(expected["ids"]))
    assert not missing, f"{screen_cls.__name__} lost widgets: {missing}"
    assert not added, f"{screen_cls.__name__} gained widgets: {added}"
    assert classes == expected["classes"], f"{screen_cls.__name__} styling classes changed"

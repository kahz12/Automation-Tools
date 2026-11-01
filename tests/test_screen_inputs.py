"""What a screen hands to its tool, given what the user actually typed.

`test_screens_chrome` proves every screen mounts. This covers the step after:
the values that reach the tool, where stripping or a hidden switch changes the
meaning of what was entered.
"""
import asyncio

import pytest
from textual.app import App
from textual.widgets import Input, RadioButton, Static, Switch

from automation_tools.cli import menu
from automation_tools.cli.menu import MENU_ENTRIES
from automation_tools.cli.screens import (
    MonitorScreen,
    PasswordScreen,
    PdfToolkitScreen,
    RenamerScreen,
    VaultScreen,
    YoutubeScreen,
)
from automation_tools.cli.tui import AutomationApp


class _Harness(App):
    def __init__(self, screen):
        super().__init__()
        self._first = screen

    def on_mount(self):
        self.push_screen(self._first)


def _submit(screen, prepare):
    """Fills the form with `prepare(screen)` and presses RUN; returns the tool kwargs."""
    captured = {}

    async def fake_run_tool(fn, **kwargs):
        captured.update(kwargs)

    screen._run_tool = fake_run_tool

    async def go():
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            prepare(screen)
            await pilot.pause()
            await screen.action_do_run()
            await pilot.pause()

    asyncio.run(go())
    return captured


def _fill_rename(old, new):
    def prepare(screen):
        screen.query_one("#rb-replace", RadioButton).value = True
        screen.query_one("#dir", Input).value = "/tmp"
        screen.query_one("#old-text", Input).value = old
        screen.query_one("#new-text", Input).value = new
    return prepare


@pytest.mark.parametrize("old, new", [("_", " "), (" ", "_"), (" - ", "-")])
def test_rename_text_keeps_its_spaces(old, new):
    """Replacing "_" with " " used to delete the underscores instead."""
    sent = _submit(RenamerScreen(), _fill_rename(old, new))
    assert (sent["old_text"], sent["new_text"]) == (old, new)


def test_rename_text_to_find_is_still_required():
    assert _submit(RenamerScreen(), _fill_rename("", "x")) == {}


def test_a_pdf_password_is_used_exactly_as_typed():
    def prepare(screen):
        screen.query_one("#rb-encrypt", RadioButton).value = True
        screen.query_one("#encrypt-input", Input).value = "/tmp/a.pdf"
        screen.query_one("#encrypt-pwd", Input).value = " my pass "

    assert _submit(PdfToolkitScreen(), prepare)["password"] == " my pass "


def test_a_password_to_evaluate_is_used_exactly_as_typed():
    def prepare(screen):
        screen.query_one("#rb-strength", RadioButton).value = True
        screen.query_one("#check-pwd", Input).value = " spaced "

    assert _submit(PasswordScreen(), prepare)["password"] == " spaced "


def test_a_hidden_shred_switch_cannot_delete_the_originals():
    """Shredding implies deleting, and the switch keeps its value while hidden."""
    def prepare(screen):
        screen.query_one("#path", Input).value = "/tmp/x"
        screen.query_one("#password", Input).value = "Sup3r-Secret-Pass!"
        screen.query_one("#password2", Input).value = "Sup3r-Secret-Pass!"
        screen.query_one("#shred", Switch).value = True
        screen.query_one("#remove", Switch).value = False

    sent = _submit(VaultScreen(), prepare)
    assert (sent["remove_originals"], sent["shred"]) == (False, False)


def test_shredding_survives_when_deleting_is_on():
    def prepare(screen):
        screen.query_one("#path", Input).value = "/tmp/x"
        screen.query_one("#password", Input).value = "Sup3r-Secret-Pass!"
        screen.query_one("#password2", Input).value = "Sup3r-Secret-Pass!"
        screen.query_one("#remove", Switch).value = True
        screen.query_one("#shred", Switch).value = True

    assert _submit(VaultScreen(), prepare)["shred"] is True


def test_a_malformed_youtube_url_is_a_form_error_not_a_crash():
    """urlparse raised inside the RUN handler, which killed the app."""
    screen = YoutubeScreen()
    errors = []
    screen._err = errors.append

    def prepare(form):
        form.query_one("#url", Input).value = "https://[x"

    assert _submit(screen, prepare) == {}
    assert errors


def test_form_errors_are_shown_as_written():
    screen = VaultScreen()

    async def go():
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen._err("Not found: /tmp/[/x] [copy]")
            await pilot.pause()
            return str(screen.query_one("#error-msg", Static).render())

    assert "/tmp/[/x] [copy]" in asyncio.run(go())


def _config_report(read_output, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    screen = MonitorScreen()
    captured = {}

    async def fake_run_tool(fn, **kwargs):
        captured["fn"] = fn

    screen._run_tool = fake_run_tool

    async def go():
        app = _Harness(screen)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen.query_one("#rb-config", RadioButton).value = True
            await pilot.pause()
            await screen.action_do_run()

    asyncio.run(go())
    captured["fn"]()
    return read_output()


def test_monitor_config_names_the_file_the_monitor_will_read(tmp_path, monkeypatch, data_dir, capsys):
    (tmp_path / "productos_a_monitorear.json").write_text("{}", encoding="utf-8")

    out = _config_report(lambda: capsys.readouterr().out, tmp_path, monkeypatch)

    # It used to name the checkout's path whatever the monitor would really read.
    assert str(tmp_path / "productos_a_monitorear.json") in out.replace("\n", "")
    assert "No config file yet" not in out


def test_monitor_config_does_not_promise_a_file_nothing_creates(tmp_path, monkeypatch, data_dir, capsys):
    from automation_tools.core import config

    monkeypatch.setattr(config, "get_project_root", lambda: str(tmp_path / "root"))

    out = _config_report(lambda: capsys.readouterr().out, tmp_path, monkeypatch)

    assert "No config file yet" in out
    assert "created on first run" not in out


@pytest.mark.parametrize("content", ["5", '[["x"]]', '{"a": 1}', '"text"', "not json"])
def test_a_damaged_history_file_is_an_empty_history(content, tmp_path, monkeypatch):
    """Valid JSON of the wrong shape used to stop the menu from opening."""
    history = tmp_path / "history.json"
    history.write_text(content, encoding="utf-8")
    monkeypatch.setattr(menu, "HISTORY_FILE", str(history))

    loaded = menu._load_history()
    assert loaded == []

    async def go():
        app = AutomationApp(MENU_ENTRIES, loaded)
        async with app.run_test() as pilot:
            await pilot.pause()

    asyncio.run(go())


def test_history_keeps_its_good_entries(tmp_path, monkeypatch):
    history = tmp_path / "history.json"
    history.write_text('["a", 1, null, "b"]', encoding="utf-8")
    monkeypatch.setattr(menu, "HISTORY_FILE", str(history))

    assert menu._load_history() == ["a", "b"]


def test_a_resize_reflows_the_home_screen():
    async def go():
        app = AutomationApp(MENU_ENTRIES, [])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            return app.query(".card-grid").first().styles.grid_size_columns

    assert asyncio.run(go()) == 2


def test_a_resize_during_a_tool_reflows_the_home_screen():
    async def go():
        app = AutomationApp(MENU_ENTRIES, [])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app.push_screen(PasswordScreen())
            await pilot.pause()
            await pilot.resize_terminal(60, 30)
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            return app.query(".card-grid").first().styles.grid_size_columns

    assert asyncio.run(go()) == 2

"""Every tool screen must mount and carry the same chrome.

`test_cli_wiring` checks the maps line up; this actually mounts each screen in a
headless Textual app, which is what catches a screen that references a widget it
never composes. It is also the safety net for refactoring the shared layout out
of the 25 individual `compose()` methods.
"""
import asyncio

import pytest
from textual.app import App
from textual.widgets import Button, Input, Label, Select

from automation_tools.ai.base import Capability
from automation_tools.ai.registry import PROVIDERS, providers_with
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


# The five screens that talk to an AI provider, and what each needs.
AI_SCREENS = {
    "SummarizerScreen": Capability.TEXT,
    "TranslatorScreen": Capability.TEXT,
    "ReadmeScreen": Capability.TEXT,
    "OcrScreen": Capability.VISION,
    "TranscriberScreen": Capability.AUDIO,
}


def _provider_options(screen_cls):
    """Mounts the screen and returns the values offered by its provider Select."""

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            select = app.screen.query_one("#provider", Select)
            return [value for _label, value in select._options]

    return asyncio.run(go())


@pytest.mark.parametrize("name,capability", sorted(AI_SCREENS.items()))
def test_ai_screens_only_offer_providers_that_can_do_the_job(name, capability):
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == name)
    assert _provider_options(screen_cls) == providers_with(capability)


def test_the_ocr_screen_does_not_offer_deepseek():
    """The concrete case the capability model exists for."""
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == "OcrScreen")
    assert "deepseek" not in _provider_options(screen_cls)


def test_the_transcriber_screen_only_offers_the_three_audio_providers():
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == "TranscriberScreen")
    assert set(_provider_options(screen_cls)) == {"gemini", "openai", "groq"}


@pytest.mark.parametrize("name", sorted(AI_SCREENS))
def test_picking_a_provider_relabels_and_refills_the_key_field(name, monkeypatch):
    """Changing the dropdown has to actually reach the key field.

    This drives the widget the way a user does, assigning to `Select.value` and
    letting Textual deliver the message, rather than calling the handler itself.
    A handler that is never dispatched looks identical to a working one when
    you call it yourself, and that is exactly the bug this caught: `@on` only
    registers handlers on classes the Textual metaclass processed, so a plain
    mixin's decorated handler is silently dropped.
    """
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == name)
    # A provider the screen offers that is not the one it starts on. Taking the
    # last one keeps the three capabilities from all landing on "openai".
    options = _provider_options(screen_cls)
    other = options[-1]
    assert other != "gemini"

    spec = PROVIDERS[other]
    monkeypatch.setenv(spec.env_key, "key-from-the-environment")

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            screen.query_one("#provider", Select).value = other
            await pilot.pause()
            label = screen.query_one("#api-key-label", Label)
            field = screen.query_one("#api-key", Input)
            return str(label.render()), field.placeholder, field.value

    label_text, placeholder, value = asyncio.run(go())
    assert spec.env_key in label_text
    assert placeholder == spec.key_hint
    assert value == "key-from-the-environment"


@pytest.mark.parametrize("name", sorted(AI_SCREENS))
def test_the_key_field_starts_labelled_for_the_default_provider(name, monkeypatch):
    """The state the screen mounts in, before the user touches anything.

    This is what replaced the old hardcoded GOOGLE_API_KEY prefill, so it needs
    its own guard: gutting `on_mount` leaves every other test passing.
    """
    monkeypatch.setenv("GOOGLE_API_KEY", "key-from-the-environment")
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == name)

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            return (
                screen.query_one("#provider", Select).value,
                str(screen.query_one("#api-key-label", Label).render()),
                screen.query_one("#api-key", Input).value,
            )

    selected, label_text, value = asyncio.run(go())
    assert selected == "gemini", "no AI_PROVIDER set means the registry default"
    assert "GOOGLE_API_KEY" in label_text
    assert value == "key-from-the-environment"


def _selected_provider(screen_cls):
    """Mounts the screen and returns which provider its dropdown settled on."""

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            return app.screen.query_one("#provider", Select).value

    return asyncio.run(go())


def test_a_screen_falls_back_when_the_default_provider_cannot_do_the_job(monkeypatch):
    """`AI_PROVIDER=deepseek` must not break the vision-only screens.

    deepseek is text-only, so it is absent from OcrScreen's dropdown. Passing it
    to `Select(value=...)` anyway raises InvalidSelectValueError at compose time
    and takes the whole TUI down, so the fallback is load-bearing.
    """
    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    ocr_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == "OcrScreen")
    sumr_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == "SummarizerScreen")

    # OCR cannot use deepseek, so it drops to the first vision provider…
    assert _selected_provider(ocr_cls) == "gemini"
    # …but the summarizer honours the choice, because deepseek does text.
    assert _selected_provider(sumr_cls) == "deepseek"


def test_an_unknown_ai_provider_does_not_crash_the_screen(monkeypatch):
    """A typo in $AI_PROVIDER must not take the TUI down.

    `resolve_name()` raises UnknownProviderError on a name it does not know.
    Nothing above `compose_provider_fields` catches it, so an unguarded call
    kills the app the moment the user opens an AI screen. On the CLI the same
    typo produces a clean message; the TUI has to be no worse.
    """
    monkeypatch.setenv("AI_PROVIDER", "bogus-provider")
    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == "SummarizerScreen")

    assert _selected_provider(screen_cls) == "gemini", "an unusable setting falls back"


# The input each AI screen refuses to run without, so `action_do_run` gets past
# its own validation and actually reaches `_run_tool`.
_REQUIRED_INPUT = {
    "SummarizerScreen": "#filepath",
    "TranslatorScreen": "#filepath",
    "ReadmeScreen": "#dir",
    "OcrScreen": "#path",
    "TranscriberScreen": "#filepath",
}


@pytest.mark.parametrize("name", sorted(AI_SCREENS))
def test_running_a_tool_forwards_the_chosen_provider(name, monkeypatch):
    """The user's pick has to survive all the way into the tool call.

    Everything else about the picker can work: it can filter correctly, relabel
    correctly, and still run Gemini every time because `action_do_run` dropped
    `provider=` on the floor. Nothing else in the suite would notice, so this
    stubs `ExecutionScreen` (the seam `_run_tool` actually uses) and inspects the
    kwargs the tool would have been called with.
    """
    from textual.screen import Screen as _Screen

    from automation_tools.cli import screens as screens_mod

    screen_cls = next(c for c in SCREEN_MAP.values() if c.__name__ == name)
    chosen = _provider_options(screen_cls)[-1]
    captured = {}

    class _CaptureExecution(_Screen):
        def __init__(self, title, fn, kwargs):
            super().__init__()
            captured["fn"] = fn
            captured["kwargs"] = kwargs

    monkeypatch.setattr(screens_mod, "ExecutionScreen", _CaptureExecution)

    async def go():
        app = _Harness(screen_cls)
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            screen.query_one(_REQUIRED_INPUT[name], Input).value = "/tmp/some-input"
            # Pick the provider first and let the relabel land: switching
            # deliberately clears the key field, so typing has to come after.
            screen.query_one("#provider", Select).value = chosen
            await pilot.pause()
            screen.query_one("#api-key", Input).value = "typed-by-hand"
            await screen.action_do_run()
            await pilot.pause()

    asyncio.run(go())

    assert captured, f"{name}.action_do_run never reached _run_tool"
    assert captured["kwargs"].get("provider") == chosen, (
        f"{name} did not forward the selected provider"
    )
    assert captured["kwargs"].get("api_key") == "typed-by-hand"

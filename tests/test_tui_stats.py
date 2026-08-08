"""The launcher's hero banner must report the provider actually in use.

It read `GOOGLE_API_KEY` unconditionally and printed "Gemini key" right through
the multi-provider migration, because nothing asserted on it. Same story as the
provider dropdown that shipped dead. So these mount the real `AutomationApp` and
read the string a user would actually see, rather than calling a helper that
rebuilds it.
"""
import asyncio

from textual.widgets import Static

from automation_tools.cli.menu import MENU_ENTRIES
from automation_tools.cli.tui import AutomationApp


def _hero_stats() -> str:
    """Mounts the launcher headless and returns the hero-stats line as text."""

    async def go():
        app = AutomationApp(MENU_ENTRIES, [], record_use=lambda name: None)
        async with app.run_test() as pilot:
            await pilot.pause()
            # render() hands back the renderable with the colour markup already
            # resolved, so this is plain text.
            return str(app.query_one("#hero-stats", Static).render())

    return asyncio.run(go())


def test_the_banner_names_the_provider_actually_in_use(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_configured")

    stats = _hero_stats()

    assert "Groq key" in stats
    assert "✓ set" in stats
    assert "Gemini" not in stats


def test_a_stale_google_key_does_not_fake_readiness(monkeypatch):
    """The false positive: configured for Groq, no Groq key, old Google one left.

    The banner used to say "✓ set" here purely because GOOGLE_API_KEY existed,
    telling the user they were ready for a run that could only fail.
    """
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-left-over-from-last-year")

    stats = _hero_stats()

    assert "Groq key" in stats
    assert "✗ not set" in stats


def test_the_default_provider_still_reports_its_own_key(monkeypatch):
    """With no $AI_PROVIDER at all, the banner falls back to Gemini as before."""
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-configured")

    stats = _hero_stats()

    assert "Gemini key" in stats
    assert "✓ set" in stats


def test_an_unknown_provider_does_not_crash_the_launcher(monkeypatch):
    """A typo in $AI_PROVIDER must not take down the home screen.

    `resolve_name` raises on a name it does not know, and this runs during
    `on_mount`, so an unguarded lookup would kill the app on startup rather
    than at the point of use. The banner has to name the offending variable,
    because reporting some arbitrary provider's key would hide the real fault.
    """
    monkeypatch.setenv("AI_PROVIDER", "gemeni")

    stats = _hero_stats()

    assert "AI_PROVIDER" in stats
    assert "✗" in stats

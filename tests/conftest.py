"""Shared pytest fixtures for the Automation-Tools test suite."""
import os
import tempfile

import pytest
from PIL import Image
from pypdf import PdfWriter


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    """Every test runs with no provider-selection env vars set.

    Without this a developer's real shell leaks into the suite: any test that
    reaches `ai.registry.get_provider` without an explicit `provider=` picks up
    `$AI_PROVIDER`, and if that provider's key is exported too, the registry
    builds a real, unstubbed adapter instead of the double the test meant to
    use, which can fire a live call with a real key.
    `tests/test_gemini_shim.py` is the concrete case: it drives
    `run_transcriber` through the real registry and stubs only the Gemini SDK,
    so an ambient `AI_PROVIDER=openai` plus `OPENAI_API_KEY` would send it to
    the real OpenAI audio endpoint.

    The variables come from the registry itself rather than a hardcoded list,
    so new providers are covered automatically. Tests that need a key set still
    set it themselves; this only guarantees a clean starting state.
    """
    from automation_tools.ai.registry import PROVIDERS

    monkeypatch.delenv("AI_PROVIDER", raising=False)
    for spec in PROVIDERS.values():
        monkeypatch.delenv(spec.env_key, raising=False)


@pytest.fixture
def make_image():
    """Factory that writes a small image file and returns its path."""
    def _make(path, size=(64, 48), color=(120, 30, 30), mode="RGB"):
        if mode == "RGBA":
            color = (color[0], color[1], color[2], 255)
        Image.new(mode, size, color).save(str(path))
        return str(path)
    return _make


@pytest.fixture
def make_pdf():
    """Factory that writes a blank multi-page PDF and returns its path."""
    def _make(path, pages=3, width=200, height=200):
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=width, height=height)
        with open(str(path), "wb") as fh:
            writer.write(fh)
        return str(path)
    return _make


@pytest.fixture
def data_dir(monkeypatch, tmp_path):
    """Points the user data directory at a temporary one.

    Patching the function rather than $XDG_DATA_HOME keeps these tests honest
    on Windows and macOS, which do not read that variable.
    """
    from automation_tools.core import config

    target = tmp_path / "state"
    target.mkdir()
    monkeypatch.setattr(config, "user_data_dir", lambda: str(target))
    return target


def _symlinks_work() -> bool:
    """Windows needs Developer Mode or admin rights to create one."""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "target")
        open(target, "w").close()
        try:
            os.symlink(target, os.path.join(tmp, "link"))
        except (OSError, NotImplementedError, AttributeError):
            return False
    return True


needs_symlinks = pytest.mark.skipif(
    not _symlinks_work(), reason="this platform will not let us create a symlink"
)

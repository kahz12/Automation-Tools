"""Tests for the A/V Transcriber, now driven through the provider registry.

The upload/polling logic that used to live here now lives in `ai/gemini.py`
(GeminiProvider.transcribe) and is covered by `tests/test_ai_gemini.py`. These
tests only exercise the transcriber's own orchestration: asking the registry
for an AUDIO provider, forwarding the mode, and handling failure.
"""
import pytest

from automation_tools.tools import transcriber


class _StubAudioProvider:
    def __init__(self, text="1\n00:00:00,000 --> 00:00:02,000\nhello\n"):
        self.name = "stub"
        self.text = text
        self.calls = []

    def transcribe(self, filepath, *, mode="srt", model=None):
        self.calls.append({"filepath": filepath, "mode": mode})
        return self.text


@pytest.fixture
def fake_provider(monkeypatch):
    stub = _StubAudioProvider()
    calls = []

    def fake_get_provider(capability, name=None, api_key=None, model=None):
        calls.append({"capability": capability, "name": name, "model": model})
        return stub

    monkeypatch.setattr(transcriber, "get_provider", fake_get_provider)
    return stub, calls


def test_asks_for_an_audio_provider(tmp_path, fake_provider):
    from automation_tools.ai.base import Capability

    _stub, calls = fake_provider
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert transcriber.run_transcriber(str(media)) is True
    assert calls[0]["capability"] is Capability.AUDIO


def test_forwards_the_mode_to_the_provider(tmp_path, fake_provider):
    stub, _calls = fake_provider
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    transcriber.run_transcriber(str(media), mode="txt")
    assert stub.calls[0]["mode"] == "txt"


def test_returns_false_when_the_provider_gives_up(tmp_path, monkeypatch):
    class _Failing:
        name = "stub"

        def transcribe(self, filepath, *, mode="srt", model=None):
            return None

    monkeypatch.setattr(transcriber, "get_provider",
                        lambda *a, **k: _Failing())
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert transcriber.run_transcriber(str(media)) is False


def test_returns_false_for_a_missing_file(tmp_path):
    """The existence check runs before the registry is ever touched."""
    assert transcriber.run_transcriber(str(tmp_path / "nope.mp3")) is False


def test_reports_a_provider_error(tmp_path, monkeypatch, capsys):
    """The successor to the pre-migration 'no client' test.

    get_provider can now raise instead of returning something falsy; that
    path must be reported to the user and turned into a False return, same
    as ocr.run_ocr's twin branch (tests/test_ocr.py::
    test_run_ocr_reports_a_provider_error).
    """
    from automation_tools.ai.base import CapabilityError

    def boom(capability, name=None, api_key=None, model=None):
        raise CapabilityError("'anthropic' does not support audio.")

    monkeypatch.setattr(transcriber, "get_provider", boom)
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert transcriber.run_transcriber(str(media), provider="anthropic") is False
    assert "does not support" in capsys.readouterr().out


def test_strips_srt_markdown_fences(tmp_path, fake_provider):
    """transcriber.py:42-47 is live and unchanged by the migration.

    A regression here would silently corrupt every SRT file the tool writes.
    """
    stub, _calls = fake_provider
    stub.text = "```srt\n1\n00:00:00,000 --> 00:00:01,000\nhola\n```"
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert transcriber.run_transcriber(str(media), mode="srt") is True

    written = media.with_suffix(".srt").read_text(encoding="utf-8")
    assert not written.startswith("```")
    assert not written.endswith("```")
    assert "00:00:00,000" in written

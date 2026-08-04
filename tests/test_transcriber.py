"""Tests for the A/V Transcriber's upload-polling loop.

The transcriber has to wait for Gemini to finish processing an uploaded media
file before it can transcribe it. That wait must always terminate: a stuck file
or a persistently failing API must not hang the tool forever.
"""
import time
import types

import pytest

from automation_tools.tools import transcriber


class _FakeFile:
    def __init__(self, state):
        self.state = state


class _FakeFiles:
    """Stand-in for `client.files` with a scripted sequence of poll results.

    Each entry is either a state string or an Exception instance to raise.
    Once the script runs out, the last entry repeats forever.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def get(self, name=None):
        self.calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return _FakeFile(item)


class _FakeClient:
    def __init__(self, script):
        self.files = _FakeFiles(script)


def test_wait_for_active_returns_true_once_processing_finishes():
    client = _FakeClient(["PROCESSING", "PROCESSING", "ACTIVE"])
    assert transcriber._wait_for_active(
        client, "files/abc", timeout=5.0, poll_interval=0.01
    ) is True
    assert client.files.calls == 3


def test_wait_for_active_returns_false_when_gemini_reports_failed():
    client = _FakeClient(["PROCESSING", "FAILED"])
    assert transcriber._wait_for_active(
        client, "files/abc", timeout=5.0, poll_interval=0.01
    ) is False


def test_wait_for_active_gives_up_when_file_never_becomes_active():
    """A file stuck in PROCESSING must time out instead of looping forever."""
    client = _FakeClient(["PROCESSING"])
    started = time.monotonic()
    result = transcriber._wait_for_active(
        client, "files/abc", timeout=0.2, poll_interval=0.01
    )
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 3.0, "polling did not respect the timeout"


def test_wait_for_active_gives_up_when_the_api_keeps_failing():
    """Persistent API errors must terminate too — this used to hang forever."""
    client = _FakeClient([RuntimeError("network down")])
    started = time.monotonic()
    result = transcriber._wait_for_active(
        client, "files/abc", timeout=0.2, poll_interval=0.01
    )
    elapsed = time.monotonic() - started

    assert result is False
    assert elapsed < 3.0, "error path did not respect the timeout"


# ── exit contract ───────────────────────────────────────────────────────────
# run_transcriber returns True only when a transcript was produced and written,
# so `main()` can turn that into a usable exit code.

class _FakeUploadFiles:
    """`client.files` for the happy path, recording what gets cleaned up."""

    def __init__(self, upload_error=None, state="ACTIVE"):
        self.upload_error = upload_error
        self.state = state
        self.deleted = []

    def upload(self, file=None):
        if self.upload_error:
            raise self.upload_error
        return types.SimpleNamespace(name="files/abc")

    def get(self, name=None):
        return types.SimpleNamespace(state=self.state)

    def delete(self, name=None):
        self.deleted.append(name)


class _FakeModels:
    def __init__(self, text):
        self.text = text

    def generate_content(self, model=None, contents=None):
        if self.text is None:
            raise RuntimeError("model refused")
        return types.SimpleNamespace(text=self.text, usage_metadata=None)


class _FakeGeminiClient:
    def __init__(self, text="hola mundo", upload_error=None, state="ACTIVE"):
        self.files = _FakeUploadFiles(upload_error=upload_error, state=state)
        self.models = _FakeModels(text)


@pytest.fixture
def media(tmp_path):
    f = tmp_path / "clip.mp3"
    f.write_bytes(b"fake audio")
    return f


def test_returns_false_for_a_missing_file(tmp_path):
    assert transcriber.run_transcriber(str(tmp_path / "nope.mp3")) is False


def test_returns_false_without_an_api_client(media, monkeypatch):
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: None)
    assert transcriber.run_transcriber(str(media)) is False


def test_returns_false_when_the_upload_fails(media, monkeypatch):
    client = _FakeGeminiClient(upload_error=RuntimeError("quota"))
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: client)
    assert transcriber.run_transcriber(str(media)) is False


def test_returns_false_and_cleans_up_when_processing_never_completes(media, monkeypatch):
    client = _FakeGeminiClient(state="PROCESSING")
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: client)
    monkeypatch.setattr(transcriber, "UPLOAD_TIMEOUT", 0.1)
    monkeypatch.setattr(transcriber, "POLL_INTERVAL", 0.01)

    assert transcriber.run_transcriber(str(media)) is False
    assert client.files.deleted == ["files/abc"], "the stuck upload was not removed"


def test_returns_false_when_the_model_returns_nothing(media, monkeypatch):
    client = _FakeGeminiClient(text=None)
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: client)
    assert transcriber.run_transcriber(str(media)) is False


def test_returns_true_and_writes_the_transcript(media, monkeypatch):
    client = _FakeGeminiClient(text="hola mundo")
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: client)

    assert transcriber.run_transcriber(str(media), mode="txt") is True

    written = media.with_suffix(".txt")
    assert written.read_text(encoding="utf-8") == "hola mundo"
    assert client.files.deleted == ["files/abc"], "the remote upload was not cleaned up"


def test_srt_mode_strips_markdown_fences(media, monkeypatch):
    client = _FakeGeminiClient(text="```srt\n1\n00:00:00,000 --> 00:00:01,000\nhola\n```")
    monkeypatch.setattr(transcriber, "get_gemini_client", lambda key: client)

    assert transcriber.run_transcriber(str(media), mode="srt") is True

    written = media.with_suffix(".srt").read_text(encoding="utf-8")
    assert not written.startswith("```")
    assert not written.endswith("```")
    assert "00:00:00,000" in written

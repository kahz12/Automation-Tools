"""Tests for the A/V Transcriber's upload-polling loop.

The transcriber has to wait for Gemini to finish processing an uploaded media
file before it can transcribe it. That wait must always terminate: a stuck file
or a persistently failing API must not hang the tool forever.
"""
import time

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

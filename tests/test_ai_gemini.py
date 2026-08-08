"""The Gemini adapter, including the Files API upload it alone supports."""
import pytest

from automation_tools.ai.base import Capability
from automation_tools.ai.gemini import GeminiProvider
from automation_tools.ai.registry import PROVIDERS

SPEC = PROVIDERS["gemini"]


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = None


class _FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        return _FakeResp("ok")


class _FakeUploaded:
    name = "files/abc123"
    state = "ACTIVE"


class _FakeFiles:
    def __init__(self):
        self.uploaded = []
        self.deleted = []

    def upload(self, file):
        self.uploaded.append(file)
        return _FakeUploaded()

    def get(self, name):
        return _FakeUploaded()

    def delete(self, name):
        self.deleted.append(name)


class _FakeClient:
    def __init__(self):
        self.models = _FakeModels()
        self.files = _FakeFiles()


@pytest.fixture
def provider(monkeypatch):
    """A GeminiProvider whose SDK client is a double."""
    client = _FakeClient()
    monkeypatch.setattr(GeminiProvider, "_make_client",
                        staticmethod(lambda api_key: client))
    p = GeminiProvider("gemini", SPEC, "AIza-test")
    p._fake = client
    return p


def test_declares_all_three_capabilities(provider):
    assert provider.capabilities == SPEC.capabilities
    assert Capability.AUDIO in provider.capabilities


def test_generate_text_sends_the_prompt(provider):
    assert provider.generate_text("hola") == "ok"
    model, contents = provider._fake.models.calls[0]
    assert contents == "hola"
    assert model == SPEC.text_model


def test_generate_text_prepends_the_system_instruction(provider):
    provider.generate_text("hola", system="Be terse.")
    _model, contents = provider._fake.models.calls[0]
    assert contents.startswith("Be terse.")
    assert "hola" in contents


def test_generate_vision_sends_image_and_prompt(provider):
    assert provider.generate_vision("read this", b"\x89PNG\r\n", "image/png") == "ok"
    _model, contents = provider._fake.models.calls[0]
    assert isinstance(contents, list) and len(contents) == 2
    assert contents[1] == "read this"


def test_model_override_wins_over_the_spec(provider):
    provider.generate_text("hola", model="gemini-2.5-pro")
    model, _contents = provider._fake.models.calls[0]
    assert model == "gemini-2.5-pro"


def test_transcribe_uploads_polls_and_always_deletes(provider, tmp_path):
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert provider.transcribe(str(media), mode="srt") == "ok"
    assert provider._fake.files.uploaded == [str(media)]
    assert provider._fake.files.deleted == ["files/abc123"], (
        "the remote upload must be cleaned up"
    )


def test_transcribe_gives_up_when_the_file_never_becomes_active(provider, tmp_path, monkeypatch):
    class _StuckFile:
        name = "files/stuck"
        state = "PROCESSING"

    monkeypatch.setattr(provider._fake.files, "get", lambda name: _StuckFile())
    monkeypatch.setattr(provider._fake.files, "upload", lambda file: _StuckFile())
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    # timeout=0 makes the deadline expire immediately; sleep is never reached.
    assert provider.transcribe(str(media), timeout=0.0) is None
    assert provider._fake.files.deleted == ["files/stuck"]


def test_transcribe_reports_a_failed_upload(provider, tmp_path):
    class _FailedFile:
        name = "files/bad"
        state = "FAILED"

    provider._fake.files.get = lambda name: _FailedFile()
    provider._fake.files.upload = lambda file: _FailedFile()
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert provider.transcribe(str(media)) is None


def test_transcribe_returns_none_when_the_upload_itself_raises(provider, tmp_path):
    """Distinct from test_transcribe_reports_a_failed_upload: here `upload()`
    raises (e.g. a network error) rather than returning a FAILED-state file.
    Nothing else touches `.files.upload`, so this branch (gemini.py:96-100)
    was previously unexecuted anywhere in the suite.
    """
    def boom(file):
        raise RuntimeError("network down")

    provider._fake.files.upload = boom
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert provider.transcribe(str(media)) is None


def test_transcribe_gives_up_when_the_api_keeps_failing(provider, tmp_path):
    """Persistent polling errors must terminate too; this used to hang
    forever before `_wait_for_active` learned to catch and keep going
    (gemini.py:137-138: except Exception -> print_warning -> keep polling,
    until the deadline). Regression guard for a shipped hang bug.
    """
    def always_raises(name):
        raise RuntimeError("network down")

    provider._fake.files.get = always_raises
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert provider.transcribe(str(media), timeout=0.05, poll_interval=0.01) is None

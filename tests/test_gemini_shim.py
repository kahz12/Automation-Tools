"""End-to-end regression test: registry -> GeminiProvider.transcribe -> run_transcriber.

The name is historical: this once exercised the `gemini_utils` shim, back when
`transcriber.py` drove the google-genai client directly. The shim is gone, but
the file was worth keeping for what it grew into.

It calls the real, non-monkeypatched `ai.registry.get_provider`, which builds a
real `GeminiProvider` whose only stubbed seam is `_make_client`, so no SDK
client is constructed and no socket opens. That is the whole chain a CLI
invocation goes through. `tests/test_transcriber.py` monkeypatches
`transcriber.get_provider` instead, so it never proves the registry wiring holds.

Keep this file: nothing else asserts that `run_transcriber` writes the right
content to the right default path through a real provider build.
"""
import types

import pytest

from automation_tools.ai.gemini import GeminiProvider
from automation_tools.tools import transcriber


class _FakeUploaded:
    name = "files/abc123"
    state = "ACTIVE"


class _FakeFiles:
    def __init__(self):
        self.deleted = []

    def upload(self, file):
        return _FakeUploaded()

    def get(self, name):
        return _FakeUploaded()

    def delete(self, name):
        self.deleted.append(name)


class _FakeModels:
    def generate_content(self, model, contents):
        return types.SimpleNamespace(text="hola mundo", usage_metadata=None)


class _FakeSDKClient:
    """Stands in for the real `google.genai.Client` the SDK would build."""

    def __init__(self):
        self.files = _FakeFiles()
        self.models = _FakeModels()


@pytest.fixture
def fake_sdk_client(monkeypatch):
    """Exercises the REAL registry.get_provider -> GeminiProvider path.

    Only the SDK-construction seam is stubbed (`GeminiProvider._make_client`),
    so `ai.registry.get_provider` (and `resolve_name`/`resolve_key` inside it)
    is untouched and really runs. `GOOGLE_API_KEY` is set explicitly because
    `resolve_key` requires it; `AI_PROVIDER` is already cleared for every test
    by the autouse `_isolate_provider_env` fixture in conftest.py, so
    resolution deterministically lands on the default, "gemini".
    """
    sdk_client = _FakeSDKClient()
    monkeypatch.setattr(GeminiProvider, "_make_client",
                        staticmethod(lambda api_key: sdk_client))
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza-test")
    return sdk_client


def test_transcriber_writes_the_transcript_via_the_real_registry_path(fake_sdk_client, tmp_path):
    """Regression guard: this used to fail with

        AttributeError: 'GeminiProvider' object has no attribute 'files'

    back when `transcriber.py` reached for the SDK's `.files`/`.models` on
    whatever the old shim handed it, while `GeminiProvider` kept the client
    private. The upload/poll orchestration now lives inside the provider, so
    nothing outside it touches the raw SDK surface. This test is what proves
    the whole chain still holds together end to end.
    """
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    assert transcriber.run_transcriber(str(media), mode="txt") is True

    written = media.with_suffix(".txt")
    assert written.read_text(encoding="utf-8") == "hola mundo"
    assert fake_sdk_client.files.deleted == ["files/abc123"], (
        "the remote upload must be cleaned up"
    )

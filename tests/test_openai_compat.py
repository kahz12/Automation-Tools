"""One adapter, six providers. The tests assert the request shape, because
that is the only thing that differs between them and what breaks silently.
"""
import base64

import pytest

from automation_tools.ai.openai_compat import MAX_TRANSCRIBE_BYTES, OpenAICompatProvider
from automation_tools.ai.registry import PROVIDERS


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content="ok"):
        self.choices = [_FakeChoice(content)]
        self.usage = None


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCompletion()


class _FakeTranscriptions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({k: v for k, v in kwargs.items() if k != "file"})
        return "1\n00:00:00,000 --> 00:00:02,000\nhello\n"


class _FakeOpenAI:
    def __init__(self):
        self.chat = type("_Chat", (), {"completions": _FakeCompletions()})()
        self.audio = type("_Audio", (), {"transcriptions": _FakeTranscriptions()})()


def _provider(monkeypatch, name="groq"):
    fake = _FakeOpenAI()
    monkeypatch.setattr(OpenAICompatProvider, "_make_client",
                        staticmethod(lambda api_key, base_url: fake))
    p = OpenAICompatProvider(name, PROVIDERS[name], "test-key")
    p._fake = fake
    return p


@pytest.fixture
def groq(monkeypatch):
    return _provider(monkeypatch, "groq")


# ── text ────────────────────────────────────────────────────────────────────
def test_generate_text_sends_a_user_message(groq):
    assert groq.generate_text("hola") == "ok"
    call = groq._fake.chat.completions.calls[0]
    assert call["messages"] == [{"role": "user", "content": "hola"}]
    assert call["model"] == PROVIDERS["groq"].text_model


def test_system_instruction_becomes_a_system_message(groq):
    groq.generate_text("hola", system="Be terse.")
    messages = groq._fake.chat.completions.calls[0]["messages"]
    assert messages[0] == {"role": "system", "content": "Be terse."}
    assert messages[1]["role"] == "user"


def test_model_override_wins_over_the_spec(groq):
    groq.generate_text("hola", model="openai/gpt-oss-20b")
    assert groq._fake.chat.completions.calls[0]["model"] == "openai/gpt-oss-20b"


# ── vision ──────────────────────────────────────────────────────────────────
def test_generate_vision_sends_a_base64_data_uri(groq):
    assert groq.generate_vision("read this", b"\x89PNG\r\n", "image/png") == "ok"
    content = groq._fake.chat.completions.calls[0]["messages"][0]["content"]

    text_part = next(p for p in content if p["type"] == "text")
    image_part = next(p for p in content if p["type"] == "image_url")
    assert text_part["text"] == "read this"

    expected = base64.b64encode(b"\x89PNG\r\n").decode("ascii")
    assert image_part["image_url"]["url"] == f"data:image/png;base64,{expected}"


def test_vision_uses_the_vision_model_not_the_text_one(groq):
    groq.generate_vision("read this", b"x", "image/png")
    assert groq._fake.chat.completions.calls[0]["model"] == PROVIDERS["groq"].vision_model


# ── audio ───────────────────────────────────────────────────────────────────
def test_transcribe_requests_srt_natively(groq, tmp_path):
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    out = groq.transcribe(str(media), mode="srt")
    assert "00:00:00,000" in out
    call = groq._fake.audio.transcriptions.calls[0]
    assert call["response_format"] == "srt"
    assert call["model"] == PROVIDERS["groq"].audio_model


def test_transcribe_requests_plain_text_in_txt_mode(groq, tmp_path):
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"fake audio")

    groq.transcribe(str(media), mode="txt")
    assert groq._fake.audio.transcriptions.calls[0]["response_format"] == "text"


def test_transcribe_refuses_a_file_over_the_size_limit(groq, tmp_path, capsys):
    media = tmp_path / "huge.mp3"
    media.write_bytes(b"\0" * (MAX_TRANSCRIBE_BYTES + 1))

    assert groq.transcribe(str(media)) is None
    out = capsys.readouterr().out
    assert "gemini" in out.lower(), "must point at the provider that can handle it"
    assert groq._fake.audio.transcriptions.calls == [], "must not upload it"


# ── every openai_compat provider works through the same adapter ─────────────
@pytest.mark.parametrize("name", [
    n for n, s in PROVIDERS.items() if s.family == "openai_compat"
])
def test_each_compat_provider_sends_text_through_the_same_path(monkeypatch, name):
    provider = _provider(monkeypatch, name)
    assert provider.generate_text("hola") == "ok"
    assert provider._fake.chat.completions.calls[0]["model"] == PROVIDERS[name].text_model

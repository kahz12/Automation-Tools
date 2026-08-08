"""Anthropic's Messages API is not OpenAI-compatible: system is a top-level
parameter, images are base64 blocks, max_tokens is mandatory, and the answer
arrives as a list of content blocks.
"""
import base64

import pytest

from automation_tools.ai.anthropic_api import AnthropicProvider
from automation_tools.ai.base import Capability
from automation_tools.ai.registry import PROVIDERS

SPEC = PROVIDERS["anthropic"]


class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, *texts):
        self.content = [_FakeBlock(t) for t in texts]
        self.usage = None


class _FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage("ok")


class _FakeAnthropic:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture
def claude(monkeypatch):
    fake = _FakeAnthropic()
    monkeypatch.setattr(AnthropicProvider, "_make_client",
                        staticmethod(lambda api_key: fake))
    p = AnthropicProvider("anthropic", SPEC, "sk-ant-test")
    p._fake = fake
    return p


def test_does_not_claim_audio(claude):
    assert Capability.AUDIO not in claude.capabilities
    assert Capability.VISION in claude.capabilities


def test_every_call_carries_max_tokens(claude):
    """The Messages API rejects requests without it, so this must never regress."""
    claude.generate_text("hola")
    assert claude._fake.messages.calls[0]["max_tokens"] == SPEC.max_tokens


def test_generate_text_sends_a_user_message(claude):
    assert claude.generate_text("hola") == "ok"
    call = claude._fake.messages.calls[0]
    assert call["model"] == SPEC.text_model
    assert call["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hola"}]}
    ]


def test_system_goes_top_level_not_into_messages(claude):
    claude.generate_text("hola", system="Be terse.")
    call = claude._fake.messages.calls[0]
    assert call["system"] == "Be terse."
    roles = [m["role"] for m in call["messages"]]
    assert "system" not in roles, "Anthropic takes system as a parameter, not a message"


def test_system_is_omitted_when_absent(claude):
    claude.generate_text("hola")
    assert "system" not in claude._fake.messages.calls[0]


def test_generate_vision_sends_a_base64_image_block(claude):
    assert claude.generate_vision("read this", b"\x89PNG\r\n", "image/png") == "ok"
    content = claude._fake.messages.calls[0]["messages"][0]["content"]

    image_block = next(b for b in content if b["type"] == "image")
    assert image_block["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.b64encode(b"\x89PNG\r\n").decode("ascii"),
    }
    assert any(b["type"] == "text" and b["text"] == "read this" for b in content)


def test_joins_multiple_text_blocks_from_the_response(claude, monkeypatch):
    monkeypatch.setattr(claude._fake.messages, "create",
                        lambda **kw: _FakeMessage("part one ", "part two"))
    assert claude.generate_text("hola") == "part one part two"


def test_model_override_wins_over_the_spec(claude):
    claude.generate_text("hola", model="claude-opus-4-1")
    assert claude._fake.messages.calls[0]["model"] == "claude-opus-4-1"

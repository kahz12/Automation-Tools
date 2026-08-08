"""Vocabulary shared by every provider adapter.

No network logic here and no SDK imports, so it stays cheap to import and the
registry can load it just to list capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol


class Capability(Enum):
    """What a provider can be asked to do. One method on AIProvider each."""

    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"


class AIProviderError(Exception):
    """Base for every provider-selection failure. Message is user-facing."""


class UnknownProviderError(AIProviderError):
    """The requested provider name is not in the registry."""


class CapabilityError(AIProviderError):
    """The provider exists but cannot do the requested job."""


class MissingKeyError(AIProviderError):
    """No API key was given and the provider's env var is unset."""


class MissingDependencyError(AIProviderError):
    """The provider's SDK is not installed.

    Each adapter imports its SDK lazily, so this only surfaces for the family
    actually being used. It subclasses AIProviderError on purpose: a bare
    ImportError would sail straight through every tool's error handling and
    reach the user as a traceback.
    """


@dataclass(frozen=True)
class ProviderSpec:
    """Everything that varies between providers, as data.

    Adding a provider is a new entry in `registry.PROVIDERS` and no new code.
    """

    label: str                          # "Groq", shown in the TUI
    family: str                         # "openai_compat" | "gemini" | "anthropic"
    env_key: str                        # "GROQ_API_KEY"
    key_hint: str                       # "gsk_…", the TUI placeholder
    capabilities: frozenset             # frozenset[Capability]
    text_model: str
    base_url: Optional[str] = None      # None for gemini: its SDK knows its host
    vision_model: Optional[str] = None
    audio_model: Optional[str] = None
    # Anthropic's Messages API requires max_tokens on every call. The other
    # families ignore it.
    max_tokens: int = 4096

    def model_for(self, capability: Capability) -> Optional[str]:
        """The default model for one capability, or None if unsupported."""
        return {
            Capability.TEXT: self.text_model,
            Capability.VISION: self.vision_model,
            Capability.AUDIO: self.audio_model,
        }[capability]


class AIProvider(Protocol):
    """The contract the five AI tools program against.

    Every method returns None on failure, having already reported the problem
    on the console. That preserves the behaviour the tools were written against,
    so their error handling did not change when providers became pluggable.

    Adapters only implement the methods their provider supports; the registry
    guarantees nobody reaches an unsupported one.
    """

    name: str
    capabilities: frozenset

    def generate_text(self, prompt: str, *, system: Optional[str] = None,
                      model: Optional[str] = None) -> Optional[str]:
        ...

    def generate_vision(self, prompt: str, image_bytes: bytes, mime_type: str,
                        *, model: Optional[str] = None) -> Optional[str]:
        ...

    def transcribe(self, filepath: str, *, mode: str = "srt",
                   model: Optional[str] = None) -> Optional[str]:
        ...

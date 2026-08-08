"""Which providers exist, what they can do, and how to get one.

Everything that varies between providers lives in PROVIDERS as data. Adding a
provider later is one entry here and no new code, unless it needs a whole new
protocol, in which case it also needs a new family adapter.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, List, Optional

from automation_tools.ai.base import (
    AIProvider,
    Capability,
    CapabilityError,
    MissingDependencyError,
    MissingKeyError,
    ProviderSpec,
    UnknownProviderError,
)
from automation_tools.core.config import get_env_var

TEXT, VISION, AUDIO = Capability.TEXT, Capability.VISION, Capability.AUDIO

DEFAULT_PROVIDER = "gemini"

PROVIDERS: Dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        label="Gemini", family="gemini", base_url=None,
        env_key="GOOGLE_API_KEY", key_hint="AIza…",
        capabilities=frozenset({TEXT, VISION, AUDIO}),
        text_model="gemini-2.5-flash",
        vision_model="gemini-2.5-flash",
        audio_model="gemini-2.5-flash",
    ),
    "openai": ProviderSpec(
        label="OpenAI", family="openai_compat", base_url="https://api.openai.com/v1",
        env_key="OPENAI_API_KEY", key_hint="sk-…",
        capabilities=frozenset({TEXT, VISION, AUDIO}),
        text_model="gpt-4o-mini",
        vision_model="gpt-4o-mini",
        audio_model="whisper-1",
    ),
    "groq": ProviderSpec(
        label="Groq", family="openai_compat", base_url="https://api.groq.com/openai/v1",
        env_key="GROQ_API_KEY", key_hint="gsk_…",
        capabilities=frozenset({TEXT, VISION, AUDIO}),
        # Groq shut down llama-3.3-70b-versatile and llama-4-scout on
        # 2026-08-16; these are the migration targets it named. Whisper turbo
        # is unaffected and stays. Groq rotates models faster than the others,
        # so check console.groq.com/docs/deprecations when this next breaks.
        text_model="openai/gpt-oss-120b",
        vision_model="qwen/qwen3.6-27b",
        audio_model="whisper-large-v3-turbo",
    ),
    "anthropic": ProviderSpec(
        label="Anthropic", family="anthropic", base_url=None,
        env_key="ANTHROPIC_API_KEY", key_hint="sk-ant-…",
        capabilities=frozenset({TEXT, VISION}),
        text_model="claude-sonnet-4-5",
        vision_model="claude-sonnet-4-5",
        max_tokens=8192,
    ),
    "grok": ProviderSpec(
        label="Grok (xAI)", family="openai_compat", base_url="https://api.x.ai/v1",
        env_key="XAI_API_KEY", key_hint="xai-…",
        capabilities=frozenset({TEXT, VISION}),
        # grok-4 was never formally retired, but it is gone from xAI's model
        # catalog and its image support is undocumented, while grok-4.5 (the
        # current flagship) is the model xAI's image-understanding guide is
        # written against. Since this provider advertises VISION, it has to
        # point at a model documented to accept images.
        text_model="grok-4.5",
        vision_model="grok-4.5",
    ),
    "qwen": ProviderSpec(
        label="Qwen", family="openai_compat",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        env_key="DASHSCOPE_API_KEY", key_hint="sk-…",
        capabilities=frozenset({TEXT, VISION}),
        text_model="qwen-plus",
        vision_model="qwen-vl-max",
    ),
    "minimax": ProviderSpec(
        label="MiniMax", family="openai_compat", base_url="https://api.minimax.io/v1",
        env_key="MINIMAX_API_KEY", key_hint="eyJ…",
        capabilities=frozenset({TEXT, VISION}),
        text_model="MiniMax-Text-01",
        vision_model="MiniMax-VL-01",
    ),
    "deepseek": ProviderSpec(
        label="DeepSeek", family="openai_compat", base_url="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY", key_hint="sk-…",
        capabilities=frozenset({TEXT}),
        # The legacy `deepseek-chat` alias was retired on 2026-07-24; only the
        # explicit v4 ids answer now. v4-flash is DeepSeek's standard general
        # model (v4-pro is the heavier, pricier tier).
        text_model="deepseek-v4-flash",
    ),
}


def providers_with(capability: Capability) -> List[str]:
    """Names of every provider that supports `capability`, in registry order."""
    return [n for n, spec in PROVIDERS.items() if capability in spec.capabilities]


def resolve_name(name: Optional[str] = None) -> str:
    """Explicit argument → AI_PROVIDER → gemini. Raises on an unknown name."""
    chosen = (name or get_env_var("AI_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if chosen not in PROVIDERS:
        raise UnknownProviderError(
            f"Unknown provider '{chosen}'. "
            f"Available: {', '.join(PROVIDERS)}"
        )
    return chosen


def resolve_key(name: str, spec: ProviderSpec, api_key: Optional[str] = None) -> str:
    """Explicit key → the provider's own env var. Raises naming the variable."""
    key = api_key or get_env_var(spec.env_key)
    if not key:
        raise MissingKeyError(
            f"No API key for '{name}'. "
            f"Set {spec.env_key} in your environment or pass --key."
        )
    return key


@contextmanager
def _sdk(package: str):
    """Turns a missing SDK into an error the tools already know how to show."""
    try:
        yield
    except ImportError as e:
        raise MissingDependencyError(
            f"The '{package}' package is required for this provider but is not "
            f"installed. Run: pip install {package}"
        ) from e


def _build(name: str, spec: ProviderSpec, api_key: str,
           model: Optional[str]) -> AIProvider:
    """Constructs the adapter for a spec's family.

    Imports are local so that using one provider never pays the import cost of
    the other two SDKs, and so a missing optional SDK only breaks the family
    that needs it. Each family names the pip package it needs, because an
    ImportError here would otherwise escape the tools' `except AIProviderError`
    and reach the user as a traceback.
    """
    # The SDK import happens inside the adapter's constructor, not at module
    # import time, so the guard has to cover both.
    if spec.family == "openai_compat":
        with _sdk("openai"):
            from automation_tools.ai.openai_compat import OpenAICompatProvider
            return OpenAICompatProvider(name, spec, api_key, model)
    if spec.family == "gemini":
        with _sdk("google-genai"):
            from automation_tools.ai.gemini import GeminiProvider
            return GeminiProvider(name, spec, api_key, model)
    if spec.family == "anthropic":
        with _sdk("anthropic"):
            from automation_tools.ai.anthropic_api import AnthropicProvider
            return AnthropicProvider(name, spec, api_key, model)
    raise UnknownProviderError(f"No adapter for provider family '{spec.family}'")


def get_provider(
    capability: Capability,
    name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> AIProvider:
    """Resolves, validates and builds a provider ready for `capability`.

    Raises AIProviderError (with a message meant for the user) rather than
    returning None, so callers handle one failure shape.
    """
    resolved = resolve_name(name)
    spec = PROVIDERS[resolved]

    if capability not in spec.capabilities:
        able = providers_with(capability)
        raise CapabilityError(
            f"'{resolved}' does not support {capability.value}.\n"
            f"  Providers with {capability.value}: {', '.join(able)}\n"
            f"  Try: --provider {able[0]}"
        )

    key = resolve_key(resolved, spec, api_key)
    return _build(resolved, spec, key, model)

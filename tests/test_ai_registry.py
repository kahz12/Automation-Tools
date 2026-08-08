"""Resolution order, capability filtering and key lookup.

These never build a real adapter: `_build` is monkeypatched so no SDK is
imported and no socket is opened.
"""
import builtins

import pytest

from automation_tools.ai import registry
from automation_tools.ai.base import (
    AIProviderError, Capability, CapabilityError, MissingKeyError,
    UnknownProviderError,
)


@pytest.fixture(autouse=True)
def no_ambient_config(monkeypatch):
    """The developer's own AI_PROVIDER / API keys must not leak into tests."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    for spec in registry.PROVIDERS.values():
        monkeypatch.delenv(spec.env_key, raising=False)


@pytest.fixture
def built(monkeypatch):
    """Captures what get_provider would have built, without building it."""
    calls = []

    def fake_build(name, spec, api_key, model):
        calls.append({"name": name, "spec": spec, "api_key": api_key, "model": model})
        return object()

    monkeypatch.setattr(registry, "_build", fake_build)
    return calls


# ── the registry itself ─────────────────────────────────────────────────────
def test_every_advertised_provider_is_present():
    assert set(registry.PROVIDERS) == {
        "gemini", "openai", "groq", "anthropic",
        "grok", "qwen", "minimax", "deepseek",
    }


def test_deepseek_is_the_only_provider_without_vision():
    assert registry.providers_with(Capability.VISION) == [
        n for n in registry.PROVIDERS if n != "deepseek"
    ]


def test_only_gemini_openai_and_groq_do_audio():
    assert set(registry.providers_with(Capability.AUDIO)) == {"gemini", "openai", "groq"}


def test_every_provider_declares_a_model_for_each_capability_it_claims():
    for name, spec in registry.PROVIDERS.items():
        for capability in spec.capabilities:
            assert spec.model_for(capability), (
                f"{name} claims {capability.value} but declares no model for it"
            )


# ── resolution order ────────────────────────────────────────────────────────
def test_defaults_to_gemini_when_nothing_is_configured():
    assert registry.resolve_name() == "gemini"


def test_env_var_overrides_the_default(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    assert registry.resolve_name() == "groq"


def test_explicit_name_beats_the_env_var(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    assert registry.resolve_name("openai") == "openai"


def test_provider_names_are_case_and_space_insensitive(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "  GroQ ")
    assert registry.resolve_name() == "groq"


def test_unknown_provider_names_the_valid_ones():
    with pytest.raises(UnknownProviderError) as excinfo:
        registry.resolve_name("gemeni")
    message = str(excinfo.value)
    assert "gemeni" in message
    assert "gemini" in message, "the error must list what the user could have meant"


# ── capability gate ─────────────────────────────────────────────────────────
def test_refuses_vision_on_deepseek_and_says_who_can(monkeypatch, built):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    with pytest.raises(CapabilityError) as excinfo:
        registry.get_provider(Capability.VISION, name="deepseek")

    message = str(excinfo.value)
    assert "deepseek" in message
    assert "vision" in message
    assert "openai" in message, "must list the providers that do support it"
    assert built == [], "must fail before constructing a client"


def test_refuses_audio_on_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    with pytest.raises(CapabilityError):
        registry.get_provider(Capability.AUDIO, name="anthropic")


def test_allows_a_capability_the_provider_has(monkeypatch, built):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    registry.get_provider(Capability.TEXT, name="deepseek")
    assert built[0]["name"] == "deepseek"


# ── key resolution ──────────────────────────────────────────────────────────
def test_reads_the_key_from_the_providers_own_env_var(monkeypatch, built):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_env")
    registry.get_provider(Capability.TEXT, name="groq")
    assert built[0]["api_key"] == "gsk_from_env"


def test_explicit_key_beats_the_env_var(monkeypatch, built):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_env")
    registry.get_provider(Capability.TEXT, name="groq", api_key="gsk_explicit")
    assert built[0]["api_key"] == "gsk_explicit"


def test_missing_key_names_the_exact_variable_to_set():
    with pytest.raises(MissingKeyError) as excinfo:
        registry.get_provider(Capability.TEXT, name="groq")
    assert "GROQ_API_KEY" in str(excinfo.value)


def test_gemini_still_reads_google_api_key(monkeypatch, built):
    """Backward compatibility: existing setups must keep working untouched."""
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza_existing")
    registry.get_provider(Capability.TEXT)
    assert built[0]["name"] == "gemini"
    assert built[0]["api_key"] == "AIza_existing"


# ── model override ──────────────────────────────────────────────────────────
def test_model_override_is_passed_through(monkeypatch, built):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    registry.get_provider(Capability.TEXT, name="groq", model="openai/gpt-oss-20b")
    assert built[0]["model"] == "openai/gpt-oss-20b"


# ── missing optional SDK ─────────────────────────────────────────────────────
# `openai` and `anthropic` are declared dependencies, but a user on an old
# install (or a partial one) can easily have neither. The import lives inside
# `_build`, so a plain ImportError escapes every tool's `except AIProviderError`
# and surfaces as a raw traceback. These pin the friendly message instead.
def test_a_missing_sdk_is_reported_as_a_provider_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    real_import = builtins.__import__

    def no_openai(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise ModuleNotFoundError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_openai)

    with pytest.raises(AIProviderError) as excinfo:
        registry.get_provider(Capability.TEXT, name="openai")

    message = str(excinfo.value)
    assert "openai" in message
    assert "pip install" in message, "the message has to say how to fix it"


def test_a_missing_sdk_error_is_catchable_by_the_tools(monkeypatch):
    """The tools only catch AIProviderError, so ImportError must not leak."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    real_import = builtins.__import__

    def no_anthropic(name, *args, **kwargs):
        if name == "anthropic" or name.startswith("anthropic."):
            raise ModuleNotFoundError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_anthropic)

    try:
        registry.get_provider(Capability.TEXT, name="anthropic")
    except AIProviderError:
        pass  # what the tools expect
    except ImportError as e:
        pytest.fail(f"ImportError escaped instead of AIProviderError: {e}")


# ── .env.example stays in sync ───────────────────────────────────────────────
def test_env_example_documents_exactly_the_registry_variables():
    """A new provider must not ship without its key documented.

    Adding an entry to PROVIDERS and forgetting `.env.example` leaves users
    with a provider they cannot configure, and nothing else would catch it.
    """
    import pathlib
    import re

    example = pathlib.Path(__file__).parent.parent / ".env.example"
    documented = set(re.findall(r"^([A-Z_]+)=", example.read_text(), re.M))
    expected = {spec.env_key for spec in registry.PROVIDERS.values()}

    assert documented == expected, (
        f"undocumented: {sorted(expected - documented)}, "
        f"stale: {sorted(documented - expected)}"
    )


def test_env_example_never_contains_a_real_key():
    """It is committed, so every value must be blank."""
    import pathlib
    import re

    example = pathlib.Path(__file__).parent.parent / ".env.example"
    filled = [
        line for line in example.read_text().splitlines()
        if re.match(r"^[A-Z_]+=.+", line)
    ]
    assert not filled, f"these lines carry a value: {filled}"

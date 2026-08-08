"""Provider-agnostic access to the AI models the tools use."""
from automation_tools.ai.base import (
    AIProvider,
    AIProviderError,
    Capability,
    CapabilityError,
    MissingDependencyError,
    MissingKeyError,
    ProviderSpec,
    UnknownProviderError,
)
from automation_tools.ai.registry import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    get_provider,
    providers_with,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "Capability",
    "CapabilityError",
    "MissingDependencyError",
    "MissingKeyError",
    "ProviderSpec",
    "UnknownProviderError",
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "get_provider",
    "providers_with",
]

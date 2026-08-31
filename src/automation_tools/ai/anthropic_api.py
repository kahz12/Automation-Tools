"""Anthropic adapter, on the native Messages API.

Anthropic publishes an OpenAI-compatible endpoint, but documents it as a
migration aid rather than something to build on, so this speaks the real API.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from automation_tools.ai.base import Capability, ProviderSpec
from automation_tools.ai.retry import with_retry
from automation_tools.core.logger import console, get_logger

logger = get_logger()


class AnthropicProvider:
    """Implements the text and vision halves of AIProvider.

    `transcribe` is absent on purpose: the registry refuses AUDIO for this
    provider, so nothing can reach it.
    """

    def __init__(self, name: str, spec: ProviderSpec, api_key: str,
                 model: Optional[str] = None) -> None:
        self.name = name
        self.spec = spec
        self.capabilities = spec.capabilities
        self._model_override = model
        self._client = self._make_client(api_key)

    @staticmethod
    def _make_client(api_key: str) -> Any:
        """Split out so tests can substitute a double without touching the SDK."""
        import anthropic
        return anthropic.Anthropic(api_key=api_key)

    def _model(self, capability: Capability, override: Optional[str] = None) -> str:
        return override or self._model_override or self.spec.model_for(capability)

    def _log_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        prompt = getattr(usage, "input_tokens", None)
        out = getattr(usage, "output_tokens", None)
        total = (prompt or 0) + (out or 0)
        logger.info(
            f"Anthropic tokens | model={model} prompt={prompt} out={out} total={total}"
        )
        if total:
            console.print(
                f"[dim]🧮 Tokens: {total} (prompt {prompt} + output {out}) · {model}[/dim]"
            )

    def _message(self, blocks: List[Dict[str, Any]], model: str,
                 system: Optional[str] = None) -> Optional[str]:
        def call():
            kwargs: Dict[str, Any] = {
                "model": model,
                # Mandatory on this API, unlike OpenAI's.
                "max_tokens": self.spec.max_tokens,
                "messages": [{"role": "user", "content": blocks}],
            }
            if system:
                kwargs["system"] = system
            response = self._client.messages.create(**kwargs)
            self._log_usage(response, model)
            return "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )

        return with_retry(call, label=self.spec.label)

    # ── capabilities ────────────────────────────────────────────────────────
    def generate_text(self, prompt: str, *, system: Optional[str] = None,
                      model: Optional[str] = None) -> Optional[str]:
        return self._message(
            [{"type": "text", "text": prompt}],
            self._model(Capability.TEXT, model),
            system=system,
        )

    def generate_vision(self, prompt: str, image_bytes: bytes, mime_type: str,
                        *, model: Optional[str] = None) -> Optional[str]:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return self._message(
            [
                {"type": "image", "source": {
                    "type": "base64", "media_type": mime_type, "data": encoded}},
                {"type": "text", "text": prompt},
            ],
            self._model(Capability.VISION, model),
        )

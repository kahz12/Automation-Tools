"""One adapter for every provider that speaks the OpenAI protocol.

openai, groq, grok, qwen, minimax and deepseek differ only in base_url, key and
model names, all of which live in the registry rather than here.
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

from automation_tools.ai.base import Capability, ProviderSpec
from automation_tools.ai.retry import with_retry
from automation_tools.core.logger import console, print_error, setup_logger

logger = setup_logger()

# Whisper-style endpoints reject large uploads. Gemini's Files API does not,
# which is why the transcriber keeps both providers.
MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024


class OpenAICompatProvider:
    """Implements AIProvider against an OpenAI-compatible HTTP API."""

    def __init__(self, name: str, spec: ProviderSpec, api_key: str,
                 model: Optional[str] = None) -> None:
        self.name = name
        self.spec = spec
        self.capabilities = spec.capabilities
        self._model_override = model
        self._client = self._make_client(api_key, spec.base_url)

    @staticmethod
    def _make_client(api_key: str, base_url: Optional[str]) -> Any:
        """Split out so tests can substitute a double without touching the SDK."""
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url)

    def _model(self, capability: Capability, override: Optional[str] = None) -> str:
        return override or self._model_override or self.spec.model_for(capability)

    def _log_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", None)
        out = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        logger.info(
            f"{self.spec.label} tokens | model={model} prompt={prompt} out={out} total={total}"
        )
        if total:
            console.print(
                f"[dim]🧮 Tokens: {total} (prompt {prompt} + output {out}) · {model}[/dim]"
            )

    def _chat(self, messages: List[Dict[str, Any]], model: str) -> Optional[str]:
        def call():
            response = self._client.chat.completions.create(model=model, messages=messages)
            self._log_usage(response, model)
            return response.choices[0].message.content

        return with_retry(call, label=self.spec.label)

    # ── capabilities ────────────────────────────────────────────────────────
    def generate_text(self, prompt: str, *, system: Optional[str] = None,
                      model: Optional[str] = None) -> Optional[str]:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self._chat(messages, self._model(Capability.TEXT, model))

    def generate_vision(self, prompt: str, image_bytes: bytes, mime_type: str,
                        *, model: Optional[str] = None) -> Optional[str]:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
            ],
        }]
        return self._chat(messages, self._model(Capability.VISION, model))

    def transcribe(self, filepath: str, *, mode: str = "srt",
                   model: Optional[str] = None) -> Optional[str]:
        """Transcribes via the dedicated audio endpoint.

        Unlike Gemini, these return real timestamps rather than ones the model
        invented, but they reject anything over MAX_TRANSCRIBE_BYTES.
        """
        size = os.path.getsize(filepath)
        if size > MAX_TRANSCRIBE_BYTES:
            print_error(
                f"'{os.path.basename(filepath)}' is {size / 1_048_576:.1f} MB; "
                f"{self.spec.label} accepts at most "
                f"{MAX_TRANSCRIBE_BYTES / 1_048_576:.0f} MB.\n"
                f"  Try: --provider gemini (its Files API handles large media)."
            )
            return None

        target_model = self._model(Capability.AUDIO, model)
        response_format = "srt" if mode == "srt" else "text"

        def call():
            with open(filepath, "rb") as handle:
                return self._client.audio.transcriptions.create(
                    model=target_model, file=handle, response_format=response_format,
                )

        result = with_retry(call, label=self.spec.label)
        if result is None:
            return None
        # With response_format srt/text the SDK returns a plain string; with the
        # default json shape it returns an object carrying `.text`.
        return result if isinstance(result, str) else getattr(result, "text", None)

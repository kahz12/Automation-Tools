"""Google Gemini adapter.

The only provider with a Files API, which is what lets the transcriber handle
media far larger than Whisper's per-file limit.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from automation_tools.ai.base import Capability, ProviderSpec
from automation_tools.ai.retry import with_retry
from automation_tools.core.logger import console, print_error, print_warning, setup_logger

logger = setup_logger()

# How long to wait for Gemini to finish processing an uploaded media file, and
# how often to re-check. A file stuck in PROCESSING must never hang the tool.
UPLOAD_TIMEOUT = 600.0  # seconds
POLL_INTERVAL = 3.0     # seconds


class GeminiProvider:
    """Implements AIProvider on top of the google-genai SDK."""

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
        from google import genai
        return genai.Client(api_key=api_key)

    def _model(self, capability: Capability, override: Optional[str] = None) -> str:
        return override or self._model_override or self.spec.model_for(capability)

    def _generate(self, contents: Any, model: str) -> Optional[str]:
        def call():
            response = self._client.models.generate_content(model=model, contents=contents)
            self._log_usage(response, model)
            return response.text

        return with_retry(call, label=self.spec.label)

    def _log_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return
        prompt = getattr(usage, "prompt_token_count", None)
        out = getattr(usage, "candidates_token_count", None)
        total = getattr(usage, "total_token_count", None)
        logger.info(f"Gemini tokens | model={model} prompt={prompt} out={out} total={total}")
        if total:
            console.print(
                f"[dim]🧮 Tokens: {total} (prompt {prompt} + output {out}) · {model}[/dim]"
            )

    # ── capabilities ────────────────────────────────────────────────────────
    def generate_text(self, prompt: str, *, system: Optional[str] = None,
                      model: Optional[str] = None) -> Optional[str]:
        if system:
            prompt = f"{system}\n\n{prompt}"
        return self._generate(prompt, self._model(Capability.TEXT, model))

    def generate_vision(self, prompt: str, image_bytes: bytes, mime_type: str,
                        *, model: Optional[str] = None) -> Optional[str]:
        from google.genai import types

        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        return self._generate([part, prompt], self._model(Capability.VISION, model))

    def transcribe(self, filepath: str, *, mode: str = "srt",
                   model: Optional[str] = None,
                   timeout: float = UPLOAD_TIMEOUT,
                   poll_interval: float = POLL_INTERVAL) -> Optional[str]:
        """Uploads the media, waits for it to become ACTIVE, then transcribes.

        The remote upload is always deleted, including on failure.
        """
        try:
            uploaded = self._client.files.upload(file=filepath)
        except Exception as e:
            print_error(f"Failed to upload file: {e}")
            return None

        console.print(f"[dim]File uploaded. ID: {uploaded.name}. Waiting for processing…[/dim]")

        try:
            if not self._wait_for_active(uploaded.name, timeout, poll_interval):
                return None
            if mode == "srt":
                prompt = (
                    "Transcribe the audio in this file and output it in strict SRT "
                    "subtitle format. Only output the raw SRT content, nothing else "
                    "(no markdown blocks)."
                )
            else:
                prompt = (
                    "Transcribe the audio in this file. Provide a clean, readable "
                    "transcript in paragraphs."
                )
            return self._generate([uploaded, prompt], self._model(Capability.AUDIO, model))
        finally:
            try:
                self._client.files.delete(name=uploaded.name)
            except Exception:
                pass

    def _wait_for_active(self, file_name: str, timeout: float, poll_interval: float) -> bool:
        """Polls until the upload reports ACTIVE. False on FAILED or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                # The SDK's state may be a string or an Enum; compare on text.
                state = str(self._client.files.get(name=file_name).state).upper()
                if "ACTIVE" in state:
                    return True
                if "FAILED" in state:
                    print_error("Gemini failed to process the media file.")
                    return False
            except Exception as e:
                print_warning(f"Error checking file state: {e}")
            time.sleep(poll_interval)

        print_error(f"Gave up waiting for Gemini to process the file after {timeout:.0f}s.")
        return False

"""Screens for the tools backed by a language model."""
from __future__ import annotations

import os

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, RadioButton, RadioSet, Select, Switch
from automation_tools.ai.base import Capability


from automation_tools.cli.screens.base import ProviderFieldMixin, ToolScreen


# ── 3. AI Summarizer ───────────────────────────────────────────────────────
class SummarizerScreen(ProviderFieldMixin, ToolScreen):
    TOOL_TITLE = "📝  Document Summarizer"
    TOOL_DESC = "Generate an executive summary of PDF or TXT files with AI"
    PROVIDER_CAPABILITY = Capability.TEXT

    def compose_fields(self) -> ComposeResult:
        yield Label("File path (PDF or TXT):", classes="field-label")
        yield Input(placeholder="/path/to/file.pdf", id="filepath")
        yield from self.compose_provider_fields()
        yield Label("Save summary to file?", classes="field-label")
        yield Switch(id="save", value=False)
        with Vertical(id="sec-outpath", classes="sub-section"):
            yield Label("Output path (leave empty for auto):", classes="field-label")
            yield Input(placeholder="summary.txt", id="out-path")

    def on_mount(self) -> None:
        self.refresh_provider_key_field(str(self.query_one("#provider", Select).value))
        self.query_one("#sec-outpath").display = False

    @on(Switch.Changed, "#save")
    def _save_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-outpath").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import summarizer
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        provider_name, api_key = self._provider_values()
        save = self._bval(self.query_one("#save", Switch))
        out_path = None
        if save:
            raw = self._ival(self.query_one("#out-path", Input))
            out_path = raw or (os.path.splitext(filepath)[0] + "_summary.txt")
        await self._run_tool(summarizer.run_summarizer, filepath=filepath,
                             api_key=api_key, out_path=out_path,
                             provider=provider_name)


# ── 6. File Translator ─────────────────────────────────────────────────────
class TranslatorScreen(ProviderFieldMixin, ToolScreen):
    TOOL_TITLE = "🌐  File Translator"
    TOOL_DESC = "Translate text, subtitles, or code files with AI"
    PROVIDER_CAPABILITY = Capability.TEXT

    def compose_fields(self) -> ComposeResult:
        yield Label("File to translate:", classes="field-label")
        yield Input(placeholder="/path/to/file.txt", id="filepath")
        yield Label("Target language:", classes="field-label")
        with RadioSet(id="lang"):
            yield RadioButton("English", id="rb-en", value=True)
            yield RadioButton("Spanish", id="rb-es")
            yield RadioButton("French", id="rb-fr")
            yield RadioButton("Portuguese", id="rb-pt")
            yield RadioButton("German", id="rb-de")
            yield RadioButton("Other…", id="rb-other")
        with Vertical(id="sec-other", classes="sub-section"):
            yield Label("Language name:", classes="field-label")
            yield Input(placeholder="Japanese", id="other-lang")
        yield from self.compose_provider_fields()
        yield Label("Save translation to file?", classes="field-label")
        yield Switch(id="save", value=False)

    def on_mount(self) -> None:
        self.refresh_provider_key_field(str(self.query_one("#provider", Select).value))
        self.query_one("#sec-other").display = False

    @on(RadioSet.Changed, "#lang")
    def _lang_changed(self, e: RadioSet.Changed) -> None:
        self.query_one("#sec-other").display = (
            (e.pressed.id if e.pressed else "") == "rb-other"
        )

    async def action_do_run(self) -> None:
        from automation_tools.tools import translator
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        lang_map = {
            "rb-en": "english", "rb-es": "spanish", "rb-fr": "french",
            "rb-pt": "portuguese", "rb-de": "german",
        }
        rid = self._rval(self.query_one("#lang", RadioSet)) or "rb-en"
        if rid == "rb-other":
            lang = self._ival(self.query_one("#other-lang", Input)).lower()
            if not lang:
                self._err("Language name is required.")
                return
        else:
            lang = lang_map.get(rid, "english")
        provider_name, api_key = self._provider_values()
        save = self._bval(self.query_one("#save", Switch))
        out_path = None
        if save:
            base, ext = os.path.splitext(filepath)
            out_path = f"{base}_{lang}{ext}"
        await self._run_tool(translator.run_translator, filepath=filepath,
                             target_lang=lang, api_key=api_key, out_path=out_path,
                             provider=provider_name)


# ── 9. README Generator ────────────────────────────────────────────────────
class ReadmeScreen(ProviderFieldMixin, ToolScreen):
    TOOL_TITLE = "📘  README Generator"
    TOOL_DESC = "Analyze a project and draft its README using AI"
    PROVIDER_CAPABILITY = Capability.TEXT

    def compose_fields(self) -> ComposeResult:
        yield Label("Project directory:", classes="field-label")
        yield Input(placeholder="/path/to/project", id="dir")
        yield from self.compose_provider_fields()

    def on_mount(self) -> None:
        self.refresh_provider_key_field(str(self.query_one("#provider", Select).value))

    async def action_do_run(self) -> None:
        from automation_tools.tools import readme_generator
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Project directory is required.")
            return
        provider_name, api_key = self._provider_values()
        await self._run_tool(readme_generator.run_readme_generator,
                             directory=directory, api_key=api_key,
                             provider=provider_name)


# ── 19. Image OCR ──────────────────────────────────────────────────────────
class OcrScreen(ProviderFieldMixin, ToolScreen):
    TOOL_TITLE = "🔡  Image OCR"
    TOOL_DESC = "Extract text from images or scans with AI vision"
    PROVIDER_CAPABILITY = Capability.VISION

    def compose_fields(self) -> ComposeResult:
        yield Label("Image file or folder:", classes="field-label")
        yield Input(placeholder="/path/to/scan.png  or  /path/to/folder", id="path")
        yield from self.compose_provider_fields()
        yield Label("Reconstruct layout as Markdown? (off = plain text)", classes="field-label")
        yield Switch(id="markdown", value=False)
        yield Label("Language hint (optional):", classes="field-label")
        yield Input(placeholder="e.g. Spanish, English…", id="language")
        yield Label("Recurse into subfolders? (when a folder is given)", classes="field-label")
        yield Switch(id="recursive", value=False)
        yield Label("Output file (single image) or folder (batch) — optional:", classes="field-label")
        yield Input(placeholder="leave empty to auto-name / save next to source", id="out-path")

    def on_mount(self) -> None:
        self.refresh_provider_key_field(str(self.query_one("#provider", Select).value))

    async def action_do_run(self) -> None:
        from automation_tools.tools import ocr
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("An image file or folder is required.")
            return
        provider_name, api_key = self._provider_values()
        await self._run_tool(
            ocr.run_ocr,
            path=path,
            api_key=api_key,
            out_path=self._ival(self.query_one("#out-path", Input)) or None,
            markdown=self._bval(self.query_one("#markdown", Switch)),
            language=self._ival(self.query_one("#language", Input)) or None,
            recursive=self._bval(self.query_one("#recursive", Switch)),
            provider=provider_name,
        )


# ── 21. A/V Transcriber ────────────────────────────────────────────────────
class TranscriberScreen(ProviderFieldMixin, ToolScreen):
    TOOL_TITLE = "🎤  A/V Transcriber"
    TOOL_DESC = "Transcribe audio and video files using AI"
    PROVIDER_CAPABILITY = Capability.AUDIO

    def compose_fields(self) -> ComposeResult:
        yield Label("File path (audio or video):", classes="field-label")
        yield Input(placeholder="/path/to/media.mp3", id="filepath")
        yield Label("Output format:", classes="field-label")
        with RadioSet(id="mode"):
            yield RadioButton("SRT Subtitles", id="rb-srt", value=True)
            yield RadioButton("Plain Text", id="rb-txt")
        yield from self.compose_provider_fields()
        with Vertical(id="sec-outpath", classes="sub-section"):
            yield Label("Output path (leave empty for auto):", classes="field-label")
            yield Input(placeholder="transcription.srt", id="out-path")

    def on_mount(self) -> None:
        self.refresh_provider_key_field(str(self.query_one("#provider", Select).value))

    async def action_do_run(self) -> None:
        from automation_tools.tools import transcriber
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        mode = "srt" if self._rval(self.query_one("#mode", RadioSet)) == "rb-srt" else "txt"
        provider_name, api_key = self._provider_values()
        out_path = self._ival(self.query_one("#out-path", Input)) or None

        await self._run_tool(transcriber.run_transcriber, filepath=filepath,
                             mode=mode, api_key=api_key, out_path=out_path,
                             provider=provider_name)


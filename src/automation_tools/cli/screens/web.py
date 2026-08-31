"""Screens for the tools that go out to the network."""
from __future__ import annotations

import os
from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, RadioButton, RadioSet, Switch


from automation_tools.cli.screens.base import ToolScreen


# ── 2. Price Monitor ───────────────────────────────────────────────────────
class MonitorScreen(ToolScreen):
    TOOL_TITLE = "💰  Price Monitor"
    TOOL_DESC = "Track prices on MercadoLibre and Amazon"

    def compose_fields(self) -> ComposeResult:
        yield Label("Action:", classes="field-label")
        with RadioSet(id="action"):
            yield RadioButton("⚡  Run a check right now", id="rb-now", value=True)
            yield RadioButton("🔁  Start continuous monitoring (hourly)", id="rb-loop")
            yield RadioButton("📝  View configuration file path", id="rb-config")

    async def action_do_run(self) -> None:
        from automation_tools.tools import monitor
        from automation_tools.core.config import get_project_root
        action = self._rval(self.query_one("#action", RadioSet)) or "rb-now"
        if action == "rb-config":
            cfg = os.path.join(get_project_root(), "productos_a_monitorear.json")

            def _show_config() -> None:
                from automation_tools.core.logger import console
                console.print(f"[bold #22d3ee]Config file:[/] {cfg}")
                if os.path.exists(cfg):
                    console.print("[#22c55e]✓ Path exists on disk.[/]")
                    try:
                        size = os.path.getsize(cfg)
                        console.print(f"[dim #94a3b8]Size: {size} bytes[/]")
                    except OSError:
                        pass
                else:
                    console.print("[#f59e0b]⚠ File does not exist yet — it will be created on first run.[/]")

            await self._run_tool(_show_config)
        elif action == "rb-loop":
            await self._run_tool(monitor.run_continuous_monitor)
        else:
            await self._run_tool(monitor.run_price_monitor_job)


# ── 8. YouTube Downloader ──────────────────────────────────────────────────
class YoutubeScreen(ToolScreen):
    TOOL_TITLE = "📺  YouTube Downloader"
    TOOL_DESC = "Download videos and audio in maximum quality"

    def compose_fields(self) -> ComposeResult:
        yield Label("Video or playlist URL:", classes="field-label")
        yield Input(placeholder="https://youtube.com/watch?v=...", id="url")
        yield Label("Download mode:", classes="field-label")
        with RadioSet(id="mode"):
            yield RadioButton("🎬  Video — high quality MP4", id="rb-video", value=True)
            yield RadioButton("🎵  Audio — MP3", id="rb-audio")
        yield Label("Download full playlist?", classes="field-label")
        yield Switch(id="playlist", value=False)

    async def action_do_run(self) -> None:
        from automation_tools.tools import youtube_downloader
        url = self._ival(self.query_one("#url", Input))
        if not url:
            self._err("URL is required.")
            return
        mode_map = {"rb-video": "video", "rb-audio": "audio"}
        mode = mode_map.get(self._rval(self.query_one("#mode", RadioSet)) or "rb-video", "video")
        playlist = self._bval(self.query_one("#playlist", Switch))
        await self._run_tool(youtube_downloader.run_youtube_downloader,
                             url=url, mode=mode, playlist=playlist)


# ── 15. Web Clipper ────────────────────────────────────────────────────────
class WebClipperScreen(ToolScreen):
    TOOL_TITLE = "📰  Web Clipper"
    TOOL_DESC = "Save a web page's main article as clean Markdown or text"

    def compose_fields(self) -> ComposeResult:
        yield Label("Page URL:", classes="field-label")
        yield Input(placeholder="https://example.com/article", id="url")
        yield Label("Output format:", classes="field-label")
        with RadioSet(id="fmt"):
            yield RadioButton("📝  Markdown", id="rb-md", value=True)
            yield RadioButton("📄  Plain text", id="rb-txt")
        with Vertical(id="sec-img", classes="sub-section"):
            yield Label("Include images? (Markdown only)", classes="field-label")
            yield Switch(id="images", value=True)
        yield Label("Save to a file?", classes="field-label")
        yield Switch(id="save", value=True)
        with Vertical(id="sec-out", classes="sub-section"):
            yield Label("Output path (leave empty for auto-name):", classes="field-label")
            yield Input(placeholder="article.md", id="out-path")

    @on(RadioSet.Changed, "#fmt")
    def _fmt_changed(self, e: RadioSet.Changed) -> None:
        self.query_one("#sec-img").display = (
            (e.pressed.id if e.pressed else "rb-md") == "rb-md"
        )

    @on(Switch.Changed, "#save")
    def _save_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-out").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import web_clipper
        url = self._ival(self.query_one("#url", Input))
        if not url:
            self._err("A page URL is required.")
            return
        fmt = "markdown" if (self._rval(self.query_one("#fmt", RadioSet)) or "rb-md") == "rb-md" else "text"
        include_images = self._bval(self.query_one("#images", Switch))
        save = self._bval(self.query_one("#save", Switch))
        out_path = self._ival(self.query_one("#out-path", Input)) or None
        await self._run_tool(
            web_clipper.run_web_clipper,
            url=url, out_path=out_path, fmt=fmt,
            include_images=include_images, save=save,
        )



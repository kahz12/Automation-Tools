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
        clean_url = youtube_downloader.normalize_youtube_url(url)
        if not clean_url:
            self._err("That is not a valid http(s) link.")
            return
        mode_map = {"rb-video": "video", "rb-audio": "audio"}
        mode = mode_map.get(self._rval(self.query_one("#mode", RadioSet)) or "rb-video", "video")
        playlist = self._bval(self.query_one("#playlist", Switch))
        await self._run_tool(youtube_downloader.run_youtube_downloader,
                             url=clean_url, mode=mode, playlist=playlist)


# ── Instagram Downloader ───────────────────────────────────────────────────
class InstagramScreen(ToolScreen):
    TOOL_TITLE = "📸  Instagram Downloader"
    TOOL_DESC = "Download photos, videos and reels from posts, profiles and stories"

    def compose_fields(self) -> ComposeResult:
        from automation_tools.core.config import get_env_var
        from automation_tools.tools.instagram_downloader import COOKIES_ENV

        yield Label("Post, reel, profile or stories link — or a @username:",
                    classes="field-label")
        yield Input(placeholder="https://www.instagram.com/p/...", id="url")
        yield Label("What to download:", classes="field-label")
        with RadioSet(id="media"):
            yield RadioButton("🖼️  Photos and videos", id="rb-all", value=True)
            yield RadioButton("📷  Photos only", id="rb-images")
            yield RadioButton("🎬  Videos only", id="rb-videos")
        yield Label("Profiles only — newest posts to fetch (empty = all):",
                    classes="field-label")
        yield Input(placeholder="e.g. 20", id="limit", type="integer")
        yield Label("Cookies file, for stories, highlights and private accounts "
                    "(optional):", classes="field-label")
        # Prefilled from INSTAGRAM_COOKIES; clearing it means no login.
        yield Input(value=get_env_var(COOKIES_ENV, "") or "",
                    placeholder="~/instagram_cookies.txt", id="cookies")

    async def action_do_run(self) -> None:
        from automation_tools.tools import instagram_downloader
        url = self._ival(self.query_one("#url", Input))
        if not url:
            self._err("A link or @username is required.")
            return
        if not instagram_downloader.classify_url(url)[0]:
            self._err("That is not an Instagram link or username.")
            return
        limit_text = self._ival(self.query_one("#limit", Input))
        limit = None
        if limit_text:
            try:
                limit = int(limit_text)
            except ValueError:
                limit = 0
            if limit < 1:
                self._err("The post limit must be a whole number of 1 or more.")
                return
        cookies = self._ival(self.query_one("#cookies", Input)) or None
        if cookies and not os.path.isfile(os.path.expanduser(cookies)):
            from rich.markup import escape
            self._err(f"Cookies file not found: {escape(cookies)}")
            return
        media_map = {"rb-all": "all", "rb-images": "images", "rb-videos": "videos"}
        media = media_map.get(self._rval(self.query_one("#media", RadioSet)) or "rb-all", "all")
        await self._run_tool(instagram_downloader.run_instagram_downloader,
                             url=url, media=media, limit=limit, cookies=cookies)


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



from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from rich.text import Text

from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Vertical, VerticalScroll
from textual.widgets import Footer, Input, Static

from automation_tools.ai.base import UnknownProviderError
from automation_tools.ai.registry import PROVIDERS, resolve_name
from automation_tools.core.config import get_env_var
from automation_tools.core.logger import ASCII_TITLE, PALETTE, _gradient_text


# ── Per-tool presentation: raw label → (icon, name, short description) ──────
TOOL_INFO: dict[str, tuple[str, str, str]] = {
    "✂️   Massive Renamer": (
        "✂️", "Massive Renamer",
        "Rename batches of files using patterns,\ndates, or text replacement.",
    ),
    "📦  Organize Downloads": (
        "📦", "Organize Downloads",
        "Move files in Downloads into subfolders\nby type. Supports undo and history.",
    ),
    "🧬  Duplicate Detector": (
        "🧬", "Duplicate Detector",
        "Find identical files by content (MD5).\nOptional CSV export and auto-delete.",
    ),
    "👯  Similar Photos": (
        "👯", "Similar Photos",
        "Group photos that look alike even if the\nfiles differ. Resized, re-sent, re-saved.",
    ),
    "🧹  Space Cleaner": (
        "🧹", "Space Cleaner",
        "Detect cache, large, and old files.\nDry-run by default — safe to explore.",
    ),
    "💾  Archiver": (
        "💾", "Archiver",
        "Bundle files into a zip/tar backup, list\nit, or extract it. Dry-run by default.",
    ),
    "🔍  Log Analyzer": (
        "🔍", "Log Analyzer",
        "Scan .log files for keywords or regex\npatterns. Exports a full report.",
    ),
    "🖼️   Image Converter": (
        "🖼️", "Image Converter",
        "Convert images between formats\n(png, jpg, webp…) or render PDF to images.",
    ),
    "🪄  Image Processor": (
        "🪄", "Image Processor",
        "Batch resize, compress or watermark\nimages. Originals are never touched.",
    ),
    "📄  Convert to PDF": (
        "📄", "Convert to PDF",
        "Documents, images or a mixed batch into\nPDF. No external binaries needed.",
    ),
    "📑  PDF Toolkit": (
        "📑", "PDF Toolkit",
        "Merge, split, extract, rotate, encrypt\nor decrypt PDF files. No extra deps.",
    ),
    "📝  Document Summarizer": (
        "📝", "Document Summarizer",
        "Generate an executive summary of PDF\nor TXT files using the AI provider you pick.",
    ),
    "🌐  File Translator": (
        "🌐", "File Translator",
        "Translate text, subtitles, or code files\nto any language via your AI provider.",
    ),
    "📘  README Generator": (
        "📘", "README Generator",
        "Analyze a project directory and auto-generate\na professional README with AI.",
    ),
    "🔡  Image OCR": (
        "🔡", "Image OCR",
        "Extract text from images or scans with AI\nvision. Plain text or Markdown.",
    ),
    "🎤  A/V Transcriber": (
        "🎤", "A/V Transcriber",
        "Transcribe audio or video into SRT\nsubtitles or plain text with AI.",
    ),
    "💰  Price Monitor": (
        "💰", "Price Monitor",
        "Track product prices on MercadoLibre\nand Amazon. Supports Telegram alerts.",
    ),
    "📺  YouTube Downloader": (
        "📺", "YouTube Downloader",
        "Download videos (MP4) or audio (MP3)\nfrom YouTube. Playlist support.",
    ),
    "📰  Web Clipper": (
        "📰", "Web Clipper",
        "Save a web page's main article as clean\nMarkdown or text. Feeds the AI tools.",
    ),
    "🔎  Metadata Extractor": (
        "🔎", "Metadata Extractor",
        "Reveal EXIF data from images and PDFs.\nOptional EXIF-strip to remove GPS data.",
    ),
    "🔐  Password Manager": (
        "🔐", "Password Manager",
        "Generate secure passwords or passphrases.\nStrength check via HaveIBeenPwned.",
    ),
    "🔒  Encryption Vault": (
        "🔒", "Encryption Vault",
        "Encrypt or decrypt files and folders\nwith a password (scrypt + AES-256-GCM).",
    ),
    "🧾  Integrity Checker": (
        "🧾", "Integrity Checker",
        "Create a checksum manifest of a folder\nand verify it later. Detects corruption.",
    ),
    "🔬  File Type Check": (
        "🔬", "File Type Check",
        "Verify a file really is what its extension\nclaims, by reading its magic number.",
    ),
    "🎼  FLAC Authenticity": (
        "🎼", "FLAC Authenticity",
        "Tell real lossless from an MP3 in a\nFLAC costume. Spectrum and checksum.",
    ),
    "⚙️  Dotenv Manager": (
        "⚙️", "Dotenv Manager",
        "Generate .env.example, scan for exposed\n.env files, validate against a template.",
    ),
}


def _key_status() -> str:
    """Hero-banner fragment reporting the key for the provider actually in use.

    This read GOOGLE_API_KEY unconditionally and printed "Gemini key", which
    lied both ways once the AI tools grew past Gemini: it told a correctly
    configured user they had no key, and told someone whose provider has no key
    that they were ready, just because a stale Google key was still exported.
    """
    try:
        spec = PROVIDERS[resolve_name()]
    except UnknownProviderError:
        # $AI_PROVIDER names a provider that does not exist. Reporting some
        # other provider's key here would bury the real problem, so name it.
        return "[#ef4444]✗ unknown $AI_PROVIDER[/]"
    state = ("[#22c55e]✓ set[/]" if get_env_var(spec.env_key)
             else "[#ef4444]✗ not set[/]")
    return f"[#94a3b8]{spec.label} key[/] {state}"


# ── Search box ──────────────────────────────────────────────────────────────
class SearchInput(Input):
    """Filter box. Down / Enter hand focus over to the first matching card."""

    BINDINGS = [
        Binding("down", "to_grid", show=False),
        Binding("enter", "to_grid", show=False),
    ]

    def action_to_grid(self) -> None:
        self.app.focus_first_card()


# ── Tool card: a focusable, clickable tile in the grid ──────────────────────
class ToolCard(Static):
    """One launchable tool. Click or press Enter to open its screen."""

    can_focus = True

    def __init__(self, raw_label: str, icon: str, name: str, desc: str) -> None:
        super().__init__(f"{icon}  {name}")
        self.raw_label = raw_label
        self.tool_name = name
        self.tool_desc = " ".join(desc.split())  # collapse the 2-line blurb

    def on_focus(self) -> None:
        self.app.show_detail(self)

    def on_click(self) -> None:
        self.focus()
        self.app.launch_card(self)

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            self.app.launch_card(self)
        elif event.key in ("up", "down", "left", "right"):
            event.stop()
            self.app.nav(self, event.key)


# ── Home / launcher app ─────────────────────────────────────────────────────
class AutomationApp(App):
    TITLE = "Automation Tools"

    # Below this width the ASCII banner is swapped for a one-line title.
    _COMPACT_WIDTH = 72

    CSS = """
Screen {
    background: #080810;
}

#hero-wrap {
    height: auto;
    background: #0d0d1a;
    border: heavy #7c3aed;
    margin: 1 2 0 2;
    padding: 1 2;
    align-horizontal: center;
}
#hero {
    width: auto;
    height: auto;
    content-align: center middle;
}
#hero-stats {
    width: 1fr;
    height: 1;
    text-align: center;
    margin-top: 1;
}

#search {
    margin: 1 2 0 2;
    border: tall #475569;
    background: #11111d;
    color: #e2e8f0;
}
#search:focus {
    border: tall #22d3ee;
    background: #1a1a2e;
}

#detail {
    height: 1;
    margin: 0 3 0 3;
    color: #64748b;
    text-style: italic;
}

#grid-scroll {
    height: 1fr;
    padding: 0 1 1 1;
    scrollbar-color: #7c3aed #080810;
    scrollbar-color-active: #22d3ee #080810;
    scrollbar-corner-color: #080810;
}

.cat-block {
    height: auto;
}
.cat-title {
    color: #7c3aed;
    text-style: bold;
    margin: 1 2 0 2;
    height: 1;
}
.card-grid {
    height: auto;
    grid-rows: 3;
    grid-gutter: 1 2;
    margin: 0 1 0 1;
}

ToolCard {
    height: 3;
    border: heavy #1f2937;
    background: #0d0d1a;
    color: #94a3b8;
    content-align: center middle;
    text-align: center;
    text-wrap: nowrap;
    text-overflow: ellipsis;
}
ToolCard:hover {
    border: heavy #7c3aed;
    color: #e2e8f0;
}
ToolCard:focus {
    border: heavy #22d3ee;
    background: #1a0a2e;
    color: #22d3ee;
    text-style: bold;
}

#empty {
    width: 1fr;
    height: auto;
    margin: 2 2 0 2;
    text-align: center;
    color: #64748b;
}

Footer {
    background: #0d0d1a;
    color: #7c3aed;
}
"""

    BINDINGS = [
        Binding("slash", "focus_search", "Search"),
        Binding("q", "quit_app", "Quit"),
        Binding("escape", "handle_escape", "Quit", show=False),
    ]

    def __init__(self, menu_entries: list, history: list,
                 record_use: Optional[Callable] = None) -> None:
        super().__init__()
        self._menu_entries = menu_entries
        self._history = history
        self._record_use = record_use or (lambda _: None)
        # raw label → (icon, name, desc), keyed by the stripped label.
        self._info = {k.strip(): v for k, v in TOOL_INFO.items()}

    # ── layout ──────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        with Vertical(id="hero-wrap"):
            yield Static("", id="hero")
            yield Static("", id="hero-stats")
        yield SearchInput(placeholder="Search tools…   (press / )", id="search")
        yield Static("", id="detail")
        with VerticalScroll(id="grid-scroll"):
            recent = [h for h in self._history if h in self._info]
            if recent:
                yield from self._category_block("🕘  Recent", recent[:5])
            for group_label, entries in self._menu_entries:
                labels = [label.strip() for label, _ in entries]
                yield from self._category_block(group_label, labels)
            yield Static("[dim]No tools match your search.[/]", id="empty")
        yield Footer()

    def _category_block(self, title: str, raw_labels: list[str]) -> ComposeResult:
        with Vertical(classes="cat-block"):
            yield Static(title, classes="cat-title")
            with Grid(classes="card-grid"):
                for rl in raw_labels:
                    icon, name, desc = self._info.get(rl, ("🔧", rl, ""))
                    yield ToolCard(rl, icon, name, desc)

    # ── lifecycle ───────────────────────────────────────────────────────
    def on_mount(self) -> None:
        self.query_one("#empty").display = False
        self._set_stats()
        # Widths/regions aren't final until the first paint settles.
        self.call_after_refresh(self._post_mount)

    def _post_mount(self) -> None:
        self._relayout()
        self.focus_first_card()

    def on_resize(self, event: events.Resize) -> None:
        self._relayout()

    # ── rendering helpers ────────────────────────────────────────────────
    def _set_stats(self) -> None:
        n_tools = sum(len(entries) for _, entries in self._menu_entries)
        when = datetime.now().strftime("%Y-%m-%d  %H:%M")
        self.query_one("#hero-stats", Static).update(
            f"[#a78bfa]{n_tools} tools[/]   [#374151]·[/]   "
            f"{_key_status()}   [#374151]·[/]   "
            f"[#64748b]{when}[/]"
        )

    def _relayout(self) -> None:
        # A Resize can arrive before compose finishes (or during teardown);
        # bail out quietly if the widgets aren't in the DOM yet.
        try:
            hero = self.query_one("#hero", Static)
        except Exception:
            return
        width = self.size.width or 80
        # Hero banner: full ASCII art when wide, compact title when narrow.
        if width < self._COMPACT_WIDTH:
            hero.update(Text("⚡  AUTOMATION TOOLS",
                             style=f"bold {PALETTE['accent']}", justify="center"))
        else:
            hero.update(_gradient_text(ASCII_TITLE, PALETTE["primary"], PALETTE["accent"]))
        # Responsive columns, keeping each card at roughly 24 cells or wider.
        available = max(20, width - 6)
        columns = max(1, available // 24)
        for grid in self.query(".card-grid"):
            grid.styles.grid_size_columns = columns

    # ── navigation / focus ────────────────────────────────────────────────
    def focus_first_card(self) -> None:
        for card in self.query(ToolCard):
            if card.display:
                card.focus()
                card.scroll_visible()
                return

    def nav(self, current: ToolCard, key: str) -> None:
        """Geometric 2D move to the nearest visible card in `key` direction."""
        cards = [c for c in self.query(ToolCard) if c.display]
        cr = current.region
        cx, cy = cr.x + cr.width / 2, cr.y + cr.height / 2
        dx = {"left": -1, "right": 1}.get(key, 0)
        dy = {"up": -1, "down": 1}.get(key, 0)

        best, best_score = None, float("inf")
        for c in cards:
            if c is current:
                continue
            r = c.region
            ox, oy = r.x + r.width / 2, r.y + r.height / 2
            if dx > 0 and ox <= cx:
                continue
            if dx < 0 and ox >= cx:
                continue
            if dy > 0 and oy <= cy:
                continue
            if dy < 0 and oy >= cy:
                continue
            # Distance along the travel axis, penalising perpendicular drift.
            if dx != 0:
                score = abs(ox - cx) + abs(oy - cy) * 3
            else:
                score = abs(oy - cy) + abs(ox - cx) * 3
            if score < best_score:
                best, best_score = c, score

        if best is not None:
            best.focus()
            best.scroll_visible()
        elif dy < 0:
            # Already on the top row, so step up into the search box.
            self.query_one("#search", Input).focus()

    def show_detail(self, card: ToolCard) -> None:
        try:
            detail = self.query_one("#detail", Static)
        except Exception:
            return
        desc = f"  —  [#64748b]{card.tool_desc}[/]" if card.tool_desc else ""
        detail.update(
            f"[#94a3b8]{card.tool_name}[/]{desc}   [dim #475569]· Enter to launch[/]"
        )

    # ── search ────────────────────────────────────────────────────────────
    @on(Input.Changed, "#search")
    def _filter(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        any_match = False
        for block in self.query(".cat-block"):
            block_match = False
            for card in block.query(ToolCard):
                match = (
                    True if not query
                    else query in card.tool_name.lower()
                    or query in card.tool_desc.lower()
                )
                card.display = match
                block_match = block_match or match
            block.display = block_match
            any_match = any_match or block_match

        self.query_one("#empty").display = not any_match

        focused = self.focused
        if isinstance(focused, ToolCard) and not focused.display:
            self.focus_first_card()

    # ── launching ──────────────────────────────────────────────────────────
    def launch_card(self, card: ToolCard) -> None:
        from automation_tools.cli.screens import SCREEN_MAP
        screen_cls = SCREEN_MAP.get(card.raw_label)
        if screen_cls:
            self._record_use(card.raw_label)
            self.push_screen(screen_cls())

    # ── actions ──────────────────────────────────────────────────────────
    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_quit_app(self) -> None:
        self.exit(None)

    def action_handle_escape(self) -> None:
        search = self.query_one("#search", Input)
        if search.value:
            search.value = ""
            self.focus_first_card()
        elif self.focused is search:
            self.focus_first_card()
        else:
            self.exit(None)

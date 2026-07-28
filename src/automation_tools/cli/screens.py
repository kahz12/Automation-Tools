from __future__ import annotations

import asyncio
import os
import threading
from typing import Callable, Optional

from rich.color import ColorSystem
from rich.text import Text

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label,
    RadioButton, RadioSet, RichLog, Static, Switch,
)


# ── Shared CSS ─────────────────────────────────────────────────────────────
_CSS = """
Screen {
    background: #080810;
}
Header {
    background: #0d0d1a;
    color: #22d3ee;
    text-style: bold;
}
Footer {
    background: #0d0d1a;
    color: #7c3aed;
}
ScrollableContainer.tool-body {
    background: #080810;
    scrollbar-color: #7c3aed #080810;
    scrollbar-color-active: #22d3ee #080810;
    scrollbar-corner-color: #080810;
    padding: 0 0 2 0;
}
.tool-panel {
    border: heavy #7c3aed;
    padding: 1 2;
    margin: 1 2 1 2;
    height: auto;
}
.section-sep {
    color: #7c3aed;
    text-style: bold;
    margin: 1 2 0 2;
    height: 1;
}
.field-label {
    color: #64748b;
    margin: 0 2 0 2;
    height: 1;
}
Input {
    border: tall #475569;
    background: #11111d;
    color: #e2e8f0;
    margin: 0 2 1 2;
}
Input:focus {
    border: tall #22d3ee;
    background: #1a1a2e;
}
Input.-invalid {
    border: tall #ef4444;
}
RadioSet {
    background: #080810;
    border: tall #374151;
    margin: 0 2 1 2;
    height: auto;
    padding: 0 1;
}
RadioSet:focus {
    border: tall #22d3ee;
}
RadioButton {
    color: #64748b;
    background: #080810;
}
RadioButton.-selected {
    color: #22d3ee;
    text-style: bold;
}
Switch {
    margin: 0 2 1 2;
}
Switch > .switch--slider {
    color: #374151;
}
Switch.-on > .switch--slider {
    color: #22d3ee;
}
.sub-section {
    margin: 0;
    padding: 0;
    height: auto;
}
.error-msg {
    margin: 0 2 1 2;
    height: auto;
    min-height: 1;
}
.btn-row {
    margin: 1 2 0 2;
    height: auto;
}
#run-btn {
    background: #7c3aed;
    color: #ffffff;
    border: heavy #a78bfa;
    margin-right: 1;
    min-width: 18;
    text-style: bold;
}
#run-btn:hover {
    background: #22d3ee;
    color: #080810;
    text-style: bold;
    border: heavy #22d3ee;
}
#run-btn:focus {
    background: #a78bfa;
    border: heavy #22d3ee;
}
#back-btn {
    background: #0d0d1a;
    color: #7c3aed;
    border: heavy #374151;
    min-width: 12;
}
#back-btn:hover {
    background: #1a0a2e;
    border: heavy #7c3aed;
}
"""


# ── Execution screen CSS ───────────────────────────────────────────────────
_EXEC_CSS = _CSS + """
#exec-title {
    color: #22d3ee;
    text-style: bold;
    margin: 1 2 0 2;
    height: auto;
}
#exec-log {
    background: #050508;
    border: heavy #7c3aed;
    margin: 1 2 0 2;
    height: 1fr;
    scrollbar-color: #7c3aed #050508;
    scrollbar-color-active: #22d3ee #050508;
    color: #e2e8f0;
}
#exec-status {
    color: #a78bfa;
    margin: 0 2 0 2;
    height: 1;
    text-style: italic;
}
ExecutionScreen #back-btn:disabled {
    background: #0d0d1a;
    color: #374151;
    border: heavy #1f2937;
}
ExecutionScreen #back-btn {
    background: #7c3aed;
    color: #ffffff;
    border: heavy #a78bfa;
    text-style: bold;
}
ExecutionScreen #back-btn:hover {
    background: #22d3ee;
    color: #080810;
    border: heavy #22d3ee;
}
"""


# ── Confirm modal CSS ──────────────────────────────────────────────────────
_MODAL_CSS = """
ConfirmModal {
    align: center middle;
}
#confirm-dialog {
    background: #0d0d1a;
    border: heavy #7c3aed;
    padding: 1 2;
    width: 64;
    height: auto;
}
#confirm-msg {
    color: #e2e8f0;
    margin: 0 0 1 0;
    height: auto;
}
#confirm-row {
    height: auto;
    align: center middle;
    margin-top: 1;
}
ConfirmModal Button {
    margin: 0 1;
    min-width: 14;
}
#yes-btn {
    background: #7c3aed;
    color: #ffffff;
    border: heavy #a78bfa;
    text-style: bold;
}
#yes-btn:hover {
    background: #22d3ee;
    color: #080810;
    border: heavy #22d3ee;
}
#no-btn {
    background: #0d0d1a;
    color: #ef4444;
    border: heavy #374151;
    text-style: bold;
}
#no-btn:hover {
    background: #1a0000;
    border: heavy #ef4444;
}
"""


# ── Sink: rich Console output → Textual RichLog ────────────────────────────
class _ConsoleSink:
    """File-like target installed onto rich.Console.

    Each `write(data)` chunk arrives on a worker thread; we split by newlines
    and forward each line to the RichLog via `App.call_from_thread`, parsing
    ANSI escapes back into a `rich.text.Text` renderable so colours survive.
    """

    def __init__(self, app, rich_log: RichLog) -> None:
        self._app = app
        self._rich_log = rich_log
        self._pending = ""

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._pending += data
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._emit(line)
        return len(data)

    def flush(self) -> None:
        if self._pending:
            self._emit(self._pending)
            self._pending = ""

    def isatty(self) -> bool:
        return True

    def _emit(self, line: str) -> None:
        try:
            text = Text.from_ansi(line) if line else Text("")
            self._app.call_from_thread(self._rich_log.write, text)
        except Exception:
            pass


# ── Confirm modal ──────────────────────────────────────────────────────────
class ConfirmModal(ModalScreen[bool]):
    CSS = _MODAL_CSS

    BINDINGS = [
        Binding("escape", "deny", "No"),
        Binding("y", "approve", "Yes"),
        Binding("n", "deny", "No"),
    ]

    def __init__(self, message: str, default: bool = False) -> None:
        super().__init__()
        self._message = message
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(f"[bold #22d3ee]?[/]  {self._message}", id="confirm-msg")
            with Horizontal(id="confirm-row"):
                yield Button("✓  Yes", id="yes-btn")
                yield Button("✗  No", id="no-btn")

    def on_mount(self) -> None:
        target = "#yes-btn" if self._default else "#no-btn"
        try:
            self.query_one(target, Button).focus()
        except Exception:
            pass

    @on(Button.Pressed, "#yes-btn")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def _no(self) -> None:
        self.dismiss(False)

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)


# ── In-flow confirm helper (worker-thread side) ────────────────────────────
_CURRENT_EXECUTOR: Optional["ExecutionScreen"] = None


def tui_confirm(message: str, default: bool = False) -> bool:
    """Show a Textual confirm modal from a worker thread, block until answer."""
    executor = _CURRENT_EXECUTOR
    if executor is None:
        return default
    return executor.confirm_blocking(message, default)


# ── Execution screen ───────────────────────────────────────────────────────
class ExecutionScreen(Screen):
    CSS = _EXEC_CSS

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    def __init__(self, title: str, fn: Callable, kwargs: dict) -> None:
        super().__init__()
        self._title = title
        self._fn = fn
        self._kwargs = kwargs
        self._done = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"[bold #22d3ee]▶  {self._title}[/]", id="exec-title")
        yield RichLog(
            id="exec-log", wrap=True, markup=False,
            highlight=False, auto_scroll=True, max_lines=20000,
        )
        yield Static("[bold #a78bfa]●  Running…[/]", id="exec-status")
        with Horizontal(classes="btn-row"):
            yield Button("← BACK", id="back-btn", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._execute(), exclusive=True)

    async def _execute(self) -> None:
        global _CURRENT_EXECUTOR
        _CURRENT_EXECUTOR = self

        from automation_tools.core import logger
        console = logger.console
        rich_log = self.query_one("#exec-log", RichLog)
        sink = _ConsoleSink(self.app, rich_log)

        # Save current Console state
        saved = {
            "_file":            console._file,
            "_force_terminal":  console._force_terminal,
            "_color_system":    console._color_system,
            "_width":           console._width,
        }
        # Redirect rich.Console output → our sink (truecolor, fixed width)
        console._file = sink
        console._force_terminal = True
        console._color_system = ColorSystem.TRUECOLOR
        console._width = 100

        # Patch questionary.confirm → Textual modal
        q_orig = None
        try:
            import questionary

            class _QConfirm:
                def __init__(self, msg: str, default: bool = True, **_kw) -> None:
                    self._msg = msg
                    self._default = bool(default)

                def ask(self) -> bool:
                    return tui_confirm(self._msg, self._default)

            q_orig = questionary.confirm
            questionary.confirm = lambda msg, default=True, **kw: _QConfirm(msg, default, **kw)
        except ImportError:
            questionary = None  # type: ignore

        try:
            await asyncio.to_thread(self._run_sync)
        finally:
            sink.flush()
            for k, v in saved.items():
                setattr(console, k, v)
            if q_orig is not None:
                try:
                    import questionary
                    questionary.confirm = q_orig
                except Exception:
                    pass
            _CURRENT_EXECUTOR = None
            self._done = True
            # We're back on the event-loop thread here (asyncio.to_thread
            # has returned), so call _mark_done directly rather than via
            # call_from_thread (which would raise RuntimeError).
            try:
                self._mark_done()
            except Exception:
                pass

    def _run_sync(self) -> None:
        from automation_tools.core.logger import console, print_error
        try:
            self._fn(**self._kwargs)
        except KeyboardInterrupt:
            console.print("\n[dim #64748b]Interrupted.[/]")
        except Exception as exc:
            import traceback
            print_error(str(exc))
            console.print("[dim #4b5563]" + traceback.format_exc().rstrip() + "[/]")

    def _mark_done(self) -> None:
        try:
            self.query_one("#exec-status", Static).update(
                "[bold #22c55e]✓  Done.[/]  [dim #94a3b8]Press Esc or ← BACK to return.[/]"
            )
            btn = self.query_one("#back-btn", Button)
            btn.disabled = False
            btn.focus()
        except Exception:
            pass

    def action_go_back(self) -> None:
        if self._done:
            self.app.pop_screen()

    @on(Button.Pressed, "#back-btn")
    def _on_back(self) -> None:
        if self._done:
            self.app.pop_screen()

    # ── confirm bridge (called from worker thread) ─────────────────────
    def confirm_blocking(self, message: str, default: bool = False) -> bool:
        event = threading.Event()
        result = [default]

        def _show() -> None:
            def _on_dismiss(answer: Optional[bool]) -> None:
                result[0] = bool(answer) if answer is not None else default
                event.set()
            self.app.push_screen(ConfirmModal(message, default), _on_dismiss)

        try:
            self.app.call_from_thread(_show)
        except Exception:
            return default
        event.wait()
        return result[0]


# ── Base tool screen ───────────────────────────────────────────────────────
class ToolScreen(Screen):
    CSS = _CSS

    TOOL_TITLE = "Tool"

    # The default selector ("*") focuses the first focusable widget, which is
    # the ScrollableContainer itself — keystrokes then drive scrolling instead
    # of reaching the form fields. Restrict to actual form widgets.
    AUTO_FOCUS = "Input, RadioSet"

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("ctrl+r", "do_run", "Run"),
    ]

    def action_go_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#back-btn")
    def _on_back(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#run-btn")
    async def _on_run_btn(self) -> None:
        await self.action_do_run()

    async def action_do_run(self) -> None:
        pass  # Override in subclass

    def _err(self, msg: str) -> None:
        try:
            self.query_one("#error-msg", Static).update(f"[bold #ef4444]✗  {msg}[/]")
        except Exception:
            pass

    def _clear_err(self) -> None:
        try:
            self.query_one("#error-msg", Static).update("")
        except Exception:
            pass

    async def _run_tool(self, fn: Callable, **kwargs) -> None:
        """Push an ExecutionScreen that runs `fn(**kwargs)` inside Textual."""
        self._clear_err()
        self.app.push_screen(ExecutionScreen(self.TOOL_TITLE, fn, kwargs))

    # ── helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _rval(radio: RadioSet) -> Optional[str]:
        btn = radio.pressed_button
        return btn.id if btn else None

    @staticmethod
    def _ival(inp: Input) -> str:
        return inp.value.strip()

    @staticmethod
    def _bval(sw: Switch) -> bool:
        return sw.value


# ── 1. Massive Renamer ─────────────────────────────────────────────────────
class RenamerScreen(ToolScreen):
    TOOL_TITLE = "✂️   Massive Renamer"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]✂️   Massive Renamer[/]\n"
                "[dim #64748b]Rename batches of files using patterns, dates, or text replacement[/]",
                classes="tool-panel",
            )
            yield Label("Directory:", classes="field-label")
            yield Input(placeholder="/path/to/folder", id="dir")
            yield Label("Mode:", classes="field-label")
            with RadioSet(id="mode"):
                yield RadioButton("Pattern  (e.g. photo_{:03d}.jpg)", id="rb-patron", value=True)
                yield RadioButton("Date  (e.g. 2024-01-01_file.jpg)", id="rb-fecha")
                yield RadioButton("Text replacement  (find → replace)", id="rb-replace")
            # Pattern section
            with Vertical(id="sec-patron", classes="sub-section"):
                yield Label("Pattern (use {:03d} for numbering):", classes="field-label")
                yield Input(placeholder="photo_{:03d}", id="pattern")
            # Fecha section
            with Vertical(id="sec-fecha", classes="sub-section"):
                yield Label("Keep original name as suffix?", classes="field-label")
                yield Switch(id="keep-name")
            # Replace section
            with Vertical(id="sec-replace", classes="sub-section"):
                yield Label("Text to find:", classes="field-label")
                yield Input(placeholder="copy of", id="old-text")
                yield Label("Replacement (empty = delete):", classes="field-label")
                yield Input(placeholder="", id="new-text")
            yield Static("[dim #4b5563]── Options ──────────────────────────[/]", classes="section-sep")
            yield Label("Filter by extension (optional, e.g. .jpg):", classes="field-label")
            yield Input(placeholder=".jpg", id="ext")
            yield Label("Apply changes? (off = simulation only)", classes="field-label")
            yield Switch(id="apply", value=False)
            with Vertical(id="sec-preview", classes="sub-section"):
                yield Label("Preview & confirm before applying?", classes="field-label")
                yield Switch(id="preview", value=True)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-fecha").display = False
        self.query_one("#sec-replace").display = False
        self.query_one("#sec-preview").display = False

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-patron"
        self.query_one("#sec-patron").display = (rid == "rb-patron")
        self.query_one("#sec-fecha").display = (rid == "rb-fecha")
        self.query_one("#sec-replace").display = (rid == "rb-replace")

    @on(Switch.Changed, "#apply")
    def _apply_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-preview").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import renamer
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        mode_map = {"rb-patron": "patron", "rb-fecha": "fecha", "rb-replace": "reemplazo"}
        mode = mode_map.get(self._rval(self.query_one("#mode", RadioSet)) or "rb-patron", "patron")
        pattern, old_text, new_text, keep = None, None, "", False
        if mode == "patron":
            pattern = self._ival(self.query_one("#pattern", Input)) or None
        elif mode == "fecha":
            keep = self._bval(self.query_one("#keep-name", Switch))
        elif mode == "reemplazo":
            old_text = self._ival(self.query_one("#old-text", Input))
            if not old_text:
                self._err("Text to find is required.")
                return
            new_text = self._ival(self.query_one("#new-text", Input))
        ext = self._ival(self.query_one("#ext", Input)) or None
        apply_changes = self._bval(self.query_one("#apply", Switch))
        preview = self._bval(self.query_one("#preview", Switch)) if apply_changes else False
        await self._run_tool(
            renamer.run_massive_rename,
            directory=directory, mode=mode, apply_changes=apply_changes,
            ext_filter=ext, pattern=pattern, keep_name=keep,
            old_text=old_text, new_text=new_text, preview=preview,
        )


# ── 2. Price Monitor ───────────────────────────────────────────────────────
class MonitorScreen(ToolScreen):
    TOOL_TITLE = "💰  Price Monitor"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]💰  Price Monitor[/]\n"
                "[dim #64748b]Track prices on MercadoLibre and Amazon[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("⚡  Run a check right now", id="rb-now", value=True)
                yield RadioButton("🔁  Start continuous monitoring (hourly)", id="rb-loop")
                yield RadioButton("📝  View configuration file path", id="rb-config")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

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


# ── 3. AI Summarizer ───────────────────────────────────────────────────────
class SummarizerScreen(ToolScreen):
    TOOL_TITLE = "📝  Document Summarizer"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📝  Document Summarizer[/]\n"
                "[dim #64748b]Generate an executive summary of PDF or TXT files with Gemini AI[/]",
                classes="tool-panel",
            )
            yield Label("File path (PDF or TXT):", classes="field-label")
            yield Input(placeholder="/path/to/file.pdf", id="filepath")
            yield Label("Google API Key (or set GOOGLE_API_KEY env var):", classes="field-label")
            yield Input(placeholder="AIza...", password=True, id="api-key")
            yield Label("Save summary to file?", classes="field-label")
            yield Switch(id="save", value=False)
            with Vertical(id="sec-outpath", classes="sub-section"):
                yield Label("Output path (leave empty for auto):", classes="field-label")
                yield Input(placeholder="summary.txt", id="out-path")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        from automation_tools.core.config import get_env_var
        key = get_env_var("GOOGLE_API_KEY", "")
        if key:
            self.query_one("#api-key", Input).value = key
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
        api_key = self._ival(self.query_one("#api-key", Input)) or None
        save = self._bval(self.query_one("#save", Switch))
        out_path = None
        if save:
            raw = self._ival(self.query_one("#out-path", Input))
            out_path = raw or (os.path.splitext(filepath)[0] + "_summary.txt")
        await self._run_tool(summarizer.run_summarizer, filepath=filepath,
                             api_key=api_key, out_path=out_path)


# ── 4. Image / PDF Converter ───────────────────────────────────────────────
class ConverterScreen(ToolScreen):
    TOOL_TITLE = "🖼️   Image Converter"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🖼️   Image Converter[/]\n"
                "[dim #64748b]Convert images between formats or render PDF pages to images[/]",
                classes="tool-panel",
            )
            yield Label("Mode:", classes="field-label")
            with RadioSet(id="mode"):
                yield RadioButton("🖼️   Convert image or folder", id="rb-img", value=True)
                yield RadioButton("📄  Render PDF to images", id="rb-pdf")
            yield Label("File or folder path:", classes="field-label")
            yield Input(placeholder="/path/to/image_or_folder", id="path")
            # Image options
            with Vertical(id="sec-img", classes="sub-section"):
                yield Label("Output format:", classes="field-label")
                with RadioSet(id="img-fmt"):
                    yield RadioButton("PNG", id="rb-png", value=True)
                    yield RadioButton("JPG", id="rb-jpg")
                    yield RadioButton("WEBP", id="rb-webp")
                    yield RadioButton("TIFF", id="rb-tiff")
                with Vertical(id="sec-quality", classes="sub-section"):
                    yield Label("Quality (1–100):", classes="field-label")
                    yield Input(placeholder="85", id="quality")
            # PDF options
            with Vertical(id="sec-pdf-opts", classes="sub-section"):
                yield Label("Output format:", classes="field-label")
                with RadioSet(id="pdf-fmt"):
                    yield RadioButton("PNG", id="rb-pdf-png", value=True)
                    yield RadioButton("JPG", id="rb-pdf-jpg")
                    yield RadioButton("WEBP", id="rb-pdf-webp")
                yield Label("DPI:", classes="field-label")
                yield Input(placeholder="200", id="dpi")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-pdf-opts").display = False
        self.query_one("#sec-quality").display = False

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-img"
        self.query_one("#sec-img").display = (rid == "rb-img")
        self.query_one("#sec-pdf-opts").display = (rid == "rb-pdf")

    @on(RadioSet.Changed, "#img-fmt")
    def _fmt_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-png"
        self.query_one("#sec-quality").display = rid in ("rb-jpg", "rb-webp")

    async def action_do_run(self) -> None:
        from automation_tools.tools import converter
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        mode = self._rval(self.query_one("#mode", RadioSet)) or "rb-img"
        if mode == "rb-pdf":
            fmt_map = {"rb-pdf-png": "png", "rb-pdf-jpg": "jpg", "rb-pdf-webp": "webp"}
            fmt = fmt_map.get(self._rval(self.query_one("#pdf-fmt", RadioSet)) or "rb-pdf-png", "png")
            try:
                dpi = max(50, min(600, int(self._ival(self.query_one("#dpi", Input)) or "200")))
            except ValueError:
                dpi = 200
            await self._run_tool(converter.run_pdf_to_image, input_path=path,
                                 output_format=fmt, dpi=dpi)
        else:
            fmt_map = {"rb-png": "png", "rb-jpg": "jpg", "rb-webp": "webp", "rb-tiff": "tiff"}
            fmt = fmt_map.get(self._rval(self.query_one("#img-fmt", RadioSet)) or "rb-png", "png")
            try:
                quality = max(1, min(100, int(self._ival(self.query_one("#quality", Input)) or "85")))
            except ValueError:
                quality = 85
            await self._run_tool(converter.run_image_converter, input_path=path,
                                 output_format=fmt, quality=quality)


# ── 5. Convert to PDF ──────────────────────────────────────────────────────
class PdfConverterScreen(ToolScreen):
    TOOL_TITLE = "📄  Convert to PDF"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📄  Convert to PDF[/]\n"
                "[dim #64748b]Transform Office documents to PDF using LibreOffice[/]",
                classes="tool-panel",
            )
            yield Label("File to convert (.docx, .odt, .pptx, …):", classes="field-label")
            yield Input(placeholder="/path/to/document.docx", id="filepath")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    async def action_do_run(self) -> None:
        from automation_tools.tools import converter
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        await self._run_tool(converter.run_pdf_converter, input_path=filepath)


# ── 6. File Translator ─────────────────────────────────────────────────────
class TranslatorScreen(ToolScreen):
    TOOL_TITLE = "🌐  File Translator"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🌐  File Translator[/]\n"
                "[dim #64748b]Translate text, subtitles, or code files with Gemini AI[/]",
                classes="tool-panel",
            )
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
            yield Label("Google API Key:", classes="field-label")
            yield Input(placeholder="AIza...", password=True, id="api-key")
            yield Label("Save translation to file?", classes="field-label")
            yield Switch(id="save", value=False)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        from automation_tools.core.config import get_env_var
        key = get_env_var("GOOGLE_API_KEY", "")
        if key:
            self.query_one("#api-key", Input).value = key
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
        api_key = self._ival(self.query_one("#api-key", Input)) or None
        save = self._bval(self.query_one("#save", Switch))
        out_path = None
        if save:
            base, ext = os.path.splitext(filepath)
            out_path = f"{base}_{lang}{ext}"
        await self._run_tool(translator.run_translator, filepath=filepath,
                             target_lang=lang, api_key=api_key, out_path=out_path)


# ── 7. Duplicate Detector ──────────────────────────────────────────────────
class DuplicatesScreen(ToolScreen):
    TOOL_TITLE = "🧬  Duplicate Detector"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🧬  Duplicate Detector[/]\n"
                "[dim #64748b]Find identical files by content (MD5 hash)[/]",
                classes="tool-panel",
            )
            yield Label("Directory to scan:", classes="field-label")
            yield Input(placeholder="/path/to/folder", id="dir")
            yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
            yield Input(placeholder="*.tmp, backup_*", id="excludes")
            yield Label("Export CSV report of duplicates?", classes="field-label")
            yield Switch(id="export", value=False)
            with Vertical(id="sec-export", classes="sub-section"):
                yield Label("CSV output path:", classes="field-label")
                yield Input(placeholder="duplicates.csv", id="export-path")
            yield Label("Auto-delete duplicates (keep one original)?", classes="field-label")
            yield Switch(id="delete", value=False)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import duplicate_finder
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "duplicates.csv"
        delete = self._bval(self.query_one("#delete", Switch))
        await self._run_tool(duplicate_finder.run_duplicate_finder,
                             directory=directory, auto_delete=delete,
                             excludes=excludes, export_path=export_path)


# ── 8. YouTube Downloader ──────────────────────────────────────────────────
class YoutubeScreen(ToolScreen):
    TOOL_TITLE = "📺  YouTube Downloader"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📺  YouTube Downloader[/]\n"
                "[dim #64748b]Download videos and audio in maximum quality[/]",
                classes="tool-panel",
            )
            yield Label("Video or playlist URL:", classes="field-label")
            yield Input(placeholder="https://youtube.com/watch?v=...", id="url")
            yield Label("Download mode:", classes="field-label")
            with RadioSet(id="mode"):
                yield RadioButton("🎬  Video — high quality MP4", id="rb-video", value=True)
                yield RadioButton("🎵  Audio — MP3", id="rb-audio")
            yield Label("Download full playlist?", classes="field-label")
            yield Switch(id="playlist", value=False)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

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


# ── 9. README Generator ────────────────────────────────────────────────────
class ReadmeScreen(ToolScreen):
    TOOL_TITLE = "📘  README Generator"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📘  README Generator[/]\n"
                "[dim #64748b]Analyze a project and draft its README using Gemini AI[/]",
                classes="tool-panel",
            )
            yield Label("Project directory:", classes="field-label")
            yield Input(placeholder="/path/to/project", id="dir")
            yield Label("Google API Key:", classes="field-label")
            yield Input(placeholder="AIza...", password=True, id="api-key")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        from automation_tools.core.config import get_env_var
        key = get_env_var("GOOGLE_API_KEY", "")
        if key:
            self.query_one("#api-key", Input).value = key

    async def action_do_run(self) -> None:
        from automation_tools.tools import readme_generator
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Project directory is required.")
            return
        api_key = self._ival(self.query_one("#api-key", Input)) or None
        await self._run_tool(readme_generator.run_readme_generator,
                             directory=directory, api_key=api_key)


# ── 10. Metadata Extractor ─────────────────────────────────────────────────
class MetadataScreen(ToolScreen):
    TOOL_TITLE = "🔎  Metadata Extractor"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🔎  Metadata Extractor[/]\n"
                "[dim #64748b]Reveal EXIF data from images and PDF information[/]",
                classes="tool-panel",
            )
            yield Label("File to inspect (PDF, JPG, PNG, …):", classes="field-label")
            yield Input(placeholder="/path/to/file.jpg", id="filepath")
            yield Label("Export metadata to file?", classes="field-label")
            yield Switch(id="export", value=False)
            with Vertical(id="sec-export", classes="sub-section"):
                yield Label("Output path (.json or .csv):", classes="field-label")
                yield Input(placeholder="metadata.json", id="export-path")
            yield Label("Create a copy without EXIF data (images only)?", classes="field-label")
            yield Switch(id="clean", value=False)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-export").display = False

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    async def action_do_run(self) -> None:
        from automation_tools.tools import metadata
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = self._ival(self.query_one("#export-path", Input)) or "metadata.json"
        clean = self._bval(self.query_one("#clean", Switch))
        await self._run_tool(metadata.run_metadata_extractor,
                             filepath=filepath, export_path=export_path, clean_exif=clean)


# ── 11. Downloads Organizer ────────────────────────────────────────────────
class OrganizerScreen(ToolScreen):
    TOOL_TITLE = "📦  Organize Downloads"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📦  Organize Downloads[/]\n"
                "[dim #64748b]Move files in Downloads into subfolders by type[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("📦  Organize now", id="rb-run", value=True)
                yield RadioButton("↩️   Undo last organization", id="rb-undo")
                yield RadioButton("🗂️   List history", id="rb-list")
            with Vertical(id="sec-policy", classes="sub-section"):
                yield Label("If file already exists in destination:", classes="field-label")
                with RadioSet(id="policy"):
                    yield RadioButton("📝  Rename  (file_1.ext)", id="rb-rename", value=True)
                    yield RadioButton("⏭️   Skip", id="rb-skip")
                    yield RadioButton("⚠️   Overwrite", id="rb-overwrite")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        self.query_one("#sec-policy").display = (
            (e.pressed.id if e.pressed else "") == "rb-run"
        )

    async def action_do_run(self) -> None:
        from automation_tools.tools import organizer
        action = self._rval(self.query_one("#action", RadioSet)) or "rb-run"
        if action == "rb-undo":
            await self._run_tool(organizer.undo_last)
        elif action == "rb-list":
            def _list_fn() -> None:
                from automation_tools.core.logger import console
                files = organizer.list_history()
                if not files:
                    console.print("[dim #64748b]No history found.[/]")
                else:
                    console.print(f"[bold #22d3ee]History — {len(files)} entries:[/]")
                    for f in files:
                        console.print(f"  [#a78bfa]•[/] {f}")
            await self._run_tool(_list_fn)
        else:
            policy_map = {"rb-rename": "rename", "rb-skip": "skip", "rb-overwrite": "overwrite"}
            policy = policy_map.get(
                self._rval(self.query_one("#policy", RadioSet)) or "rb-rename", "rename"
            )
            await self._run_tool(organizer.run_download_organizer, collision_policy=policy)


# ── 12. Password Manager ───────────────────────────────────────────────────
class PasswordScreen(ToolScreen):
    TOOL_TITLE = "🔐  Password Manager"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🔐  Password Manager[/]\n"
                "[dim #64748b]Generate passwords, passphrases, and evaluate strength[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("🎲  Generate secure password", id="rb-secure", value=True)
                yield RadioButton("🧠  Generate memorable passphrase", id="rb-phrase")
                yield RadioButton("🛡️   Evaluate password strength", id="rb-strength")
            # Secure password section
            with Vertical(id="sec-secure", classes="sub-section"):
                yield Static("[dim #4b5563]── Secure Password ──────────────────[/]", classes="section-sep")
                yield Label("Length (4–128):", classes="field-label")
                yield Input(placeholder="16", id="length")
                yield Label("Include symbols (!@#$…)?", classes="field-label")
                yield Switch(id="symbols", value=True)
                yield Label("Exclude ambiguous chars (I/l/1, O/0)?", classes="field-label")
                yield Switch(id="no-ambiguous", value=False)
                yield Label("How many to generate?", classes="field-label")
                yield Input(placeholder="5", id="count-pwd")
            # Passphrase section
            with Vertical(id="sec-phrase", classes="sub-section"):
                yield Static("[dim #4b5563]── Passphrase ───────────────────────[/]", classes="section-sep")
                yield Label("Number of words (2–10):", classes="field-label")
                yield Input(placeholder="4", id="num-words")
                yield Label("Word separator:", classes="field-label")
                with RadioSet(id="sep"):
                    yield RadioButton("Hyphen  (-)", id="rb-sep-dash", value=True)
                    yield RadioButton("Dot  (.)", id="rb-sep-dot")
                    yield RadioButton("Underscore  (_)", id="rb-sep-us")
                    yield RadioButton("Space", id="rb-sep-space")
                yield Label("Capitalize words?", classes="field-label")
                yield Switch(id="capitalize", value=True)
                yield Label("Add number at end?", classes="field-label")
                yield Switch(id="add-number", value=True)
                yield Label("Add symbol at end?", classes="field-label")
                yield Switch(id="add-special", value=False)
                yield Label("How many to generate?", classes="field-label")
                yield Input(placeholder="5", id="count-phrase")
            # Strength section
            with Vertical(id="sec-strength", classes="sub-section"):
                yield Static("[dim #4b5563]── Strength Check ───────────────────[/]", classes="section-sep")
                yield Label("Password to evaluate:", classes="field-label")
                yield Input(placeholder="••••••••", password=True, id="check-pwd")
                yield Label("Check HaveIBeenPwned? (k-anonymity, secure)", classes="field-label")
                yield Switch(id="check-breach", value=True)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-phrase").display = False
        self.query_one("#sec-strength").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-secure"
        self.query_one("#sec-secure").display = (rid == "rb-secure")
        self.query_one("#sec-phrase").display = (rid == "rb-phrase")
        self.query_one("#sec-strength").display = (rid == "rb-strength")

    async def action_do_run(self) -> None:
        from automation_tools.tools import password_generator
        action = self._rval(self.query_one("#action", RadioSet)) or "rb-secure"

        if action == "rb-secure":
            try:
                length = max(4, min(128, int(self._ival(self.query_one("#length", Input)) or "16")))
            except ValueError:
                length = 16
            try:
                count = max(1, min(20, int(self._ival(self.query_one("#count-pwd", Input)) or "5")))
            except ValueError:
                count = 5
            await self._run_tool(
                password_generator.run_generate_password,
                length=length,
                use_special=self._bval(self.query_one("#symbols", Switch)),
                exclude_ambiguous=self._bval(self.query_one("#no-ambiguous", Switch)),
                count=count,
            )

        elif action == "rb-phrase":
            try:
                num_words = max(2, min(10, int(self._ival(self.query_one("#num-words", Input)) or "4")))
            except ValueError:
                num_words = 4
            sep_map = {
                "rb-sep-dash": "-", "rb-sep-dot": ".", "rb-sep-us": "_", "rb-sep-space": " "
            }
            sep = sep_map.get(self._rval(self.query_one("#sep", RadioSet)) or "rb-sep-dash", "-")
            try:
                count = max(1, min(20, int(self._ival(self.query_one("#count-phrase", Input)) or "5")))
            except ValueError:
                count = 5
            await self._run_tool(
                password_generator.run_generate_passphrase,
                num_words=num_words,
                separator=sep,
                capitalize=self._bval(self.query_one("#capitalize", Switch)),
                add_number=self._bval(self.query_one("#add-number", Switch)),
                add_special=self._bval(self.query_one("#add-special", Switch)),
                count=count,
            )

        else:  # strength
            pwd = self._ival(self.query_one("#check-pwd", Input))
            if not pwd:
                self._err("Enter the password to evaluate.")
                return
            await self._run_tool(
                password_generator.run_evaluate_strength,
                password=pwd,
                check_breach=self._bval(self.query_one("#check-breach", Switch)),
            )


# ── 13. Space Cleaner ──────────────────────────────────────────────────────
class CleanerScreen(ToolScreen):
    TOOL_TITLE = "🧹  Space Cleaner"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🧹  Space Cleaner[/]\n"
                "[dim #64748b]Detect cache, large, and old files (dry-run by default)[/]",
                classes="tool-panel",
            )
            yield Label("Directory to analyze:", classes="field-label")
            yield Input(placeholder="/path/to/folder", id="dir")
            yield Static("[dim #4b5563]── What to detect ───────────────────[/]", classes="section-sep")
            yield Label("Find junk/cache files?", classes="field-label")
            yield Switch(id="find-junk", value=True)
            yield Label("Find large files?", classes="field-label")
            yield Switch(id="find-large", value=True)
            with Vertical(id="sec-large", classes="sub-section"):
                yield Label("Large file threshold (MB):", classes="field-label")
                yield Input(placeholder="100", id="large-mb")
            yield Label("Find old files?", classes="field-label")
            yield Switch(id="find-old", value=True)
            with Vertical(id="sec-old", classes="sub-section"):
                yield Label("Age threshold (days since last modification):", classes="field-label")
                yield Input(placeholder="365", id="old-days")
            yield Static("[dim #4b5563]── Actions ──────────────────────────[/]", classes="section-sep")
            yield Label("Apply deletion? (off = simulation only)", classes="field-label")
            yield Switch(id="apply", value=False)
            with Vertical(id="sec-delete-all", classes="sub-section"):
                yield Label("Include large/old files in deletion?", classes="field-label")
                yield Switch(id="delete-all", value=False)
            yield Label("Export scan report to file?", classes="field-label")
            yield Switch(id="export", value=False)
            with Vertical(id="sec-export", classes="sub-section"):
                yield Label("Output path (.json or .csv):", classes="field-label")
                yield Input(placeholder="cleaning_report.json", id="export-path")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    @on(Switch.Changed, "#find-large")
    def _large_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-large").display = e.value

    @on(Switch.Changed, "#find-old")
    def _old_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-old").display = e.value

    @on(Switch.Changed, "#apply")
    def _apply_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-delete-all").display = e.value

    @on(Switch.Changed, "#export")
    def _export_changed(self, e: Switch.Changed) -> None:
        self.query_one("#sec-export").display = e.value

    def on_mount(self) -> None:
        self.query_one("#sec-delete-all").display = False
        self.query_one("#sec-export").display = False

    async def action_do_run(self) -> None:
        from automation_tools.tools import space_cleaner
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        try:
            large_mb = max(1, int(self._ival(self.query_one("#large-mb", Input)) or "100"))
        except ValueError:
            large_mb = 100
        try:
            old_days = max(1, int(self._ival(self.query_one("#old-days", Input)) or "365"))
        except ValueError:
            old_days = 365
        apply = self._bval(self.query_one("#apply", Switch))
        export_path = None
        if self._bval(self.query_one("#export", Switch)):
            export_path = (
                self._ival(self.query_one("#export-path", Input)) or "cleaning_report.json"
            )
        await self._run_tool(
            space_cleaner.run_space_cleaner,
            directory=directory,
            large_mb=large_mb,
            old_days=old_days,
            find_junk=self._bval(self.query_one("#find-junk", Switch)),
            find_large=self._bval(self.query_one("#find-large", Switch)),
            find_old=self._bval(self.query_one("#find-old", Switch)),
            apply=apply,
            delete_large_and_old=self._bval(self.query_one("#delete-all", Switch)) if apply else False,
            export_path=export_path,
        )


# ── 14. PDF Toolkit ────────────────────────────────────────────────────────
class PdfToolkitScreen(ToolScreen):
    TOOL_TITLE = "📑  PDF Toolkit"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📑  PDF Toolkit[/]\n"
                "[dim #64748b]Merge, split, extract, rotate, encrypt or decrypt PDF files[/]",
                classes="tool-panel",
            )
            yield Label("Operation:", classes="field-label")
            with RadioSet(id="op"):
                yield RadioButton("🔗  Merge several PDFs into one", id="rb-merge", value=True)
                yield RadioButton("✂️   Split into one file per page", id="rb-split")
                yield RadioButton("📑  Extract selected pages", id="rb-extract")
                yield RadioButton("🔄  Rotate pages", id="rb-rotate")
                yield RadioButton("🔒  Encrypt (set a password)", id="rb-encrypt")
                yield RadioButton("🔓  Decrypt (remove password)", id="rb-decrypt")

            # Merge
            with Vertical(id="sec-merge", classes="sub-section"):
                yield Label("PDF files (comma-separated) or a folder:", classes="field-label")
                yield Input(placeholder="/a.pdf, /b.pdf    or    /folder", id="merge-input")
                yield Label("Output PDF path:", classes="field-label")
                yield Input(placeholder="/path/to/merged.pdf", id="merge-out")

            # Split
            with Vertical(id="sec-split", classes="sub-section"):
                yield Label("PDF file to split:", classes="field-label")
                yield Input(placeholder="/path/to/file.pdf", id="split-input")
                yield Label("Output folder (optional):", classes="field-label")
                yield Input(placeholder="default: <name>_pages", id="split-out")

            # Extract
            with Vertical(id="sec-extract", classes="sub-section"):
                yield Label("PDF file:", classes="field-label")
                yield Input(placeholder="/path/to/file.pdf", id="extract-input")
                yield Label("Pages to keep (1-based, e.g. 1-3,5,8-10):", classes="field-label")
                yield Input(placeholder="1-3,5", id="extract-pages")
                yield Label("Output PDF (optional):", classes="field-label")
                yield Input(placeholder="default: <name>_extract.pdf", id="extract-out")

            # Rotate
            with Vertical(id="sec-rotate", classes="sub-section"):
                yield Label("PDF file:", classes="field-label")
                yield Input(placeholder="/path/to/file.pdf", id="rotate-input")
                yield Label("Angle (clockwise):", classes="field-label")
                with RadioSet(id="rotate-angle"):
                    yield RadioButton("90°", id="rb-90", value=True)
                    yield RadioButton("180°", id="rb-180")
                    yield RadioButton("270°", id="rb-270")
                yield Label("Pages (optional, blank = all pages):", classes="field-label")
                yield Input(placeholder="all pages", id="rotate-pages")
                yield Label("Output PDF (optional):", classes="field-label")
                yield Input(placeholder="default: <name>_rotated.pdf", id="rotate-out")

            # Encrypt
            with Vertical(id="sec-encrypt", classes="sub-section"):
                yield Label("PDF file:", classes="field-label")
                yield Input(placeholder="/path/to/file.pdf", id="encrypt-input")
                yield Label("Password to set:", classes="field-label")
                yield Input(placeholder="••••••••", password=True, id="encrypt-pwd")
                yield Label("Output PDF (optional):", classes="field-label")
                yield Input(placeholder="default: <name>_encrypted.pdf", id="encrypt-out")

            # Decrypt
            with Vertical(id="sec-decrypt", classes="sub-section"):
                yield Label("Encrypted PDF file:", classes="field-label")
                yield Input(placeholder="/path/to/file.pdf", id="decrypt-input")
                yield Label("Current password:", classes="field-label")
                yield Input(placeholder="••••••••", password=True, id="decrypt-pwd")
                yield Label("Output PDF (optional):", classes="field-label")
                yield Input(placeholder="default: <name>_decrypted.pdf", id="decrypt-out")

            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    _SECTIONS = ("merge", "split", "extract", "rotate", "encrypt", "decrypt")

    def on_mount(self) -> None:
        for name in self._SECTIONS:
            if name != "merge":
                self.query_one(f"#sec-{name}").display = False

    @on(RadioSet.Changed, "#op")
    def _op_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-merge"
        selected = rid.replace("rb-", "")
        for name in self._SECTIONS:
            self.query_one(f"#sec-{name}").display = (name == selected)

    async def action_do_run(self) -> None:
        from automation_tools.tools import pdf_toolkit
        op = (self._rval(self.query_one("#op", RadioSet)) or "rb-merge").replace("rb-", "")

        if op == "merge":
            inputs = self._ival(self.query_one("#merge-input", Input))
            out = self._ival(self.query_one("#merge-out", Input))
            if not inputs:
                self._err("Provide PDF files or a folder.")
                return
            if not out:
                self._err("Output path is required.")
                return
            await self._run_tool(pdf_toolkit.run_pdf_merge, inputs=inputs, output_path=out)

        elif op == "split":
            inp = self._ival(self.query_one("#split-input", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            out = self._ival(self.query_one("#split-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_split, input_path=inp, output_dir=out)

        elif op == "extract":
            inp = self._ival(self.query_one("#extract-input", Input))
            pages = self._ival(self.query_one("#extract-pages", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            if not pages:
                self._err("Page selection is required.")
                return
            out = self._ival(self.query_one("#extract-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_extract, input_path=inp,
                                 pages=pages, output_path=out)

        elif op == "rotate":
            inp = self._ival(self.query_one("#rotate-input", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            angle_map = {"rb-90": 90, "rb-180": 180, "rb-270": 270}
            angle = angle_map.get(self._rval(self.query_one("#rotate-angle", RadioSet)) or "rb-90", 90)
            pages = self._ival(self.query_one("#rotate-pages", Input)) or None
            out = self._ival(self.query_one("#rotate-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_rotate, input_path=inp,
                                 angle=angle, pages=pages, output_path=out)

        elif op == "encrypt":
            inp = self._ival(self.query_one("#encrypt-input", Input))
            pwd = self._ival(self.query_one("#encrypt-pwd", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            if not pwd:
                self._err("Password is required.")
                return
            out = self._ival(self.query_one("#encrypt-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_encrypt, input_path=inp,
                                 password=pwd, output_path=out)

        else:  # decrypt
            inp = self._ival(self.query_one("#decrypt-input", Input))
            pwd = self._ival(self.query_one("#decrypt-pwd", Input))
            if not inp:
                self._err("PDF file is required.")
                return
            out = self._ival(self.query_one("#decrypt-out", Input)) or None
            await self._run_tool(pdf_toolkit.run_pdf_decrypt, input_path=inp,
                                 password=pwd, output_path=out)


# ── 15. Web Clipper ────────────────────────────────────────────────────────
class WebClipperScreen(ToolScreen):
    TOOL_TITLE = "📰  Web Clipper"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]📰  Web Clipper[/]\n"
                "[dim #64748b]Save a web page's main article as clean Markdown or text[/]",
                classes="tool-panel",
            )
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
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

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


class ImageProcessorScreen(ToolScreen):
    TOOL_TITLE = "🪄  Image Processor"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🪄  Image Processor[/]\n"
                "[dim #64748b]Batch resize, compress or watermark images. Originals are kept[/]",
                classes="tool-panel",
            )
            yield Label("Operation:", classes="field-label")
            with RadioSet(id="op"):
                yield RadioButton("📐  Resize", id="rb-resize", value=True)
                yield RadioButton("🗜️   Compress", id="rb-compress")
                yield RadioButton("🪄  Watermark", id="rb-watermark")
            yield Label("Image file or folder:", classes="field-label")
            yield Input(placeholder="/path/to/image_or_folder", id="path")
            # Resize options
            with Vertical(id="sec-resize", classes="sub-section"):
                yield Label("Max dimension — longest side, px (leave empty if using %):",
                            classes="field-label")
                yield Input(placeholder="1920", id="max-size")
                yield Label("Or scale by percentage (e.g. 50):", classes="field-label")
                yield Input(placeholder="(optional)", id="scale")
            # Compress options
            with Vertical(id="sec-compress", classes="sub-section"):
                yield Label("Quality (1–100, lower = smaller file):", classes="field-label")
                yield Input(placeholder="80", id="quality")
            # Watermark options
            with Vertical(id="sec-watermark", classes="sub-section"):
                yield Label("Watermark text:", classes="field-label")
                yield Input(placeholder="© My Name 2026", id="wm-text")
                yield Label("Position:", classes="field-label")
                with RadioSet(id="wm-pos"):
                    yield RadioButton("Bottom-right", id="rb-br", value=True)
                    yield RadioButton("Bottom-left", id="rb-bl")
                    yield RadioButton("Top-right", id="rb-tr")
                    yield RadioButton("Top-left", id="rb-tl")
                    yield RadioButton("Center", id="rb-center")
                yield Label("Opacity (0–100):", classes="field-label")
                yield Input(placeholder="50", id="wm-opacity")
            yield Label("Recurse into subfolders?", classes="field-label")
            yield Switch(id="recursive", value=False)
            yield Label("Output folder (leave empty for '<input>/processed'):",
                        classes="field-label")
            yield Input(placeholder="(optional)", id="out-dir")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-compress").display = False
        self.query_one("#sec-watermark").display = False

    @on(RadioSet.Changed, "#op")
    def _op_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-resize"
        self.query_one("#sec-resize").display = (rid == "rb-resize")
        self.query_one("#sec-compress").display = (rid == "rb-compress")
        self.query_one("#sec-watermark").display = (rid == "rb-watermark")

    async def action_do_run(self) -> None:
        from automation_tools.tools import image_processor

        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return

        op_map = {"rb-resize": "resize", "rb-compress": "compress", "rb-watermark": "watermark"}
        operation = op_map.get(self._rval(self.query_one("#op", RadioSet)) or "rb-resize", "resize")
        out_dir = self._ival(self.query_one("#out-dir", Input)) or None
        recursive = self._bval(self.query_one("#recursive", Switch))

        kwargs: dict = {
            "input_path": path,
            "operation": operation,
            "output_dir": out_dir,
            "recursive": recursive,
        }

        if operation == "resize":
            scale_raw = self._ival(self.query_one("#scale", Input))
            max_raw = self._ival(self.query_one("#max-size", Input))
            scale_percent = None
            max_size = None
            if scale_raw:
                try:
                    scale_percent = max(1, min(1000, int(scale_raw)))
                except ValueError:
                    self._err("Scale must be a whole number.")
                    return
            else:
                try:
                    max_size = max(1, int(max_raw or "1920"))
                except ValueError:
                    self._err("Max dimension must be a whole number.")
                    return
            kwargs["scale_percent"] = scale_percent
            kwargs["max_size"] = max_size
        elif operation == "compress":
            try:
                kwargs["quality"] = max(1, min(100, int(self._ival(self.query_one("#quality", Input)) or "80")))
            except ValueError:
                kwargs["quality"] = 80
        else:  # watermark
            text = self._ival(self.query_one("#wm-text", Input))
            if not text:
                self._err("Watermark text is required.")
                return
            pos_map = {
                "rb-br": "bottom-right", "rb-bl": "bottom-left",
                "rb-tr": "top-right", "rb-tl": "top-left", "rb-center": "center",
            }
            kwargs["watermark_text"] = text
            kwargs["wm_position"] = pos_map.get(
                self._rval(self.query_one("#wm-pos", RadioSet)) or "rb-br", "bottom-right"
            )
            try:
                kwargs["wm_opacity"] = max(0, min(100, int(self._ival(self.query_one("#wm-opacity", Input)) or "50")))
            except ValueError:
                kwargs["wm_opacity"] = 50

        await self._run_tool(image_processor.run_batch_image_processor, **kwargs)


class VaultScreen(ToolScreen):
    TOOL_TITLE = "🔒  Encryption Vault"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🔒  Encryption Vault[/]\n"
                "[dim #64748b]Encrypt or decrypt files and folders with a password (AES)[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("🔒  Encrypt", id="rb-encrypt", value=True)
                yield RadioButton("🔓  Decrypt", id="rb-decrypt")
            yield Label("File or folder:", classes="field-label")
            yield Input(placeholder="/path/to/file_or_folder", id="path")
            yield Label("Password:", classes="field-label")
            yield Input(placeholder="••••••••", password=True, id="password")
            # Only shown for encryption: confirm to avoid locking yourself out.
            with Vertical(id="sec-confirm", classes="sub-section"):
                yield Label("Confirm password:", classes="field-label")
                yield Input(placeholder="••••••••", password=True, id="password2")
            yield Label("Recurse into subfolders?", classes="field-label")
            yield Switch(id="recursive", value=True)
            yield Label("Delete originals after? (irreversible — asks to confirm)",
                        classes="field-label")
            yield Switch(id="remove", value=False)
            yield Label("Output folder (leave empty to write next to each file):",
                        classes="field-label")
            yield Input(placeholder="(optional)", id="out-dir")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        is_encrypt = (e.pressed.id if e.pressed else "rb-encrypt") == "rb-encrypt"
        self.query_one("#sec-confirm").display = is_encrypt

    async def action_do_run(self) -> None:
        from automation_tools.tools import vault

        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        password = self.query_one("#password", Input).value
        if not password:
            self._err("Password is required.")
            return

        action = "encrypt" if (self._rval(self.query_one("#action", RadioSet)) or "rb-encrypt") == "rb-encrypt" else "decrypt"
        if action == "encrypt":
            password2 = self.query_one("#password2", Input).value
            if password != password2:
                self._err("Passwords do not match.")
                return

        await self._run_tool(
            vault.run_vault,
            path=path,
            action=action,
            password=password,
            output_dir=self._ival(self.query_one("#out-dir", Input)) or None,
            remove_originals=self._bval(self.query_one("#remove", Switch)),
            recursive=self._bval(self.query_one("#recursive", Switch)),
        )


# ── 18. Archiver ───────────────────────────────────────────────────────────
class ArchiverScreen(ToolScreen):
    TOOL_TITLE = "💾  Archiver"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]💾  Archiver[/]\n"
                "[dim #64748b]Bundle files into a zip/tar backup, list it, or extract it[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("📦  Create a backup archive", id="rb-create", value=True)
                yield RadioButton("📋  List an archive's contents", id="rb-list")
                yield RadioButton("📂  Extract an archive", id="rb-extract")

            # Create
            with Vertical(id="sec-create", classes="sub-section"):
                yield Label("Sources — files/folders (comma-separated):", classes="field-label")
                yield Input(placeholder="/path/to/folder, /path/to/file.txt", id="create-sources")
                yield Label("Output archive (optional):", classes="field-label")
                yield Input(placeholder="default: <source>_<timestamp>", id="create-output")
                yield Label("Format:", classes="field-label")
                with RadioSet(id="create-format"):
                    yield RadioButton("zip", id="rb-zip", value=True)
                    yield RadioButton("tar.gz", id="rb-targz")
                    yield RadioButton("tar.bz2", id="rb-tarbz2")
                yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
                yield Input(placeholder="*.log, __pycache__, node_modules", id="create-exclude")
                yield Label("Include hidden dotfiles?", classes="field-label")
                yield Switch(id="create-hidden", value=False)
                yield Label("Apply? (off = preview only)", classes="field-label")
                yield Switch(id="create-apply", value=False)

            # List
            with Vertical(id="sec-list", classes="sub-section"):
                yield Label("Archive to inspect:", classes="field-label")
                yield Input(placeholder="/path/to/backup.zip", id="list-archive")

            # Extract
            with Vertical(id="sec-extract", classes="sub-section"):
                yield Label("Archive to extract:", classes="field-label")
                yield Input(placeholder="/path/to/backup.zip", id="extract-archive")
                yield Label("Destination folder (optional):", classes="field-label")
                yield Input(placeholder="default: archive name", id="extract-dest")
                yield Label("Overwrite existing files?", classes="field-label")
                yield Switch(id="extract-overwrite", value=False)
                yield Label("Apply? (off = preview only)", classes="field-label")
                yield Switch(id="extract-apply", value=False)

            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    _SECTIONS = ("create", "list", "extract")

    def on_mount(self) -> None:
        for name in self._SECTIONS:
            if name != "create":
                self.query_one(f"#sec-{name}").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        rid = e.pressed.id if e.pressed else "rb-create"
        selected = rid.replace("rb-", "")
        for name in self._SECTIONS:
            self.query_one(f"#sec-{name}").display = (name == selected)

    @staticmethod
    def _split(value: str) -> list:
        return [item.strip() for item in value.split(",") if item.strip()]

    async def action_do_run(self) -> None:
        from automation_tools.tools import archiver
        action = (self._rval(self.query_one("#action", RadioSet)) or "rb-create").replace("rb-", "")

        if action == "create":
            sources = self._split(self._ival(self.query_one("#create-sources", Input)))
            if not sources:
                self._err("At least one source file or folder is required.")
                return
            fmt_map = {"rb-zip": "zip", "rb-targz": "tar.gz", "rb-tarbz2": "tar.bz2"}
            fmt = fmt_map.get(self._rval(self.query_one("#create-format", RadioSet)) or "rb-zip", "zip")
            await self._run_tool(
                archiver.run_archiver,
                action="create",
                sources=sources,
                output=self._ival(self.query_one("#create-output", Input)) or None,
                fmt=fmt,
                exclude=self._split(self._ival(self.query_one("#create-exclude", Input))),
                include_hidden=self._bval(self.query_one("#create-hidden", Switch)),
                apply=self._bval(self.query_one("#create-apply", Switch)),
            )

        elif action == "list":
            archive = self._ival(self.query_one("#list-archive", Input))
            if not archive:
                self._err("Archive path is required.")
                return
            await self._run_tool(archiver.run_archiver, action="list", archive=archive)

        else:  # extract
            archive = self._ival(self.query_one("#extract-archive", Input))
            if not archive:
                self._err("Archive path is required.")
                return
            await self._run_tool(
                archiver.run_archiver,
                action="extract",
                archive=archive,
                dest=self._ival(self.query_one("#extract-dest", Input)) or None,
                overwrite=self._bval(self.query_one("#extract-overwrite", Switch)),
                apply=self._bval(self.query_one("#extract-apply", Switch)),
            )


# ── 19. Image OCR ──────────────────────────────────────────────────────────
class OcrScreen(ToolScreen):
    TOOL_TITLE = "🔡  Image OCR"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🔡  Image OCR[/]\n"
                "[dim #64748b]Extract text from images or scans with Gemini Vision[/]",
                classes="tool-panel",
            )
            yield Label("Image file or folder:", classes="field-label")
            yield Input(placeholder="/path/to/scan.png  or  /path/to/folder", id="path")
            yield Label("Google API Key (or set GOOGLE_API_KEY env var):", classes="field-label")
            yield Input(placeholder="AIza...", password=True, id="api-key")
            yield Label("Reconstruct layout as Markdown? (off = plain text)", classes="field-label")
            yield Switch(id="markdown", value=False)
            yield Label("Language hint (optional):", classes="field-label")
            yield Input(placeholder="e.g. Spanish, English…", id="language")
            yield Label("Recurse into subfolders? (when a folder is given)", classes="field-label")
            yield Switch(id="recursive", value=False)
            yield Label("Output file (single image) or folder (batch) — optional:", classes="field-label")
            yield Input(placeholder="leave empty to auto-name / save next to source", id="out-path")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        from automation_tools.core.config import get_env_var
        key = get_env_var("GOOGLE_API_KEY", "")
        if key:
            self.query_one("#api-key", Input).value = key

    async def action_do_run(self) -> None:
        from automation_tools.tools import ocr
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("An image file or folder is required.")
            return
        await self._run_tool(
            ocr.run_ocr,
            path=path,
            api_key=self._ival(self.query_one("#api-key", Input)) or None,
            out_path=self._ival(self.query_one("#out-path", Input)) or None,
            markdown=self._bval(self.query_one("#markdown", Switch)),
            language=self._ival(self.query_one("#language", Input)) or None,
            recursive=self._bval(self.query_one("#recursive", Switch)),
        )


# ── 20. Integrity Checker ──────────────────────────────────────────────────
class IntegrityScreen(ToolScreen):
    TOOL_TITLE = "🧾  Integrity Checker"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🧾  Integrity Checker[/]\n"
                "[dim #64748b]Create a checksum manifest of a folder and verify it later[/]",
                classes="tool-panel",
            )
            yield Label("Action:", classes="field-label")
            with RadioSet(id="action"):
                yield RadioButton("🧾  Create a checksum manifest", id="rb-create", value=True)
                yield RadioButton("✅  Verify a folder against a manifest", id="rb-verify")
            yield Label("Directory:", classes="field-label")
            yield Input(placeholder="/path/to/folder", id="dir")

            # Create
            with Vertical(id="sec-create", classes="sub-section"):
                yield Label("Hash algorithm:", classes="field-label")
                with RadioSet(id="algorithm"):
                    yield RadioButton("SHA-256  (recommended)", id="rb-sha256", value=True)
                    yield RadioButton("SHA-512", id="rb-sha512")
                    yield RadioButton("MD5  (fast, legacy)", id="rb-md5")
                yield Label("Manifest output path (optional):", classes="field-label")
                yield Input(placeholder="default: <directory>/checksums.sha256", id="output")

            # Verify
            with Vertical(id="sec-verify", classes="sub-section"):
                yield Label("Manifest file (optional — auto-detects checksums.*):", classes="field-label")
                yield Input(placeholder="default: auto-detect inside the folder", id="manifest")
                yield Label("Also report new files not in the manifest?", classes="field-label")
                yield Switch(id="extra", value=True)

            yield Static("[dim #4b5563]── Options ──────────────────────────[/]", classes="section-sep")
            yield Label("Exclude patterns (comma-separated, optional):", classes="field-label")
            yield Input(placeholder="*.log, __pycache__", id="excludes")
            yield Label("Include hidden dotfiles?", classes="field-label")
            yield Switch(id="hidden", value=False)
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#sec-verify").display = False

    @on(RadioSet.Changed, "#action")
    def _action_changed(self, e: RadioSet.Changed) -> None:
        is_create = (e.pressed.id if e.pressed else "rb-create") == "rb-create"
        self.query_one("#sec-create").display = is_create
        self.query_one("#sec-verify").display = not is_create

    async def action_do_run(self) -> None:
        from automation_tools.tools import integrity
        directory = self._ival(self.query_one("#dir", Input))
        if not directory:
            self._err("Directory is required.")
            return
        raw_exc = self._ival(self.query_one("#excludes", Input))
        excludes = [p.strip() for p in raw_exc.split(",") if p.strip()] if raw_exc else None
        include_hidden = self._bval(self.query_one("#hidden", Switch))
        action = (self._rval(self.query_one("#action", RadioSet)) or "rb-create").replace("rb-", "")

        if action == "create":
            alg_map = {"rb-sha256": "sha256", "rb-sha512": "sha512", "rb-md5": "md5"}
            algorithm = alg_map.get(
                self._rval(self.query_one("#algorithm", RadioSet)) or "rb-sha256", "sha256"
            )
            await self._run_tool(
                integrity.run_integrity,
                action="create",
                directory=directory,
                output=self._ival(self.query_one("#output", Input)) or None,
                algorithm=algorithm,
                exclude=excludes,
                include_hidden=include_hidden,
            )
        else:  # verify
            await self._run_tool(
                integrity.run_integrity,
                action="verify",
                directory=directory,
                manifest=self._ival(self.query_one("#manifest", Input)) or None,
                exclude=excludes,
                include_hidden=include_hidden,
                check_extra=self._bval(self.query_one("#extra", Switch)),
            )

# ── 21. A/V Transcriber ────────────────────────────────────────────────────
class TranscriberScreen(ToolScreen):
    TOOL_TITLE = "🎤  A/V Transcriber"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🎤  A/V Transcriber[/]\n"
                "[dim #64748b]Transcribe audio and video files using Gemini AI[/]",
                classes="tool-panel",
            )
            yield Label("File path (audio or video):", classes="field-label")
            yield Input(placeholder="/path/to/media.mp3", id="filepath")
            yield Label("Output format:", classes="field-label")
            with RadioSet(id="mode"):
                yield RadioButton("SRT Subtitles", id="rb-srt", value=True)
                yield RadioButton("Plain Text", id="rb-txt")
            yield Label("Google API Key (or set GOOGLE_API_KEY env var):", classes="field-label")
            yield Input(placeholder="AIza...", password=True, id="api-key")
            with Vertical(id="sec-outpath", classes="sub-section"):
                yield Label("Output path (leave empty for auto):", classes="field-label")
                yield Input(placeholder="transcription.srt", id="out-path")
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        from automation_tools.core.config import get_env_var
        key = get_env_var("GOOGLE_API_KEY", "")
        if key:
            self.query_one("#api-key", Input).value = key

    async def action_do_run(self) -> None:
        from automation_tools.tools import transcriber
        filepath = self._ival(self.query_one("#filepath", Input))
        if not filepath:
            self._err("File path is required.")
            return
        mode = "srt" if self._rval(self.query_one("#mode", RadioSet)) == "rb-srt" else "txt"
        api_key = self._ival(self.query_one("#api-key", Input)) or None
        out_path = self._ival(self.query_one("#out-path", Input)) or None
        
        await self._run_tool(transcriber.run_transcriber, filepath=filepath,
                             mode=mode, api_key=api_key, out_path=out_path)

# ── 22. Log Analyzer ─────────────────────────────────────────────────────────
class LogAnalyzerScreen(ToolScreen):
    TOOL_TITLE = "🔍  Log Analyzer"

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                "[bold #22d3ee]🔍  Log Analyzer[/]\n"
                "[dim #64748b]Scan log files for errors, exceptions or specific patterns[/]",
                classes="tool-panel",
            )
            yield Label("File or Directory path:", classes="field-label")
            yield Input(placeholder="/var/log/ OR /path/to/app.log", id="path")
            yield Label("Keywords (comma separated) or Regex pattern:", classes="field-label")
            yield Input(placeholder="Error, Exception, Fatal", id="keywords")
            
            yield Label("Search mode:", classes="field-label")
            with RadioSet(id="mode"):
                yield RadioButton("Normal text (comma separated)", id="rb-text", value=True)
                yield RadioButton("Regex pattern", id="rb-regex")
                
            yield Label("Case Sensitive?", classes="field-label")
            yield Switch(id="case-sensitive", value=False)
            
            yield Label("Save report to file? (Optional):", classes="field-label")
            yield Input(placeholder="report.txt", id="out-path")
            
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    async def action_do_run(self) -> None:
        from automation_tools.tools import log_analyzer
        path = self._ival(self.query_one("#path", Input))
        if not path:
            self._err("Path is required.")
            return
        keywords = self._ival(self.query_one("#keywords", Input))
        if not keywords:
            self._err("Keywords are required.")
            return
            
        use_regex = self._rval(self.query_one("#mode", RadioSet)) == "rb-regex"
        case_sensitive = self._bval(self.query_one("#case-sensitive", Switch))
        out_path = self._ival(self.query_one("#out-path", Input)) or None
        
        await self._run_tool(
            log_analyzer.run_log_analyzer,
            path=path,
            keywords=keywords,
            use_regex=use_regex,
            ignore_case=not case_sensitive,
            out_path=out_path
        )


# ── Screen map: tool label → Screen class ──────────────────────────────────
SCREEN_MAP: dict[str, type[ToolScreen]] = {
    "✂️   Massive Renamer":     RenamerScreen,
    "📦  Organize Downloads":   OrganizerScreen,
    "🧬  Duplicate Detector":   DuplicatesScreen,
    "🧹  Space Cleaner":        CleanerScreen,
    "💾  Archiver":             ArchiverScreen,
    "🔍  Log Analyzer":        LogAnalyzerScreen,
    "🖼️   Image Converter":      ConverterScreen,
    "🪄  Image Processor":      ImageProcessorScreen,
    "📄  Convert to PDF":       PdfConverterScreen,
    "📑  PDF Toolkit":          PdfToolkitScreen,
    "📝  Document Summarizer":  SummarizerScreen,
    "🌐  File Translator":      TranslatorScreen,
    "📘  README Generator":     ReadmeScreen,
    "🔡  Image OCR":            OcrScreen,
    "🎤  A/V Transcriber":      TranscriberScreen,
    "💰  Price Monitor":        MonitorScreen,
    "📺  YouTube Downloader":   YoutubeScreen,
    "📰  Web Clipper":          WebClipperScreen,
    "🔎  Metadata Extractor":   MetadataScreen,
    "🔐  Password Manager":     PasswordScreen,
    "🔒  Encryption Vault":     VaultScreen,
    "🧾  Integrity Checker":    IntegrityScreen,
}

"""Shared chrome for every tool screen: the layout, the execution view
and the confirm modal.

The 25 tool screens live beside this file, grouped the way the menu
groups them. They were all in one 2356-line module until it stopped
being navigable.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
from typing import Any, Callable, Optional
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button, Footer, Header, Input, Label, ProgressBar, RadioSet, RichLog, Select,
    Static, Switch,
)
from automation_tools.ai.base import Capability


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
Select {
    margin: 0 2 1 2;
    height: auto;
}
Select SelectCurrent {
    border: tall #475569;
    background: #11111d;
    color: #e2e8f0;
}
Select:focus SelectCurrent {
    border: tall #22d3ee;
    background: #1a1a2e;
}
Select SelectOverlay {
    border: tall #22d3ee;
    background: #11111d;
    color: #e2e8f0;
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
#exec-progress {
    margin: 0 2 0 2;
    height: 1;
}
#exec-cancel-btn {
    background: #7f1d1d;
    color: #ffffff;
    border: heavy #ef4444;
    min-width: 18;
    text-style: bold;
}
#exec-cancel-btn:hover {
    background: #ef4444;
    color: #080810;
    border: heavy #fca5a5;
}
#exec-cancel-btn:disabled {
    background: #0d0d1a;
    color: #374151;
    border: heavy #1f2937;
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

    def __init__(self, app, rich_log: RichLog, on_line: Optional[Callable[[], None]] = None) -> None:
        self._app = app
        self._rich_log = rich_log
        self._on_line = on_line
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
        if self._on_line is not None:
            try:
                self._on_line()
            except Exception:
                pass
        try:
            text = Text.from_ansi(line) if line else Text("")
            if threading.current_thread() is threading.main_thread():
                self._rich_log.write(text)
            else:
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


class TuiCancelled(Exception):
    """Raised by a cooperative tool when the user cancels its TUI run.

    Tool functions are not required to know about the TUI.  Functions that do
    accept the optional ``cancel_event`` can either return as soon as it is
    set, or call :func:`tui_check_cancelled` between file operations.  The
    latter gives them one common exception to catch when cleanup is needed.
    """


def tui_cancelled() -> bool:
    """Return whether the current TUI execution has received cancellation."""
    executor = _CURRENT_EXECUTOR
    return bool(executor is not None and executor.cancel_event.is_set())


def tui_check_cancelled() -> None:
    """Stop a cooperative TUI task at a safe file-operation boundary."""
    if tui_cancelled():
        raise TuiCancelled()


def tui_progress(
    current: Optional[float] = None,
    total: Optional[float] = None,
    message: Optional[str] = None,
) -> None:
    """Report optional progress from a tool running inside the TUI.

    This is intentionally a no-op for CLI/library callers.  It lets existing
    tool APIs gain a progress display without requiring a mandatory argument
    or changing their standalone behaviour.
    """
    executor = _CURRENT_EXECUTOR
    if executor is not None:
        executor.update_progress(current=current, total=total, message=message)


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
        Binding("escape", "go_back", "Cancel / back"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(self, title: str, fn: Callable, kwargs: dict) -> None:
        super().__init__()
        self._title = title
        self._fn = fn
        self._kwargs = kwargs
        self._done = False
        self._cancel_requested = False
        self._cancel_event = threading.Event()
        self._output_lines = 0
        self._confirm_event: Optional[threading.Event] = None
        self._confirm_modal: Optional[ConfirmModal] = None

    @property
    def cancel_event(self) -> threading.Event:
        """Event passed to tools that opt into cooperative cancellation."""
        return self._cancel_event

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(f"[bold #22d3ee]▶  {self._title}[/]", id="exec-title")
        yield RichLog(
            id="exec-log", wrap=True, markup=False,
            highlight=False, auto_scroll=True, max_lines=20000,
        )
        yield ProgressBar(total=None, id="exec-progress", show_eta=False)
        yield Static("[bold #a78bfa]●  Running…[/]", id="exec-status")
        with Horizontal(classes="btn-row"):
            yield Button("■  CANCEL", id="exec-cancel-btn")
            yield Button("← BACK", id="back-btn", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        # Keep the worker alive while cancellation is requested.  Textual's
        # Worker.cancel() would only cancel the coroutine awaiting
        # ``to_thread``; the underlying thread could keep writing files after
        # the screen had already reported completion.
        self._worker = self.run_worker(self._execute(), exclusive=True)

    async def _execute(self) -> None:
        global _CURRENT_EXECUTOR
        _CURRENT_EXECUTOR = self

        from automation_tools.core import prompt
        from automation_tools.core.logger import redirect_console

        rich_log = self.query_one("#exec-log", RichLog)
        sink = _ConsoleSink(self.app, rich_log, self._record_output_line)

        # Everything the tool prints goes to the log pane, and anything it asks
        # comes back as a modal. Both are scoped to this block, so neither can
        # outlive the run.
        try:
            with redirect_console(sink), prompt.confirm_backend(tui_confirm):
                await asyncio.to_thread(self._run_sync)
        finally:
            sink.flush()
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
        call_kwargs = dict(self._kwargs)
        # Optional hooks are injected only when the callable explicitly
        # declares them.  This preserves every existing tool signature and
        # avoids sending internal arguments to wrappers accepting **kwargs.
        params: Any = {}
        try:
            params = inspect.signature(self._fn).parameters
        except (TypeError, ValueError):
            params = {}
        if "cancel_event" in params:
            call_kwargs["cancel_event"] = self._cancel_event
        if "progress_callback" in params:
            call_kwargs["progress_callback"] = self.update_progress
        try:
            self._fn(**call_kwargs)
        except TuiCancelled:
            console.print("\n[dim #f59e0b]Cancellation acknowledged at a safe boundary.[/]")
        except KeyboardInterrupt:
            console.print("\n[dim #64748b]Interrupted.[/]")
        except Exception as exc:
            import traceback
            print_error(str(exc))
            console.print("[dim #4b5563]" + traceback.format_exc().rstrip() + "[/]")

    def _record_output_line(self) -> None:
        """Keep an honest activity indicator when a tool has no callback."""
        self._output_lines += 1
        if self._cancel_requested:
            return
        self.update_progress(
            message=(
                f"Running… · {self._output_lines} output step(s)"
            )
        )

    def update_progress(
        self,
        current: Optional[float] = None,
        total: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        """Thread-safe progress hook for cooperative tool functions."""
        def _update() -> None:
            try:
                bar = self.query_one("#exec-progress", ProgressBar)
                if total is not None:
                    bar.update(total=max(0.0, total))
                if current is not None:
                    bar.update(progress=max(0.0, current))
                elif total is None:
                    bar.update(advance=1)
                if message:
                    self._set_status(f"[bold #a78bfa]●  {message}[/]")
            except Exception:
                pass

        # ``update_progress`` is normally called by the ``to_thread`` worker,
        # but tests and a few integrations call it on the UI thread directly.
        # Textual's ``call_from_thread`` waits for the callback and therefore
        # must never be used from the event-loop thread (it would deadlock).
        if threading.current_thread() is threading.main_thread():
            _update()
            return
        try:
            self.app.call_from_thread(_update)
        except Exception:
            # Useful for unit tests calling the hook before the app loop has
            # started, and harmless if the screen has already been unmounted.
            _update()

    def _set_status(self, message: str) -> None:
        try:
            self.query_one("#exec-status", Static).update(message)
        except Exception:
            pass

    def _request_cancel(self) -> None:
        if self._done or self._cancel_requested:
            return
        self._cancel_requested = True
        self._cancel_event.set()
        self._set_status(
            "[bold #f59e0b]⚠  Cancellation requested…[/] "
            "[dim #94a3b8]finishing the current safe step.[/]"
        )
        try:
            self.query_one("#exec-cancel-btn", Button).disabled = True
        except Exception:
            pass
        # A tool can be blocked waiting for a confirmation modal.  Dismiss it
        # so its worker can observe the event and unwind instead of hanging.
        modal = self._confirm_modal
        if modal is not None:
            try:
                modal.dismiss(False)
            except Exception:
                pass

    def action_cancel(self) -> None:
        self._request_cancel()

    def _mark_done(self) -> None:
        try:
            if self._cancel_requested:
                status = (
                    "[bold #f59e0b]■  Canceled safely.[/]  "
                    "[dim #94a3b8]No further writes will be started. Press Esc or ← BACK.[/]"
                )
            else:
                status = (
                    "[bold #22c55e]✓  Done.[/]  "
                    "[dim #94a3b8]Press Esc or ← BACK to return.[/]"
                )
            self.query_one("#exec-status", Static).update(status)
            btn = self.query_one("#back-btn", Button)
            btn.disabled = False
            self.query_one("#exec-cancel-btn", Button).disabled = True
            btn.focus()
        except Exception:
            pass

    def action_go_back(self) -> None:
        if self._done:
            self.app.pop_screen()
        else:
            self._request_cancel()

    @on(Button.Pressed, "#exec-cancel-btn")
    def _on_cancel(self) -> None:
        self._request_cancel()

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
                self._confirm_modal = None
                self._confirm_event = None
            self._confirm_modal = ConfirmModal(message, default)
            self._confirm_event = event
            self.app.push_screen(self._confirm_modal, _on_dismiss)

        try:
            self.app.call_from_thread(_show)
        except Exception:
            return default
        while not event.wait(0.1):
            if self._cancel_event.is_set():
                return default
        return result[0]


# ── Base tool screen ───────────────────────────────────────────────────────
class ToolScreen(Screen):
    CSS = _CSS

    # Subclasses supply these two plus `compose_fields`; the surrounding chrome
    # (header panel, error slot, RUN/BACK row) is built once, here.
    TOOL_TITLE = "Tool"
    TOOL_DESC = ""

    # The default selector ("*") focuses the first focusable widget, which is
    # the ScrollableContainer itself, and keystrokes then drive scrolling instead
    # of reaching the form fields. Restrict to actual form widgets.
    AUTO_FOCUS = "Input, RadioSet"

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
        Binding("ctrl+r", "do_run", "Run"),
    ]

    def compose(self) -> ComposeResult:
        """Standard tool layout. Override `compose_fields`, not this."""
        yield Header()
        with ScrollableContainer(classes="tool-body"):
            yield Static(
                f"[bold #22d3ee]{self.TOOL_TITLE}[/]\n"
                f"[dim #64748b]{self.TOOL_DESC}[/]",
                classes="tool-panel",
            )
            yield from self.compose_fields()
            yield Static("", id="error-msg", classes="error-msg")
            with Horizontal(classes="btn-row"):
                yield Button("▶  RUN", id="run-btn")
                yield Button("← BACK", id="back-btn")
        yield Footer()

    def compose_fields(self) -> ComposeResult:
        """The form fields between the header panel and the buttons."""
        yield from ()

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
            slot = self.query_one("#error-msg", Static)
            slot.update(f"[bold #ef4444]✗  {msg}[/]")
            # The slot sits at the bottom of a scrolling body, so on a long
            # form in a short terminal it lands below the fold and pressing RUN
            # looks like nothing happened. Bring it into view.
            slot.scroll_visible()
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


# ── Provider field mixin ────────────────────────────────────────────────────
class ProviderFieldMixin:
    """The provider picker plus its key field, shared by the five AI screens.

    Each screen declares which capability it needs; the dropdown then only
    offers providers that have it, so the unsupported combination cannot be
    selected in the first place.

    The `refresh_provider_key_field` call each screen makes in `on_mount` is
    redundant today: Textual's `Select._on_mount` assigns `self.value`, which
    posts a `Select.Changed` that lands on `on_select_changed` and does the
    same work. Keep it anyway. That path is an undocumented Textual internal,
    and the explicit call is what stops init from depending on it.

    Note the bubbled `Changed` arrives *after* `on_mount`, so anything a screen
    writes into `#api-key` there gets overwritten. Nothing does that today, but
    it will matter to whoever adds a "remember the last key" feature.
    """

    PROVIDER_CAPABILITY: Optional[Capability] = None  # set by each screen

    def compose_provider_fields(self) -> ComposeResult:
        from automation_tools.ai.base import UnknownProviderError
        from automation_tools.ai.registry import PROVIDERS, providers_with, resolve_name

        capability = self.PROVIDER_CAPABILITY
        if capability is None:
            raise RuntimeError("AI screen did not declare a provider capability")
        names = providers_with(capability)
        # `resolve_name` raises on a name it does not recognise, and a typo in
        # $AI_PROVIDER would otherwise take the whole TUI down the moment this
        # screen is opened. Anything unusable (unknown, or known but lacking
        # this screen's capability) quietly falls back to the first that fits.
        try:
            default = resolve_name()
        except UnknownProviderError:
            default = ""
        current = default if default in names else names[0]

        yield Label("AI provider:", classes="field-label")
        yield Select(
            [(PROVIDERS[n].label, n) for n in names],
            value=current, allow_blank=False, id="provider",
        )
        yield Label("API key (or set the provider's env var):",
                    classes="field-label", id="api-key-label")
        yield Input(placeholder=PROVIDERS[current].key_hint,
                    password=True, id="api-key")

    def refresh_provider_key_field(self: Any, name: str) -> None:
        """Re-labels and re-fills the key field for the selected provider."""
        from automation_tools.ai.registry import PROVIDERS
        from automation_tools.core.config import get_env_var

        spec = PROVIDERS[name]
        self.query_one("#api-key-label", Label).update(
            f"API key (or set {spec.env_key}):"
        )
        field = self.query_one("#api-key", Input)
        field.placeholder = spec.key_hint
        field.value = get_env_var(spec.env_key, "") or ""

    # Deliberately the `on_<message>` naming convention rather than `@on`:
    # `@on` handlers are collected by Textual's MessagePump metaclass, which
    # never runs on a plain mixin, so a decorated handler here would be
    # silently dropped. The convention is resolved by walking the MRO, so it
    # survives the mixin. Hence the manual id check `@on` would have done.
    def on_select_changed(self, e: Select.Changed) -> None:
        if e.select.id == "provider":
            self.refresh_provider_key_field(str(e.value))

    def _provider_values(self: Any) -> "tuple[str, Optional[str]]":
        """Returns (provider_name, api_key_or_None) from the two fields.

        The name is always a real provider: `allow_blank=False` on the Select
        means it can never hold a blank sentinel.
        """
        name = str(self.query_one("#provider", Select).value)
        key = self._ival(self.query_one("#api-key", Input)) or None
        return name, key

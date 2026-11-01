"""Stopping a tool that is already running.

A tool runs on a worker thread, and nothing can kill a thread from outside, so
Cancel has to be something the tool notices. It notices here. This works like
`core.prompt`: tools call these functions, the front end decides what they
mean, and with no front end listening each one simply does its plain job. That
is the whole story on the command line, where Ctrl+C is already a
KeyboardInterrupt.

A tool can be busy in three ways, and each needs a different answer:

- Working through a list: call `check()` between steps, at a point where
  stopping leaves things consistent.
- Waiting on a child process: `run()` kills it.
- Stuck in a call nothing can interrupt, which in practice means a network
  request: `interruptible()` stops waiting and walks away from it.

`sleep()` covers the last case that matters, waiting on purpose.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar

T = TypeVar("T")

# How often a wait looks up to see whether it should stop.
_POLL_SECONDS = 0.1
# What a child process gets to shut down cleanly before it is killed outright.
_GRACE_SECONDS = 3.0

_event: Optional[threading.Event] = None


class Cancelled(BaseException):
    """The user asked the running tool to stop.

    A BaseException, like KeyboardInterrupt and for the same reason. Nearly
    every tool wraps each file in `except Exception` so that one bad file cannot
    end a batch, and a cancellation has to go straight through those instead of
    being reported as one more bad file. `finally` and `with` still run, so
    cleanup still happens.
    """


@contextmanager
def scope(event: threading.Event) -> Iterator[None]:
    """Makes `event` the cancel signal for whatever runs inside the block.

    Open it on the thread running the tool, not on the one that started it. If
    that one goes away first, as it does when the app quits mid-run, the scope
    closes with it and the tool never hears that it should stop.
    """
    global _event
    previous = _event
    _event = event
    try:
        yield
    finally:
        _event = previous


def active() -> bool:
    """Whether a front end is able to cancel what is running."""
    return _event is not None


def requested() -> bool:
    """Whether the user has asked to stop."""
    event = _event
    return event is not None and event.is_set()


def check() -> None:
    """Raises Cancelled if the user has asked to stop."""
    if requested():
        raise Cancelled()


def sleep(seconds: float) -> None:
    """`time.sleep` that a cancel cuts short."""
    event = _event
    if event is None:
        time.sleep(seconds)
    elif event.wait(seconds):
        raise Cancelled()


class _CheckedReader:
    """A readable file whose reads double as cancellation points."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def read(self, size: int = -1) -> Any:
        check()
        return self._handle.read(size)


def checked(handle: Any) -> _CheckedReader:
    """Wraps a file so a library copying from it can be cancelled mid-file."""
    return _CheckedReader(handle)


def interruptible(
    call: Callable[[], T],
    on_abandoned: Optional[Callable[[T], None]] = None,
) -> T:
    """Runs a blocking call, and stops waiting for it on a cancel.

    For work that cannot be stopped from outside, above all a request already
    on the wire. The call moves to a daemon thread so this one stays free to
    watch for a cancel; once cancelled it is left to finish alone, and being a
    daemon it cannot hold the process open. Only suitable for a call with no
    local side effects worth waiting for.

    `on_abandoned` receives the result if one arrives after all, for whatever
    needs tidying up at the far end.
    """
    event = _event
    if event is None:
        return call()
    check()

    outcome: Dict[str, Any] = {}
    finished = threading.Event()
    lock = threading.Lock()
    state = {"done": False, "abandoned": False}

    def target() -> None:
        try:
            outcome["result"] = call()
        except BaseException as exc:  # handed over to the waiting thread
            outcome["error"] = exc
        with lock:
            state["done"] = True
            tidy_up = state["abandoned"]
        finished.set()
        if tidy_up and on_abandoned is not None and "result" in outcome:
            try:
                on_abandoned(outcome["result"])
            except Exception:
                pass  # Best effort, and nobody is left to tell.

    threading.Thread(target=target, daemon=True).start()
    while not finished.wait(_POLL_SECONDS):
        if event.is_set():
            with lock:
                if not state["done"]:
                    state["abandoned"] = True
                    raise Cancelled()

    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def _terminate(process: "subprocess.Popen[Any]") -> None:
    """Ends a process and, where the platform allows, everything it started.

    The children matter: yt-dlp hands the real work to ffmpeg, and `soffice` is
    a launcher for the program that does the converting.
    """
    if process.poll() is not None:
        return

    def signal_all(number: int, fallback: Callable[[], None]) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, number)
            else:
                fallback()
        except OSError:
            pass  # It got there first.

    signal_all(signal.SIGTERM, process.terminate)
    try:
        process.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        signal_all(getattr(signal, "SIGKILL", signal.SIGTERM), process.kill)
        process.wait()


def run(
    command: Any,
    *,
    check: bool = False,
    timeout: Optional[float] = None,
    on_line: Optional[Callable[[str], None]] = None,
    **kwargs: Any,
) -> "subprocess.CompletedProcess[Any]":
    """`subprocess.run` whose process dies with the run.

    `on_line` receives each line of output, and only when something can cancel
    this: in the TUI a child must not inherit the terminal, or it writes all
    over the screen. On the command line it keeps the terminal, which is what
    lets a program like yt-dlp draw its own progress bar.
    """
    event = _event
    if event is None:
        return subprocess.run(command, check=check, timeout=timeout, **kwargs)

    if event.is_set():
        raise Cancelled()

    # A process that shares the terminal could also steal the app's keystrokes.
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    if on_line is not None:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                      encoding="utf-8", errors="replace")
    if os.name == "posix":
        # Its own process group, so `_terminate` can reach its children.
        kwargs["start_new_session"] = True

    deadline = None if timeout is None else time.monotonic() + timeout
    stdout: Any = None
    stderr: Any = None

    with subprocess.Popen(command, **kwargs) as process:
        pump: Optional[threading.Thread] = None
        if on_line is not None:
            pump = threading.Thread(target=_pump_lines, args=(process, on_line), daemon=True)
            pump.start()
        try:
            while True:
                try:
                    if pump is None:
                        stdout, stderr = process.communicate(timeout=_POLL_SECONDS)
                    else:
                        process.wait(timeout=_POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    if event.is_set():
                        raise Cancelled() from None
                    if deadline is not None and time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(command, timeout or 0) from None
        except BaseException:
            _terminate(process)
            raise
        finally:
            if pump is not None:
                pump.join(timeout=_GRACE_SECONDS)

    code = process.returncode
    if check and code:
        raise subprocess.CalledProcessError(code, command, stdout, stderr)
    return subprocess.CompletedProcess(command, code, stdout, stderr)


def _pump_lines(process: "subprocess.Popen[Any]", on_line: Callable[[str], None]) -> None:
    try:
        assert process.stdout is not None
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            if line.strip():
                on_line(line)
    except (OSError, ValueError):
        pass  # The pipe went away with the process.


__all__ = [
    "Cancelled",
    "active",
    "check",
    "checked",
    "interruptible",
    "requested",
    "run",
    "scope",
    "sleep",
]

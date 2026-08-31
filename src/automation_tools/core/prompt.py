from contextlib import contextmanager
from typing import Callable, Optional

import questionary

# Where a yes/no question goes depends on what is running the tool.
#
# On the command line it is a questionary prompt. Inside the TUI a terminal
# prompt would fight Textual for the screen, so the app answers with a modal
# instead. It used to arrange that by overwriting `questionary.confirm` itself,
# which changed a third-party module for the whole process and stayed changed
# if anything escaped the restore. The tools ask here now, and only this file
# knows there is a choice.

ConfirmFn = Callable[[str, bool], bool]

_backend: Optional[ConfirmFn] = None


def confirm(message: str, default: bool = False) -> bool:
    """Asks a yes/no question through whichever front end is running.

    `default` is what the user gets by pressing Enter, and it is also the
    button the TUI modal opens with, so anything destructive passes False.
    """
    if _backend is not None:
        return bool(_backend(message, default))
    return bool(questionary.confirm(message, default=default).ask())


@contextmanager
def confirm_backend(handler: ConfirmFn):
    """Routes confirmations through `handler` while the block runs."""
    global _backend
    previous = _backend
    _backend = handler
    try:
        yield
    finally:
        _backend = previous

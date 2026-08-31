import csv
import json
import os
from typing import Any, Dict, Iterable, Sequence

from automation_tools.core.logger import print_error, print_success

# Writing a CSV report was copied into four tools, each with its own idea of
# which errors to catch and what to say afterwards. One of them caught bare
# Exception, the others OSError; the messages had drifted apart. This is the
# one that gets fixed when the next thing goes wrong with it.


def export_rows(out_path: str, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> bool:
    """Writes a report as CSV. Returns whether it actually got there.

    `newline=""` is not decoration: without it the csv module's own line ending
    is written on top of the platform's and every other row comes out blank on
    Windows.
    """
    try:
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(list(header))
            for row in rows:
                writer.writerow(list(row))
    except OSError as e:
        print_error(f"Could not export report: {e}")
        return False
    print_success(f"Report exported to: {out_path}")
    return True


def export_json(out_path: str, payload: Dict[str, Any]) -> bool:
    """Writes a report as JSON, for the tools that offer both."""
    try:
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
    except (OSError, TypeError) as e:
        print_error(f"Could not export report: {e}")
        return False
    print_success(f"Report exported to: {out_path}")
    return True


def is_csv(out_path: str) -> bool:
    """Whether a destination asks for CSV rather than JSON, by extension."""
    return os.path.splitext(out_path)[1].lower() == ".csv"

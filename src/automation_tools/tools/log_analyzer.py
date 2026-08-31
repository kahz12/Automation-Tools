import os
import argparse
import re
from typing import Optional

from automation_tools.core import fs
from automation_tools.core.logger import console, print_error, print_step, print_warning

# Matches beyond this are still written to the report file, just not echoed to
# the console; a million-hit scan should not scroll for an hour.
MAX_CONSOLE_MATCHES = 100


def run_log_analyzer(
    path: str,
    keywords: str,
    use_regex: bool = False,
    ignore_case: bool = True,
    out_path: Optional[str] = None
) -> bool:
    """Scans a log file, or a directory of them, for keywords or regex patterns.

    True when the scan ran to completion; finding zero matches still counts as
    success. False when it could not run at all: a bad path, no patterns, an
    invalid regex, nothing to scan, or an unwritable report destination.
    """
    if not os.path.exists(path):
        print_error(f"Path '{path}' does not exist.")
        return False

    if not keywords:
        print_error("You must provide at least one keyword or regex pattern to search for.")
        return False

    # Parse keywords
    if use_regex:
        patterns = [keywords]
    else:
        patterns = [kw.strip() for kw in keywords.split(",") if kw.strip()]

    # Compile regexes for speed
    flags = re.IGNORECASE if ignore_case else 0
    compiled_regexes = []
    for pat in patterns:
        try:
            if use_regex:
                compiled_regexes.append(re.compile(pat, flags))
            else:
                compiled_regexes.append(re.compile(re.escape(pat), flags))
        except re.error as e:
            print_error(f"Invalid regex '{pat}': {e}")
            return False

    # Gather files
    if os.path.isfile(path):
        files_to_scan = [path]
    else:
        print_step(f"Scanning directory '{path}' for .log files...")
        files_to_scan = list(fs.walk_files(path, extensions=(".log",)))
    
    if not files_to_scan:
        print_warning("No .log files found to analyze.")
        return False

    print_step(f"Analyzing {len(files_to_scan)} file(s) for {len(patterns)} pattern(s)...")

    # Open the report up front so a bad path fails before a long scan, and so
    # matches can be streamed straight to disk instead of piling up in memory.
    report = None
    if out_path:
        try:
            report = open(out_path, "w", encoding="utf-8")
        except OSError as e:
            print_error(f"Error saving report to {out_path}: {e}")
            return False

    console.print(f"\n[cyan]{'='*50}[/cyan]")
    console.print("[bold]LOG ANALYSIS REPORT[/bold]")
    console.print(f"[cyan]{'='*50}[/cyan]\n")

    total_matches = 0
    try:
        if report:
            report.write("LOG ANALYSIS REPORT\n\n")

        for file_path in files_to_scan:
            file_matches = 0
            shown = 0
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        # One hit per line, no matter how many patterns match it.
                        if not any(regex.search(line) for regex in compiled_regexes):
                            continue

                        if file_matches == 0:
                            console.print(f"[bold #a78bfa]📄 {file_path}[/]")
                            if report:
                                report.write(f"--- {file_path} ---\n")
                        file_matches += 1
                        total_matches += 1

                        if shown < MAX_CONSOLE_MATCHES:
                            console.print(f"  [dim]Line {line_num}:[/] {line[:200]}")
                            shown += 1
                        elif shown == MAX_CONSOLE_MATCHES:
                            console.print("  [dim]... more matches hidden here; see the full report.[/]")
                            shown += 1

                        if report:
                            report.write(f"Line {line_num}: {line}\n")
            except OSError as e:
                print_warning(f"Could not read {file_path}: {e}")
                continue

            if file_matches:
                console.print(f"  [dim]({file_matches} match(es) in this file)[/]\n")
                if report:
                    report.write(f"({file_matches} matches)\n\n")

        # The total is only known once every file has been streamed through.
        if total_matches == 0:
            console.print("[green]✓ No matches found for the given keywords.[/green]")
        console.print(f"[cyan]{'='*50}[/cyan]")
        console.print(f"[dim]Total matches found: {total_matches}[/dim]")
        if report:
            report.write(f"Total matches found: {total_matches}\n")
    finally:
        if report:
            report.close()

    if out_path:
        console.print(f"[dim]Full report saved to: {out_path}[/dim]")

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Log Analyzer - Scan logs for errors or patterns")
    parser.add_argument("path", help="Path to a .log file or directory containing .log files")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords, or a regex pattern")
    parser.add_argument("--regex", action="store_true", help="Treat keywords as a single regex pattern")
    parser.add_argument("--case-sensitive", action="store_true", help="Make search case sensitive")
    parser.add_argument("--out", help="Save the full report to this file")
    
    args = parser.parse_args()
    
    ok = run_log_analyzer(
        path=args.path,
        keywords=args.keywords,
        use_regex=args.regex,
        ignore_case=not args.case_sensitive,
        out_path=args.out
    )
    raise SystemExit(0 if ok else 1)

if __name__ == "__main__":
    main()

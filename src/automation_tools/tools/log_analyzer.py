import os
import argparse
import re
from typing import List, Optional

from automation_tools.core.logger import console, print_error, print_step, print_warning


def run_log_analyzer(
    path: str,
    keywords: str,
    use_regex: bool = False,
    ignore_case: bool = True,
    out_path: Optional[str] = None
) -> None:
    """
    Scans a log file or a directory of log files for specific keywords or regex patterns.
    Outputs a summary of matches found.
    """
    if not os.path.exists(path):
        print_error(f"Path '{path}' does not exist.")
        return

    if not keywords:
        print_error("You must provide at least one keyword or regex pattern to search for.")
        return

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
            return

    # Gather files
    files_to_scan = []
    if os.path.isfile(path):
        files_to_scan.append(path)
    else:
        print_step(f"Scanning directory '{path}' for .log files...")
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith(".log"):
                    files_to_scan.append(os.path.join(root, file))
    
    if not files_to_scan:
        print_warning("No .log files found to analyze.")
        return

    print_step(f"Analyzing {len(files_to_scan)} file(s) for {len(patterns)} pattern(s)...")

    results = []
    total_matches = 0

    for file_path in files_to_scan:
        file_matches = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    for regex in compiled_regexes:
                        if regex.search(line):
                            file_matches.append((line_num, line))
                            total_matches += 1
                            break  # Avoid double counting if multiple regexes match
        except Exception as e:
            print_warning(f"Could not read {file_path}: {e}")
            continue

        if file_matches:
            results.append((file_path, file_matches))

    # Display results
    console.print(f"\n[cyan]{'='*50}[/cyan]")
    console.print(f"[bold]LOG ANALYSIS REPORT[/bold]")
    console.print(f"[cyan]{'='*50}[/cyan]")
    console.print(f"[dim]Total matches found: {total_matches}[/dim]\n")

    report_lines = []
    report_lines.append("LOG ANALYSIS REPORT")
    report_lines.append(f"Total matches found: {total_matches}\n")

    for file_path, matches in results:
        file_header = f"📄 {file_path} ({len(matches)} matches)"
        console.print(f"[bold #a78bfa]{file_header}[/]")
        report_lines.append(f"--- {file_path} ({len(matches)} matches) ---")
        
        # Only show up to 100 matches per file in the console to avoid spam
        for i, (line_num, line) in enumerate(matches):
            if i < 100:
                console.print(f"  [dim]Line {line_num}:[/] {line[:200]}")
            elif i == 100:
                console.print(f"  [dim]... and {len(matches) - 100} more matches (hidden in UI).[/]")
            report_lines.append(f"Line {line_num}: {line}")
        console.print()
        report_lines.append("")

    if total_matches == 0:
        console.print("[green]✓ No matches found for the given keywords.[/green]")
        report_lines.append("No matches found.")

    # Save to file
    if out_path:
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(report_lines))
            console.print(f"[dim]Full report saved to: {out_path}[/dim]")
        except Exception as e:
            print_error(f"Error saving report to {out_path}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Log Analyzer - Scan logs for errors or patterns")
    parser.add_argument("path", help="Path to a .log file or directory containing .log files")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords, or a regex pattern")
    parser.add_argument("--regex", action="store_true", help="Treat keywords as a single regex pattern")
    parser.add_argument("--case-sensitive", action="store_true", help="Make search case sensitive")
    parser.add_argument("--out", help="Save the full report to this file")
    
    args = parser.parse_args()
    
    run_log_analyzer(
        path=args.path,
        keywords=args.keywords,
        use_regex=args.regex,
        ignore_case=not args.case_sensitive,
        out_path=args.out
    )

if __name__ == "__main__":
    main()

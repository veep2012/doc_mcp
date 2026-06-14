#!/usr/bin/env python3
"""Fail when any documentation file has more than one Change Log entry per date."""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGE_LOG_HEADING = re.compile(r"^##\s+Change Log\s*$")
NEXT_HEADING = re.compile(r"^##\s+")
ENTRY_DATE = re.compile(r"^\s*[-*]\s*(\d{4}-\d{2}-\d{2})\s*\|")


def iter_markdown_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md") if path.is_file())


def scan_file(path: Path) -> list[tuple[str, int, int]]:
    duplicates: list[tuple[str, int, int]] = []
    in_change_log = False
    seen: dict[str, int] = {}

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if CHANGE_LOG_HEADING.match(line):
            in_change_log = True
            continue
        if in_change_log and NEXT_HEADING.match(line):
            break
        if not in_change_log:
            continue

        match = ENTRY_DATE.match(line)
        if not match:
            continue

        date = match.group(1)
        if date in seen:
            duplicates.append((date, seen[date], line_no))
            continue
        seen[date] = line_no

    return duplicates


def main() -> int:
    root = Path("documentation")
    failures: list[str] = []

    for path in iter_markdown_files(root):
        for date, first_line, duplicate_line in scan_file(path):
            failures.append(
                f"{path}: duplicate Change Log date {date} "
                f"(first entry line {first_line}, duplicate line {duplicate_line})"
            )

    if failures:
        print("Documentation Change Log date duplication detected:", file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

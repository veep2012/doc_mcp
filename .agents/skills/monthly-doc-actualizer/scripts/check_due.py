#!/usr/bin/env python3
"""Check whether monthly documentation actualization is due and update state file."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

LINE_RE = {
    "last_check": re.compile(r"^-\s+Last Check:\s+(\d{4}-\d{2}-\d{2})\s*$"),
    "last_full": re.compile(r"^-\s+Last Full Actualization:\s+(\d{4}-\d{2}-\d{2})\s*$"),
    "cadence_days": re.compile(r"^-\s+Cadence Days:\s+(\d+)\s*$"),
}


@dataclass
class State:
    last_check: date
    last_full: date
    cadence_days: int


def _parse_iso_day(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _read_state(path: Path) -> State:
    lines = path.read_text(encoding="utf-8").splitlines()

    values: dict[str, str] = {}
    for line in lines:
        for key, pattern in LINE_RE.items():
            match = pattern.match(line)
            if match:
                values[key] = match.group(1)

    missing = {"last_check", "last_full", "cadence_days"} - set(values)
    if missing:
        needed = ", ".join(sorted(missing))
        raise ValueError(f"State file missing required fields: {needed}")

    cadence_days = int(values["cadence_days"])
    if cadence_days <= 0:
        raise ValueError("State file invalid: Cadence Days must be > 0")

    return State(
        last_check=_parse_iso_day(values["last_check"]),
        last_full=_parse_iso_day(values["last_full"]),
        cadence_days=cadence_days,
    )


def _write_state(path: Path, state: State) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()

    def replace_or_append(pattern: re.Pattern[str], replacement: str) -> None:
        for idx, line in enumerate(lines):
            if pattern.match(line):
                lines[idx] = replacement
                return
        lines.append(replacement)

    replace_or_append(LINE_RE["last_check"], f"- Last Check: {state.last_check.isoformat()}")
    replace_or_append(
        LINE_RE["last_full"], f"- Last Full Actualization: {state.last_full.isoformat()}"
    )
    replace_or_append(LINE_RE["cadence_days"], f"- Cadence Days: {state.cadence_days}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", required=True, help="Path to markdown state file.")
    parser.add_argument("--days", type=int, default=None, help="Override cadence days.")
    parser.add_argument("--mark-check", action="store_true", help="Update Last Check to today.")
    parser.add_argument(
        "--mark-full",
        action="store_true",
        help="Update Last Check and Last Full Actualization to today.",
    )
    args = parser.parse_args()

    path = Path(args.state_file)
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")

    state = _read_state(path)
    today = date.today()

    if args.days is not None:
        if args.days <= 0:
            raise ValueError("--days must be > 0")
        state.cadence_days = args.days

    if args.mark_full:
        state.last_full = today
        state.last_check = today
    elif args.mark_check:
        state.last_check = today

    days_since_full = (today - state.last_full).days
    due = days_since_full >= state.cadence_days
    next_due = state.last_full + timedelta(days=state.cadence_days)

    if args.mark_check or args.mark_full or args.days is not None:
        _write_state(path, state)

    print(f"DUE={'true' if due else 'false'}")
    print(f"LAST_CHECK={state.last_check.isoformat()}")
    print(f"LAST_FULL_ACTUALIZATION={state.last_full.isoformat()}")
    print(f"CADENCE_DAYS={state.cadence_days}")
    print(f"DAYS_SINCE_FULL={days_since_full}")
    print(f"NEXT_DUE_DATE={next_due.isoformat()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

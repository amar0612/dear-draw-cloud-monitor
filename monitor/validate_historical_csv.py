#!/usr/bin/env python3
"""Preflight validation for source-backed, human-verified historical draw CSVs."""
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

EXPECTED = {"1st": 1, "Consolation": 1, "2nd": 10, "3rd": 10, "4th": 10, "5th": 100}
PATTERNS = {
    "1st": re.compile(r"^[0-9]{2}[A-Z] [0-9]{5}$"),
    "Consolation": re.compile(r"^[0-9]{5}$"),
    "2nd": re.compile(r"^[0-9]{5}$"),
    "3rd": re.compile(r"^[0-9]{4}$"),
    "4th": re.compile(r"^[0-9]{4}$"),
    "5th": re.compile(r"^[0-9]{4}$"),
}
REQUIRED = {"date", "draw", "prize_tier", "position", "winning_number",
            "verification_status", "source_file"}


def validate_rows(rows):
    errors = []
    grouped = defaultdict(list)
    for line, row in enumerate(rows, start=2):
        date_text = (row.get("date") or "").strip()
        draw = (row.get("draw") or "").strip().upper()
        if draw not in {"1PM", "8PM"}:
            continue  # Sikkim 6PM and other draws are outside this archive.
        key = (date_text, draw)
        grouped[key].append((line, row))

    if not grouped:
        return ["No Nagaland 1PM/8PM rows found"]

    for (date_text, draw), items in grouped.items():
        label = f"{date_text} {draw}"
        try:
            date.fromisoformat(date_text)
            if len(date_text) != 10:
                raise ValueError
        except ValueError:
            errors.append(f"{label}: invalid ISO date")
        if len(items) != 132:
            errors.append(f"{label}: expected 132 rows, found {len(items)}")

        by_tier = defaultdict(dict)
        for line, row in items:
            tier = (row.get("prize_tier") or "").strip()
            if tier not in EXPECTED:
                errors.append(f"{label}: line {line} has unknown prize tier {tier!r}")
                continue
            if (row.get("verification_status") or "").strip().lower() != "human_verified":
                errors.append(f"{label}: line {line} is not human_verified")
            if not (row.get("source_file") or "").strip():
                errors.append(f"{label}: line {line} has no source_file")
            try:
                position = int((row.get("position") or "").strip())
            except ValueError:
                errors.append(f"{label}: line {line} has invalid position")
                continue
            if position < 1 or position > EXPECTED[tier]:
                errors.append(f"{label}: line {line} has out-of-range {tier} position")
                continue
            if position in by_tier[tier]:
                errors.append(f"{label}: duplicate {tier} position {position}")
                continue
            number = (row.get("winning_number") or "").strip()
            if not PATTERNS[tier].fullmatch(number):
                errors.append(f"{label}: line {line} has invalid {tier} number {number!r}")
            by_tier[tier][position] = number

        for tier, expected_count in EXPECTED.items():
            positions = set(by_tier[tier])
            if positions != set(range(1, expected_count + 1)):
                errors.append(f"{label}: {tier} must contain positions 1..{expected_count}")

        first = by_tier["1st"].get(1, "")
        consolation = by_tier["Consolation"].get(1, "")
        if first and consolation and first[-5:] != consolation:
            errors.append(f"{label}: consolation does not match first-prize suffix")

    return errors


def validate_file(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED - headers
        if missing:
            return [f"Missing required columns: {', '.join(sorted(missing))}"]
        return validate_rows(list(reader))


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/human_verified_draws_2023-01.csv")
    problems = validate_file(target)
    if problems:
        print("\n".join(problems))
        raise SystemExit(1)
    print(f"PASS: {target} contains complete, source-backed human-verified Nagaland draws.")

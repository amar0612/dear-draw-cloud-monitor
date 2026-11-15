
#!/usr/bin/env python3
"""Structural validation for Nagaland 1PM and 8PM lottery results."""

import re
from datetime import date

EXPECTED_COUNTS = {
    "1st": 1,
    "Consolation": 1,
    "2nd": 10,
    "3rd": 10,
    "4th": 10,
    "5th": 100,
}

PATTERNS = {
    "1st": re.compile(r"^[0-9]{2}[A-Z] [0-9]{5}$"),
    "Consolation": re.compile(r"^[0-9]{5}$"),
    "2nd": re.compile(r"^[0-9]{5}$"),
    "3rd": re.compile(r"^[0-9]{4}$"),
    "4th": re.compile(r"^[0-9]{4}$"),
    "5th": re.compile(r"^[0-9]{4}$"),
}


def validate_result(record):
    errors = []

    try:
        date.fromisoformat(str(record.get("date", "")))
    except ValueError:
        errors.append("Invalid date: use YYYY-MM-DD")

    if record.get("draw") not in {"1PM", "8PM"}:
        errors.append("Only Nagaland 1PM and 8PM draws are accepted")

    prizes = record.get("prizes")

    if not isinstance(prizes, dict):
        return errors + ["Missing or invalid prizes object"]

    for tier in EXPECTED_COUNTS:
        if tier not in prizes:
            errors.append(f"Missing prize group: {tier}")
            continue

        values = prizes[tier]

        if not isinstance(values, list):
            errors.append(f"{tier} must be a list")
            continue

        expected = EXPECTED_COUNTS[tier]

        if len(values) != expected:
            errors.append(
                f"{tier}: expected {expected}, got {len(values)}"
            )

        pattern = PATTERNS[tier]

        for index, value in enumerate(values, start=1):
            if not isinstance(value, str) or not pattern.fullmatch(value):
                errors.append(
                    f"{tier} entry {index} has invalid format: {value!r}"
                )

    first = prizes.get("1st", [])
    consolation = prizes.get("Consolation", [])

    if (
        isinstance(first, list)
        and len(first) == 1
        and isinstance(first[0], str)
        and PATTERNS["1st"].fullmatch(first[0])
        and isinstance(consolation, list)
        and len(consolation) == 1
        and isinstance(consolation[0], str)
        and PATTERNS["Consolation"].fullmatch(consolation[0])
    ):
        if first[0][-5:] != consolation[0]:
            errors.append(
                "Consolation does not match the last five digits of 1st prize"
            )

    return errors

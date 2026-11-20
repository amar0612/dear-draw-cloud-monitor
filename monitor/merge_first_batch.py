#!/usr/bin/env python3
"""Merge the first recovered 2026 Nagaland batch into the master CSV.

This deliberately replaces the existing rows for the same date/draw keys
instead of appending duplicates. The source provenance and pending official
lower-tier review status are retained.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "data" / "nagaland_master_prize_numbers.csv"
STAGING = ROOT / "data" / "nagaland_2026_first_batch_extracted.csv"
PROVENANCE = ROOT / "data" / "nagaland_2026_first_batch_provenance.csv"

MASTER_FIELDS = [
    "date", "draw", "prize_tier", "position",
    "winning_number", "source_pdf", "verification_status",
]
PROVENANCE_FIELDS = [
    "date", "draw", "source_pdf", "source_sha256",
    "extraction_status", "verification_note",
]
STATUS = (
    "MERGED - MIRROR PDF FULL-TIER AGREEMENT; "
    "OFFICIAL LOWER-TIER REVIEW PENDING"
)


def padded(value: str, width: int) -> str:
    value = str(value).strip()
    if not value.isdigit():
        raise ValueError(f"Non-numeric prize number: {value!r}")
    return value.zfill(width)


def main() -> None:
    with STAGING.open("r", encoding="utf-8-sig", newline="") as f:
        draws = list(csv.DictReader(f))
    if not draws:
        raise SystemExit("No extracted draws found")

    keys: set[tuple[str, str]] = set()
    replacement_rows: list[dict[str, str]] = []
    provenance_rows: list[dict[str, str]] = []

    for draw in draws:
        date, slot = draw["date"], draw["draw"]
        if slot not in {"1PM", "8PM"}:
            raise SystemExit(f"Out-of-scope draw slot: {date} {slot}")
        key = (date, slot)
        if key in keys:
            raise SystemExit(f"Duplicate staged draw: {date} {slot}")
        keys.add(key)

        source_pdf = draw["source_file"]
        source_hash = draw["source_sha256"]
        rows = [
            ("1st", 1, f'{draw["first_prize_series"].strip()} '
                       f'{padded(draw["first_prize_number"], 5)}'),
            ("Consolation", 1, padded(draw["consolation_number"], 5)),
        ]
        for tier, field, width, expected in (
            ("2nd", "second_prize", 5, 10),
            ("3rd", "third_prize", 4, 10),
            ("4th", "fourth_prize", 4, 10),
            ("5th", "fifth_prize", 4, 100),
        ):
            numbers = draw[field].split()
            if len(numbers) != expected:
                raise SystemExit(
                    f"{date} {slot} {tier}: expected {expected}, got {len(numbers)}"
                )
            rows.extend(
                (tier, position, padded(number, width))
                for position, number in enumerate(numbers, start=1)
            )
        if len(rows) != 132:
            raise SystemExit(f"{date} {slot}: expected 132 rows, got {len(rows)}")

        draw_status = (
            "MERGED - TWO PUBLISHED MIRRORS AGREE ON FULL TIERS; "
            "OFFICIAL GAZETTE CROSS-CHECK PENDING"
            if draw["extraction_status"] == "two_mirror_full_tier_match"
            else STATUS
        )
        replacement_rows.extend({
            "date": date,
            "draw": slot,
            "prize_tier": tier,
            "position": str(position),
            "winning_number": number,
            "source_pdf": source_pdf,
            "verification_status": draw_status,
        } for tier, position, number in rows)

        provenance_rows.append({
            "date": date,
            "draw": slot,
            "source_pdf": source_pdf,
            "source_sha256": source_hash,
            "extraction_status": draw["extraction_status"],
            "verification_note": (
                "Two published result pages agree on all prize tiers; "
                "official Gazette cross-check pending"
                if draw["extraction_status"] == "two_mirror_full_tier_match"
                else "Full-tier mirror PDF comparison passed; "
                     "official lower-tier review remains pending"
            ),
        })

    if len(replacement_rows) != len(keys) * 132:
        raise SystemExit("Batch shape check failed")

    with MASTER.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != MASTER_FIELDS:
            raise SystemExit(f"Unexpected master schema: {reader.fieldnames}")
        existing = list(reader)

    kept = [
        row for row in existing
        if (row["date"], row["draw"]) not in keys
    ]
    removed = len(existing) - len(kept)
    if removed % 132 != 0:
        raise SystemExit(
            f"Existing rows removed were not a whole number of 132-row draws: {removed}"
        )

    merged = kept + replacement_rows
    with MASTER.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        writer.writerows(merged)

    with PROVENANCE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROVENANCE_FIELDS)
        writer.writeheader()
        writer.writerows(provenance_rows)

    print(f"MERGED_PAIRS={len(keys)}")
    print(f"REPLACED_OLD_ROWS={removed}")
    print(f"WRITTEN_ROWS={len(replacement_rows)}")
    print(f"MASTER_TOTAL_ROWS={len(merged)}")
    print("SCOPE=Nagaland 1PM and 8PM only; 6PM excluded")
    print("NOTE=Official lower-tier review pending; no human-verification claim")
    if ("2026-07-01", "1PM") not in keys:
        print("STILL_MISSING=2026-07-01 1PM")


if __name__ == "__main__":
    main()

# Trigger merge workflow after workflow file registration.

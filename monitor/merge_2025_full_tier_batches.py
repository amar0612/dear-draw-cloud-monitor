#!/usr/bin/env python3
"""Merge recovered 2025 full-tier batches into the Nagaland master CSV.

Only Nagaland 1PM and 8PM draws are imported. Each draw must contain exactly
132 entries across the six prize groups. Existing rows for recovered draw keys
are replaced; missing keys are added.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MASTER = DATA / "nagaland_master_prize_numbers.csv"
BATCHES = sorted(DATA.glob("recovered_2025_full_tier_batch_*.csv"))
EXTRA = DATA / "recovered_draws_2025-12-03-8pm-full.csv"
MASTER_FIELDS = [
    "date", "draw", "prize_tier", "position",
    "winning_number", "source_pdf", "verification_status",
]
EXPECTED = {"1st": 1, "Consolation": 1, "2nd": 10, "3rd": 10, "4th": 10, "5th": 100}
TIER_ORDER = {"1st": 0, "Consolation": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5}


def read_batch(path: Path, grouped: dict) -> tuple[int, int]:
    skipped_6pm = 0
    rows_read = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"date", "draw", "prize_tier", "position", "winning_number"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise SystemExit(f"{path.name}: unexpected columns {reader.fieldnames}")
        for raw in reader:
            rows_read += 1
            slot = raw["draw"].strip().upper()
            if slot == "6PM":
                skipped_6pm += 1
                continue
            if slot not in {"1PM", "8PM"}:
                raise SystemExit(f"{path.name}: unexpected draw slot {slot!r}")
            row = {
                "date": raw["date"].strip(),
                "draw": slot,
                "prize_tier": raw["prize_tier"].strip(),
                "position": raw["position"].strip(),
                "winning_number": raw["winning_number"].strip(),
                "source_pdf": (raw.get("source_reference") or raw.get("source_pdf") or path.name).strip(),
                "verification_status": (raw.get("verification_status") or "recovered_2025_batch").strip(),
                "_batch": path.name,
            }
            grouped[(row["date"], slot)].append(row)
    return rows_read, skipped_6pm


def normalize(rows: list[dict], key: tuple[str, str]) -> tuple[list[dict] | None, str]:
    counts = Counter(r["prize_tier"] for r in rows)
    if counts != Counter(EXPECTED):
        return None, f"tier counts {dict(counts)}"
    seen = set()
    for r in rows:
        pos_key = (r["prize_tier"], r["position"])
        if pos_key in seen:
            return None, f"duplicate position {pos_key}"
        seen.add(pos_key)
        if not r["winning_number"]:
            return None, "empty winning number"
    ordered = sorted(
        rows,
        key=lambda r: (TIER_ORDER.get(r["prize_tier"], 99), int(r["position"]))
    )
    if len(ordered) != 132:
        return None, f"row count {len(ordered)}"
    return ordered, ""


def main() -> None:
    files = list(BATCHES)
    if EXTRA.exists():
        files.append(EXTRA)
    if not files:
        raise SystemExit("No recovered 2025 full-tier batch files found")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    total_source_rows = 0
    skipped_6pm = 0
    for path in files:
        n, n6 = read_batch(path, grouped)
        total_source_rows += n
        skipped_6pm += n6

    chosen: dict[tuple[str, str], list[dict]] = {}
    incomplete = []
    conflicts = []
    for key, candidates in sorted(grouped.items()):
        # If batches overlap, compare their actual prize rows. Prefer a complete
        # two-source-matched candidate; otherwise retain the first full group.
        normalized = []
        for candidate in candidates:
            clean, reason = normalize(candidate, key)
            if clean is not None:
                normalized.append(clean)
        if not normalized:
            incomplete.append((key, len(candidates), "no complete 132-row candidate"))
            continue
        signatures = {
            tuple((r["prize_tier"], r["position"], r["winning_number"]) for r in group)
            for group in normalized
        }
        if len(signatures) > 1:
            conflicts.append(key)
        def quality(group):
            matched = sum("two_source_matched" in r["verification_status"].lower() for r in group)
            return (matched, group[0]["_batch"])
        chosen[key] = max(normalized, key=quality)

    if not chosen:
        raise SystemExit("No complete 2025 Nagaland 1PM/8PM draws to merge")

    with MASTER.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != MASTER_FIELDS:
            raise SystemExit(f"Unexpected master schema: {reader.fieldnames}")
        existing = list(reader)

    existing_2025 = [
        r for r in existing
        if r["date"].startswith("2025-") and r["draw"] in {"1PM", "8PM"}
    ]
    old_keys = {(r["date"], r["draw"]) for r in existing_2025}
    new_keys = set(chosen)
    kept = [r for r in existing if (r["date"], r["draw"]) not in new_keys]

    merged = []
    for key in sorted(chosen):
        for r in chosen[key]:
            merged.append({field: r[field] for field in MASTER_FIELDS})

    # Preserve the existing master order; append recovered keys chronologically.
    output = kept + merged
    with MASTER.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_FIELDS)
        writer.writeheader()
        writer.writerows(output)

    replaced = len(existing_2025) - sum(1 for r in existing_2025 if (r["date"], r["draw"]) not in new_keys)
    print(f"2025_BATCH_FILES={len(files)}")
    print(f"2025_SOURCE_ROWS_READ={total_source_rows}")
    print(f"2025_6PM_ROWS_EXCLUDED={skipped_6pm}")
    print(f"2025_COMPLETE_DRAW_PAIRS_MERGED={len(chosen)}")
    print(f"2025_MASTER_ROWS_REPLACED={replaced}")
    print(f"2025_NEW_DRAW_PAIRS_ADDED={len(new_keys - old_keys)}")
    print(f"2025_ROWS_WRITTEN={len(merged)}")
    print(f"2025_INCOMPLETE_GROUPS_SKIPPED={len(incomplete)}")
    print(f"2025_CONFLICTING_DUPLICATE_GROUPS={len(conflicts)}")
    print(f"MASTER_TOTAL_ROWS={len(output)}")
    if incomplete:
        for key, n, reason in incomplete[:30]:
            print(f"SKIPPED {key[0]} {key[1]} rows={n}: {reason}")
    if conflicts:
        for key in conflicts[:30]:
            print(f"CONFLICT_RESOLVED {key[0]} {key[1]}")


if __name__ == "__main__":
    main()

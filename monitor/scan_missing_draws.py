#!/usr/bin/env python3
"""Find incomplete Nagaland 1PM/8PM draws in the master CSV and rotate recovery batches."""
from __future__ import annotations
import argparse, csv, json, os, re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EXPECTED = {"1st": 1, "Consolation": 1, "2nd": 10, "3rd": 10, "4th": 10, "5th": 100}
TIERS = set(EXPECTED)
PATTERNS = {
    "1st": re.compile(r"^[0-9]{2}[A-Z] [0-9]{5}$"),
    "Consolation": re.compile(r"^[0-9]{5}$"),
    "2nd": re.compile(r"^[0-9]{5}$"),
    "3rd": re.compile(r"^[0-9]{4}$"),
    "4th": re.compile(r"^[0-9]{4}$"),
    "5th": re.compile(r"^[0-9]{4}$"),
}

def complete(rows):
    if len(rows) != 132:
        return False
    counts = Counter()
    positions = defaultdict(set)
    for row in rows:
        tier = (row.get("prize_tier") or "").strip()
        try:
            pos = int((row.get("position") or "").strip())
        except ValueError:
            return False
        if tier not in TIERS or pos in positions[tier] or not (1 <= pos <= EXPECTED[tier]):
            return False
        number = (row.get("winning_number") or "").strip()
        if not PATTERNS[tier].fullmatch(number):
            return False
        counts[tier] += 1
        positions[tier].add(pos)
    if counts != Counter(EXPECTED) or not all(
        positions[t] == set(range(1, EXPECTED[t] + 1)) for t in EXPECTED
    ):
        return False
    first = next((r.get("winning_number", "").strip() for r in rows if r.get("prize_tier") == "1st"), "")
    consolation = next((r.get("winning_number", "").strip() for r in rows if r.get("prize_tier") == "Consolation"), "")
    return bool(first and consolation and first[-5:] == consolation)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--master", default="data/nagaland_master_prize_numbers.csv")
    p.add_argument("--start-date", default="2021-01-01")
    p.add_argument("--end-date", default=None)
    p.add_argument("--batch-size", type=int, default=25)
    p.add_argument("--cursor", type=int, default=1)
    p.add_argument("--output-dir", default="scanner-output")
    a = p.parse_args()
    start = date.fromisoformat(a.start_date)
    end = date.fromisoformat(a.end_date) if a.end_date else datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if end < start or a.batch_size < 1:
        raise SystemExit("Invalid date range or batch size")
    groups = defaultdict(list)
    with open(a.master, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"date", "draw", "prize_tier", "position", "winning_number"}
        if not required.issubset(reader.fieldnames or []):
            raise SystemExit(f"Master CSV missing columns: {sorted(required - set(reader.fieldnames or []))}")
        for row in reader:
            draw = (row.get("draw") or "").strip().upper()
            if draw not in {"1PM", "8PM"}:
                continue
            try:
                d = date.fromisoformat((row.get("date") or "").strip())
            except ValueError:
                continue
            if start <= d <= end:
                groups[(d.isoformat(), draw)].append(row)
    missing = []
    d = start
    while d <= end:
        for draw in ("1PM", "8PM"):
            key = (d.isoformat(), draw)
            if not complete(groups.get(key, [])):
                missing.append(key)
        d = date.fromordinal(d.toordinal() + 1)

    out = Path(a.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_path = out / "all_missing_draws.csv"
    batch_path = out / "missing_batch.csv"
    for path, items in ((all_path, missing),):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["date", "draw"]); w.writerows(items)
    if missing:
        start_index = ((max(a.cursor, 1) - 1) * a.batch_size) % len(missing)
        selected = [missing[(start_index + i) % len(missing)] for i in range(min(a.batch_size, len(missing)))]
    else:
        start_index, selected = 0, []
    with batch_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "draw"]); w.writerows(selected)
    report = {
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "expected_draw_pairs": (end - start).days * 2 + 2,
        "complete_draw_pairs": ((end - start).days * 2 + 2) - len(missing),
        "missing_draw_pairs": len(missing), "batch_size": len(selected),
        "batch_cursor": a.cursor, "batch_start_index": start_index,
        "status": "gaps_found" if missing else "complete"
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"has_missing={'true' if selected else 'false'}\n")
            f.write(f"missing_total={len(missing)}\n")
            f.write(f"batch_count={len(selected)}\n")

if __name__ == "__main__":
    main()

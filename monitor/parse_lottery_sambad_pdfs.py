#!/usr/bin/env python3
"""Parse Lottery Sambad PDFs into 132-number Nagaland 1PM/8PM batch rows.

The printed footer is the authority for the draw slot. Any 6PM PDF is ignored.
For overlapping copies, the first parseable PDF for a date/slot is retained.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from collections import defaultdict
from pathlib import Path


def pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout


def parse_result(text: str):
    lines = text.splitlines()
    footer = None
    for line in lines:
        match = re.search(
            r"Lottery Sambad\s+(1PM|6PM|8PM)\s+Result Today\s+(\d{2})-(\d{2})-(\d{4})",
            line, re.I,
        )
        if match:
            footer = match
            break
    if not footer:
        return None
    slot = footer.group(1).upper()
    draw_date = f"{footer.group(4)}-{footer.group(3)}-{footer.group(2)}"
    if slot == "6PM":
        return {"date": draw_date, "draw": slot, "skip": True}

    first_index = None
    series = first = None
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\s*(\d{2}[A-Z])\s+(\d{5})\s*", line)
        if match:
            first_index, series, first = index, match.group(1), match.group(2)
            break
    if first_index is None:
        raise ValueError("first-prize series/number not found")

    consolation = None
    consolation_index = None
    for index in range(first_index + 1, min(first_index + 8, len(lines))):
        values = re.findall(r"(?<!\d)\d{5}(?!\d)", lines[index])
        if len(values) == 1 and values[0] == first:
            consolation, consolation_index = values[0], index
            break
    if consolation is None:
        raise ValueError("consolation number not found")

    before_fifth = []
    fifth_header = None
    for index in range(consolation_index + 1, len(lines)):
        if "5th Prize Amount" in lines[index]:
            fifth_header = index
            break
        before_fifth.extend(re.findall(r"(?<!\d)\d{4,5}(?!\d)", lines[index]))
    if fifth_header is None:
        raise ValueError("5th prize section not found")

    second = [value for value in before_fifth if len(value) == 5]
    four_digit = [value for value in before_fifth if len(value) == 4]
    if len(second) != 10 or len(four_digit) != 20:
        raise ValueError(
            f"unexpected upper-tier counts: second={len(second)}, "
            f"third/fourth={len(four_digit)}"
        )

    fifth = []
    for line in lines[fifth_header + 1:]:
        if "TDS" in line:
            break
        fifth.extend(re.findall(r"(?<!\d)\d{4}(?!\d)", line))
    if len(fifth) != 100:
        raise ValueError(f"expected 100 fifth-prize numbers, got {len(fifth)}")

    return {
        "date": draw_date, "draw": slot, "skip": False,
        "first_prize_series": series, "first_prize_number": first,
        "consolation_number": consolation, "second_prize": second,
        "third_prize": four_digit[:10], "fourth_prize": four_digit[10:],
        "fifth_prize": fifth,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.input_dir)
    manifest_path = root / "manifest.json"
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    provenance = {item.get("source_file"): item for item in manifest if item.get("source_file")}

    selected = {}
    skipped_6pm = 0
    failures = []
    for pdf in sorted(root.glob("copies/**/*.pdf")):
        try:
            result = parse_result(pdf_text(pdf))
            if result is None:
                continue
            if result.get("skip"):
                skipped_6pm += 1
                continue
            key = (result["date"], result["draw"])
            if key in selected:
                continue
            item = provenance.get(pdf.relative_to(root).as_posix(), {})
            result["source_file"] = pdf.relative_to(root).as_posix()
            result["source_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
            result["source_url"] = item.get("source_url", "")
            result["discovery_url"] = item.get("discovery_url", "")
            selected[key] = result
        except Exception as error:
            failures.append((pdf.name, str(error)))

    fields = [
        "date", "draw", "prize_tier", "position", "winning_number",
        "source_reference", "additional_source_url", "verification_status",
    ]
    rows = []
    for (draw_date, draw), item in sorted(selected.items()):
        source = item["source_url"] or item["source_file"]
        source_reference = f'{source} | SHA256:{item["source_sha256"]}'
        groups = [
            ("1st", [f'{item["first_prize_series"]} {item["first_prize_number"]}']),
            ("Consolation", [item["consolation_number"]]),
            ("2nd", item["second_prize"]),
            ("3rd", item["third_prize"]),
            ("4th", item["fourth_prize"]),
            ("5th", item["fifth_prize"]),
        ]
        count = 0
        for tier, numbers in groups:
            expected = {"1st": 1, "Consolation": 1, "2nd": 10, "3rd": 10, "4th": 10, "5th": 100}[tier]
            if len(numbers) != expected:
                raise SystemExit(f"{draw_date} {draw} {tier}: expected {expected}, got {len(numbers)}")
            for position, number in enumerate(numbers, 1):
                rows.append({
                    "date": draw_date, "draw": draw, "prize_tier": tier,
                    "position": str(position), "winning_number": number,
                    "source_reference": source_reference,
                    "additional_source_url": item["discovery_url"],
                    "verification_status": "single_archive_pdf_full_tier_extracted",
                })
                count += 1
        if count != 132:
            raise SystemExit(f"{draw_date} {draw}: expected 132 rows, got {count}")

    if not rows:
        raise SystemExit("No complete Nagaland 1PM/8PM PDFs parsed")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"PDF_FILES={len(list(root.glob('copies/**/*.pdf')))}")
    print(f"PARSED_DRAW_PAIRS={len(selected)}")
    print(f"ROWS_EXTRACTED={len(rows)}")
    print(f"6PM_PDFS_SKIPPED={skipped_6pm}")
    print(f"PARSE_FAILURES={len(failures)}")
    for name, error in failures[:20]:
        print(f"PARSE_SKIP {name}: {error}")


if __name__ == "__main__":
    main()

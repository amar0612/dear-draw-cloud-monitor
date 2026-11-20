#!/usr/bin/env python3
"""Multi-layout parser for Nagaland 1PM/8PM lottery result PDFs.

Uses the archive manifest as provenance for date/slot when a publisher PDF
does not print a Lottery Sambad footer. Any explicit footer must agree.
Only complete 132-record draws are exported. Ambiguous/scanned PDFs are logged,
never guessed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    )
    text = result.stdout
    # Scanned government gazettes have no embedded text. OCR is attempted
    # only for those PDFs, not for ordinary text-based archive copies.
    if len(re.sub(r"\s+", "", text)) < 100:
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                prefix = str(Path(tmp) / "page")
                subprocess.run(
                    ["pdftoppm", "-f", "1", "-l", "1", "-r", "300", "-png",
                     str(path), prefix],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                images = sorted(Path(tmp).glob("page-*.png"))
                if images:
                    ocr = subprocess.run(
                        ["tesseract", str(images[0]), "stdout", "--psm", "6"],
                        check=True, capture_output=True, text=True,
                    )
                    text = ocr.stdout
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
    return text


def parse_result(text: str, expected_date: str, expected_draw: str):
    """Parse the two known text layouts; never infer a missing prize number."""
    lines = text.splitlines()
    slot = expected_draw.upper()
    draw_date = expected_date

    # Layout A: classic Lottery Sambad footer. It is authoritative when present.
    footer = None
    for line in lines:
        match = re.search(
            r"Lottery Sambad\s+(1PM|6PM|8PM)\s+Result Today\s+(\d{2})-(\d{2})-(\d{4})",
            line, re.I,
        )
        if match:
            footer = match
            break
    if footer:
        footer_slot = footer.group(1).upper()
        footer_date = f"{footer.group(4)}-{footer.group(3)}-{footer.group(2)}"
        if footer_slot == "6PM":
            return {"skip": True}, None
        if footer_slot != slot or footer_date != draw_date:
            return None, f"manifest/footer mismatch: {draw_date} {slot} vs {footer_date} {footer_slot}"

    # Layout B: weekly-lottery publisher PDF. Its print layout has no
    # Lottery Sambad footer; date/slot are supplied by the source manifest
    # and source URL (1pm-/8pm- route). Require the expected date in the body.
    body_date = re.search(r"\b(\d{2})/(\d{2})/(\d{2,4})\b", text)
    if not footer and body_date:
        dd, mm, yy = body_date.groups()
        yyyy = ("20" + yy) if len(yy) == 2 else yy
        if f"{yyyy}-{mm}-{dd}" != draw_date:
            return None, f"body date mismatch: expected {draw_date}, found {dd}/{mm}/{yy}"

    # First prize line, e.g. "69K 54281".
    first_index = None
    series = first = None
    for index, line in enumerate(lines):
        match = re.fullmatch(r"\s*(\d{2}[A-Z])\s+(\d{5})\s*", line, re.I)
        if match:
            first_index, series, first = index, match.group(1).upper(), match.group(2)
            break
    if first_index is None:
        return None, "first prize series/number not found (OCR/layout review required)"

    # Consolation: same 5-digit suffix as the first prize, printed separately.
    consolation_index = None
    for index in range(first_index + 1, min(first_index + 10, len(lines))):
        values = re.findall(r"(?<!\d)\d{5}(?!\d)", lines[index])
        if len(values) == 1 and values[0] == first:
            consolation_index = index
            break
    if consolation_index is None:
        return None, "consolation number not found"

    fifth_header = None
    for index in range(consolation_index + 1, len(lines)):
        if re.search(r"5th\s+Prize\s+Amount", lines[index], re.I):
            fifth_header = index
            break
    if fifth_header is None:
        return None, "5th prize section heading not found"

    upper = []
    for line in lines[consolation_index + 1:fifth_header]:
        upper.extend(re.findall(r"(?<!\d)\d{4,5}(?!\d)", line))
    second = [value for value in upper if len(value) == 5]
    four_digit = [value for value in upper if len(value) == 4]
    if len(second) != 10 or len(four_digit) != 20:
        return None, f"upper-tier counts mismatch: second={len(second)}, third/fourth={len(four_digit)}"

    fifth = []
    for line in lines[fifth_header + 1:]:
        if re.search(r"\bTDS\b", line, re.I):
            break
        fifth.extend(re.findall(r"(?<!\d)\d{4}(?!\d)", line))
    if len(fifth) != 100:
        return None, f"fifth-tier count mismatch: expected 100, got {len(fifth)}"

    return {
        "date": draw_date, "draw": slot, "skip": False,
        "first_prize_series": series, "first_prize_number": first,
        "consolation_number": first, "second_prize": second,
        "third_prize": four_digit[:10], "fourth_prize": four_digit[10:],
        "fifth_prize": fifth,
    }, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.input_dir)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    provenance = {item.get("source_file"): item for item in manifest if item.get("source_file")}

    selected = {}
    skipped_6pm = 0
    failures = []
    pdfs = sorted(root.glob("copies/**/*.pdf"))
    for pdf in pdfs:
        relative = pdf.relative_to(root).as_posix()
        item = provenance.get(relative, {})
        expected_date = item.get("date")
        expected_draw = item.get("draw")
        if not expected_date or expected_draw not in ("1PM", "8PM"):
            failures.append((pdf.name, "missing trusted date/draw metadata"))
            continue
        try:
            result, error = parse_result(pdf_text(pdf), expected_date, expected_draw)
            if error:
                failures.append((pdf.name, error))
                continue
            if result is None:
                failures.append((pdf.name, "unclassified PDF"))
                continue
            if result.get("skip"):
                skipped_6pm += 1
                continue
            key = (result["date"], result["draw"])
            if key in selected:
                continue
            result["source_file"] = relative
            result["source_sha256"] = hashlib.sha256(pdf.read_bytes()).hexdigest()
            result["source_url"] = item.get("source_url", "")
            result["discovery_url"] = item.get("discovery_url", "")
            selected[key] = result
        except Exception as error:
            failures.append((pdf.name, f"parser exception: {error}"))

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

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"PDF_FILES={len(pdfs)}")
    print(f"PARSED_DRAW_PAIRS={len(selected)}")
    print(f"ROWS_EXTRACTED={len(rows)}")
    print(f"6PM_PDFS_SKIPPED={skipped_6pm}")
    print(f"PARSE_FAILURES={len(failures)}")
    reasons = Counter(error for _, error in failures)
    for reason, count in reasons.most_common():
        print(f"FAILURE_REASON count={count}: {reason}")
    for name, error in failures[:50]:
        print(f"PARSE_SKIP {name}: {error}")
    if not selected:
        raise SystemExit("No complete Nagaland 1PM/8PM PDFs parsed")


if __name__ == "__main__":
    main()

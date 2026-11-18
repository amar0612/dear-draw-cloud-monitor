#!/usr/bin/env python3
"""Download official Nagaland result gazettes and create a provenance manifest.

A downloaded PDF is evidence for review, NOT an automatic human verification.
The script never edits the master CSV or changes verification_status.
"""
import argparse
import csv
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL = "https://www.nagalandlotteries.com/old_results/"
USER_AGENT = "DearDrawAnalyzer/1.0 (official result source archive)"
REQUIRED = {"date", "draw"}


def official_filename(draw_date, draw):
    date_obj = date.fromisoformat(draw_date)
    if draw not in {"1PM", "8PM"}:
        raise ValueError("Only Nagaland 1PM and 8PM are supported")
    prefix = "MN" if draw == "1PM" else "EN"
    return f"{prefix}{date_obj:%d%m%y}.PDF"


def read_draws(csv_path):
    grouped = set()
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        for row in reader:
            draw_date = (row.get("date") or "").strip()
            draw = (row.get("draw") or "").strip().upper()
            if draw not in {"1PM", "8PM"}:
                continue
            date.fromisoformat(draw_date)
            grouped.add((draw_date, draw))
    return sorted(grouped)


def fetch_pdf(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Official source URL did not return a PDF")
    return data


def archive_sources(csv_path, output_dir, fetcher=fetch_pdf, dry_run=False):
    output_dir = Path(output_dir)
    manifest_path = output_dir / "manifest.json"
    manifest = []
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    known = {(item["date"], item["draw"]): item for item in manifest}
    results = []
    for draw_date, draw in read_draws(csv_path):
        filename = official_filename(draw_date, draw)
        url = BASE_URL + filename
        key = (draw_date, draw)
        if dry_run:
            results.append({"date": draw_date, "draw": draw, "url": url,
                            "status": "dry_run_not_downloaded"})
            continue
        try:
            data = fetcher(url)
            digest = hashlib.sha256(data).hexdigest()
            relative = Path(draw_date[:4]) / filename
            destination = output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                if existing_digest != digest:
                    raise FileExistsError(
                        f"Existing source differs; refusing overwrite: {destination}"
                    )
            else:
                destination.write_bytes(data)

            record = {
                "date": draw_date,
                "draw": draw,
                "source_type": "official_nagaland_gazette",
                "source_url": url,
                "source_file": str(relative).replace("\\", "/"),
                "sha256": digest,
                "bytes": len(data),
                "verification_status": "downloaded_pending_number_comparison",
            }
            known[key] = record
            results.append(record)
        except Exception as error:
            results.append({"date": draw_date, "draw": draw, "url": url,
                            "verification_status": "source_unavailable_or_error",
                            "error": str(error)})

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = sorted(known.values(), key=lambda x: (x["date"], x["draw"]))
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Candidate results CSV")
    parser.add_argument("--output-dir", default="sources/official")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        results = archive_sources(args.csv, args.output_dir, dry_run=args.dry_run)
    except Exception as error:
        sys.exit(f"SOURCE ARCHIVE FAILED: {error}")
    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    if any(item.get("verification_status") == "source_unavailable_or_error" for item in results):
        raise SystemExit(1)
    print("Downloaded sources remain pending number-by-number comparison.")


if __name__ == "__main__":
    main()

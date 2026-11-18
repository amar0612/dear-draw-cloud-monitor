#!/usr/bin/env python3
"""Download Nagaland result PDFs and preserve source provenance.

Third-party mirror PDFs are never labelled as official government gazettes and
no downloaded file is automatically marked human_verified.
"""
import argparse
import csv
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL = "https://www.nagalandlotteries.com/old_results/"
MIRROR_BASE = "https://lotterysambadresult.in/wp-content/uploads/"
USER_AGENT = "DearDrawAnalyzer/1.0 (historical result source archive)"
REQUIRED = {"date", "draw"}


def official_filename(draw_date, draw):
    date_obj = date.fromisoformat(draw_date)
    if draw not in {"1PM", "8PM"}:
        raise ValueError("Only Nagaland 1PM and 8PM are supported")
    # Legacy mirror filenames observed in January 2023: MD for 1 PM, ED for 8 PM.
    prefix = "MD" if draw == "1PM" else "ED"
    return f"{prefix}{date_obj:%d%m%y}.pdf"


def source_candidates(draw_date, draw):
    date_obj = date.fromisoformat(draw_date)
    legacy = official_filename(draw_date, draw)
    current_prefix = "MN" if draw == "1PM" else "EN"
    current_name = f"{current_prefix}{date_obj:%d%m%y}.PDF"
    legacy_upper = legacy[:-4] + ".PDF"
    return [
        ("official_nagaland_gazette", BASE_URL + current_name),
        ("official_nagaland_gazette_legacy_name", BASE_URL + legacy_upper),
        ("third_party_mirror_copy", MIRROR_BASE + f"{date_obj:%Y/%m}/" + legacy),
    ]


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
        raise ValueError("Source URL did not return a PDF")
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
        candidates = source_candidates(draw_date, draw)
        key = (draw_date, draw)
        if dry_run:
            results.append({
                "date": draw_date, "draw": draw,
                "candidate_sources": [{"source_type": kind, "url": url} for kind, url in candidates],
                "status": "dry_run_not_downloaded",
            })
            continue

        failures = []
        for source_type, url in candidates:
            try:
                data = fetcher(url)
                if not isinstance(data, (bytes, bytearray)) or not data.startswith(b"%PDF-"):
                    raise ValueError("Source URL did not return a valid PDF")
                digest = hashlib.sha256(data).hexdigest()
                relative = Path(draw_date[:4]) / filename
                destination = output_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    old_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                    if old_digest != digest:
                        raise FileExistsError(f"Existing source differs; refusing overwrite: {destination}")
                else:
                    destination.write_bytes(data)

                status = (
                    "mirror_copy_pending_official_comparison"
                    if source_type == "third_party_mirror_copy"
                    else "downloaded_pending_number_comparison"
                )
                record = {
                    "date": draw_date, "draw": draw,
                    "source_type": source_type, "source_url": url,
                    "source_file": str(relative).replace("\\", "/"),
                    "sha256": digest, "bytes": len(data),
                    "verification_status": status,
                }
                known[key] = record
                results.append(record)
                break
            except Exception as error:
                failures.append({"source_type": source_type, "url": url, "error": str(error)})
        else:
            failure = {
                "date": draw_date, "draw": draw,
                "source_type": "source_candidates_exhausted",
                "verification_status": "source_unavailable_or_error",
                "attempts": failures,
            }
            known[key] = failure
            results.append(failure)

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = sorted(known.values(), key=lambda x: (x["date"], x["draw"]))
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Candidate results CSV")
    parser.add_argument("--output-dir", default="sources/historical")
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
    print("Downloaded sources remain pending number-by-number comparison; mirror copies are not official government files.")


if __name__ == "__main__":
    main()

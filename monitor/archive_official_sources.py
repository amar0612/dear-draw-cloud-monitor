#!/usr/bin/env python3
"""Discover and archive all applicable Nagaland 1PM/8PM source copies.

Registry landing pages are treated as discovery leads, not proof of coverage.
No downloaded file is automatically marked human_verified.
"""
import argparse
import csv
import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

BASE_URL = "https://www.nagalandlotteries.com/old_results/"
MIRROR_BASE = "https://lotterysambadresult.in/wp-content/uploads/"
USER_AGENT = "DearDrawAnalyzer/1.0 (historical result source archive)"
DATE_COLUMNS = ("date", "draw_date", "result_date")
DRAW_COLUMNS = ("draw", "draw_time", "time", "draw_slot")
DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "data" / "nagaland_source_registry.csv"
EXCLUDED_REGISTRY_INDICES = {"23", "24"}
NON_PDF_REGISTRY_INDICES = {"3", "21"}
DATE_FORMATS = ("%d%m%y", "%d%m%Y", "%Y-%m-%d", "%d-%m-%Y", "%d_%m_%Y")


def official_filename(draw_date, draw):
    date_obj = date.fromisoformat(draw_date)
    if draw not in {"1PM", "8PM"}:
        raise ValueError("Only Nagaland 1PM and 8PM are supported")
    prefix = "MD" if draw == "1PM" else "ED"
    return f"{prefix}{date_obj:%d%m%y}.pdf"


def _registry_rows(registry_path=DEFAULT_REGISTRY):
    with Path(registry_path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:48] or "source"


def _date_tokens(draw_date):
    d = date.fromisoformat(draw_date)
    return {
        d.strftime("%d%m%y").lower(), d.strftime("%d%m%Y").lower(),
        d.strftime("%Y-%m-%d").lower(), d.strftime("%d-%m-%Y").lower(),
        d.strftime("%d_%m_%Y").lower(), d.strftime("%d-%m-%y").lower(),
        d.strftime("%d %B %Y").lower(), d.strftime("%B %d, %Y").lower(),
        d.strftime("%d %b %Y").lower(),
    }


def _direct_registry_urls(row, draw_date, draw):
    d = date.fromisoformat(draw_date)
    index = row["index"]
    base = row["url_or_pattern"]
    legacy = official_filename(draw_date, draw)
    current = ("MN" if draw == "1PM" else "EN") + d.strftime("%d%m%y") + ".PDF"
    if index == "1":
        return [base.replace("MNDDMMYY.PDF", current)]
    if index == "2":
        return [base.replace("ENDDMMYY.PDF", current)]
    if index == "13":
        return [base.replace("YYYY-MM-DD", draw_date).replace("1pm", "1pm" if draw == "1PM" else "8pm")]
    if index == "22":
        names = [legacy, legacy.upper(), ("ML" if draw == "1PM" else "EL") + d.strftime("%d%m%y") + ".pdf"]
        monthly_base = f"https://lotterysambadresult.in/wp-content/uploads/{d:%Y/%m}/"
        return [urljoin(monthly_base, name) for name in names]
    # Annual archive roots are the best known starting points for year-specific calendars.
    if index in {"6", "7", "8", "9", "10", "11"}:
        return [base]
    return [base]


def source_candidates(draw_date, draw, registry_path=DEFAULT_REGISTRY):
    """Return every registry-backed lead applicable to this draw.

    Excluded schedule-mismatch sources and non-result documentation/reference
    pages remain in the CSV registry but are not treated as full-result sources.
    """
    date.fromisoformat(draw_date)
    if draw not in {"1PM", "8PM"}:
        raise ValueError("Only Nagaland 1PM and 8PM are supported")
    candidates = []
    for row in _registry_rows(registry_path):
        index = row["index"]
        if index in EXCLUDED_REGISTRY_INDICES or index in NON_PDF_REGISTRY_INDICES:
            continue
        if draw not in row.get("draw_scope", ""):
            continue
        for url in _direct_registry_urls(row, draw_date, draw):
            candidates.append((f"registry_{index}_{_slug(row['source_name'])}", url))
    # Keep explicitly observed mirror filename variants as independent leads.
    d = date.fromisoformat(draw_date)
    for name in (official_filename(draw_date, draw),
                 ("ML" if draw == "1PM" else "EL") + d.strftime("%d%m%y") + ".pdf"):
        candidates.append(("legacy_wordpress_mirror", MIRROR_BASE + f"{d:%Y/%m}/" + name))
    # ICU is the sole primary archive. All other sites are fallback candidates,
    # attempted only when ICU has no matching PDF for this exact date/draw.
    candidates.sort(key=lambda item: (0 if item[0].startswith("registry_15_") else 1))
    seen = set()
    return [(kind, url) for kind, url in candidates
            if not (url in seen or seen.add(url))]


def read_draws(csv_path):
    grouped = set()
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        date_column = next((name for name in DATE_COLUMNS if name in headers), None)
        draw_column = next((name for name in DRAW_COLUMNS if name in headers), None)
        if not date_column or not draw_column:
            raise ValueError(
                "CSV must contain a date column (date/draw_date/result_date) "
                "and a draw column (draw/draw_time/time/draw_slot)"
            )
        for row in reader:
            draw_date = (row.get(date_column) or "").strip()[:10]
            raw_draw = (row.get(draw_column) or "").strip().upper().replace(" ", "")
            draw = {"1PM": "1PM", "13:00": "1PM", "1:00PM": "1PM",
                    "8PM": "8PM", "20:00": "8PM", "8:00PM": "8PM"}.get(raw_draw, raw_draw)
            if draw not in {"1PM", "8PM"}:
                continue
            date.fromisoformat(draw_date)
            grouped.add((draw_date, draw))
    return sorted(grouped)


def fetch_pdf(url, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    return data


def _slot_is_compatible(value, draw):
    """Reject wrong draw slots using PDF filename codes and visible labels.

    Confirmed archive filename convention: MN=1PM, EN=8PM, DN=6PM (excluded).
    Older mirror aliases MD=1PM and ED=8PM are retained.
    """
    text = unquote(str(value)).lower().replace("%20", " ")
    filename = urlparse(text).path.rsplit("/", 1)[-1]
    code_match = re.match(r"^(mn|md|en|ed|dn)(\d{6,8})\.pdf$", filename, re.I)
    if code_match:
        code = code_match.group(1).upper()
        code_draw = {"MN": "1PM", "MD": "1PM", "EN": "8PM", "ED": "8PM"}.get(code)
        if code == "DN" or code_draw is None or code_draw != draw:
            return False

    # Explicit schedule labels take precedence over ambiguous page context.
    if re.search(r"(?<![0-9])6\s?pm(?![a-z])|(?<![0-9])18:00(?![0-9])", text):
        return False
    has_1pm = bool(re.search(r"(?<![0-9])1\s?pm(?![a-z])|(?<![0-9])13:00(?![0-9])", text))
    has_8pm = bool(re.search(r"(?<![0-9])8\s?pm(?![a-z])|(?<![0-9])20:00(?![0-9])", text))
    if has_1pm and not has_8pm and draw != "1PM":
        return False
    if has_8pm and not has_1pm and draw != "8PM":
        return False
    return True

def _matching_link(href, label, draw_date, draw):
    joined = (unquote(href) + " " + html.unescape(label)).lower()
    if not _slot_is_compatible(joined, draw):
        return False
    d = date.fromisoformat(draw_date)
    tokens = _date_tokens(draw_date)
    compact = re.sub(r"[^0-9]", "", draw_date)
    date_match = any(token in joined for token in tokens) or compact in re.sub(r"[^0-9]", "", joined)
    # Also traverse month archive links (e.g. /2024/06/) to reach date pages.
    month_names = {d.strftime("%B").lower(), d.strftime("%b").lower()}
    month_tokens = {d.strftime("%m"), str(d.month)}
    month_match = str(d.year) in joined and (
        any(name in joined for name in month_names)
        or any(re.search(rf"/{re.escape(token)}/", joined) for token in month_tokens)
    )
    if not date_match and not month_match:
        return False
    # Explicit wrong-slot labels are rejected. If the link has no slot label,
    # it can still be a date page whose child page contains the draw-specific PDF.
    wrong = "8pm" if draw == "1PM" else "1pm"
    right = draw.lower()
    if wrong in joined and right not in joined:
        return False
    return True


def _extract_links(page_bytes, page_url, draw_date, draw):
    try:
        page = page_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return []
    found = []
    for match in re.finditer(r'<a\b[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        href, label = match.group(1), re.sub(r"<[^>]+>", " ", match.group(2))
        absolute = urljoin(page_url, html.unescape(href))
        if urlparse(absolute).scheme not in {"http", "https"}:
            continue
        parent_has_date = any(token in page_url.lower() for token in _date_tokens(draw_date))
        combined_link_text = (absolute + " " + label).lower()
        date_page_pdf = parent_has_date and _slot_is_compatible(combined_link_text, draw) and (
            ".pdf" in absolute.lower() or "pdf" in label.lower() or draw.lower() in label.lower()
        )
        if _slot_is_compatible(combined_link_text, draw) and (
            _matching_link(absolute, label, draw_date, draw) or date_page_pdf
        ):
            found.append(absolute)
    return list(dict.fromkeys(found))


def _safe_filename(draw_date, draw, source_type, digest):
    return f"{date.fromisoformat(draw_date):%Y%m%d}_{draw}_{_slug(source_type)}_{digest[:12]}.pdf"


def archive_sources(csv_path, output_dir, fetcher=fetch_pdf, dry_run=False,
                    offset=0, limit=None, start_date=None, end_date=None,
                    registry_path=DEFAULT_REGISTRY):
    output_dir = Path(output_dir)
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    # Preserve legacy manifest rows while making new records unique per source URL.
    known = {}
    for item in manifest:
        identity = (item.get("date"), item.get("draw"), item.get("source_url", item.get("source_type", "__summary__")))
        known[identity] = item
    results = []
    draws = read_draws(csv_path)
    if not draws:
        raise ValueError(
            f"No 1PM/8PM date-draw pairs found in {csv_path}; "
            "check the CSV headers and contents. Refusing to report an empty batch as success."
        )
    if start_date:
        date.fromisoformat(start_date)
    if end_date:
        date.fromisoformat(end_date)
    if start_date and end_date and start_date > end_date:
        raise ValueError("start-date must be on or before end-date")
    if start_date:
        draws = [item for item in draws if item[0] >= start_date]
    if end_date:
        draws = [item for item in draws if item[0] <= end_date]
    if offset < 0 or (limit is not None and limit < 1):
        raise ValueError("offset must be >= 0 and limit must be >= 1")
    draws = draws[offset:offset + limit if limit is not None else None]

    page_cache = {}
    for draw_date, draw in draws:
        candidates = source_candidates(draw_date, draw, registry_path)
        if dry_run:
            results.append({"date": draw_date, "draw": draw,
                            "candidate_sources": [{"source_type": k, "url": u} for k, u in candidates],
                            "status": "dry_run_not_downloaded"})
            continue

        successful = []
        failures = []
        for source_type, landing_url in candidates:
            identity = (draw_date, draw, landing_url)
            # Still re-fetch on reruns so new/changed source copies can be discovered.
            try:
                print(f"[{draw_date} {draw}] CHECK {source_type} {landing_url}", flush=True)
                payload = page_cache.get(landing_url)
                if payload is None:
                    payload = fetcher(landing_url)
                    page_cache[landing_url] = payload
                pdf_candidates = []
                if isinstance(payload, (bytes, bytearray)) and payload.startswith(b"%PDF-"):
                    if _slot_is_compatible(landing_url, draw):
                        pdf_candidates.append((landing_url, payload))
                    else:
                        print(f"[{draw_date} {draw}] SKIP wrong-slot PDF {landing_url}", flush=True)
                else:
                    # A landing/calendar page can expose date-specific result pages or PDFs.
                    links = _extract_links(payload, landing_url, draw_date, draw)
                    for child_url in links[:30]:
                        try:
                            child = page_cache.get(child_url)
                            if child is None:
                                child = fetcher(child_url)
                                page_cache[child_url] = child
                            if isinstance(child, (bytes, bytearray)) and child.startswith(b"%PDF-"):
                                if _slot_is_compatible(child_url, draw):
                                    pdf_candidates.append((child_url, child))
                                else:
                                    print(f"[{draw_date} {draw}] SKIP wrong-slot PDF {child_url}", flush=True)
                            else:
                                for pdf_url in _extract_links(child, child_url, draw_date, draw)[:30]:
                                    try:
                                        pdf_data = page_cache.get(pdf_url)
                                        if pdf_data is None:
                                            pdf_data = fetcher(pdf_url)
                                            page_cache[pdf_url] = pdf_data
                                        if isinstance(pdf_data, (bytes, bytearray)) and pdf_data.startswith(b"%PDF-"):
                                            if _slot_is_compatible(pdf_url, draw):
                                                pdf_candidates.append((pdf_url, pdf_data))
                                            else:
                                                print(f"[{draw_date} {draw}] SKIP wrong-slot PDF {pdf_url}", flush=True)
                                    except Exception as nested_error:
                                        failures.append({"source_type": source_type, "url": pdf_url, "error": str(nested_error)})
                        except Exception as child_error:
                            failures.append({"source_type": source_type, "url": child_url, "error": str(child_error)})

                for resolved_url, data in pdf_candidates:
                    digest = hashlib.sha256(data).hexdigest()
                    relative = Path("copies") / date.fromisoformat(draw_date).strftime("%Y") / _safe_filename(draw_date, draw, source_type, digest)
                    destination = output_dir / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists():
                        old_digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                        if old_digest != digest:
                            raise FileExistsError(f"Hash-named archive file unexpectedly differs: {destination}")
                    else:
                        destination.write_bytes(data)
                    is_official = source_type.startswith(("registry_0_", "registry_1_", "registry_2_"))
                    status = "downloaded_pending_number_comparison" if is_official else "mirror_copy_pending_official_comparison"
                    record = {
                        "date": draw_date, "draw": draw, "source_type": source_type,
                        "source_url": resolved_url, "discovery_url": landing_url,
                        "source_file": str(relative).replace("\\", "/"),
                        "sha256": digest, "bytes": len(data),
                        "verification_status": status,
                    }
                    rec_identity = (draw_date, draw, resolved_url)
                    known[rec_identity] = record
                    successful.append(record)
                for resolved_url, data in pdf_candidates:
                    print(f"[{draw_date} {draw}] PDF {len(data)} bytes {resolved_url}", flush=True)
                # Stop at the first source that supplies a date- and draw-matched PDF.
                # Remaining registry sites are strictly fallback sources.
                if successful:
                    print(f"[{draw_date} {draw}] PRIMARY/FALLBACK HIT; skipping remaining sources", flush=True)
                    break
            except Exception as error:
                print(f"[{draw_date} {draw}] ERROR {source_type} {landing_url}: {error}", flush=True)
                failures.append({"source_type": source_type, "url": landing_url, "error": str(error)})

        # Add a per-source failure row only where no source record already exists.
        for source_type, url in candidates:
            if not any(r.get("discovery_url") == url or r.get("source_url") == url for r in successful):
                if not any(f["url"] == url for f in failures):
                    failures.append({"source_type": source_type, "url": url, "error": "No matching PDF link found"})
        hashes = {}
        for record in successful:
            hashes.setdefault(record["sha256"], []).append(record)
        conflict = len(hashes) > 1
        for record in successful:
            record["content_group"] = record["sha256"][:12]
            record["content_match_count"] = len(hashes[record["sha256"]])
            record["source_comparison_status"] = "source_content_conflict" if conflict else "same_content_or_single_copy"
            known[(draw_date, draw, record["source_url"])] = record
        summary = {
            "date": draw_date, "draw": draw,
            "source_candidates_checked": len(candidates),
            "successful_pdf_copies": len(successful),
            "distinct_sha256": len(hashes),
            "comparison_status": "source_content_conflict" if conflict else ("identical_copies" if successful and max(map(len, hashes.values())) > 1 else ("single_copy_only" if successful else "no_pdf_found")),
            "verification_status": "pending_number_comparison" if successful else "source_unavailable_or_error",
            "attempts": failures,
        }
        results.append({**summary, "copies": successful})
        print(f"[{draw_date} {draw}] SUMMARY candidates={len(candidates)} PDFs={len(successful)} hashes={len(hashes)} status={summary['comparison_status']}", flush=True)
        known[(draw_date, draw, "__summary__")] = summary

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = sorted(known.values(), key=lambda x: (x.get("date", ""), x.get("draw", ""), x.get("source_url", x.get("source_type", ""))))
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Candidate results CSV")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="25-entry source registry CSV")
    parser.add_argument("--output-dir", default="sources/historical")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--start-date", help="Include draws on/after YYYY-MM-DD")
    parser.add_argument("--end-date", help="Include draws on/before YYYY-MM-DD")
    args = parser.parse_args()
    try:
        results = archive_sources(args.csv, args.output_dir, dry_run=args.dry_run,
                                  offset=args.offset, limit=args.limit,
                                  start_date=args.start_date, end_date=args.end_date,
                                  registry_path=args.registry)
    except Exception as error:
        sys.exit(f"SOURCE ARCHIVE FAILED: {error}")
    for item in results:
        print(json.dumps(item, ensure_ascii=False))
    missing = [item for item in results
               if item.get("verification_status") == "source_unavailable_or_error"]
    print(f"Batch finished: {len(results) - len(missing)} date/draw pairs had at least one PDF; "
          f"{len(missing)} remain missing after all applicable sources were tried.")
    print("Missing pairs are recorded in the manifest for targeted fallback recovery. "
          "Copies are retained by source and SHA-256; no copy is human-verified automatically.")


if __name__ == "__main__":
    main()

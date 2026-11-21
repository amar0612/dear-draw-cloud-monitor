#!/usr/bin/env python3
"""Discover explicit Nagaland 1PM/8PM archive evidence with bounded crawling.

The crawler follows archive/year/month/date pages on each registered host. It
never infers a draw merely from a date or weekday: a slot-labelled result link
must be present on the date page (or directly on a dated result link).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

UA = "DearDrawAnalyzer/1.1 (bounded historical calendar discovery)"
MAX_PAGES_PER_SOURCE = 160
MAX_DEPTH = 4
FETCH_TIMEOUT = 12
SOURCES = [
    ("official_gazette", "https://www.nagalandlotteries.com/results.php", "official"),
    ("lottery_sambad_fax", "https://www.lotterysambadfax.com/results", "mirror"),
    ("lottery_sambad_annual", "https://www.lotterysambad.co/old/", "mirror"),
    ("dear_1_crore", "https://www.dear1crore.com/nagaland-state-lottery/result/archive/", "mirror"),
    ("nagaland_sambad", "https://nagalandsambad.in/old-result", "mirror"),
    ("dearresult", "https://dearresult.in/", "mirror"),
    ("lottery_sambad_store", "https://lotterysambad.store/", "mirror"),
    ("lottery_sambad_icu", "https://lotterysambad.icu/old-result", "mirror"),
]
DATE_PATTERNS = [
    re.compile(r"(?<!\\d)(20\\d{2})[-_/](0?[1-9]|1[0-2])[-_/]([0-3]?\\d)(?!\\d)"),
    re.compile(r"(?<!\\d)([0-3]?\\d)[-_/](0?[1-9]|1[0-2])[-_/](20\\d{2})(?!\\d)"),
    re.compile(r"(?<!\\d)([0-3]?\\d)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?(20\\d{2})(?!\\d)", re.I),
]
MONTHS = {m.lower(): i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
)}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._parts)))
            self._href = None
            self._parts = []


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return ""
        return response.read(2_500_000).decode("utf-8", "ignore")


def extract_dates(text):
    found = set()
    for index, pattern in enumerate(DATE_PATTERNS):
        for match in pattern.finditer(text):
            try:
                if index == 0:
                    year, month, day = map(int, match.groups())
                elif index == 1:
                    day, month, year = map(int, match.groups())
                else:
                    day, mon, year = match.groups()
                    month, day, year = MONTHS[mon[:3].lower()], int(day), int(year)
                found.add(date(year, month, day).isoformat())
            except (ValueError, TypeError):
                continue
    return found


def draw_flags(href, label):
    value = (str(href) + " " + str(label)).lower()
    value = re.sub(r"[\\s_+-]+", "", value)
    one = bool(re.search(r"(?:1pm|13:00|13%3a00|13\.00)", value))
    eight = bool(re.search(r"(?:8pm|20:00|20%3a00|20\.00)", value))
    six = bool(re.search(r"(?:6pm|18:00|18%3a00|18\.00)", value))
    if six and not (one or eight):
        return set()
    return ({"1PM"} if one else set()) | ({"8PM"} if eight else set())


def archive_candidate(url, source_url):
    parsed, root = urlparse(url), urlparse(source_url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != root.netloc.lower():
        return False
    path = parsed.path.lower()
    return (
        bool(extract_dates(path))
        or bool(re.search(r"/(?:20\\d{2})(?:/|$)", path))
        or any(token in path for token in ("archive", "old", "result", "month", "year"))
    )


def discover_source(source, source_url, kind, start, end):
    evidence = {}
    failures = []
    visited = set()
    # Carry a date from an archive calendar link into its date detail page.
    queue = deque([(source_url, None, 0)])
    pages = 0
    while queue and pages < MAX_PAGES_PER_SOURCE:
        url, inherited_date, depth = queue.popleft()
        url = urldefrag(url)[0]
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetch(url)
            pages += 1
            if not html:
                continue
            parser = Links()
            parser.feed(html)
            page_dates = extract_dates(url) or ({inherited_date} if inherited_date else set())
            for href, label in parser.links:
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                target = urljoin(url, href)
                link_dates = extract_dates(href + " " + label + " " + target)
                dates = link_dates or page_dates
                flags = draw_flags(href, label)
                for draw_date in dates:
                    if not (start <= draw_date <= end):
                        continue
                    if flags:
                        for draw in flags:
                            evidence.setdefault((draw_date, draw), []).append(
                                (source, kind, target, "dated_slot_link")
                            )
                    elif depth < MAX_DEPTH and link_dates and archive_candidate(target, source_url):
                        queue.append((target, draw_date, depth + 1))
                # Follow archive hierarchy links (year/month/date) even before a
                # complete date is visible, so annual indexes can lead to month pages.
                if depth < MAX_DEPTH and archive_candidate(target, source_url):
                    queue.append((target, inherited_date, depth + 1))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            failures.append({"url": url, "error": str(exc)[:180]})
    return evidence, {"source": source, "pages_fetched": pages, "pages_seen": len(visited),
                      "queue_remaining": len(queue), "page_limit_hit": bool(queue),
                      "failures": failures}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--output", default="data/nagaland_expected_draw_calendar.csv")
    parser.add_argument("--report", default="calendar-output/report.json")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start_date).isoformat(), date.fromisoformat(args.end_date).isoformat()
    evidence, diagnostics = {}, []
    for source, url, kind in SOURCES:
        found, diagnostic = discover_source(source, url, kind, start, end)
        diagnostics.append(diagnostic)
        for key, items in found.items():
            evidence.setdefault(key, []).extend(items)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "draw", "calendar_status", "source_count", "sources", "evidence_urls"])
        for (draw_date, draw), items in sorted(evidence.items()):
            source_names = sorted({item[0] for item in items})
            status = "official_explicit" if any(item[1] == "official" for item in items) else "mirror_explicit"
            writer.writerow([draw_date, draw, status, len(source_names), ";".join(source_names),
                             ";".join(sorted({item[2] for item in items}))])

    report = {
        "start_date": start, "end_date": end,
        "expected_draw_pairs_found": len(evidence),
        "dates_found": len({draw_date for draw_date, _ in evidence}),
        "sources_checked": len(SOURCES),
        "pages_fetched": sum(item["pages_fetched"] for item in diagnostics),
        "source_diagnostics": diagnostics,
        "calendar_file": str(output),
        "warning": "Evidence-backed archive calendar only; unlisted dates remain unknown, not non-draw days."
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

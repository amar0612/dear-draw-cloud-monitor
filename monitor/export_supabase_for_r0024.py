#!/usr/bin/env python3
"""Export Nagaland Dear 1PM/8PM Supabase rows into the R002.4 analysis schema."""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_URL = "https://sxdrqithncjdrokwpkzm.supabase.co"
PAGE_SIZE = 1000

def fetch_page(key, offset):
    params = urllib.parse.urlencode({
        "select": "draw_date,draw_slot,prizes,source,verification_status",
        "draw_slot": "in.(1PM,8PM)",
        "order": "draw_date.asc,draw_slot.asc",
        "limit": str(PAGE_SIZE),
        "offset": str(offset),
    })
    req = urllib.request.Request(
        PROJECT_URL + "/rest/v1/draws?" + params,
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="analysis-input/r0024_live_supabase_export.json")
    args = ap.parse_args()
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not key:
        sys.exit("ERROR: SUPABASE_SECRET_KEY is required.")
    rows = []
    offset = 0
    while True:
        page = fetch_page(key, offset)
        if not isinstance(page, list):
            sys.exit("ERROR: Supabase returned a non-list response.")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    draws = []
    for row in rows:
        slot = row.get("draw_slot")
        date = row.get("draw_date")
        prizes = row.get("prizes") or {}
        if slot not in ("1PM", "8PM") or not isinstance(date, str):
            continue
        # Preserve the exact digit strings and tier cardinalities for R002.4's parser.
        draws.append({
            "date": date,
            "time": "1:00PM" if slot == "1PM" else "8:00PM",
            "third": prizes.get("3rd"),
            "fourth": prizes.get("4th"),
            "fifth": prizes.get("5th"),
            "source": row.get("source"),
            "verification_status": row.get("verification_status"),
        })

    if not draws:
        sys.exit("ERROR: No Nagaland Dear 1PM/8PM rows were returned from Supabase.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"draws": draws}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "export": str(output),
        "supabase_rows": len(rows),
        "analysis_draw_records": len(draws),
        "one_pm_records": sum(d["time"] == "1:00PM" for d in draws),
        "eight_pm_records": sum(d["time"] == "8:00PM" for d in draws),
        "earliest_date": min(d["date"] for d in draws),
        "latest_date": max(d["date"] for d in draws),
    }, indent=2))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit("SUPABASE EXPORT FAILED: " + str(exc))

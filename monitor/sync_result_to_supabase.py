#!/usr/bin/env python3
"""Idempotently publish a validated Sambad API draw into Supabase.

Uses the service-role key only in GitHub Actions (never in browser code).
Existing date/slot rows are compared and never overwritten automatically.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

PROJECT_URL = "https://sxdrqithncjdrokwpkzm.supabase.co"


def request_json(url, key, method="GET", payload=None, prefer=None):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else []
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail}") from exc


def comparable(row):
    return {
        "draw_date": row["draw_date"],
        "draw_slot": row["draw_slot"],
        "prizes": row["prizes"],
        "source": row.get("source"),
        "verification_status": row["verification_status"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()

    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        sys.exit("ERROR: GitHub secret SUPABASE_SERVICE_ROLE_KEY is not configured.")

    record = json.loads(Path(args.file).read_text(encoding="utf-8"))
    from validate_result import validate_result
    errors = validate_result(record)
    if errors:
        sys.exit("Refusing cloud upload; validation failed: " + "; ".join(errors))

    slot = record["draw"]
    if slot not in {"1PM", "8PM"}:
        sys.exit("Refusing upload: only Nagaland 1PM and 8PM are allowed.")

    row = {
        "id": str(uuid.uuid4()),
        "draw_date": record["date"],
        "draw_slot": slot,
        "prizes": record["prizes"],
        "source": record["source"],
        "verification_status": record["verification_status"],
    }
    base = PROJECT_URL + "/rest/v1/draws"
    filters = urllib.parse.urlencode({
        "select": "id,draw_date,draw_slot,prizes,source,verification_status",
        "draw_date": f"eq.{row['draw_date']}",
        "draw_slot": f"eq.{slot}",
    })
    existing = request_json(base + "?" + filters, key)

    if existing:
        if len(existing) != 1:
            sys.exit("Conflict: multiple rows exist for this draw date and slot.")
        if comparable(existing[0]) == comparable(row):
            print(f"ALREADY SYNCED: {row['draw_date']} {slot}; existing row matches.")
            return
        sys.exit(
            f"CONFLICT: {row['draw_date']} {slot} already exists with different data. "
            "No cloud row was changed; manual review required."
        )

    inserted = request_json(
        base + "?on_conflict=draw_date,draw_slot",
        key,
        method="POST",
        payload=row,
        prefer="resolution=ignore-duplicates,return=representation",
    )
    if inserted:
        print(f"SYNCED: {row['draw_date']} {slot} inserted into Supabase.")
        return

    # A concurrent run may have inserted the same unique key after our GET.
    raced = request_json(base + "?" + filters, key)
    if len(raced) == 1 and comparable(raced[0]) == comparable(row):
        print(f"ALREADY SYNCED: {row['draw_date']} {slot}; concurrent insert matches.")
        return
    sys.exit(
        f"CONFLICT: {row['draw_date']} {slot} was inserted concurrently with "
        "different data, or Supabase returned no inserted row. Manual review required."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"CLOUD SYNC FAILED: {exc}")

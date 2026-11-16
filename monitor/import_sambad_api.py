
#!/usr/bin/env python3
"""Import Nagaland Dear 1PM / 8PM results from Sambad API v2."""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from validate_result import validate_result

API_URL = "https://api.sambad.com/v2/dear/result"
IST = ZoneInfo("Asia/Kolkata")

TIER_MAP = {
    "cons": "Consolation",
    "consolation": "Consolation",
    "2nd": "2nd",
    "3rd": "3rd",
    "4th": "4th",
    "5th": "5th",
}


def fetch_result(draw, draw_date, token):
    date_param = datetime.strptime(
        draw_date, "%Y-%m-%d"
    ).strftime("%d-%m-%Y")

    params = urllib.parse.urlencode({
        "date": date_param,
        "slot": draw,
        "access-token": token,
    })

    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "DearDrawAnalyzer/1.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_result(payload, draw, draw_date):
    if payload.get("success") is not True:
        raise ValueError("API did not return success=true")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Missing API data object")

    if data.get("status") != "published":
        raise ValueError(
            f"Result is not published. API status: {data.get('status')}"
        )

    if data.get("lottery") != "dear":
        raise ValueError("Unexpected lottery returned by API")

    if data.get("slot") != draw:
        raise ValueError("API returned a different draw slot")

    api_date = datetime.strptime(
        data.get("date", ""), "%d-%m-%Y"
    ).strftime("%Y-%m-%d")

    if api_date != draw_date:
        raise ValueError("API returned a different draw date")

    first = data.get("first")
    if not isinstance(first, dict):
        raise ValueError("Missing first prize")

    series = str(first.get("series", "")).strip()
    number = str(first.get("number", "")).strip()

    if not series or not number:
        raise ValueError("Incomplete first prize")

    prizes = {
        "1st": [f"{series} {number}"],
        "Consolation": [],
        "2nd": [],
        "3rd": [],
        "4th": [],
        "5th": [],
    }

    api_prizes = data.get("prizes")
    if not isinstance(api_prizes, list):
        raise ValueError("Missing API prize list")

    for prize in api_prizes:
        tier_key = str(prize.get("tier", "")).strip().lower()
        tier = TIER_MAP.get(tier_key)

        if tier is None:
            continue

        if tier == "Consolation" and prize.get("match") != "number":
            raise ValueError("Unexpected consolation matching rule")

        if tier == "2nd" and prize.get("match") != "number":
            raise ValueError("Unexpected second-prize matching rule")

        if tier in {"3rd", "4th", "5th"} and prize.get("match") != "last4":
            raise ValueError(f"Unexpected matching rule for {tier}")

        numbers = prize.get("numbers")
        if not isinstance(numbers, list):
            raise ValueError(f"{tier} numbers are missing")

        prizes[tier].extend(str(value).strip() for value in numbers)

    return {
        "date": draw_date,
        "draw": "1PM" if draw == "1pm" else "8PM",
        "prizes": prizes,
        "source": "Lottery Sambad API v2",
        "verification_status": "API_IMPORTED_NOT_GAZETTE_VERIFIED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--draw", required=True, choices=["1pm", "8pm"]
    )
    parser.add_argument(
        "--date",
        default=datetime.now(IST).strftime("%Y-%m-%d"),
        help="Date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "--output-dir", default="api-results"
    )
    args = parser.parse_args()

    token = os.environ.get("SAMBAD_API_TOKEN")
    if not token:
        sys.exit("ERROR: SAMBAD_API_TOKEN secret is missing")

    try:
        datetime.strptime(args.date, "%Y-%m-%d")

        print(f"Fetching Dear {args.draw.upper()} for {args.date}...")

        payload = fetch_result(args.draw, args.date, token)
        record = normalize_result(payload, args.draw, args.date)

        errors = validate_result(record)
        if errors:
            print("VALIDATION FAILED:")
            for error in errors:
                print(f"- {error}")
            sys.exit(1)

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = (
            f"{args.date}_{record['draw']}.json"
        )
        output_path = output_dir / filename

                new_content = (
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )

        if output_path.exists():
            existing_content = output_path.read_text(encoding="utf-8")

            if existing_content == new_content:
                print(f"SKIPPED: Identical result already archived: {output_path}")
                return

            sys.exit(
                f"STOP: Different data already exists at {output_path}. "
                "Existing archive was not overwritten."
            )

        output_path.write_text(new_content, encoding="utf-8")

        output_path.write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8"
        )

        print("SUCCESS: All 132 prize entries passed validation.")
        print(f"Saved separately to: {output_path}")
        print("Status: API imported; Gazette verification still required.")

    except Exception as error:
        sys.exit(f"IMPORT FAILED: {error}")


if __name__ == "__main__":
    main()

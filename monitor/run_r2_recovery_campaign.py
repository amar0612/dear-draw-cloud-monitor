#!/usr/bin/env python3
"""Run the 2023 Nagaland 1PM/8PM archive campaign and persist it in Cloudflare R2."""
import argparse
import json
import os
import sys
import time
import zipfile
from pathlib import Path
import boto3
from botocore.config import Config
from archive_official_sources import archive_sources, read_draws

YEAR = "2023"
PREFIX = "2023/"
OUT = Path("official-source-archive")
CHECKPOINT_KEY = PREFIX + "checkpoints/campaign.json"


def r2_client():
    required = ["R2_ACCOUNT_ID", "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing GitHub secrets: " + ", ".join(missing))
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", retries={"max_attempts": 8, "mode": "standard"}),
    )


def bucket_name():
    value = os.environ.get("R2_BUCKET_NAME", "")
    if not value:
        raise RuntimeError("Missing GitHub secret R2_BUCKET_NAME")
    return value


def restore(client, bucket):
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".zip"):
                continue
            target = OUT / key[len(PREFIX):]
            target.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, str(target))


def upload_tree(client, bucket):
    for path in OUT.rglob("*"):
        if path.is_file():
            key = PREFIX + path.relative_to(OUT).as_posix()
            client.upload_file(str(path), bucket, key)


def read_checkpoint(client, bucket):
    try:
        response = client.get_object(Bucket=bucket, Key=CHECKPOINT_KEY)
        return json.loads(response["Body"].read().decode("utf-8"))
    except client.exceptions.NoSuchKey:
        return {"year": YEAR, "next_offset": 0, "total_pairs": 0,
                "completed_pairs": 0, "status": "not_started", "batches": []}
    except Exception as exc:
        if "NoSuchKey" in str(exc) or "404" in str(exc):
            return {"year": YEAR, "next_offset": 0, "total_pairs": 0,
                    "completed_pairs": 0, "status": "not_started", "batches": []}
        raise


def save_checkpoint(client, bucket, state):
    body = json.dumps(state, indent=2).encode("utf-8")
    client.put_object(Bucket=bucket, Key=CHECKPOINT_KEY, Body=body,
                      ContentType="application/json")


def make_final_zip():
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "final" / "nagaland_2023_recovery.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(OUT.rglob("*")):
            if not path.is_file() or path == target:
                continue
            if "final" in path.relative_to(OUT).parts:
                continue
            zf.write(path, path.relative_to(OUT).as_posix())
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/recovery_candidates_2023.csv")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-batches", type=int, default=0, help="0 means finish the campaign")
    args = parser.parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be at least 1")

    client, bucket = r2_client(), bucket_name()
    # Validate credentials, endpoint and bucket access before doing any recovery work.
    client.head_bucket(Bucket=bucket)
    print(f"R2 connection verified; bucket={bucket}", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    restore(client, bucket)
    state = read_checkpoint(client, bucket)
    if state.get("status") == "completed":
        print("Campaign is already completed in R2; no further work is required.", flush=True)
        return
    draws = [item for item in read_draws(args.csv) if item[0].startswith(YEAR + "-")]
    total = len(draws)
    if total == 0:
        raise RuntimeError("No 2023 Nagaland 1PM/8PM candidates found")
    if state.get("total_pairs") not in (0, total):
        raise RuntimeError(f"Checkpoint has {state.get('total_pairs')} pairs but CSV has {total}; refusing unsafe resume")
    state["total_pairs"] = total
    offset = int(state.get("next_offset", 0))
    batch_count = 0
    state["status"] = "running"
    save_checkpoint(client, bucket, state)
    print(f"Campaign resume: offset={offset}/{total}; batch_size={args.batch_size}", flush=True)

    while offset < total:
        limit = min(args.batch_size, total - offset)
        print(f"=== BATCH offset={offset} limit={limit} ===", flush=True)
        results = archive_sources(
            args.csv, OUT, offset=offset, limit=limit,
            start_date="2023-01-01", end_date="2023-12-31"
        )
        missing = sum(1 for item in results
                      if item.get("verification_status") == "source_unavailable_or_error")
        batch_record = {
            "offset": offset, "requested": limit, "processed": len(results),
            "with_pdf": len(results) - missing, "missing": missing,
            "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        state.setdefault("batches", []).append(batch_record)
        offset += len(results)
        state["next_offset"] = offset
        state["completed_pairs"] = offset
        state["last_batch"] = batch_record
        state["status"] = "running" if offset < total else "packaging"
        # Persist PDFs, manifests and checkpoint after every batch.
        upload_tree(client, bucket)
        save_checkpoint(client, bucket, state)
        print(f"R2 checkpoint saved: {offset}/{total}; batch PDFs={batch_record['with_pdf']}; missing={missing}", flush=True)
        batch_count += 1
        if args.max_batches and batch_count >= args.max_batches:
            print("Stopped at requested max-batches; rerun workflow to resume from R2 checkpoint.", flush=True)
            return

    # Retry unresolved date/draw pairs twice, keeping every attempt in the manifest.
    manifest_path = OUT / "manifest.json"
    for retry_round in (1, 2):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
        missing_pairs = sorted({
            (item.get("date"), item.get("draw"))
            for item in manifest
            if "source_candidates_checked" in item
            and item.get("verification_status") == "source_unavailable_or_error"
        })
        if not missing_pairs:
            break
        retry_csv = OUT / f"retry_candidates_round_{retry_round}.csv"
        with retry_csv.open("w", encoding="utf-8", newline="") as handle:
            handle.write("date,draw\n")
            for draw_date, draw in missing_pairs:
                handle.write(f"{draw_date},{draw}\n")
        print(f"=== RETRY ROUND {retry_round}: {len(missing_pairs)} unresolved pairs ===", flush=True)
        time.sleep(15)
        retry_results = archive_sources(
            retry_csv, OUT, offset=0, limit=None,
            start_date="2023-01-01", end_date="2023-12-31"
        )
        retry_missing = sum(1 for item in retry_results
                            if item.get("verification_status") == "source_unavailable_or_error")
        state.setdefault("retry_rounds", []).append({
            "round": retry_round, "attempted": len(retry_results),
            "still_missing": retry_missing,
            "completed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        upload_tree(client, bucket)
        save_checkpoint(client, bucket, state)
        print(f"Retry round {retry_round} saved to R2; still missing={retry_missing}", flush=True)

    final_zip = make_final_zip()
    upload_tree(client, bucket)
    state["status"] = "completed"
    state["completed_pairs"] = total
    state["next_offset"] = total
    state["finished_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["final_zip_r2_key"] = PREFIX + final_zip.relative_to(OUT).as_posix()
    save_checkpoint(client, bucket, state)
    print(f"CAMPAIGN COMPLETE: {total} pairs processed. Final ZIP: {state['final_zip_r2_key']}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"RECOVERY CAMPAIGN FAILED: {exc}", file=sys.stderr, flush=True)
        raise

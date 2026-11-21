#!/usr/bin/env python3
"""Safely merge complete 132-number recovered draws into the existing master CSV."""
from __future__ import annotations
import argparse, csv
from collections import Counter, defaultdict
from pathlib import Path
import re

MASTER_FIELDS = ["date","draw","prize_tier","position","winning_number","source_pdf","verification_status"]
EXPECTED = {"1st":1,"Consolation":1,"2nd":10,"3rd":10,"4th":10,"5th":100}
PATTERNS = {
 "1st": re.compile(r"^[0-9]{2}[A-Z] [0-9]{5}$"),
 "Consolation": re.compile(r"^[0-9]{5}$"),
 "2nd": re.compile(r"^[0-9]{5}$"),
 "3rd": re.compile(r"^[0-9]{4}$"),
 "4th": re.compile(r"^[0-9]{4}$"),
 "5th": re.compile(r"^[0-9]{4}$"),
}

def is_complete_master(rows):
    if len(rows) != 132 or Counter(r.get("prize_tier") for r in rows) != Counter(EXPECTED):
        return False
    seen=set()
    for r in rows:
        tier=r.get("prize_tier","")
        try: pos=int(r.get("position",""))
        except ValueError: return False
        if tier not in EXPECTED or not 1 <= pos <= EXPECTED[tier] or (tier,pos) in seen:
            return False
        if not PATTERNS[tier].fullmatch((r.get("winning_number") or "").strip()):
            return False
        seen.add((tier,pos))
    if len(seen) != 132:
        return False
    first=next((r.get("winning_number","") for r in rows if r.get("prize_tier")=="1st"),"")
    cons=next((r.get("winning_number","") for r in rows if r.get("prize_tier")=="Consolation"),"")
    return bool(first and cons and first[-5:] == cons)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--master", default="data/nagaland_master_prize_numbers.csv")
    a=p.parse_args()
    grouped=defaultdict(list)
    with open(a.input,newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        required={"date","draw","prize_tier","position","winning_number"}
        if not required.issubset(reader.fieldnames or []):
            raise SystemExit(f"Parsed CSV missing columns: {sorted(required-set(reader.fieldnames or []))}")
        for raw in reader:
            draw=(raw.get("draw") or "").strip().upper()
            if draw not in {"1PM","8PM"}: continue
            source=" | ".join(x.strip() for x in [raw.get("source_reference") or raw.get("source_pdf") or "", raw.get("additional_source_url") or ""] if x and x.strip())
            grouped[(raw["date"].strip(),draw)].append({
                "date":raw["date"].strip(),"draw":draw,
                "prize_tier":raw["prize_tier"].strip(),
                "position":raw["position"].strip(),
                "winning_number":raw["winning_number"].strip(),
                "source_pdf":source,
                "verification_status":(raw.get("verification_status") or "single_archive_pdf_full_tier_extracted").strip()
            })
    valid={}
    rejected=[]
    for key,rows in grouped.items():
        counts=Counter(r["prize_tier"] for r in rows)
        seen=set(); ok=(len(rows)==132 and counts==Counter(EXPECTED))
        for r in rows:
            tier=r["prize_tier"]
            try: pos=int(r["position"])
            except ValueError: ok=False; continue
            if tier not in EXPECTED or not 1<=pos<=EXPECTED[tier] or (tier,pos) in seen:
                ok=False
            seen.add((tier,pos))
            if tier in PATTERNS and not PATTERNS[tier].fullmatch(r["winning_number"]): ok=False
            if not r["source_pdf"]: ok=False
        if ok:
            if { (t,p) for t,n in EXPECTED.items() for p in range(1,n+1) } != seen: ok=False
        if ok:
            first=next(r["winning_number"] for r in rows if r["prize_tier"]=="1st")
            cons=next(r["winning_number"] for r in rows if r["prize_tier"]=="Consolation")
            if first[-5:] != cons: ok=False
        if ok: valid[key]=rows
        else: rejected.append(key)
    if not valid:
        print(f"NO_COMPLETE_DRAWS_TO_MERGE; parsed_groups={len(grouped)} rejected={len(rejected)}")
        return
    master=Path(a.master)
    with master.open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames != MASTER_FIELDS:
            raise SystemExit(f"Unexpected master schema: {reader.fieldnames}")
        existing=list(reader)
    existing_groups=defaultdict(list)
    for r in existing:
        if r.get("draw") in {"1PM","8PM"}: existing_groups[(r.get("date"),r.get("draw"))].append(r)
    add={}
    replace={}
    for key,rows in valid.items():
        if is_complete_master(existing_groups.get(key,[])):
            # Never overwrite an already complete master draw automatically.
            continue
        if existing_groups.get(key): replace[key]=rows
        else: add[key]=rows
    changed=set(add)|set(replace)
    if not changed:
        print(f"MASTER_ALREADY_COMPLETE_FOR_PARSED_DRAWS; parsed_complete={len(valid)}")
        return
    kept=[r for r in existing if (r.get("date"),r.get("draw")) not in changed]
    new_rows=[]
    for key in sorted(changed):
        new_rows.extend({field:r[field] for field in MASTER_FIELDS} for r in (add.get(key) or replace.get(key)))
    output=kept+new_rows
    with master.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=MASTER_FIELDS);w.writeheader();w.writerows(output)
    print(f"PARSED_COMPLETE_DRAWS={len(valid)}")
    print(f"NEW_DRAW_PAIRS_ADDED={len(add)}")
    print(f"INCOMPLETE_DRAW_PAIRS_REPLACED={len(replace)}")
    print(f"ROWS_MERGED={len(new_rows)}")
    print(f"REJECTED_GROUPS={len(rejected)}")
    print(f"MASTER_TOTAL_ROWS={len(output)}")

if __name__=="__main__": main()

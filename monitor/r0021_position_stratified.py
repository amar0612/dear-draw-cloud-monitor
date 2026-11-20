#!/usr/bin/env python3
"""R002.1: position-stratified, draw-block permutation validation.

Whole draw rows are permuted, never individual winning numbers or digits.
This is an exploratory dependence test, not a prediction model.
"""
import argparse, csv, json, random, re, math
from pathlib import Path
from collections import Counter
import numpy as np

TIERS = {
    "1st_5digit": ("first", 5, 1),
    "2nd_5digit": ("second", 5, 10),
    "3rd_4digit": ("third", 4, 10),
    "4th_4digit": ("fourth", 4, 10),
    "5th_4digit": ("fifth", 4, 100),
}
SLOTS = ("1PM", "8PM")

def parse_numbers(draw, field, width, expected):
    value = draw.get(field)
    if field == "first":
        values = [re.sub(r"^\s*\d{2}[A-Za-z]\s+", "", str(value or ""))]
    elif isinstance(value, list):
        values = value
    else:
        values = re.findall(r"(?<!\d)\d{%d}(?!\d)" % width, str(value or ""))
    out = []
    for item in values:
        s = str(item).strip()
        if field == "first":
            s = re.sub(r"^\s*\d{2}[A-Za-z]\s+", "", s)
        if re.fullmatch(r"\d{%d}" % width, s):
            out.append(s)
    return out if len(out) == expected else None

def mutual_information(x, y):
    x = np.asarray(x, dtype=np.int16).ravel()
    y = np.asarray(y, dtype=np.int16).ravel()
    if x.size == 0:
        return 0.0, np.zeros((10, 10), dtype=np.int64)
    counts = np.bincount(x * 10 + y, minlength=100).reshape(10, 10)
    n = counts.sum()
    row = counts.sum(axis=1, keepdims=True)
    col = counts.sum(axis=0, keepdims=True)
    expected = row @ col
    mask = counts > 0
    mi = np.sum((counts[mask] / n) * np.log2((counts[mask] * n) / expected[mask]))
    return float(mi), counts

def bh_adjust(pvalues):
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    out = np.empty(len(p), dtype=float)
    running = 1.0
    m = len(p)
    for rank0 in range(m - 1, -1, -1):
        idx = order[rank0]
        rank = rank0 + 1
        running = min(running, p[idx] * m / rank)
        out[idx] = min(1.0, running)
    return out

def permutation_test(left, right, reps, rng, mode):
    """Rows are whole draws; columns are prize-position winners."""
    obs, matrix = mutual_information(left, right)
    # For lag-1, reconstruct the complete sequence from overlapping
    # left=t and right=t+1 matrices so every draw participates in the null.
    sequence = np.concatenate((left[:1, :], right), axis=0) if mode == "lag1" else None
    n = sequence.shape[0] if mode == "lag1" else left.shape[0]
    if n < 30 or left.size == 0:
        return obs, 1.0, matrix, "insufficient_pairs"
    exceed = 0
    idx = np.arange(n)
    for _ in range(reps):
        perm = rng.permutation(idx)
        if mode == "lag1":
            shuffled = sequence[perm, :]
            a, b = shuffled[:-1, :], shuffled[1:, :]
        else:
            a, b = left, right[perm, :]
        null_mi, _ = mutual_information(a, b)
        if null_mi >= obs - 1e-15:
            exceed += 1
    return obs, (exceed + 1) / (reps + 1), matrix, "ok"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="r0021-output")
    ap.add_argument("--permutations", type=int, default=1000)
    args = ap.parse_args()
    if args.permutations < 99:
        raise SystemExit("Use at least 99 permutations.")
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    byslot = {s: {} for s in SLOTS}
    seen = Counter()
    for d in payload.get("draws", []):
        if d.get("isSample"):
            continue
        t = str(d.get("time", "")).upper().replace(" ", "")
        slot = "1PM" if t in ("1:00PM", "1PM", "13:00") else "8PM" if t in ("8:00PM", "8PM", "20:00") else None
        date = str(d.get("date", ""))
        if slot and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            byslot[slot][date] = d
            seen[slot] += 1

    rng = np.random.default_rng(20261121)
    rows, matrices = [], []
    def run_test(label, slot_label, tier, digit_pos, left, right, mode, paired_draws):
        obs, p, mat, status = permutation_test(left, right, args.permutations, rng, mode)
        rows.append({
            "analysis": label, "slot": slot_label, "tier": tier,
            "digit_position_from_left": digit_pos + 1,
            "paired_draws": int(paired_draws),
            "digit_pairs": int(left.size if mode != "lag1" else max(0, left.shape[0]-1) * left.shape[1]),
            "mutual_information_bits": round(obs, 9),
            "permutation_p_value": round(p, 9),
            "test_status": status,
            "null_model": "whole-draw row permutation; prize-position columns and within-draw clusters preserved"
        })
        for i in range(10):
            for j in range(10):
                matrices.append({
                    "analysis": label, "slot": slot_label, "tier": tier,
                    "digit_position_from_left": digit_pos + 1,
                    "from_digit": i, "to_digit": j, "count": int(mat[i, j])
                })

    # Within-slot lag-1 tests. Each digit position is analysed separately.
    slot_arrays = {s: {} for s in SLOTS}
    for slot in SLOTS:
        for tier, (field, width, expected) in TIERS.items():
            dates, digit_rows = [], []
            for date, draw in sorted(byslot[slot].items()):
                nums = parse_numbers(draw, field, width, expected)
                if nums is None:
                    continue
                dates.append(date)
                digit_rows.append([[int(ch) for ch in number] for number in nums])
            if digit_rows:
                arr = np.asarray(digit_rows, dtype=np.int8)  # draw x prize-position x digit-position
                slot_arrays[slot][tier] = (dates, arr)
                for pos in range(width):
                    x, y = arr[:-1, :, pos], arr[1:, :, pos]
                    run_test("within_slot_lag1", slot, tier, pos, x, y, "lag1", len(dates)-1)

    # Same-date 1PM -> 8PM, and 8PM -> next available later-date 1PM.
    for label, leftslot, rightslot, next_date in [
        ("same_date_1PM_to_8PM", "1PM", "8PM", False),
        ("next_draw_8PM_to_1PM", "8PM", "1PM", True),
    ]:
        for tier, (field, width, expected) in TIERS.items():
            lmap, rmap = {}, {}
            for date, d in byslot[leftslot].items():
                nums = parse_numbers(d, field, width, expected)
                if nums is not None:
                    lmap[date] = [[int(ch) for ch in number] for number in nums]
            for date, d in byslot[rightslot].items():
                nums = parse_numbers(d, field, width, expected)
                if nums is not None:
                    rmap[date] = [[int(ch) for ch in number] for number in nums]
            pairs = []
            if not next_date:
                for date in sorted(set(lmap) & set(rmap)):
                    pairs.append((date, lmap[date], rmap[date]))
            else:
                rdates = sorted(rmap)
                for date in sorted(lmap):
                    nxt = next((x for x in rdates if x > date), None)
                    if nxt:
                        pairs.append((date, lmap[date], rmap[nxt]))
            if not pairs:
                continue
            left = np.asarray([p[1] for p in pairs], dtype=np.int8)
            right = np.asarray([p[2] for p in pairs], dtype=np.int8)
            for pos in range(width):
                run_test(label, leftslot + "->" + rightslot, tier, pos,
                         left[:, :, pos], right[:, :, pos], "paired", len(pairs))

    if not rows:
        raise SystemExit("No valid transition tests were generated; check backup schema.")
    adjusted = bh_adjust([r["permutation_p_value"] for r in rows])
    for row, q in zip(rows, adjusted):
        row["p_value_bh_all_tests"] = round(float(q), 9)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "r0021_position_tests.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (out / "r0021_position_matrices.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(matrices[0]))
        w.writeheader()
        w.writerows(matrices)
    summary = {
        "project": "R002.1",
        "title": "Position-stratified temporal dependence validation",
        "input": Path(args.input).name,
        "exportedAt": payload.get("exportedAt"),
        "slot_draw_records_detected": dict(seen),
        "permutation_replicates": args.permutations,
        "tests": len(rows),
        "valid_tests": sum(r["test_status"] == "ok" for r in rows),
        "significant_bh_005": sum(r["p_value_bh_all_tests"] < 0.05 and r["test_status"] == "ok" for r in rows),
        "method": "Digit positions tested separately. Within-slot lag-1 null permutes whole draw rows; cross-slot null permutes whole destination draw rows. Prize-position columns remain intact, preserving within-draw clustering and positional composition.",
        "limitations": [
            "Exploratory association tests, not prediction or causality.",
            "Whole-draw permutation tests exchangeability; trends, seasonality, regime changes, and missing-date patterns may violate this assumption.",
            "A significant result requires chronological holdout validation and robustness checks.",
            "Permutation p-values have finite resolution 1/(replicates+1).",
            "No candidate-number ranking is produced."
        ]
    }
    (out / "r0021_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()

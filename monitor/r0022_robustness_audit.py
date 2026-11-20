#!/usr/bin/env python3
"""R002.2: data-order audit and draw-level robustness tests.

This version deliberately avoids pairing the 100 fifth-prize numbers by list
index as if they were independent observations. It audits list ordering and
tests per-draw digit-composition vectors instead. It is exploratory, not predictive.
"""
import argparse, csv, json, math, random, re
from collections import Counter
from pathlib import Path
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

def mi_from_pairs(a, b):
    x = np.asarray(a, dtype=np.int16).ravel()
    y = np.asarray(b, dtype=np.int16).ravel()
    if x.size == 0: return 0.0
    c = np.bincount(x * 10 + y, minlength=100).reshape(10,10)
    n = c.sum()
    r, col = c.sum(axis=1, keepdims=True), c.sum(axis=0, keepdims=True)
    e = r @ col
    m = c > 0
    return float(np.sum((c[m]/n) * np.log2((c[m]*n)/e[m])))

def bh_adjust(values):
    p=np.asarray(values,dtype=float); order=np.argsort(p); out=np.empty(len(p))
    running=1.0; m=len(p)
    for k in range(m-1,-1,-1):
        idx=order[k]; running=min(running,p[idx]*m/(k+1)); out[idx]=min(1.0,running)
    return out

def centered_hist(numbers, pos):
    h=np.zeros(10,dtype=float)
    for s in numbers: h[int(s[pos])] += 1
    return h / max(1,len(numbers))

def score_adjacent(g, order):
    n=len(order)
    if n<2:return 0.0
    idx=np.asarray(order,dtype=int)
    return float(np.mean(g[idx[:-1],idx[1:]]))

def block_permutation_p(x, reps, rng, block):
    n=len(x)
    if n < max(30,block*3): return None, "insufficient_draws"
    g=x @ x.T
    order=np.arange(n)
    obs=score_adjacent(g,order)
    blocks=[np.arange(i,min(i+block,n)) for i in range(0,n,block)]
    exceed=0
    for _ in range(reps):
        perm=rng.permutation(len(blocks))
        idx=np.concatenate([blocks[k] for k in perm])
        if score_adjacent(g,idx) >= obs-1e-15: exceed+=1
    return (exceed+1)/(reps+1), "ok"

def circular_shift_p(left,right,reps,rng):
    n=len(left)
    if n<30:return None,"insufficient_pairs"
    g=left @ right.T
    obs=float(np.mean(g[np.arange(n),np.arange(n)]))
    shifts=rng.integers(1,n,size=reps)
    exceed=0
    ix=np.arange(n)
    for k in shifts:
        if float(np.mean(g[ix,(ix+k)%n])) >= obs-1e-15: exceed+=1
    return (exceed+1)/(reps+1),"ok"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--outdir",default="r0022-output")
    ap.add_argument("--permutations",type=int,default=10000)
    ap.add_argument("--block-sizes",default="5,10,20")
    args=ap.parse_args()
    if args.permutations<999: raise SystemExit("Use at least 999 permutations.")
    blocks=[int(x) for x in args.block_sizes.split(",") if x.strip()]
    if not blocks or any(x<2 for x in blocks): raise SystemExit("Invalid block sizes.")
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    byslot={s:{} for s in SLOTS}; record_counts=Counter(); malformed=Counter()
    for d in payload.get("draws",[]):
        if d.get("isSample"): continue
        t=str(d.get("time","")).upper().replace(" ","")
        slot="1PM" if t in ("1:00PM","1PM","13:00") else "8PM" if t in ("8:00PM","8PM","20:00") else None
        date=str(d.get("date",""))
        if slot and re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
            byslot[slot][date]=d; record_counts[slot]+=1

    integrity=[]; index_rows=[]; tests=[]
    # Cache parsed records; preserve source list order for order diagnostics.
    parsed={s:{} for s in SLOTS}
    for slot in SLOTS:
      for tier,(field,width,expected) in TIERS.items():
        for date,d in sorted(byslot[slot].items()):
            nums=parse_numbers(d,field,width,expected)
            if nums is None:
                malformed[(slot,tier)]+=1
                continue
            parsed[slot].setdefault(tier,{})[date]=nums
            vals=[int(v) for v in nums]
            unique=len(set(nums))
            asc=all(vals[i]<=vals[i+1] for i in range(len(vals)-1))
            desc=all(vals[i]>=vals[i+1] for i in range(len(vals)-1))
            integrity.append({"slot":slot,"tier":tier,"date":date,"number_count":len(nums),
                "unique_count":unique,"duplicate_count":len(nums)-unique,
                "ascending_non_decreasing":int(asc),"descending_non_increasing":int(desc),
                "first_number":nums[0],"last_number":nums[-1]})
            if tier=="5th_4digit":
                n=len(nums)
                for dec in range(10):
                    lo=dec*n//10; hi=(dec+1)*n//10
                    c=Counter(v[0] for v in nums[lo:hi])
                    index_rows.append({"slot":slot,"date":date,"winner_index_decile":dec+1,
                        "index_start":lo+1,"index_end":hi,
                        **{f"first_digit_{k}":c.get(str(k),0) for k in range(10)}})

    # Draw-level histograms: one vector per draw and digit position.
    vectors={s:{} for s in SLOTS}
    for slot in SLOTS:
      for tier,(field,width,expected) in TIERS.items():
        rec=parsed[slot].get(tier,{})
        dates=sorted(rec)
        if len(dates)<2: continue
        raw=np.asarray([[centered_hist(rec[d],p) for p in range(width)] for d in dates],dtype=float)
        # Center by tier/slot/position marginal, removing global digit prevalence.
        raw=raw-raw.mean(axis=0,keepdims=True)
        vectors[slot][tier]=(dates,raw)
        for pos in range(width):
            x=raw[:,pos,:]
            for block in blocks:
                p,status=block_permutation_p(x,args.permutations,np.random.default_rng(20261120+pos+block),block)
                tests.append({"analysis":"within_slot_draw_composition_lag1","slot":slot,"tier":tier,
                    "digit_position_from_left":pos+1,"paired_draws":len(dates)-1,
                    "block_size_draws":block,"permutations":args.permutations,
                    "observed_mean_centered_dot":round(float(np.mean(np.sum(x[:-1]*x[1:],axis=1))),10),
                    "permutation_p_value":None if p is None else round(float(p),10),"test_status":status,
                    "null_model":f"permute whole chronological blocks of {block} draws; within-block order retained"})
    # Same-date cross-slot tests; destination sequence is circularly shifted by whole draws.
    for tier,(_,width,_) in TIERS.items():
        l=vectors["1PM"].get(tier); r=vectors["8PM"].get(tier)
        if not l or not r: continue
        lm=dict(zip(l[0],l[1])); rm=dict(zip(r[0],r[1]))
        dates=sorted(set(lm)&set(rm))
        if len(dates)<30: continue
        for pos in range(width):
            a=np.asarray([lm[d][pos] for d in dates]); b=np.asarray([rm[d][pos] for d in dates])
            p,status=circular_shift_p(a,b,args.permutations,np.random.default_rng(881+pos+width))
            obs=float(np.mean(np.sum(a*b,axis=1)))
            tests.append({"analysis":"same_date_cross_slot_draw_composition","slot":"1PM->8PM","tier":tier,
                "digit_position_from_left":pos+1,"paired_draws":len(dates)-1,
                "block_size_draws":"circular_shift","permutations":args.permutations,
                "observed_mean_centered_dot":round(obs,10),
                "permutation_p_value":None if p is None else round(float(p),10),"test_status":status,
                "null_model":"circularly shift 8PM whole-draw composition vectors relative to 1PM"})
    valid=[i for i,r in enumerate(tests) if r["permutation_p_value"] is not None]
    q=bh_adjust([tests[i]["permutation_p_value"] for i in valid]) if valid else []
    for i,val in zip(valid,q): tests[i]["p_value_bh_all_tests"]=round(float(val),10)
    for i in range(len(tests)):
        tests[i].setdefault("p_value_bh_all_tests",None)

    # Summarise list-order artefacts by slot/tier.
    order_summary=[]
    for slot in SLOTS:
      for tier in TIERS:
        rr=[r for r in integrity if r["slot"]==slot and r["tier"]==tier]
        if not rr: continue
        order_summary.append({"slot":slot,"tier":tier,"valid_draws":len(rr),
          "draws_with_duplicates":sum(r["duplicate_count"]>0 for r in rr),
          "mean_duplicates_per_draw":round(float(np.mean([r["duplicate_count"] for r in rr])),4),
          "ascending_sorted_draws":sum(r["ascending_non_decreasing"] for r in rr),
          "descending_sorted_draws":sum(r["descending_non_increasing"] for r in rr),
          "malformed_draws":int(malformed[(slot,tier)])})
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    def write(name,rows):
        if not rows:return
        with (out/name).open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write("r0022_draw_integrity.csv",integrity)
    write("r0022_fifth_prize_index_profile.csv",index_rows)
    write("r0022_robustness_tests.csv",tests)
    write("r0022_order_summary.csv",order_summary)
    summary={"project":"R002.2","title":"Data-order audit and draw-level robustness tests",
      "input":Path(args.input).name,"exportedAt":payload.get("exportedAt"),
      "slot_draw_records_detected":dict(record_counts),"malformed_draw_groups":{f"{k[0]}_{k[1]}":v for k,v in malformed.items()},
      "permutations":args.permutations,"block_sizes":blocks,"robustness_tests":len(tests),
      "valid_tests":len(valid),"bh_significant_005":sum(tests[i]["p_value_bh_all_tests"]<.05 for i in valid),
      "method":"Audit source winner-list order, duplicates and sortedness. Robustness statistics use one 10-bin digit-composition vector per draw and digit position, centered by the slot/tier marginal. Within-slot null permutes whole chronological blocks; cross-slot null circularly shifts whole destination draws.",
      "limitations":["Exploratory only; no predictions or causal claims.","Block permutation assumes approximate exchangeability of blocks; trends and regime changes may remain.","Circular shifts test relative alignment but not all possible temporal confounding.","Winner-list ordering may be a source/reporting convention, not draw-generation order.","A significant result requires untouched chronological holdout testing and independent source verification."]}
    (out/"r0022_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()

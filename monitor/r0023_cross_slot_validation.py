#!/usr/bin/env python3
"""R002.3: cross-slot association stress test. Exploratory, never a lottery predictor."""
import argparse, csv, json, re
from pathlib import Path
from collections import Counter
import numpy as np

TIERS = {
    "1st_5digit": ("first", 5, 1), "2nd_5digit": ("second", 5, 10),
    "3rd_4digit": ("third", 4, 10), "4th_4digit": ("fourth", 4, 10),
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
    out=[]
    for item in values:
        s=str(item).strip()
        if field=="first": s=re.sub(r"^\s*\d{2}[A-Za-z]\s+","",s)
        if re.fullmatch(r"\d{%d}" % width,s): out.append(s)
    return out if len(out)==expected else None

def bh(p):
    p=np.asarray(p,float); order=np.argsort(p); out=np.ones(len(p)); run=1.0; m=len(p)
    for k in range(m-1,-1,-1):
        i=order[k]; run=min(run,p[i]*m/(k+1)); out[i]=min(1.0,run)
    return out

def hist(nums,pos):
    h=np.zeros(10,float)
    for n in nums: h[int(n[pos])]+=1
    return h/max(1,len(nums))

def corr_flat(a,b):
    x=np.asarray(a,float).ravel(); y=np.asarray(b,float).ravel()
    if len(x)<30 or np.std(x)==0 or np.std(y)==0: return 0.0
    return float(np.corrcoef(x,y)[0,1])

def detrend(x):
    t=np.linspace(-1,1,len(x))
    design=np.column_stack([np.ones(len(t)),t])
    return x-design@np.linalg.lstsq(design,x,rcond=None)[0]

def circular_p(a,b,reps,rng):
    obs=corr_flat(a,b); n=len(a); exceed=0
    for k in rng.integers(1,n,size=reps):
        if corr_flat(a,b[np.roll(np.arange(n),int(k))]) >= obs-1e-15: exceed+=1
    return obs,(exceed+1)/(reps+1)

def shuffle_p(a,b,reps,rng):
    obs=corr_flat(a,b); exceed=0; idx=np.arange(len(b))
    for _ in range(reps):
        if corr_flat(a,b[rng.permutation(idx)]) >= obs-1e-15: exceed+=1
    return obs,(exceed+1)/(reps+1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--outdir",default="r0023-output")
    ap.add_argument("--permutations",type=int,default=10000); ap.add_argument("--holdout-fraction",type=float,default=.30)
    args=ap.parse_args()
    if args.permutations<999: raise SystemExit("Use at least 999 permutations.")
    if not .2<=args.holdout_fraction<=.5: raise SystemExit("Holdout fraction must be 0.20–0.50.")
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    byslot={s:{} for s in SLOTS}; detected=Counter()
    for d in payload.get("draws",[]):
        if d.get("isSample"): continue
        t=str(d.get("time","")).upper().replace(" ","")
        slot="1PM" if t in ("1:00PM","1PM","13:00") else "8PM" if t in ("8:00PM","8PM","20:00") else None
        date=str(d.get("date",""))
        if slot and re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
            byslot[slot][date]=d; detected[slot]+=1
    parsed={s:{} for s in SLOTS}; malformed=Counter()
    for slot in SLOTS:
        for tier,(field,width,expected) in TIERS.items():
            for date,d in sorted(byslot[slot].items()):
                nums=parse_numbers(d,field,width,expected)
                if nums is None: malformed[(slot,tier)]+=1
                else: parsed[slot].setdefault(tier,{})[date]=nums

    rows=[]; primary_indices=[]
    for ti,(tier,(_,width,_)) in enumerate(TIERS.items()):
        lm=parsed["1PM"].get(tier,{}); rm=parsed["8PM"].get(tier,{})
        dates=sorted(set(lm)&set(rm))
        if len(dates)<60: continue
        for pos in range(width):
            a=np.asarray([hist(lm[d],pos) for d in dates]); b=np.asarray([hist(rm[d],pos) for d in dates])
            # Remove each slot/tier/position's marginal digit prevalence.
            a=a-a.mean(axis=0); b=b-b.mean(axis=0)
            n=len(dates); cut=int(n*(1-args.holdout_fraction))
            rng=np.random.default_rng(2300+ti*31+pos)
            obs,pc=circular_p(a,b,args.permutations,rng)
            _,ps=shuffle_p(a,b,args.permutations,rng)
            ad,bd=detrend(a),detrend(b)
            od,pd=circular_p(ad,bd,args.permutations,rng)
            # Untouched later chronological segment: no model fit or tuning on it.
            oh,ph=circular_p(a[cut:],b[cut:],args.permutations,rng) if n-cut>=30 else (0.0,1.0)
            # Sensitivity: remove each calendar month in turn, preserving remaining order.
            month_keys=[d[:7] for d in dates]
            leave_month=[corr_flat(a[[i for i,m in enumerate(month_keys) if m!=month]],
                                    b[[i for i,m in enumerate(month_keys) if m!=month]])
                         for month in sorted(set(month_keys)) if sum(m!=month for m in month_keys)>=30]
            row={"tier":tier,"digit_position_from_left":pos+1,"paired_dates":n,"holdout_dates":n-cut,
                 "full_sample_centered_correlation":round(obs,8),"full_sample_circular_shift_p":round(pc,8),
                 "full_sample_shuffled_date_p":round(ps,8),"linear_detrended_correlation":round(od,8),
                 "linear_detrended_circular_shift_p":round(pd,8),
                 "chronological_holdout_correlation":round(oh,8),"chronological_holdout_circular_shift_p":round(ph,8),
                 "leave_one_month_out_min_correlation":round(min(leave_month),8) if leave_month else None,
                 "leave_one_month_out_max_correlation":round(max(leave_month),8) if leave_month else None,
                 "leave_one_month_out_positive_fraction":round(float(np.mean(np.asarray(leave_month)>0)),4) if leave_month else None}
            rows.append(row); primary_indices.append(len(rows)-1)
    # BH adjustment is applied separately to each inferential family.
    for pcol,qcol in [("full_sample_circular_shift_p","full_sample_circular_shift_bh"),
                      ("full_sample_shuffled_date_p","full_sample_shuffled_date_bh"),
                      ("linear_detrended_circular_shift_p","linear_detrended_circular_shift_bh"),
                      ("chronological_holdout_circular_shift_p","chronological_holdout_circular_shift_bh")]:
        q=bh([r[pcol] for r in rows]) if rows else []
        for r,v in zip(rows,q): r[qcol]=round(float(v),8)
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    if rows:
        with (out/"r0023_cross_slot_validation.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={"project":"R002.3","title":"Cross-slot association stress test and chronological holdout",
      "input":Path(args.input).name,"exportedAt":payload.get("exportedAt"),
      "slot_draw_records_detected":dict(detected),
      "paired_tier_position_tests":len(rows),"permutations_per_test":args.permutations,
      "holdout_fraction":args.holdout_fraction,"chronological_split":"earliest 70% discovery / latest 30% holdout by default",
      "malformed_draw_groups":{f"{k[0]}_{k[1]}":v for k,v in malformed.items()},
      "method":"Same-date 1PM/8PM per-draw digit-composition vectors; subtract slot/tier/position marginal; test raw alignment against circular-shift and shuffled-date nulls; remove linear chronological trend and retest; assess latest chronological holdout; leave one calendar month out for sensitivity. BH correction is separate within each p-value family.",
      "limitations":["Exploratory association tests only; no causal interpretation or lottery prediction.","Circular-shift null assumes approximate stationarity; shuffled-date null ignores serial structure and is a diagnostic, not a replacement null.","Linear detrending removes only a simple linear trend; nonlinear seasonality or source/regime changes may remain.","Holdout is a validation check, not proof of a stable mechanism; repeated future analyses can contaminate it.","Digit-composition correlation is not an exact-number forecasting method.","Historical data integrity and source provenance remain relevant."],
      "decision_rule":"Do not promote a candidate signal unless the direction is stable, adjusted holdout evidence is credible, detrended and null-model checks agree, and a later untouched period independently replicates it."}
    (out/"r0023_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()

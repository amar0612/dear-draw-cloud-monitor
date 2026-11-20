#!/usr/bin/env python3
"""R002.4: preregistered prospective validation using only post-cutoff draws."""
import argparse, csv, json, re
from pathlib import Path
from collections import Counter
import numpy as np

CUTOFF = "2026-11-20"
HYPOTHESES = [
    ("3rd_4digit", 1), ("4th_4digit", 4),
    ("5th_4digit", 1), ("5th_4digit", 2),
]
TIERS = {
    "3rd_4digit": ("third", 4, 10),
    "4th_4digit": ("fourth", 4, 10),
    "5th_4digit": ("fifth", 4, 100),
}

def parse_numbers(draw, field, width, expected):
    value=draw.get(field)
    if isinstance(value,list): values=value
    else: values=re.findall(r"(?<!\d)\d{%d}(?!\d)" % width,str(value or ""))
    out=[]
    for item in values:
        s=str(item).strip()
        if re.fullmatch(r"\d{%d}" % width,s): out.append(s)
    return out if len(out)==expected else None

def hist(nums,pos):
    h=np.zeros(10,float)
    for n in nums: h[int(n[pos])]+=1
    return h/max(1,len(nums))

def corr(a,b):
    x=np.asarray(a,float).ravel(); y=np.asarray(b,float).ravel()
    if len(x)<30 or np.std(x)==0 or np.std(y)==0: return 0.0
    return float(np.corrcoef(x,y)[0,1])

def circular_one_sided(a,b,reps,rng):
    obs=corr(a,b); n=len(a); exceed=0
    for k in rng.integers(1,n,size=reps):
        if corr(a,b[np.roll(np.arange(n),int(k))]) >= obs-1e-15: exceed+=1
    return obs,(exceed+1)/(reps+1)

def bh(values):
    p=np.asarray(values,float); order=np.argsort(p); out=np.ones(len(p)); run=1.0; m=len(p)
    for k in range(m-1,-1,-1):
        i=order[k]; run=min(run,p[i]*m/(k+1)); out[i]=min(1.0,run)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--outdir",default="r0024-output")
    ap.add_argument("--permutations",type=int,default=50000)
    ap.add_argument("--minimum-paired-dates",type=int,default=60)
    args=ap.parse_args()
    if args.permutations<9999: raise SystemExit("Use at least 9999 permutations for prospective validation.")
    if args.minimum_paired_dates<30: raise SystemExit("Minimum paired dates must be at least 30.")
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    records={s:{} for s in ("1PM","8PM")}; seen=Counter(); malformed=Counter()
    for d in payload.get("draws",[]):
        if d.get("isSample"): continue
        t=str(d.get("time","")).upper().replace(" ","")
        slot="1PM" if t in ("1:00PM","1PM","13:00") else "8PM" if t in ("8:00PM","8PM","20:00") else None
        date=str(d.get("date",""))
        if slot and re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):
            records[slot][date]=d; seen[slot]+=1
    rows=[]
    for tier,pos in HYPOTHESES:
        field,width,expected=TIERS[tier]
        historical={s:{} for s in records}; future={s:{} for s in records}
        for slot in records:
            for date,d in records[slot].items():
                nums=parse_numbers(d,field,width,expected)
                if nums is None:
                    malformed[(slot,tier)]+=1; continue
                target=historical if date<=CUTOFF else future
                target[slot][date]=nums
        # Baseline marginals are frozen from pre-cutoff records only.
        base={}
        for slot in records:
            vals=[hist(v,pos) for v in historical[slot].values()]
            if not vals: raise SystemExit("Missing pre-cutoff baseline for "+slot+" "+tier)
            base[slot]=np.mean(vals,axis=0)
        dates=sorted(set(future["1PM"]) & set(future["8PM"]))
        n=len(dates)
        if n<args.minimum_paired_dates:
            raise SystemExit("Only "+str(n)+" paired post-cutoff dates for "+tier+
                "; need "+str(args.minimum_paired_dates)+". No historical fallback is allowed.")
        a=np.asarray([hist(future["1PM"][d],pos)-base["1PM"] for d in dates])
        b=np.asarray([hist(future["8PM"][d],pos)-base["8PM"] for d in dates])
        rng=np.random.default_rng(2400+pos+len(tier))
        observed,p=circular_one_sided(a,b,args.permutations,rng)
        rows.append({"tier":tier,"digit_position_from_left":pos,"cutoff_inclusive":CUTOFF,
            "first_future_date":dates[0],"last_future_date":dates[-1],"paired_future_dates":n,
            "observed_correlation":round(observed,9),"one_sided_circular_shift_p":round(p,9),
            "baseline":"slot-specific digit-composition means estimated only from dates on/before cutoff",
            "status":"prospective_test"})
    q=bh([r["one_sided_circular_shift_p"] for r in rows])
    for r,v in zip(rows,q): r["bh_adjusted_p_four_preregistered_tests"]=round(float(v),9)
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    with (out/"r0024_prospective_validation.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={"project":"R002.4","title":"Preregistered prospective cross-slot validation",
      "cutoff_inclusive":CUTOFF,"historical_records_detected":dict(seen),
      "post_cutoff_paired_dates":min(r["paired_future_dates"] for r in rows),
      "preregistered_hypotheses":[{"tier":t,"digit_position_from_left":p} for t,p in HYPOTHESES],
      "permutations_per_test":args.permutations,"multiple_testing":"BH across exactly four preregistered primary hypotheses",
      "method":"For each frozen tier-position hypothesis, estimate each slot's digit-composition baseline using only records dated on/before cutoff. On paired post-cutoff dates only, correlate centered 1PM and 8PM draw-composition vectors. One-sided circular-shift null tests positive alignment. No historical dates can enter the evaluation period.",
      "limitations":["Prospective association test only; it does not predict exact winning numbers or establish causality.","Circular-shift inference assumes approximate stationarity within the future evaluation period.","The four hypotheses were selected using historical data; this test evaluates only those frozen hypotheses and is not a fresh discovery search.","Source provenance, missing dates, draw rules, and data integrity must be independently checked.","If fewer than the configured minimum post-cutoff paired dates exist, the workflow stops without substituting historical data."]}
    (out/"r0024_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()

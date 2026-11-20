#!/usr/bin/env python3
"""R003: Weighted Carry Bridge — exploratory transition analysis.

Tests whether digit/jodi composition in one draw is associated with the next
draw's composition beyond each series' marginal frequency. This is descriptive
research, not a lottery predictor. Draws are the sampling unit.
"""
import argparse, csv, json, re
from pathlib import Path
from collections import Counter
import numpy as np

SLOTS=("1PM","8PM")
TIERS={
 "1st_5digit":("first",5,1),
 "2nd_5digit":("second",5,10),
 "3rd_4digit":("third",4,10),
 "4th_4digit":("fourth",4,10),
 "5th_4digit":("fifth",4,100),
}

def parse_numbers(draw,field,width,expected):
    value=draw.get(field)
    if field=="first":
        values=[re.sub(r"^\\s*\\d{2}[A-Za-z]\\s+","",str(value or ""))]
    elif isinstance(value,list):
        values=value
    else:
        values=re.findall(r"(?<!\\d)\\d{%d}(?!\\d)"%width,str(value or ""))
    out=[]
    for item in values:
        s=str(item).strip()
        if field=="first": s=re.sub(r"^\\s*\\d{2}[A-Za-z]\\s+","",s)
        if re.fullmatch(r"\\d{%d}"%width,s): out.append(s)
    return out if len(out)==expected else None

def slot_of(d):
    t=str(d.get("time","")).upper().replace(" ","")
    return "1PM" if t in ("1:00PM","1PM","13:00") else "8PM" if t in ("8:00PM","8PM","20:00") else None

def digit_vector(nums,pos):
    v=np.zeros(10,float)
    for n in nums: v[int(n[pos])]+=1
    return v/max(1,len(nums))

def jodi_vector(nums,where="last"):
    v=np.zeros(100,float)
    for n in nums:
        pair=n[-2:] if where=="last" else n[:2]
        v[int(pair)]+=1
    return v/max(1,len(nums))

def corr(a,b):
    x=np.asarray(a,float).ravel(); y=np.asarray(b,float).ravel()
    if x.size<2 or np.std(x)==0 or np.std(y)==0:return 0.0
    return float(np.corrcoef(x,y)[0,1])

def circular_test(a,b,reps,seed):
    """One-sided positive alignment; shift whole destination draws."""
    n=len(a)
    if n<30:return None,None,"insufficient_pairs"
    obs=float(np.mean(np.sum(a*b,axis=1)))
    rng=np.random.default_rng(seed)
    exceed=0
    for k in rng.integers(1,n,size=reps):
        stat=float(np.mean(np.sum(a*b[np.roll(np.arange(n),int(k))],axis=1)))
        if stat>=obs-1e-15:exceed+=1
    return obs,(exceed+1)/(reps+1),"ok"

def bh(pvals):
    p=np.asarray(pvals,float); order=np.argsort(p); q=np.ones(len(p)); run=1.0; m=len(p)
    for k in range(m-1,-1,-1):
        i=order[k]; run=min(run,p[i]*m/(k+1)); q[i]=min(1.0,run)
    return q

def analyze_pair(label,dates,left,right,reps,seed):
    n=len(dates)
    if n<60:return None
    cut=int(n*.70)
    rows=[]
    # Holdout is later 30%; evaluate with the same fixed representation.
    for part,ix in (("full",np.arange(n)),("chronological_holdout",np.arange(cut,n))):
        if len(ix)<30: continue
        a=left[ix].copy(); b=right[ix].copy()
        # Center using discovery-period marginals only; do not fit on holdout.
        mu_a=left[:cut].mean(axis=0); mu_b=right[:cut].mean(axis=0)
        a-=mu_a; b-=mu_b
        obs,p,status=circular_test(a,b,reps,seed+(0 if part=="full" else 1))
        rows.append({"series":label,"evaluation":part,"paired_transitions":len(ix),
          "first_source_date":dates[int(ix[0])],"last_destination_date":dates[int(ix[-1])],
          "observed_centered_dot":round(obs,10) if obs is not None else None,
          "circular_shift_p_one_sided":round(p,10) if p is not None else None,
          "status":status})
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--outdir",default="r003-output")
    ap.add_argument("--permutations",type=int,default=10000)
    args=ap.parse_args()
    if args.permutations<999:raise SystemExit("Use at least 999 permutations.")
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    records={s:{} for s in SLOTS}
    for d in payload.get("draws",[]):
        if d.get("isSample"):continue
        slot=slot_of(d); date=str(d.get("date",""))
        if slot and re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}",date):
            records[slot][date]=d

    vectors={s:{} for s in SLOTS}; quality=[]
    for slot in SLOTS:
      for tier,(field,width,expected) in TIERS.items():
        valid={}
        for date,d in sorted(records[slot].items()):
            nums=parse_numbers(d,field,width,expected)
            if nums is None:
                quality.append({"slot":slot,"tier":tier,"date":date,"status":"incomplete_or_malformed"})
                continue
            valid[date]=nums
        vectors[slot][tier]=valid

    rows=[]
    # Within-slot consecutive calendar observations: adjacent valid draw dates,
    # with missing dates explicitly counted and reported.
    for slot in SLOTS:
      for tier,(field,width,expected) in TIERS.items():
        valid=vectors[slot][tier]; dates=sorted(valid)
        if len(dates)<61:continue
        src=dates[:-1]; dst=dates[1:]
        gaps=[(a,b) for a,b in zip(src,dst) if (np.datetime64(b)-np.datetime64(a)).astype(int)>1]
        for pos in range(width):
            a=np.asarray([digit_vector(valid[d],pos) for d in src])
            b=np.asarray([digit_vector(valid[d],pos) for d in dst])
            result=analyze_pair(f"within_slot_lag1|{slot}|{tier}|digit_position_{pos+1}",dst,a,b,args.permutations,3100+pos+width)
            if result:rows.extend(result)
        for where in ("first","last"):
            a=np.asarray([jodi_vector(valid[d],where) for d in src])
            b=np.asarray([jodi_vector(valid[d],where) for d in dst])
            result=analyze_pair(f"within_slot_lag1|{slot}|{tier}|{where}_jodi",dst,a,b,args.permutations,3200+width+(0 if where=="first" else 1))
            if result:rows.extend(result)
        for r in rows:
            if r["series"].startswith(f"within_slot_lag1|{slot}|{tier}|"):
                r["nonconsecutive_date_gaps_in_series"]=len(gaps)

    # Same-date 1PM -> 8PM: cross-slot bridge, evaluated separately.
    for tier,(field,width,expected) in TIERS.items():
        l=vectors["1PM"][tier]; r=vectors["8PM"][tier]
        dates=sorted(set(l)&set(r))
        if len(dates)<60:continue
        for pos in range(width):
            a=np.asarray([digit_vector(l[d],pos) for d in dates])
            b=np.asarray([digit_vector(r[d],pos) for d in dates])
            result=analyze_pair(f"same_date_1PM_to_8PM|{tier}|digit_position_{pos+1}",dates,a,b,args.permutations,4100+pos+width)
            if result:rows.extend(result)
        for where in ("first","last"):
            a=np.asarray([jodi_vector(l[d],where) for d in dates])
            b=np.asarray([jodi_vector(r[d],where) for d in dates])
            result=analyze_pair(f"same_date_1PM_to_8PM|{tier}|{where}_jodi",dates,a,b,args.permutations,4200+width+(0 if where=="first" else 1))
            if result:rows.extend(result)

    # Multiple-testing correction separately for full and holdout rows,
    # across all tier/position/jodi series in that family.
    for part in ("full","chronological_holdout"):
        ix=[i for i,r in enumerate(rows) if r["evaluation"]==part and r["circular_shift_p_one_sided"] is not None]
        q=bh([rows[i]["circular_shift_p_one_sided"] for i in ix]) if ix else []
        for i,v in zip(ix,q):rows[i]["bh_adjusted_p_within_"+part+"_family"]=round(float(v),10)
    for r in rows:
        r.setdefault("bh_adjusted_p_within_"+r["evaluation"]+"_family",None)

    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    def write(name,data):
        if not data:return
        with (out/name).open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    write("r003_weighted_carry_bridge_tests.csv",rows)
    write("r003_data_quality.csv",quality)
    summary={
      "project":"R003","title":"Weighted Carry Bridge Theory — exploratory transition analysis",
      "input":Path(args.input).name,"exportedAt":payload.get("exportedAt"),
      "slot_records_detected":{s:len(records[s]) for s in SLOTS},
      "test_rows":len(rows),"permutations_per_test":args.permutations,
      "chronological_split":"first 70% discovery/reference; latest 30% chronological holdout",
      "representations":["per-draw digit-frequency vectors by tier and position","first-two-digit and last-two-digit jodi-frequency vectors"],
      "transitions":["within-slot adjacent valid draw records","same-date 1PM to 8PM"],
      "null":"circular shift of whole destination-draw vectors; one-sided positive alignment; BH separately within full and holdout families",
      "limitations":[
       "Exploratory association only; no exact-number predictions or causal claims.",
       "A positive composition association does not mean a specific digit or jodi is more likely to win.",
       "Circular-shift inference assumes approximate stationarity; source changes, missing dates and regime shifts can invalidate it.",
       "The holdout is not untouched if analysts repeatedly inspect it; freeze this report before any follow-up tuning.",
       "Jodi-frequency vectors are sparse and high-dimensional; interpret them cautiously.",
       "All source records still require provenance and completeness checks."
      ]}
    (out/"r003_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()

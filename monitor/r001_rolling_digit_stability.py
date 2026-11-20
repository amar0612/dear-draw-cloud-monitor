#!/usr/bin/env python3
"""R001 Phase 3: rolling-window digit stability for Nagaland Dear draws.

Input is the app's v2.8 full JSON backup. Consolation is excluded because it
duplicates the first-prize suffix. Draws are the resampling unit (not digits).
No candidate numbers or predictive claims are produced.
"""
import argparse, csv, json, math, random, re
from collections import Counter
from pathlib import Path

WINDOWS = (30, 60, 90, 180, "FULL")
TIERS = {
    "1st_5digit": ("first", 5),
    "2nd_5digit": ("second", 5),
    "3rd_4digit": ("third", 4),
    "4th_4digit": ("fourth", 4),
    "5th_4digit": ("fifth", 4),
}

def numbers_for(draw, field, width):
    value = draw.get(field)
    if field == "first":
        value = re.sub(r"^\s*\d{2}[A-Za-z]\s+", "", str(value or ""))
        values = [value]
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
    expected = 1 if field == "first" else {"second":10,"third":10,"fourth":10,"fifth":100}[field]
    return out if len(out) == expected else []

def gamma_q(a, x):
    if x < 0 or a <= 0: return float("nan")
    if x == 0: return 1.0
    gln = math.lgamma(a)
    if x < a + 1:
        ap=a; summ=1.0/a; delta=summ
        for _ in range(10000):
            ap += 1; delta *= x/ap; summ += delta
            if abs(delta) < abs(summ)*1e-14: break
        p=summ*math.exp(-x+a*math.log(x)-gln)
        return max(0.0,min(1.0,1.0-p))
    b=x+1-a; c=1e300; d=1.0/b; h=d
    for i in range(1,10000):
        an=-i*(i-a); b += 2; d=an*d+b
        if abs(d)<1e-300: d=1e-300
        c=b+an/c
        if abs(c)<1e-300: c=1e-300
        d=1/d; delta=d*c; h*=delta
        if abs(delta-1)<1e-14: break
    return max(0.0,min(1.0,math.exp(-x+a*math.log(x)-gln)*h))

def bh_adjust(pairs):
    ordered=sorted(pairs,key=lambda z:z[1]); m=len(ordered); out={}
    running=1.0
    for rank in range(m,0,-1):
        key,p=ordered[rank-1]
        running=min(running,p*m/rank)
        out[key]=min(1.0,running)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--outdir",default="r001-output")
    ap.add_argument("--bootstrap",type=int,default=1000)
    args=ap.parse_args()
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    raw=payload.get("draws",[])
    draws=[]
    for d in raw:
        if d.get("isSample"): continue
        time=str(d.get("time","")).upper().replace(" ","")
        slot="1PM" if time in ("1:00PM","1PM","13:00") else "8PM" if time in ("8:00PM","8PM","20:00") else None
        if not slot: continue
        date=str(d.get("date",""))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date): continue
        draws.append((date,slot,d))
    draws.sort(key=lambda x:(x[0],x[1]))
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    detail=[]; tests=[]; rng=random.Random(20261120)
    for slot in ("1PM","8PM"):
      slot_draws=[x for x in draws if x[1]==slot]
      for tier,(field,width) in TIERS.items():
        eligible=[]
        for date,_,d in slot_draws:
            vals=numbers_for(d,field,width)
            if vals: eligible.append((date,vals))
        for window in WINDOWS:
            sample=eligible if window=="FULL" else eligible[-window:]
            if not sample: continue
            counts=[0]*10; per_draw=[]
            for date,vals in sample:
                local=[0]*10
                for number in vals:
                    for ch in number:
                        k=int(ch); counts[k]+=1; local[k]+=1
                per_draw.append(local)
            total=sum(counts); expected=total/10
            chi=sum((v-expected)**2/expected for v in counts if expected) if expected else 0
            p=gamma_q(4.5,chi/2)
            key=f"{slot}|{tier}|{window}"
            tests.append((key,p))
            # Draw-cluster bootstrap: resample complete draws, retaining each
            # draw's contribution so dependence within a draw is not ignored.
            boot=[[0]*10 for _ in range(max(0,args.bootstrap))]
            for b in range(args.bootstrap):
                for _ in range(len(per_draw)):
                    block=per_draw[rng.randrange(len(per_draw))]
                    for digit in range(10): boot[b][digit]+=block[digit]
            for digit in range(10):
                share=counts[digit]/total if total else 0
                vals=sorted((row[digit]/sum(row) if sum(row) else 0) for row in boot)
                lo=vals[int(.025*(len(vals)-1))] if vals else None
                hi=vals[int(.975*(len(vals)-1))] if vals else None
                detail.append({"slot":slot,"tier":tier,"window":window,
                    "draws":len(sample),"digit":digit,"digit_count":counts[digit],
                    "digit_share":round(share,6),"uniform_share":0.1,
                    "bootstrap_95_low":round(lo,6) if lo is not None else "",
                    "bootstrap_95_high":round(hi,6) if hi is not None else "",
                    "chi_square":round(chi,6),"p_value":p})
    adjusted=bh_adjust(tests)
    for row in detail:
        row["p_value_bh_all_tests"]=round(adjusted.get(f'{row["slot"]}|{row["tier"]}|{row["window"]}',1),8)
    fields=list(detail[0]) if detail else []
    with (out/"r001_rolling_digit_detail.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(detail)
    summary={"project":"R001","phase":"rolling-window digit stability","input":Path(args.input).name,
      "exportedAt":payload.get("exportedAt"),"eligible_draws":len(draws),
      "slot_draws":{s:sum(1 for x in draws if x[1]==s) for s in ("1PM","8PM")},
      "windows":list(WINDOWS),"tiers":list(TIERS),
      "bootstrap_replicates":args.bootstrap,
      "consolation":"excluded (duplicates first-prize suffix)",
      "sample_draws":"excluded","method":"last N valid draws per slot and tier; draw-cluster bootstrap; chi-square vs uniform; BH correction across all slot/tier/window tests",
      "limitations":["Descriptive stability is not predictive evidence.","Incomplete prize-tier groups are excluded for that tier only.","No claims of lottery predictability are made."]}
    (out/"r001_rolling_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    print("DETAIL_ROWS="+str(len(detail)))
    print("OUTPUT_DIR="+str(out))

if __name__=="__main__": main()

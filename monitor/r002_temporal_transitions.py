#!/usr/bin/env python3
"""R002: chronological transition/dependence diagnostics. Descriptive, not predictive."""
import argparse, csv, json, random, re
from pathlib import Path
from collections import Counter

TIERS = {
    "1st_5digit": ("first", 5, 1),
    "2nd_5digit": ("second", 5, 10),
    "3rd_4digit": ("third", 4, 10),
    "4th_4digit": ("fourth", 4, 10),
    "5th_4digit": ("fifth", 4, 100),
}
SLOTS=("1PM","8PM")

def extract(draw, field, width, expected):
    v=draw.get(field)
    if field=="first":
        vals=[re.sub(r"^\\s*\\d{2}[A-Za-z]\\s+","",str(v or ""))]
    elif isinstance(v,list): vals=v
    else: vals=re.findall(r"(?<!\\d)\\d{%d}(?!\\d)"%width,str(v or ""))
    out=[]
    for x in vals:
        s=str(x).strip()
        if field=="first": s=re.sub(r"^\\s*\\d{2}[A-Za-z]\\s+","",s)
        if re.fullmatch(r"\\d{%d}"%width,s): out.append(s)
    return out if len(out)==expected else None

def mi_from_pairs(pairs):
    if not pairs: return 0.0, [[0]*10 for _ in range(10)]
    m=[[0]*10 for _ in range(10)]
    for a,b in pairs: m[a][b]+=1
    n=len(pairs); rows=[sum(r) for r in m]; cols=[sum(m[i][j] for i in range(10)) for j in range(10)]
    mi=0.0
    for i in range(10):
      for j in range(10):
        c=m[i][j]
        if c and rows[i] and cols[j]:
          p=c/n; mi += p*__import__('math').log2(c*n/(rows[i]*cols[j]))
    return mi,m

def pair_sequence(records):
    # records: chronologically ordered (date, [prize numbers]); pair same position across adjacent draws
    pairs=[]
    for (_,prev),(_,cur) in zip(records,records[1:]):
        if len(prev)==len(cur):
            for x,y in zip(prev,cur):
                pairs.extend((int(a),int(b)) for a,b in zip(x,y))
    return pairs

def paired_records(left,right):
    pairs=[]
    for _,a,b in left:
        if _ in right and len(a)==len(right[_]):
            for x,y in zip(a,right[_]):
                pairs.extend((int(i),int(j)) for i,j in zip(x,y))
    return pairs

def test_pairs(pairs, reps, rng):
    obs,mat=mi_from_pairs(pairs)
    if not pairs: return obs,1.0,mat
    # Null: independently permute destination digits, preserving both marginals.
    src=[a for a,b in pairs]; dst=[b for a,b in pairs]
    exceed=0
    for _ in range(reps):
        rng.shuffle(dst)
        null,_=mi_from_pairs(zip(src,dst))
        if null >= obs-1e-15: exceed+=1
    return obs,(exceed+1)/(reps+1),mat

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--outdir",default="r002-output")
    ap.add_argument("--permutations",type=int,default=1000)
    args=ap.parse_args()
    payload=json.loads(Path(args.input).read_text(encoding="utf-8"))
    byslot={s:{} for s in SLOTS}; counts=Counter(); malformed=Counter()
    for d in payload.get("draws",[]):
        if d.get("isSample"): continue
        t=str(d.get("time","")).upper().replace(" ","")
        slot="1PM" if t in ("1:00PM","1PM","13:00") else "8PM" if t in ("8:00PM","8PM","20:00") else None
        date=str(d.get("date",""))
        if not slot or not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}",date): continue
        counts[slot]+=1
        byslot[slot][date]=d
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261121); rows=[]; matrices=[]; overlap=[]
    for slot in SLOTS:
      for tier,(field,width,expected) in TIERS.items():
        records=[]
        for date,d in sorted(byslot[slot].items()):
          nums=extract(d,field,width,expected)
          if nums is not None: records.append((date,nums))
          else: malformed[(slot,tier)]+=1
        pairs=pair_sequence(records)
        obs,p,mat=test_pairs(pairs,args.permutations,rng)
        rows.append({"analysis":"within_slot_lag1","slot":slot,"tier":tier,"paired_draws":max(0,len(records)-1),
          "digit_transitions":len(pairs),"mutual_information_bits":round(obs,8),"permutation_p_value":round(p,8),
          "null_model":"destination digits shuffled; source/destination marginals preserved"})
        for i in range(10):
          for j in range(10):
            matrices.append({"analysis":"within_slot_lag1","slot":slot,"tier":tier,"from_digit":i,"to_digit":j,"count":mat[i][j]})
    # Same-date 1PM -> 8PM and next available 8PM -> following 1PM
    for label,leftslot,rightslot,adjacent in [
      ("same_date_1PM_to_8PM","1PM","8PM",False),
      ("next_draw_8PM_to_1PM","8PM","1PM",True)]:
      for tier,(field,width,expected) in TIERS.items():
        left={}; right={}
        for date,d in byslot[leftslot].items():
          n=extract(d,field,width,expected)
          if n is not None:left[date]=n
        for date,d in byslot[rightslot].items():
          n=extract(d,field,width,expected)
          if n is not None:right[date]=n
        paired=[]
        if not adjacent:
          keys=sorted(set(left)&set(right))
          for date in keys: paired.append((date,left[date],right[date]))
        else:
          ldates=sorted(left); rdates=sorted(right)
          # Pair each 8PM draw with the first later calendar-date 1PM draw.
          for date in ldates:
            nxt=next((x for x in rdates if x>date),None)
            if nxt: paired.append((date,left[date],right[nxt]))
        pairs=[]
        for _,a,b in paired:
          if len(a)==len(b):
            for x,y in zip(a,b): pairs.extend((int(i),int(j)) for i,j in zip(x,y))
        obs,p,mat=test_pairs(pairs,args.permutations,rng)
        rows.append({"analysis":label,"slot":leftslot+"->"+rightslot,"tier":tier,"paired_draws":len(paired),
          "digit_transitions":len(pairs),"mutual_information_bits":round(obs,8),"permutation_p_value":round(p,8),
          "null_model":"destination digits shuffled; source/destination marginals preserved"})
        for i in range(10):
          for j in range(10):
            matrices.append({"analysis":label,"slot":leftslot+"->"+rightslot,"tier":tier,"from_digit":i,"to_digit":j,"count":mat[i][j]})
    # Benjamini-Hochberg correction across all R002 transition tests.
    ordered=sorted(enumerate(rows),key=lambda z:z[1]["permutation_p_value"])
    m=len(ordered); running=1.0; adjusted=[1.0]*m
    for rank in range(m,0,-1):
      idx,row=ordered[rank-1]
      running=min(running,row["permutation_p_value"]*m/rank)
      adjusted[idx]=min(1.0,running)
    for i,row in enumerate(rows):
      row["p_value_bh_all_tests"]=round(adjusted[i],8)
    fields=list(rows[0])
    with (out/"r002_transition_tests.csv").open("w",newline="",encoding="utf-8") as f:
      w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with (out/"r002_transition_matrices.csv").open("w",newline="",encoding="utf-8") as f:
      w=csv.DictWriter(f,fieldnames=list(matrices[0]));w.writeheader();w.writerows(matrices)
    summary={"project":"R002","title":"Temporal dependence and transition diagnostics","input":Path(args.input).name,
      "exportedAt":payload.get("exportedAt"),"slot_draw_records":dict(counts),"tiers":list(TIERS),
      "permutation_replicates":args.permutations,"tests":len(rows),
      "method":"position-matched digit transitions between consecutive valid draws within each slot; plus same-date 1PM->8PM and next-date 8PM->1PM; mutual information; permutation null shuffles destination digits preserving marginals",
      "limitations":["Exploratory dependence diagnostics, not predictions.","The permutation null does not establish causality.","Overlapping prize positions within a draw are dependent; draws are the chronological units.","No candidate-number ranking is produced.","No significance claim should be made without family-wise or false-discovery correction across R002 tests."]}
    (out/"r002_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()

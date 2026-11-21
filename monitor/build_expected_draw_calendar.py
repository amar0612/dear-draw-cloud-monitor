#!/usr/bin/env python3
"""Build a conservative expected-draw calendar from explicit archive evidence.

Only dates with an explicit 1PM/8PM result link are emitted. A date is never
inferred merely because it is a weekday or lies inside a month. The official
Nagaland gazette portal is checked first; archive mirrors are discovery leads.
"""
from __future__ import annotations
import argparse, csv, re, sys, urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

UA = "DearDrawAnalyzer/1.0 (calendar discovery; contact via repository)"
SOURCES = [
    ("official_gazette", "https://www.nagalandlotteries.com/results.php", "official"),
    ("lottery_sambad_fax", "https://www.lotterysambadfax.com/results", "mirror"),
    ("lottery_sambad_annual", "https://www.lotterysambad.co/old/", "mirror"),
    ("dear_1_crore", "https://www.dear1crore.com/nagaland-state-lottery/result/archive/", "mirror"),
    ("nagaland_sambad", "https://nagalandsambad.in/old-result", "mirror"),
    ("dearresult", "https://dearresult.in/", "mirror"),
    ("lottery_sambad_store", "https://lotterysambad.store/", "mirror"),
    ("lottery_sambad_icu", "https://lotterysambad.icu/old-result", "mirror"),
]
DATE_PATTERNS = [
    re.compile(r"(?<!\\d)(20\\d{2})[-_/](0?[1-9]|1[0-2])[-_/]([0-3]?\\d)(?!\\d)"),
    re.compile(r"(?<!\\d)([0-3]?\\d)[-_/](0?[1-9]|1[0-2])[-_/](20\\d{2})(?!\\d)"),
    re.compile(r"(?<!\\d)([0-3]?\\d)(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?(20\\d{2})(?!\\d)", re.I),
]
MONTHS = {m.lower(): i for i, m in enumerate(("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"),1)}

class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.href=None; self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower()=="a":
            self.href=dict(attrs).get("href"); self.parts=[]
    def handle_data(self, data):
        if self.href is not None: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag.lower()=="a" and self.href is not None:
            self.links.append((self.href," ".join(self.parts))); self.href=None; self.parts=[]

def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(req,timeout=20) as r: return r.read().decode("utf-8","ignore")

def extract_dates(text, url):
    found=set()
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text+" "+url):
            try:
                if pat is DATE_PATTERNS[0]: y,mo,da=map(int,m.groups())
                elif pat is DATE_PATTERNS[1]: da,mo,y=map(int,m.groups())
                else: da,mon,y=m.groups(); mo=MONTHS[mon[:3].lower()]; da=int(da); y=int(y)
                found.add(date(y,mo,da).isoformat())
            except Exception: pass
    return found

def draw_flags(href,label):
    s=(href+" "+label).lower().replace(" ","")
    one=bool(re.search(r"1pm|13:00|13%3a00|morning",s))
    eight=bool(re.search(r"8pm|20:00|20%3a00|night",s))
    six=bool(re.search(r"6pm|18:00",s))
    if six and not (one or eight): return set()
    out=set()
    if one: out.add("1PM")
    if eight: out.add("8PM")
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--start-date",default="2021-01-01")
    ap.add_argument("--end-date",default=date.today().isoformat())
    ap.add_argument("--output",default="data/nagaland_expected_draw_calendar.csv")
    ap.add_argument("--report",default="calendar-output/report.json")
    a=ap.parse_args()
    start=date.fromisoformat(a.start_date); end=date.fromisoformat(a.end_date)
    evidence={}
    failures=[]
    for source,url,kind in SOURCES:
        try:
            html=fetch(url); parser=Links(); parser.feed(html)
            for href,label in parser.links:
                target=urljoin(url,href)
                dates=extract_dates(href+" "+label,target)
                flags=draw_flags(href,label)
                # Explicitly slot-labelled links are strong evidence. For date pages,
                # inspect the page itself and require child links naming a draw slot.
                for ds in dates:
                    if not (start.isoformat()<=ds<=end.isoformat()): continue
                    if flags:
                        for draw in flags:
                            evidence.setdefault((ds,draw),[]).append((source,kind,target,"explicit_slot_link"))
                    elif target.startswith(("http://","https://")) and target not in {url}:
                        try:
                            child=fetch(target); cp=Links(); cp.feed(child)
                            for chref,clabel in cp.links:
                                cflags=draw_flags(chref,clabel)
                                for draw in cflags:
                                    evidence.setdefault((ds,draw),[]).append((source,kind,urljoin(target,chref),"date_page_slot_link"))
                        except Exception: pass
            # Official current gazette may expose date anchors with no textual slot.
            # These are recorded separately for review, never treated as draw evidence.
        except Exception as e:
            failures.append({"source":source,"url":url,"error":str(e)[:240]})
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["date","draw","calendar_status","source_count","sources","evidence_urls"])
        for (ds,draw),items in sorted(evidence.items()):
            sources=sorted({x[0] for x in items})
            status="official_explicit" if any(x[1]=="official" for x in items) else "mirror_explicit"
            w.writerow([ds,draw,status,len(sources),";".join(sources),";".join(sorted({x[2] for x in items}))])
    report={"start_date":start.isoformat(),"end_date":end.isoformat(),"expected_draw_pairs_found":len(evidence),
            "dates_found":len({d for d,_ in evidence}),"sources_checked":len(SOURCES),
            "source_failures":failures,"calendar_file":str(out),
            "warning":"This is a conservative evidence calendar, not proof of complete historical draw coverage. Unlisted dates remain unknown, not non-draw days."}
    rp=Path(a.report); rp.parent.mkdir(parents=True,exist_ok=True)
    import json
    rp.write_text(json.dumps(report,indent=2)+"\\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": main()

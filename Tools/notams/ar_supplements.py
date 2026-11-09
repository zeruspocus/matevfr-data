#!/usr/bin/env python3
"""Builds `ar-supplements.json`: the AIP supplements (SUP) in force at the ANAC, for the app's list.

Source: the public list at https://ais.anac.gob.ar/sup (the page loads its table with an AJAX call to /sup/a, so the
request carries X-Requested-With). Only the rows marked as in force ("vigente") are kept. A supplement is a temporary
or long-lasting change to the AIP (runway works, restricted areas, suspended procedures...). Reference only.

Usage: ar_supplements.py --fetch --out ar-supplements.json
"""
import argparse, datetime, html, json, re, sys, urllib.request

BASE = "https://ais.anac.gob.ar"
ROW = re.compile(r'<tr class="(vigente|[^"]*)">.*?<td id="nroanno">\s*([^<]+?)\s*</td>.*?<a href="(/descarga/sup-[0-9a-f]+)"[^>]*>(.*?)</a>.*?<td id="from">\s*([^<]+?)\s*</td>', re.S)
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
CODE_SLASH = re.compile(r"\([A-Z]{3}/([A-Z]{4})\)")
CODE_PLAIN = re.compile(r"\(([A-Z]{4})\)")

def parse_date(text):
    m = re.match(r"(\d{2})-([A-Za-z]{3})-(\d{2})$", text.strip())
    if not m or m[2].title() not in MONTHS:
        return None
    return datetime.date(2000 + int(m[3]), MONTHS[m[2].title()], int(m[1])).isoformat()

def kind_of(title):
    t = title.upper()
    if t.startswith("AD "):
        return "aerodrome"
    if re.search(r"RESTRICCI[OÓ]N|AFECTACI[OÓ]N|ESPACIO A[EÉ]REO|ZONA|CONTINGENCIA|FIR |TMA ", t):
        return "airspace"
    if re.search(r"AIP PART|MODIFICACIONES|RUTAS|ENR", t):
        return "publication"
    return "other"

def parse(page, only_in_force=True):
    items = []
    for state, number, link, title, date in ROW.findall(page):
        in_force = state.strip() == "vigente"
        if only_in_force and not in_force:
            continue
        clean = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title))).strip()
        codes = sorted(set(CODE_SLASH.findall(clean)) | set(CODE_PLAIN.findall(clean)))
        items.append({
            "id": re.sub(r"\s+", " ", html.unescape(number)).strip(),
            "title": clean,
            "published": parse_date(date),
            "pdf": BASE + link,
            "codes": codes,
            "kind": kind_of(clean),
        })
    return items

def fetch():
    req = urllib.request.Request(BASE + "/sup/a", headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--min", type=int, default=10, help="fail if fewer supplements than this were read (the page probably changed)")
    a = ap.parse_args()
    if not a.fetch:
        sys.exit("use --fetch")
    items = parse(fetch())
    if len(items) < a.min:
        print(f"ERROR: only {len(items)} supplements in force were read (expected at least {a.min}). The ANAC page probably changed.")
        sys.exit(1)
    out = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "ANAC AIS · Suplementos a la AIP (vigentes)",
        "count": len(items),
        "supplements": items,
    }
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{len(items)} supplements in force")

if __name__ == "__main__":
    main()

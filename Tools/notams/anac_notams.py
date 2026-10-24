#!/usr/bin/env python3
"""Argentina (ANAC / EANA) NOTAM areas for the MateVFR map.

The ANAC AIS page (https://ais.anac.gob.ar/notam) answers a form post with a table of the active NOTAMs of a place or FIR,
in English and Spanish. This reads the five FIR lists and writes the same GeoJSON as `gcaa_notams.py`, for the NOTAMs that
are areas: a circle ("COORD GEO 342910S/0612923W, RDO 3NM") or a polygon ("COORD GEO a - b - c ..."). Arcs, areas that only
name a zone and everything without coordinates are left out, as in the UAE file.

Usage:
    python3 Tools/notams/anac_notams.py --fetch --out ar-notams.geojson
    python3 Tools/notams/anac_notams.py --html pib_-EF.html pib_-CF.html --out ar-notams.geojson

NOT an official product: informational only, the ANAC says its list does not replace the ARO-AIS briefing (PIB).
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from gcaa_notams import circle, dms, limit

SOURCE_PAGE = "https://ais.anac.gob.ar/notam"
PIB_URL = "https://ais.anac.gob.ar/notam/pib"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"
FIRS = ["-EF", "-CF", "-MF", "-VF", "-RR"]  # Ezeiza, Cordoba, Mendoza, Comodoro Rivadavia, Resistencia

COORD = re.compile(r"(\d{6})([NS])\s*/?\s*-?(\d{7})([EW])")
RADIUS = re.compile(r"R(?:DO|ADIUS)\s*:?\s*([\d.]+)\s*(NM|KM|M)\b")
LIMIT_TOKEN = r"(GND|SFC|UNL|FL\s?\d{2,3}|\d{1,5}\s?(?:FT|M)(?:\s?(?:AGL|AMSL))?)"
LIMITS = re.compile(rf"F\)\s*{LIMIT_TOKEN}\s*G\)\s*{LIMIT_TOKEN}", re.I)
# Without F) and G): two limits one after the other, "GND-FL100", "2000FT FL350", "GND UNL".
LIMITS_PAIR = re.compile(
    r"(?<![\w/])(GND|SFC|FL\s?\d{2,3}|\d{1,5}\s?FT(?:\s?(?:AGL|AMSL))?)\s*(?:-\s*|\s)(GND|UNL|FL\s?\d{2,3}|\d{1,5}\s?FT(?:\s?(?:AGL|AMSL))?)(?![\w/])", re.I)
SCHEDULE = re.compile(r"D\)\s*(.*?)(?=\s+F\)|\s+G\)|$)")
DAILY = re.compile(r"\b(DLY\b.*?)(?=\s+F\)|\s+G\)|$)")


def classify(english: str) -> str:
    text = english.upper()
    if re.search(r"\bPJE\b|PARACHUT", text):
        return "parachute"
    if "PROHIBITED" in text:
        return "prohibited"
    if re.search(r"TEMPO(?:RARY)? RESTRICTED", text):
        return "tempRestricted"
    if "RESTRICTED" in text:
        return "restricted"
    if "DANGER" in text:
        return "danger"
    return "other"


def points(text: str) -> list[tuple[float, float]]:
    return [(round(dms(lon, ew, 3), 6), round(dms(lat, ns, 2), 6)) for lat, ns, lon, ew in COORD.findall(text)]


def geometry(english: str) -> dict | None:
    if re.search(r"\bARC\b", english.upper()):
        return None  # an arc around a point or a VOR: not drawn in this version
    found = points(english)
    radius = RADIUS.search(english)
    if radius and len(found) == 1:
        meters = float(radius.group(1)) * {"NM": 1852, "KM": 1000, "M": 1}[radius.group(2)]
        lon, lat = found[0]
        return {"type": "Polygon", "coordinates": [circle(lon, lat, meters)]}
    if radius or len(found) < 3:
        return None
    ring = list(found)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def when(value: str) -> str | None:
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})", value)
    return f"{m.group(1)}T{m.group(2)}Z" if m else None  # the ANAC page says the NOTAM times are UTC


def limits(english: str) -> tuple[dict, dict]:
    text = COORD.sub(" ", english)
    m = LIMITS.search(text) or LIMITS_PAIR.search(text)
    if not m:
        return limit(None), limit(None)
    lower, upper = limit(m.group(1).upper()), limit(m.group(2).upper())
    # "500FT 1000FT AGL": the first number takes the reference of the second.
    if upper["reference"] == "AGL" and lower["reference"] == "AMSL" and "AMSL" not in m.group(1).upper():
        lower["reference"] = "AGL"
        lower["text"] = lower["text"] + " AGL"
    return lower, upper


def rows(page: str) -> list[dict]:
    result = []
    for row in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        paragraphs = [htmllib.unescape(re.sub(r"<[^>]+>", " ", p)).strip() for p in re.findall(r"<p>(.*?)</p>", row, re.S)]
        paragraphs = [" ".join(p.split()) for p in paragraphs]
        if len(paragraphs) < 5 or not re.match(r"A\d{4}/\d{4}$", paragraphs[0]):
            continue
        body = re.search(r'<td id="info">.*?<p>.*?</p>\s*<p>.*?</p>\s*<p>(.*?)</p>', row, re.S)
        both = htmllib.unescape(re.sub(r"<[^>]+>", "\n", body.group(1).replace('<span id="versionbreak">', "\x00"))) if body else ""
        english, _, spanish = both.partition("\x00")
        clean = lambda t: " ".join(t.replace("\n", " ").replace("Versión en Español:", " ").split())
        result.append({
            "id": paragraphs[0], "place": paragraphs[1], "code": paragraphs[2].strip("()"),
            "from": paragraphs[3].replace("Desde:", ""), "to": paragraphs[4].replace("Hasta:", ""),
            "english": clean(english), "spanish": clean(spanish),
        })
    return result


def parse(pages: list[str], generated: str | None = None) -> dict:
    features, seen, count = [], set(), 0
    for page in pages:
        for item in rows(page):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            count += 1
            shape = geometry(item["english"])
            if shape is None:
                continue
            lower, upper = limits(item["english"])
            schedule = SCHEDULE.search(item["english"]) or DAILY.search(item["english"])
            features.append({
                "type": "Feature",
                "geometry": shape,
                "properties": {
                    "id": item["id"],
                    "category": classify(item["english"]),
                    "qcode": None,
                    "location": item["place"].replace("AVISOS ", ""),
                    "validFrom": when(item["from"]),
                    "validTo": when(item["to"]),
                    "permanent": item["to"].strip().upper().startswith("PERM"),
                    "schedule": " ".join(schedule.group(1).split()) if schedule else None,
                    "lower": lower,
                    "upper": upper,
                    "text": item["english"],
                    "textEs": item["spanish"] or None,
                },
            })
    return {
        "type": "FeatureCollection",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Argentina ANAC / EANA · NOTAM list (reference only, does not replace the ARO-AIS briefing)",
        "sourcePage": SOURCE_PAGE,
        "notamCount": count,
        "features": features,
    }


def fetch_pages() -> list[str]:
    pages = []
    for indicator in FIRS:
        data = urllib.parse.urlencode({"indicador": indicator}).encode()
        request = urllib.request.Request(PIB_URL, data=data, headers={
            "User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest", "Referer": SOURCE_PAGE,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })
        with urllib.request.urlopen(request, timeout=60) as response:
            pages.append(response.read().decode("utf8", errors="ignore"))
        time.sleep(1)
    return pages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--html", nargs="*")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.fetch:
        pages = fetch_pages()
    elif args.html:
        pages = [open(path, encoding="utf8", errors="ignore").read() for path in args.html]
    else:
        sys.exit("give --fetch or --html")
    result = parse(pages)
    with open(args.out, "w", encoding="utf8") as out:
        json.dump(result, out, ensure_ascii=False, separators=(",", ":"))
    counts: dict[str, int] = {}
    for feature in result["features"]:
        counts[feature["properties"]["category"]] = counts.get(feature["properties"]["category"], 0) + 1
    print(f"{result['notamCount']} NOTAMs read, {len(result['features'])} areas -> {args.out}  {counts}")


if __name__ == "__main__":
    main()

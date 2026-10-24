#!/usr/bin/env python3
"""United Kingdom NOTAM areas for the MateVFR map.

NATS publishes its Pre-flight Information Bulletin as one XML file (https://pibs.nats.co.uk/operational/pibs/PIB.xml) with every
valid UK NOTAM in fields: the Q line, the coordinates and radius, the validity, the schedule (item D), the text (item E) and the
limits (items F and G). This keeps the NOTAMs that are areas and have a shape in their text (a circle "WI 1.65NM RADIUS OF
523022N 0015244W", or a polygon of coordinates), and writes the same GeoJSON as `gcaa_notams.py`. A NOTAM that only names an area,
or has several shapes, is left out in this version.

Usage:
    python3 Tools/notams/uk_notams.py --fetch --out uk-notams.geojson
    python3 Tools/notams/uk_notams.py --xml PIB.xml --out uk-notams.geojson

Informational only, not for operational use: check the official NOTAM before flight.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from gcaa_notams import circle, coordinates, limit, notam_time

SOURCE_PAGE = "https://www.nats.aero/do-it-online/ais/"
PIB_URL = "https://pibs.nats.co.uk/operational/pibs/PIB.xml"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"

# Q code letters 2 and 3 (ICAO): the kinds of area. The first group is drawn by the app today.
CATEGORIES = {
    "RA": "tra", "RD": "danger", "RM": "military", "RO": "restricted", "RP": "prohibited", "RR": "restricted", "RT": "tempRestricted",
    "WP": "parachute", "WE": "military", "WM": "military", "WU": "uas",
}

RADIUS = re.compile(r"([\d.]+)\s*(NM|KM|M)\s+RADIUS|RADIUS\s+(?:OF\s+)?([\d.]+)\s*(NM|KM|M)\b")
MAX_HEIGHT = re.compile(r"MAX\s+HGT\s+([\d,]+)\s*FT\s*(AMSL|AGL)?", re.I)


def radius_meters(text: str) -> float | None:
    m = RADIUS.search(text)
    if not m:
        return None
    value, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    return float(value) * {"NM": 1852, "KM": 1000, "M": 1}[unit]


def geometry(text: str) -> dict | None:
    points = coordinates(text)
    radius = radius_meters(text)
    if radius is not None and len(points) == 1:
        lon, lat = points[0]
        return {"type": "Polygon", "coordinates": [circle(lon, lat, radius)]}
    if radius is not None or len(points) < 3:
        return None  # several shapes, or only a name: not drawn in this version
    ring = list(points)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def flight_level(value: str | None) -> dict:
    """The Q line limits are flight levels in hundreds of feet, rounded up: an approximation when F) and G) are not given."""
    try:
        level = int(value or "")
    except ValueError:
        return limit(None)
    return {"text": f"FL{level:03d}", "feet": level * 100, "reference": "FL"}


def limits(notam: ET.Element, body: str) -> tuple[dict, dict]:
    lower_text, upper_text = (notam.findtext(tag) for tag in ("ItemF", "ItemG"))
    if lower_text and upper_text:
        return limit(lower_text.strip()), limit(upper_text.strip())
    q = notam.find("QLine")
    lower, upper = flight_level(q.findtext("Lower")), flight_level(q.findtext("Upper"))
    height = MAX_HEIGHT.search(body)
    if height:
        feet = int(height.group(1).replace(",", ""))
        upper = {"text": f"{feet} FT {height.group(2) or 'AMSL'}".upper(), "feet": feet, "reference": (height.group(2) or "AMSL").upper()}
        lower = {"text": "SFC", "feet": 0, "reference": "GND"}
    return lower, upper


def parse(xml_text: str, generated: str | None = None) -> dict:
    root = ET.fromstring(xml_text)
    features, seen, count = [], set(), 0
    for notam in root.iter("Notam"):
        if (notam.findtext("Type") or "") == "C":
            continue
        number = f"{notam.findtext('Series')}{notam.findtext('Number')}/{notam.findtext('Year')}"
        if number in seen:
            continue
        seen.add(number)
        count += 1
        code = (notam.findtext("QLine/Code23") or "").upper()
        category = CATEGORIES.get(code)
        if category is None:
            continue
        body = " ".join((notam.findtext("ItemE") or "").split())
        shape = geometry(body)
        if shape is None:
            continue
        lower, upper = limits(notam, body)
        end = (notam.findtext("EndValidity") or "").strip()
        features.append({
            "type": "Feature",
            "geometry": shape,
            "properties": {
                "id": number,
                "category": category,
                "qcode": "Q" + code + (notam.findtext("QLine/Code45") or ""),
                "location": notam.findtext("ItemA"),
                "validFrom": notam_time(notam.findtext("StartValidity")),
                "validTo": notam_time(end),
                "permanent": end.upper().startswith("PERM"),
                "schedule": " ".join((notam.findtext("ItemD") or "").split()) or None,
                "lower": lower,
                "upper": upper,
                "text": body,
                "textEs": None,
            },
        })
    return {
        "type": "FeatureCollection",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "UK NATS · Pre-flight Information Bulletin (informational, not for operational use)",
        "sourcePage": SOURCE_PAGE,
        "notamCount": count,
        "features": features,
    }


def fetch() -> str:
    request = urllib.request.Request(PIB_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf8", errors="ignore")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--xml")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.fetch:
        xml_text = fetch()
    elif args.xml:
        xml_text = open(args.xml, encoding="utf8", errors="ignore").read()
    else:
        sys.exit("give --fetch or --xml")
    result = parse(xml_text)
    with open(args.out, "w", encoding="utf8") as out:
        json.dump(result, out, ensure_ascii=False, separators=(",", ":"))
    counts: dict[str, int] = {}
    for feature in result["features"]:
        counts[feature["properties"]["category"]] = counts.get(feature["properties"]["category"], 0) + 1
    print(f"{result['notamCount']} NOTAMs read, {len(result['features'])} areas -> {args.out}  {counts}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""United States temporary flight restrictions (TFR) for the MateVFR map.

The FAA publishes the list of active TFRs (https://tfr.faa.gov/tfrapi/getTfrList) and, for each, an XML with its shape, its
vertical limits and its dates (https://tfr.faa.gov/download/detail_<number>.xml, "/" written as "_"). The XML carries the
merged outline already as points (arcs included), so a TFR is drawn from those. Same GeoJSON as `gcaa_notams.py`.

Usage:
    python3 Tools/notams/us_tfr.py --fetch --out us-notams.geojson
    python3 Tools/notams/us_tfr.py --list list.json --xml 6_2017=detail_6_2017.xml --out us-notams.geojson

Public information of the US government. Informational only: check the official NOTAM before flight.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from gcaa_notams import circle

SOURCE_PAGE = "https://tfr.faa.gov/tfr3/"
LIST_URL = "https://tfr.faa.gov/tfrapi/getTfrList"
DETAIL_URL = "https://tfr.faa.gov/download/detail_{}.xml"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"


def text(element: ET.Element | None, path: str) -> str:
    found = element.find(path) if element is not None else None
    return (found.text or "").strip() if found is not None and found.text else ""


def coordinate(value: str) -> float:
    """'31.15007463N' / '088.89166667W' to signed degrees."""
    value = value.strip()
    return -float(value[:-1]) if value[-1] in "SW" else float(value[:-1])


def iso(value: str) -> str | None:
    value = (value or "").strip()
    return value + "Z" if len(value) == 19 else None  # the XML says its times are UTC


def limit(area: ET.Element, which: str) -> dict:
    code, value, unit = (text(area, f"{n}DistVer{which}") for n in ("code", "val", "uom"))
    if not value:
        return {"text": "", "feet": None, "reference": None}
    if value.upper() in {"UNL", "UNLIMITED"}:
        return {"text": "UNL", "feet": 99999, "reference": "AMSL"}
    amount = float(value)
    if unit.upper() == "FL":
        return {"text": f"FL{int(amount):03d}", "feet": int(amount) * 100, "reference": "FL"}
    feet = int(round(amount * (3.28084 if unit.upper() == "M" else 1)))
    if code.upper() == "HEI":
        return {"text": "GND" if feet == 0 else f"{feet} FT AGL", "feet": feet, "reference": "GND" if feet == 0 else "AGL"}
    if feet == 0:
        return {"text": "SFC", "feet": 0, "reference": "GND"}
    return {"text": f"{feet} FT AMSL", "feet": feet, "reference": "AMSL"}


def schedule(area: ET.Element) -> str | None:
    windows = []
    for group in area.iter("ScheduleGroup"):
        start, end = text(group, "startTime"), text(group, "endTime")
        if len(start) >= 16 and len(end) >= 16:
            window = f"{start[11:13]}{start[14:16]}-{end[11:13]}{end[14:16]}"
            if window not in windows:
                windows.append(window)
    return ("DLY " + " ".join(windows) + " UTC") if windows else None


def ring(group: ET.Element) -> list[tuple[float, float]]:
    merged = group.find("abdMergedArea")
    points = []
    for vertex in (merged.iter("Avx") if merged is not None else []):
        if vertex.find("geoLat") is not None and vertex.find("geoLong") is not None and text(vertex, "codeType") != "CIR":
            points.append((round(coordinate(text(vertex, "geoLong")), 6), round(coordinate(text(vertex, "geoLat")), 6)))
    if len(points) < 3:  # a circle given by its centre and radius
        for vertex in group.iter("Avx"):
            if text(vertex, "codeType") == "CIR" and text(vertex, "valRadiusArc"):
                unit = {"NM": 1852, "KM": 1000, "M": 1}.get(text(vertex, "uomRadiusArc").upper(), 1852)
                return circle(coordinate(text(vertex, "geoLong")), coordinate(text(vertex, "geoLat")), float(text(vertex, "valRadiusArc")) * unit)
        return []
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def parse_one(xml_text: str, meta: dict) -> list[dict]:
    root = ET.fromstring(xml_text.lstrip("﻿"))
    features = []
    for note in root.iter("Not"):
        number = text(note, "NotUid/txtLocalName") or meta.get("notam_id", "")
        body = " ".join(text(note, "txtDescrUSNS").split())
        groups = list(note.iter("TFRAreaGroup"))
        for index, group in enumerate(groups):
            outline = ring(group)
            if len(outline) < 4:
                continue
            area = group.find("aseTFRArea")
            name = text(area, "txtName")
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [outline]},
                "properties": {
                    "id": number if len(groups) == 1 else f"{number} {name or index + 1}",
                    "category": "tfr",
                    "qcode": None,
                    "location": " · ".join(x for x in (meta.get("state"), meta.get("type")) if x) or None,
                    "validFrom": iso(text(note, "dateEffective")),
                    "validTo": iso(text(note, "dateExpire")),
                    "permanent": False,
                    "schedule": schedule(area) if area is not None else None,
                    "lower": limit(area, "Lower") if area is not None else {"text": "", "feet": None, "reference": None},
                    "upper": limit(area, "Upper") if area is not None else {"text": "", "feet": None, "reference": None},
                    "text": body,
                    "textEs": None,
                },
            })
    return features


def parse(listing: list[dict], details: dict[str, str], generated: str | None = None) -> dict:
    features = []
    for entry in listing:
        xml_text = details.get(entry["notam_id"].replace("/", "_"))
        if xml_text:
            features.extend(parse_one(xml_text, entry))
    return {
        "type": "FeatureCollection",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "US FAA · Temporary Flight Restrictions (reference only, check the official NOTAM)",
        "sourcePage": SOURCE_PAGE,
        "notamCount": len(listing),
        "features": features,
    }


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8-sig", errors="ignore")


def fetch() -> tuple[list[dict], dict[str, str]]:
    listing = json.loads(get(LIST_URL))
    details = {}
    for entry in listing:
        key = entry["notam_id"].replace("/", "_")
        try:
            details[key] = get(DETAIL_URL.format(key))
        except Exception as error:  # one TFR that cannot be read must not stop the rest
            print(f"skipped {entry['notam_id']}: {error}", file=sys.stderr)
        time.sleep(0.3)
    return listing, details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--list")
    parser.add_argument("--xml", nargs="*", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.fetch:
        listing, details = fetch()
    elif args.list:
        listing = json.load(open(args.list))
        details = {pair.split("=")[0]: open(pair.split("=")[1], encoding="utf-8-sig").read() for pair in args.xml}
    else:
        sys.exit("give --fetch or --list")
    result = parse(listing, details)
    with open(args.out, "w", encoding="utf8") as out:
        json.dump(result, out, ensure_ascii=False, separators=(",", ":"))
    print(f"{result['notamCount']} TFRs listed, {len(result['features'])} areas -> {args.out}")


if __name__ == "__main__":
    main()

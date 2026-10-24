#!/usr/bin/env python3
"""UAE (OMAE) NOTAM areas for the MateVFR map.

Reads the GCAA "Valid NOTAM" summary (a PDF the GCAA publishes once a day) and writes a GeoJSON of the NOTAMs that are
areas: a polygon or a circle on the map, with its limits and validity. Everything else (cranes, closures, drones ...)
is left out of the drawing, but every NOTAM that has a geometry is kept with a `category` so the app can choose.

Usage:
    python3 Tools/notams/gcaa_notams.py --text notam.txt --out omae-notams.geojson
    python3 Tools/notams/gcaa_notams.py --pdf "OMAE_ValidNOTAM ... .pdf" --out omae-notams.geojson   (needs pypdf)
    python3 Tools/notams/gcaa_notams.py --fetch --out omae-notams.geojson                         (downloads the newest PDF)

NOT an official product: informational only, see the disclaimer the GCAA prints on its summary.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SOURCE_PAGE = "https://www.gcaa.gov.ae/en/ais/pages/notam.aspx"
FOLDER_API = ("https://www.gcaa.gov.ae/en/ais/admin/_api/Web/GetFolderByServerRelativeUrl("
              "'Publication%20Library/Notam')?$expand=Files")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"

# Q-code second and third letters -> what the area is. Only the first group is drawn by the app today.
CATEGORIES = {
    "RA": "tra", "RD": "danger", "RR": "restricted", "RP": "prohibited", "RT": "tempRestricted", "RM": "military",
    "WE": "military", "WU": "uas", "WC": "other", "WL": "other",
}

COORD = re.compile(r"(\d{4}(?:\d{2}(?:\.\d+)?)?)\s*([NS])\s*(\d{5}(?:\d{2}(?:\.\d+)?)?)\s*([EW])")
BLOCK_START = re.compile(
    r"\n(?=(?:NOTAM[NRC]\n)?A\d{4}/\d{2}(?: A\d{4}/\d{2})?\n(?:NOTAM[NRC]\n)?Q\))")
NOISE = re.compile(r"^(?:As of \d.* UTC|\d{1,2}|=+PAGE \d+=+)$")


def dms(value: str, hemisphere: str, degree_digits: int) -> float:
    degrees = int(value[:degree_digits])
    minutes = int(value[degree_digits:degree_digits + 2])
    seconds = float(value[degree_digits + 2:]) if len(value) > degree_digits + 2 else 0.0
    result = degrees + minutes / 60 + seconds / 3600
    return -result if hemisphere in "SW" else result


def coordinates(text: str) -> list[tuple[float, float]]:
    """(lon, lat) pairs in the order they are written."""
    return [(round(dms(lon, ew, 3), 6), round(dms(lat, ns, 2), 6)) for lat, ns, lon, ew in COORD.findall(text)]


def circle(lon: float, lat: float, radius_m: float, steps: int = 48) -> list[tuple[float, float]]:
    ring = []
    for i in range(steps):
        bearing = 2 * math.pi * i / steps
        d_lat = radius_m * math.cos(bearing) / 111_320
        d_lon = radius_m * math.sin(bearing) / (111_320 * max(math.cos(math.radians(lat)), 0.01))
        ring.append((round(lon + d_lon, 6), round(lat + d_lat, 6)))
    ring.append(ring[0])
    return ring


def radius_meters(text: str) -> float | None:
    m = re.search(r"RADIUS\s+([\d.]+)\s*(NM|KM|M)\b", text)
    if not m:
        return None
    value = float(m.group(1))
    return value * {"NM": 1852, "KM": 1000, "M": 1}[m.group(2)]


def geometry(text: str) -> dict | None:
    """A GeoJSON polygon from the NOTAM's E) text, or None when it only names an area."""
    points = coordinates(text)
    if not points:
        return None
    radius = radius_meters(text)
    if radius is not None and re.search(r"CIRCLE|CENTERED|CENTRED", text):
        lon, lat = points[0]
        return {"type": "Polygon", "coordinates": [circle(lon, lat, radius)]}
    if re.search(r"EITHER SIDE OF A LINE", text):
        return None  # a corridor around a line: not drawn in this version
    if len(points) < 3:
        return None
    ring = list(points)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


def limit(value: str | None) -> dict:
    """{'text': '2,000 FT AMSL', 'feet': 2000, 'reference': 'AMSL'} from an F) or G) line."""
    raw = (value or "").strip().replace("\n", " ")
    upper = raw.upper()
    if upper in {"SFC", "GND"}:
        return {"text": upper, "feet": 0, "reference": "GND"}
    if upper in {"UNL", "UNLIMITED"}:
        return {"text": "UNL", "feet": 99999, "reference": "AMSL"}
    m = re.match(r"FL\s*(\d+)", upper)
    if m:
        return {"text": f"FL{int(m.group(1)):03d}", "feet": int(m.group(1)) * 100, "reference": "FL"}
    m = re.match(r"([\d,]+)\s*FT\s*(AMSL|AGL)?", upper)
    if m:
        return {"text": raw, "feet": int(m.group(1).replace(",", "")), "reference": m.group(2) or "AMSL"}
    return {"text": raw, "feet": None, "reference": None}


def notam_time(value: str | None) -> str | None:
    """ICAO yymmddhhmm (UTC) to an ISO string; None for PERM or anything unreadable."""
    if not value:
        return None
    m = re.match(r"(\d{10})", value.strip())
    if not m:
        return None
    return datetime.strptime(m.group(1), "%y%m%d%H%M").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not NOISE.match(line.strip()))


def fields(block: str) -> dict[str, str]:
    result = {}
    for m in re.finditer(r"(?m)^([QABCDEFG])\)(.*?)(?=^[A-G]\)|\Z)", block, re.S):
        result[m.group(1)] = m.group(2).strip()
    return result


def parse(text: str, generated: str | None = None) -> dict:
    features, skipped = [], {"no geometry": 0}
    for block in BLOCK_START.split(clean(text)):
        header = re.match(r"\s*(?:NOTAM[NRC]\n)?(A\d{4}/\d{2})", block)
        if not header or "Q)" not in block:
            continue
        f = fields(block)
        q = f.get("Q", "").split("/")
        qcode = q[1] if len(q) > 1 else ""
        category = CATEGORIES.get(qcode[1:3]) if qcode.startswith("Q") else None
        if category is None:
            continue
        body = f.get("E", "")
        shape = geometry(body)
        if shape is None:
            skipped["no geometry"] += 1
            continue
        lower, upper = limit(f.get("F")), limit(f.get("G"))
        features.append({
            "type": "Feature",
            "geometry": shape,
            "properties": {
                "id": header.group(1),
                "category": category,
                "qcode": qcode,
                "location": f.get("A", "").split()[0] if f.get("A") else None,
                "validFrom": notam_time(f.get("B")),
                "validTo": notam_time(f.get("C")),
                "permanent": (f.get("C", "").strip().upper().startswith("PERM")),
                "schedule": " ".join(f.get("D", "").split()) or None,
                "lower": lower,
                "upper": upper,
                "text": " ".join(body.split()),
            },
        })
    return {
        "type": "FeatureCollection",
        "generated": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "UAE GCAA · Valid NOTAM summary (informational, not for operational use)",
        "sourcePage": SOURCE_PAGE,
        "features": features,
    }


def pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is needed to read a PDF: pip install pypdf")
    return "\n".join(f"=====PAGE {i + 1}=====\n{page.extract_text()}" for i, page in enumerate(PdfReader(path).pages))


def fetch_newest_pdf(destination: str) -> tuple[str, str]:
    request = urllib.request.Request(FOLDER_API, headers={"Accept": "application/json;odata=verbose", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        files = json.load(response)["d"]["Files"]["results"]
    valid = [f for f in files if "ValidNOTAM" in f["Name"]]
    if not valid:
        sys.exit("no ValidNOTAM file in the GCAA folder")
    newest = max(valid, key=lambda f: f["TimeLastModified"])
    url = "https://www.gcaa.gov.ae" + urllib.parse.quote(newest["ServerRelativeUrl"])
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(destination, "wb") as out:
        out.write(response.read())
    return newest["Name"], newest["TimeLastModified"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text")
    parser.add_argument("--pdf")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    generated = None
    if args.fetch:
        name, modified = fetch_newest_pdf("/tmp/gcaa-valid-notam.pdf")
        print(f"fetched {name} ({modified})")
        text, generated = pdf_text("/tmp/gcaa-valid-notam.pdf"), modified
    elif args.pdf:
        text = pdf_text(args.pdf)
    elif args.text:
        text = open(args.text, encoding="utf8").read()
    else:
        sys.exit("give --text, --pdf or --fetch")
    result = parse(text, generated)
    with open(args.out, "w", encoding="utf8") as out:
        json.dump(result, out, ensure_ascii=False, separators=(",", ":"))
    counts: dict[str, int] = {}
    for feature in result["features"]:
        counts[feature["properties"]["category"]] = counts.get(feature["properties"]["category"], 0) + 1
    print(f"{len(result['features'])} areas -> {args.out}  {counts}")


if __name__ == "__main__":
    main()

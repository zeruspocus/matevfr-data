#!/usr/bin/env python3
"""Adds the hand-reviewed AIP-supplement restrictions (curated_ar_sup_restrictions.json) to ar-notams.geojson.

Each curated entry names its SUP and carries its own validity, so the app stops drawing it by itself after `validTo`.
Entries that ended more than 7 days ago are not copied any more. Run after anac_notams.py.

Usage: merge_curated.py ar-notams.geojson curated_ar_sup_restrictions.json
"""
import datetime, json, sys

def main(notams_path, curated_path):
    data = json.load(open(notams_path))
    curated = json.load(open(curated_path))
    now = datetime.datetime.now(datetime.timezone.utc)
    have = {f["properties"]["id"] for f in data["features"]}
    added = 0
    for f in curated["features"]:
        p = f["properties"]
        ring = f["geometry"]["coordinates"][0]
        assert p["id"] and ring[0] == ring[-1] and len(ring) >= 4, f"bad curated entry {p.get('id')}"
        valid_to = datetime.datetime.fromisoformat(p["validTo"].replace("Z", "+00:00"))
        if now - valid_to > datetime.timedelta(days=7) or p["id"] in have:
            continue
        data["features"].append(f)
        added += 1
    json.dump(data, open(notams_path, "w"), ensure_ascii=False)
    print(f"{added} curated restriction(s) added")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

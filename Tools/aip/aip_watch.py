#!/usr/bin/env python3
"""Watches the ANAC AIP Argentina index for new editions of the chapters MateVFR uses.

Reads https://ais.anac.gob.ar/aip/enr and /aip/ad (the page loads them with an AJAX call, so the request must
send X-Requested-With), collects the edition label ("01/26 11-Jun-26") of each chapter, and compares it with
aip_baseline.json.

  * Same editions         -> exit 0, nothing happens.
  * New edition           -> prints the changes and exits 0; with --issue-file it writes the text of a GitHub
                             issue (the workflow opens it, and GitHub e-mails the owner).
  * Page changed / empty  -> exit 1. A failed workflow run is e-mailed by GitHub too, so a broken reader is never silent.

Usage: aip_watch.py --baseline aip_baseline.json [--issue-file issue.md] [--update-baseline]
"""
import argparse, html, json, re, sys, urllib.request

BASE = "https://ais.anac.gob.ar/aip/"
# Chapters the app's Argentina package is built from.
WATCH = [r"ENR-2\.1\b", r"ENR-2\.2\b", r"ENR-3\.[1-3]\b", r"ENR-4\.[1-5]\b", r"AD-1\.3\b"]
MIN_ROWS = {"enr": 30, "ad": 40}

def fetch(section):
    req = urllib.request.Request(BASE + section, headers={"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")

def parse(page):
    """-> {chapter heading: edition label}. The label sits in the link that follows each heading."""
    out = {}
    heads = [(m.start(), html.unescape(m.group(0)).replace("\xa0", " ").strip()) for m in re.finditer(r"(?:ENR|AD|GEN)-[\d.]+&nbsp;[^<]*", page)]
    for m in re.finditer(r'href="/descarga/aip-[0-9a-f]+"[^>]*>([^<]*)<', page):
        before = [h for h in heads if h[0] < m.start()]
        if before:
            out.setdefault(before[-1][1], []).append(m.group(1).strip())
    return {k: v for k, v in out.items()}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--issue-file")
    ap.add_argument("--update-baseline", action="store_true")
    a = ap.parse_args()
    current = {}
    for section in ("enr", "ad"):
        rows = parse(fetch(section))
        if len(rows) < MIN_ROWS[section]:
            print(f"ERROR: the {section.upper()} index returned {len(rows)} chapters (expected at least {MIN_ROWS[section]}). The ANAC page probably changed.")
            sys.exit(1)
        current.update(rows)
    watched = {k: v for k, v in current.items() if any(re.match(p, k) for p in WATCH)}
    if not watched:
        print("ERROR: none of the watched chapters were found. The ANAC page probably changed.")
        sys.exit(1)
    try:
        baseline = json.load(open(a.baseline))
    except FileNotFoundError:
        baseline = None
    if baseline is None or a.update_baseline:
        json.dump(watched, open(a.baseline, "w"), indent=1, ensure_ascii=False, sort_keys=True)
        print(f"Baseline written with {len(watched)} chapters.")
        return
    changes = []
    for k, v in sorted(watched.items()):
        if baseline.get(k) != v:
            changes.append(f"- {k}: {baseline.get(k)} -> {v}")
    for k in sorted(set(baseline) - set(watched)):
        changes.append(f"- {k}: no longer listed")
    if not changes:
        print("No new AIP editions.")
        return
    text = "\n".join(changes)
    print("New AIP Argentina editions:\n" + text)
    if a.issue_file:
        open(a.issue_file, "w").write(
            "The ANAC published new editions of AIP chapters that MateVFR's Argentina data is built from:\n\n" + text +
            "\n\nWhat to do: ask Claude in the MateVFR project to re-run the AIP extraction (Tools/aip/README.md) and publish a new Argentina package.\n"
            "After that, update `aip_baseline.json` (run `aip_watch.py --update-baseline`).\n")

if __name__ == "__main__":
    main()

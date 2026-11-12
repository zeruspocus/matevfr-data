#!/usr/bin/env python3
"""Copies the NOTAM / supplement assets of the `notam-data-v1` release into a folder laid out for the `web-data` branch.

The website cannot read release assets (the final download has no CORS header), but it can read raw.githubusercontent.com.
This script only prepares the folder; the workflow `web-copy.yml` pushes it. Rules:
  * a downloaded file is only used if it is non-empty, valid JSON and not an empty object/list;
  * if a file fails (download or validation), the copy already on the branch is kept, never replaced by a broken one;
  * `changed` is false when every file has the same sha256 as on the branch, so nothing is pushed.

Usage: web_copy.py --out OUT_DIR [--previous PREVIOUS_DIR] [--repo owner/name] [--release TAG]
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

FILES = [
    "ar-notams.geojson",
    "omae-notams.geojson",
    "uk-notams.geojson",
    "us-notams.geojson",
    "ar-supplements.json",
]


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_good_json(path):
    """Non-empty file holding valid JSON that is not an empty object, list or null."""
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    return data not in (None, {}, [], "")


def asset_updated_times(repo, release):
    out = subprocess.run(
        ["gh", "release", "view", release, "--repo", repo, "--json", "assets"],
        check=True, capture_output=True, text=True,
    ).stdout
    return {asset["name"]: asset.get("updatedAt") for asset in json.loads(out)["assets"]}


def download(repo, release, name, directory):
    subprocess.run(
        ["gh", "release", "download", release, "--repo", repo, "--pattern", name, "--dir", directory, "--clobber"],
        check=True, capture_output=True, text=True,
    )
    return os.path.join(directory, name)


def load_previous_index(previous):
    if not previous:
        return {}
    try:
        with open(os.path.join(previous, "notams", "index.json"), "rb") as handle:
            return json.load(handle).get("files", {})
    except (OSError, ValueError):
        return {}


def build(out, previous, repo, release):
    notams_out = os.path.join(out, "notams")
    os.makedirs(notams_out, exist_ok=True)
    previous_index = load_previous_index(previous)
    try:
        updated = asset_updated_times(repo, release)
    except (subprocess.CalledProcessError, ValueError) as error:
        print(f"could not list the release assets: {error}", file=sys.stderr)
        updated = {}

    files = {}
    changed = False
    with tempfile.TemporaryDirectory() as scratch:
        for name in FILES:
            target = os.path.join(notams_out, name)
            fresh = None
            try:
                candidate = download(repo, release, name, scratch)
                if is_good_json(candidate):
                    fresh = candidate
                else:
                    print(f"{name}: downloaded but empty or not valid JSON; keeping the previous copy", file=sys.stderr)
            except subprocess.CalledProcessError as error:
                print(f"{name}: download failed ({error.stderr.strip() if error.stderr else error}); keeping the previous copy", file=sys.stderr)

            if fresh:
                shutil.copyfile(fresh, target)
                entry = {
                    "bytes": os.path.getsize(target),
                    "sha256": sha256_of(target),
                    "assetUpdated": updated.get(name),
                }
            else:
                old = os.path.join(previous, "notams", name) if previous else None
                if old and os.path.exists(old) and is_good_json(old):
                    shutil.copyfile(old, target)
                    entry = previous_index.get(name) or {
                        "bytes": os.path.getsize(target), "sha256": sha256_of(target), "assetUpdated": None,
                    }
                else:
                    print(f"{name}: nothing good to publish and no previous copy; leaving it out", file=sys.stderr)
                    continue
            files[name] = entry
            if previous_index.get(name, {}).get("sha256") != entry["sha256"]:
                changed = True

    if set(previous_index) != set(files):
        changed = True

    index = {
        "updated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
    }
    with open(os.path.join(notams_out, "index.json"), "w") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")
    return changed, files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--previous")
    parser.add_argument("--repo", default="zeruspocus/matevfr-data")
    parser.add_argument("--release", default="notam-data-v1")
    args = parser.parse_args()
    changed, files = build(args.out, args.previous, args.repo, args.release)
    print(f"files: {', '.join(files) or 'none'}; changed: {changed}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as handle:
            handle.write(f"changed={'true' if changed else 'false'}\n")
            handle.write(f"count={len(files)}\n")


if __name__ == "__main__":
    main()

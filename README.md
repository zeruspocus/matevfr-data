# MateVFR aviation data

Downloadable aviation packages for [MateVFR](https://github.com/zeruspocus/MateVFR) — an offline-first VFR moving map for iPhone/iPad.

This repo hosts only data: per-country GeoJSON packages derived from openAIP exports, packed by `Tools/build_package_archives.py` in the main app repo. It contains no app source code.

Each [Release](../../releases) carries the `.tar` archives and a `catalog.json` the app fetches to discover what's available, with a SHA-256 checksum per archive.

**Data terms:** each package's own `manifest.json` (inside its archive) declares its source, license, and limitations — mostly openAIP exports, unverified, reference/planning use only, not for navigation.

## NOTAM areas (UAE)

`.github/workflows/gcaa-notams.yml` builds `omae-notams.geojson` from the GCAA's daily Valid NOTAM summary
(`Tools/notams/gcaa_notams.py`) and publishes it as an asset of the `notam-data-v1` release. The MateVFR apps download it.
Informational only: not an official product and not for operational use.

`.github/workflows/anac-notams.yml` does the same for Argentina (ANAC / EANA list, five FIR) with `Tools/notams/anac_notams.py`
and publishes `ar-notams.geojson` in the same release.

`us-tfr.yml` (FAA temporary flight restrictions, `us_tfr.py`) and `uk-notams.yml` (NATS bulletin, `uk_notams.py`) publish
`us-notams.geojson` and `uk-notams.geojson` in the same release.

## `web-data` branch (for matevfr.com)

A web page cannot read the assets of a GitHub release (the final download carries no `Access-Control-Allow-Origin` header),
but `raw.githubusercontent.com` does send `Access-Control-Allow-Origin: *`. So `.github/workflows/web-copy.yml`
(`Tools/web/web_copy.py`) copies these five release files to the `web-data` branch, where the website reads them:

```
notams/ar-notams.geojson   notams/omae-notams.geojson   notams/uk-notams.geojson   notams/us-notams.geojson
notams/ar-supplements.json notams/index.json
```

e.g. `https://raw.githubusercontent.com/zeruspocus/matevfr-data/web-data/notams/ar-notams.geojson`.
`index.json` lists each file with its size, `sha256` and the release asset's `updatedAt`, plus the time of the copy.

- **Written only by the `web-copy` workflow** (every 30 minutes, after any of the five data workflows succeeds, or by hand). **Do not edit the branch by hand**: it is replaced by a single forced commit whenever a file changes.
- A file that is empty or not valid JSON is never copied; the previous copy stays. Nothing is pushed when no file changed.
- The release `notam-data-v1` and the workflows that fill it are unchanged: the apps keep reading the release, not this branch.

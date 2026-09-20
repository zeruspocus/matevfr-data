# MateVFR aviation data

Downloadable aviation packages for [MateVFR](https://github.com/zeruspocus/MateVFR) — an offline-first VFR moving map for iPhone/iPad.

This repo hosts only data: per-country GeoJSON packages derived from openAIP exports, packed by `Tools/build_package_archives.py` in the main app repo. It contains no app source code.

Each [Release](../../releases) carries the `.tar` archives and a `catalog.json` the app fetches to discover what's available, with a SHA-256 checksum per archive.

**Data terms:** each package's own `manifest.json` (inside its archive) declares its source, license, and limitations — mostly openAIP exports, unverified, reference/planning use only, not for navigation.

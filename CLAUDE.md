# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A public page that compares Norwegian Cruise Line's published cabin prices on one sailing: Norwegian Joy, Nov 20 to 23, 2026, 3 nights round trip from Miami (Nassau, Great Stirrup Cay). It is for comparing rates, not booking.

Built from the owner's June 2027 tool (public repo DASatizabal/cruise-cabin-comparison). The page is `index.html` (HTML, CSS and JavaScript in one file). It reads `data/prices.json` and, when fresh, `data/counts.json`. Background, rules and probe findings are in `NOTES.md`; read it before changing pricing logic.

## Rules

- Semantic Versioning. `APP_VERSION` in `index.html` must match the newest `## [x.y.z]` entry in `CHANGELOG.md`. Add a changelog entry for every release.
- Run `python3 tools/check_release.py` before committing. GitHub Actions runs it on every push and pull request.
- Every data file the page reads has a format check: `tools/check_prices.py`, `tools/check_counts.py`.
- NEVER call NCL's `cabin/manage-cabin` (it carries recommendAndHold and holds a real cabin), `api/book`, `booking/api/recommended-cabin`, or anything that holds or books. `request()` refuses any address containing "manage-cabin" or "hold", and stops on any NCL API answer containing "hold" or "heldUntil". Keep both guards.
- NCL's ids (itinerary code, packageId, sailingId, ship code) are looked up every run, never typed in. Only the ship, date, length and home port are fixed (`SAILING` in `tools/fetch_prices.py`).
- Never guess a number. Anything NCL doesn't show is null with a warning, and the page says "Not found on NCL today".
- One owner-approved exception: the "Florida resident rate (estimate)" switch (default on) takes `FL_RESIDENT_OFF` (33.8%, from ($318 + $368) / ($478 + $558), quotes matched to I4 and BB) off the cruise fare only, not taxes, worked out by the owner's method from an NCL consultant's quotes on 2026-10-13 (NOTES.md). Keep it labeled as an estimate and switchable off.
- CruiseFeed is never called from this repo.
- Privacy: public repo. No guest names, dates of birth, Latitudes numbers or reservation numbers in any file, ever. The page asks for ages only.
- Steps written for the owner must be complete: no "same as above", no choices left open, and no em dashes.
- Family members use Android and iPhone. Keep the page working at phone width (360 px, no sideways scrolling).

## Data

- `data/prices.json` (schema 1): written by `tools/fetch_prices.py`. Same layout as the June repo's schema 2 for one sailing, plus `warnings`, `sailings[].ncl_ids` and `sailings[].kids_sail_free` (NCL's offer text and the cabin types it covers, or null). `taxes_per_guest`, `gratuities` and each entry of `rates` may be null, only with a warning.
- `data/counts.json` (schema 1): written by `tools/fetch_counts.py`, same as June.
- `tools/decide_run.py`: first job of the refresh. Scheduled runs skip work done that UTC day; every run skips from the sail date on.

## Automation

- `.github/workflows/refresh-prices.yml`: GitHub schedule 10:17, 14:47, 19:37 UTC (only on `main`), manual runs, and pushes to `joy-page-build` that touch the tools (test only, never commit data). Jobs: decide, refresh (prices), publish, counts, publish-counts.
- `.github/workflows/deploy-pages.yml`: Pages source "GitHub Actions". Build and deploy in separate jobs, artifact `github-pages-<label>-<run attempt>`, deploy retried once after 30 seconds (deploy-pages issue 451). Publishes only from `main`.
- `.github/workflows/check.yml`: release gate.
- Every job on `ubuntu-24.04`. Actions on Node.js 24 majors: checkout v7, configure-pages v6, upload-pages-artifact v5, deploy-pages v5.

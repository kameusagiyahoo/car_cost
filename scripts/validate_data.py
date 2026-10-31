#!/usr/bin/env python3
"""Validate TCO data and report evidence limitations. Python standard library only."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []
warnings = []

def fail(where, msg):
    errors.append(f"{where}: {msg}")

def warn(where, msg):
    warnings.append(f"{where}: {msg}")

def load(name):
    try:
        with (ROOT / "data" / name).open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        fail(name, str(e))
        return {}

def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0

vehicles = load("vehicles.json").get("vehicles", [])
assumptions = load("assumptions.json")
listings = load("used-listings.json").get("listings", [])
resale = load("resale-observations.json").get("series", [])
ages = load("resale-age-series.json").get("series", [])

known = set()
for v in vehicles:
    vid = v.get("id")
    if not vid or vid in known:
        fail("vehicles", f"missing or duplicate id {vid!r}")
    known.add(vid)
    pts = set()
    for t in v.get("powertrains", []):
        key = (vid, t.get("id"))
        if key in pts:
            fail("vehicles", f"duplicate powertrain {key}")
        pts.add(key)
        if not positive(t.get("newPriceMan")) or not positive(t.get("kmPerLiter")):
            fail("vehicles", f"invalid price/fuel economy {key}")
        e = t.get("priceEvidence") or {}
        if e.get("kind") != "assumption" and not (e.get("url") and e.get("retrievedAt")):
            fail("vehicles", f"missing official evidence {key}")

seen_urls = set()
for i, x in enumerate(listings):
    loc = f"used-listings[{i}]"
    if x.get("vehicleId") not in known:
        fail(loc, "unknown vehicle")
    if not positive(x.get("totalMan")) or not positive(x.get("km")):
        fail(loc, "invalid price or mileage")
    if not isinstance(x.get("modelYear"), int) or not 1990 <= x["modelYear"] <= 2026:
        fail(loc, "invalid model year")
    url = x.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        fail(loc, "missing HTTPS source URL")
    elif url in seen_urls:
        warn(loc, "duplicate URL; inspect for duplicate listing")
    seen_urls.add(url)
    for field in ("grade", "drive", "seats", "verifiedAt"):
        if x.get(field) is None:
            warn(loc, f"missing {field}; excluded from strict comparable group")

for i, x in enumerate(resale):
    loc = f"resale-observations[{i}]"
    amounts, kms = x.get("valuesMan", []), x.get("sourceKm", [])
    if len(amounts) != len(kms) or not amounts:
        fail(loc, "buyback prices and mileages must align")
        continue
    if any(not positive(n) for n in amounts) or any(not positive(n) for n in kms):
        fail(loc, "invalid individual observation")
    for field in ("drive", "seats", "repairHistory"):
        if x.get(field) is None:
            warn(loc, f"missing {field}; not eligible for regression training")
    if not x.get("url"):
        fail(loc, "missing source URL")

for i, series in enumerate(ages):
    loc = f"resale-age-series[{i}]"
    observations = series.get("observations", [])
    if not series.get("url") or not observations:
        fail(loc, "missing source or observations")
    for obs in observations:
        if not positive(obs.get("averageBuybackMan")):
            fail(loc, "invalid average buyback price")
        if "averageKm" not in obs:
            warn(loc, "averageKm absent; cannot separate age and mileage")

if not positive(assumptions.get("fuelYenPerLiter")):
    fail("assumptions", "fuelYenPerLiter must be positive")

for item in warnings:
    print("WARNING:", item)
for item in errors:
    print("ERROR:", item)
print(f"Validated {len(vehicles)} vehicles, {len(listings)} used listings, "
      f"{len(resale)} resale groups, {len(ages)} age series: "
      f"{len(errors)} errors, {len(warnings)} warnings")
sys.exit(1 if errors else 0)

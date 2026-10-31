#!/usr/bin/env python3
"""Stage reviewed listing records. Dry-run by default; --apply writes after validation."""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "used-listings.json"
REQUIRED = ("vehicleId", "powertrain", "grade", "modelYear", "km",
            "totalMan", "source", "url", "repairHistory", "seats",
            "drive", "verifiedAt")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path, help="JSON with listings array")
    parser.add_argument("--apply", action="store_true", help="write validated records")
    args = parser.parse_args()
    try:
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        current = json.loads(TARGET.read_text(encoding="utf-8"))
        records = candidate["listings"]
        if not isinstance(records, list) or not records:
            raise ValueError("listings must be a nonempty array")
        vehicles = json.loads((ROOT / "data" / "vehicles.json").read_text(encoding="utf-8"))["vehicles"]
        known = {(v["id"], t["id"]) for v in vehicles for t in v["powertrains"]}
        urls = {x["url"] for x in current["listings"]}
        new = []
        for i, x in enumerate(records):
            if not isinstance(x, dict):
                raise ValueError(f"item {i}: object required")
            missing = [k for k in REQUIRED if k not in x or x[k] in (None, "")]
            if missing:
                raise ValueError(f"item {i}: missing {missing}")
            if (x["vehicleId"], x["powertrain"]) not in known:
                raise ValueError(f"item {i}: unknown vehicle or powertrain")
            if type(x["modelYear"]) is not int or not 1990 <= x["modelYear"] <= 2026:
                raise ValueError(f"item {i}: invalid model year")
            if type(x["km"]) not in (int, float) or not math.isfinite(x["km"]) or not 0 <= x["km"] <= 1000000:
                raise ValueError(f"item {i}: invalid mileage")
            if type(x["totalMan"]) not in (int, float) or not math.isfinite(x["totalMan"]) or not 0 < x["totalMan"] <= 10000:
                raise ValueError(f"item {i}: invalid total price")
            if type(x["seats"]) is not int or not 1 <= x["seats"] <= 10:
                raise ValueError(f"item {i}: invalid seat count")
            if x["drive"] not in ("2WD", "4WD") or x["repairHistory"] not in ("none", "yes", "unknown"):
                raise ValueError(f"item {i}: invalid drive or repair history")
            if not isinstance(x["verifiedAt"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x["verifiedAt"]):
                raise ValueError(f"item {i}: invalid verification date")
            if not isinstance(x["url"], str):
                raise ValueError(f"item {i}: URL must be a string")
            u = urlsplit(x["url"])
            if u.scheme != "https" or not u.netloc:
                raise ValueError(f"item {i}: invalid HTTPS URL")
            if x["url"] in urls:
                raise ValueError(f"item {i}: duplicate URL {x['url']}")
            urls.add(x["url"])
            new.append(x)
        current["listings"].extend(new)
        print(f"Candidate records: {len(new)}; total after merge: {len(current['listings'])}")
        if not args.apply:
            print("DRY RUN: no files modified. Use --apply after manual source verification.")
            return 0
        original = TARGET.read_text(encoding="utf-8")
        try:
            TARGET.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_data.py")],
                                    cwd=ROOT, check=False)
            if result.returncode:
                raise ValueError("data validation failed; restoring original")
        except Exception:
            TARGET.write_text(original, encoding="utf-8")
            raise
        print("Updated data/used-listings.json; review git diff before commit.")
        return 0
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())

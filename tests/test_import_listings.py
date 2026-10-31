#!/usr/bin/env python3
"""Regression tests for listing import. No third-party dependencies."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "vehicleId": "sienta", "powertrain": "hev", "grade": "Z",
    "modelYear": 2023, "km": 30000, "totalMan": 280,
    "source": "fixture only", "url": "https://example.org/fixture-123",
    "repairHistory": "none", "seats": 7, "drive": "2WD",
    "verifiedAt": "2026-10-31",
}

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data").mkdir()
        (self.root / "scripts").mkdir()
        for name in ("vehicles.json", "assumptions.json", "used-listings.json",
                     "resale-observations.json", "resale-age-series.json"):
            shutil.copy2(ROOT / "data" / name, self.root / "data" / name)
        for name in ("import_listings.py", "validate_data.py"):
            shutil.copy2(ROOT / "scripts" / name, self.root / "scripts" / name)
        self.target = self.root / "data" / "used-listings.json"
        self.original = self.target.read_bytes()

    def run_import(self, record, apply=False):
        candidate = self.root / "candidate.json"
        candidate.write_text(json.dumps({"listings": [record]}), encoding="utf-8")
        command = [sys.executable, str(self.root / "scripts" / "import_listings.py"), str(candidate)]
        if apply:
            command.append("--apply")
        return subprocess.run(command, capture_output=True, text=True, timeout=20)

    def test_dry_run_does_not_write(self):
        result = self.run_import(dict(BASE))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY RUN", result.stdout)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_apply_adds_valid_record(self):
        result = self.run_import(dict(BASE), apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        records = json.loads(self.target.read_text(encoding="utf-8"))["listings"]
        self.assertEqual(records[-1]["url"], BASE["url"])
        self.assertEqual(len(records), len(json.loads(self.original)["listings"]) + 1)

    def test_duplicate_url_rejected(self):
        existing = json.loads(self.original)["listings"][0]["url"]
        result = self.run_import({**BASE, "url": existing}, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_missing_field_rejected(self):
        bad = dict(BASE)
        bad.pop("drive")
        result = self.run_import(bad, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_unknown_model_rejected(self):
        result = self.run_import({**BASE, "vehicleId": "not-a-model"}, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_invalid_mileage_rejected(self):
        result = self.run_import({**BASE, "km": -100}, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_invalid_price_rejected(self):
        result = self.run_import({**BASE, "totalMan": 0}, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_invalid_drive_rejected(self):
        result = self.run_import({**BASE, "drive": "unknown"}, apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_validation_failure_rolls_back(self):
        assumptions = self.root / "data" / "assumptions.json"
        data = json.loads(assumptions.read_text(encoding="utf-8"))
        data["fuelYenPerLiter"] = -1
        assumptions.write_text(json.dumps(data), encoding="utf-8")
        result = self.run_import(dict(BASE), apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_duplicate_urls_within_candidate_rejected(self):
        candidate = self.root / "candidate.json"
        candidate.write_text(json.dumps({"listings": [BASE, BASE]}), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "import_listings.py"), str(candidate), "--apply"],
            capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_validator_passes_current_repository_data(self):
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts" / "validate_data.py")],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == "__main__":
    unittest.main()

import csv
import unittest
from pathlib import Path

from monitor.validate_historical_csv import validate_file, validate_rows

ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "human_verified_draws_2023-01.csv"


class TestHistoricalCsvPreflight(unittest.TestCase):
    def setUp(self):
        with ARCHIVE.open(newline="", encoding="utf-8") as handle:
            self.rows = list(csv.DictReader(handle))

    def test_checked_in_archive_passes(self):
        self.assertEqual(validate_file(ARCHIVE), [])

    def test_rejects_unverified_record(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["verification_status"] = "ocr_only"
        self.assertTrue(any("not human_verified" in e for e in validate_rows(rows)))

    def test_rejects_missing_source_reference(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["source_file"] = ""
        self.assertTrue(any("no source_file" in e for e in validate_rows(rows)))

    def test_rejects_missing_prize_position(self):
        rows = [dict(row) for row in self.rows if not (
            row["date"] == "2023-01-10" and row["draw"] == "8PM"
            and row["prize_tier"] == "5th" and row["position"] == "100"
        )]
        self.assertTrue(any("expected 132 rows" in e for e in validate_rows(rows)))
        self.assertTrue(any("5th must contain positions" in e for e in validate_rows(rows)))

    def test_rejects_bad_number_format(self):
        rows = [dict(row) for row in self.rows]
        rows[0]["winning_number"] = "62A O7390"
        self.assertTrue(any("invalid 1st number" in e for e in validate_rows(rows)))

    def test_rejects_wrong_consolation(self):
        rows = [dict(row) for row in self.rows]
        rows[1]["winning_number"] = "99999"
        self.assertTrue(any("consolation does not match" in e for e in validate_rows(rows)))

    def test_excludes_six_pm_rows(self):
        rows = [dict(row) for row in self.rows]
        rows.append({**rows[0], "draw": "6PM"})
        self.assertEqual(validate_rows(rows), [])


if __name__ == "__main__":
    unittest.main()

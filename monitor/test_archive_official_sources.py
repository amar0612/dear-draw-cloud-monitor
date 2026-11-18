import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from monitor.archive_official_sources import archive_sources, official_filename, read_draws


class TestOfficialSourceArchive(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csv_path = self.root / "draws.csv"
        with self.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", "draw"])
            writer.writeheader()
            writer.writerows([
                {"date": "2023-01-10", "draw": "8PM"},
                {"date": "2023-01-31", "draw": "1PM"},
                {"date": "2023-01-10", "draw": "6PM"},
            ])

    def tearDown(self):
        self.temp.cleanup()

    def test_official_filename_mapping(self):
        self.assertEqual(official_filename("2023-01-10", "8PM"), "EN100123.PDF")
        self.assertEqual(official_filename("2023-01-31", "1PM"), "MN310123.PDF")
        with self.assertRaises(ValueError):
            official_filename("2023-01-10", "6PM")

    def test_reads_only_nagaland_slots(self):
        self.assertEqual(read_draws(self.csv_path), [
            ("2023-01-10", "8PM"), ("2023-01-31", "1PM")
        ])

    def test_downloads_and_records_hash_without_marking_verified(self):
        payloads = {
            "EN100123.PDF": b"%PDF-1.4 official gazette A",
            "MN310123.PDF": b"%PDF-1.4 official gazette B",
        }
        def fake_fetch(url):
            return payloads[url.rsplit("/", 1)[-1]]

        out = self.root / "official"
        results = archive_sources(self.csv_path, out, fetcher=fake_fetch)
        self.assertEqual(len(results), 2)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(len(manifest), 2)
        for item in manifest:
            self.assertEqual(item["verification_status"], "downloaded_pending_number_comparison")
            data = (out / item["source_file"]).read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())
            self.assertTrue(data.startswith(b"%PDF-"))

    def test_refuses_non_pdf_response(self):
        def fake_fetch(_url):
            return b"<html>not a PDF</html>"
        out = self.root / "bad"
        results = archive_sources(self.csv_path, out, fetcher=fake_fetch)
        self.assertTrue(all(x["verification_status"] == "source_unavailable_or_error" for x in results))
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(len(manifest), 2)
        self.assertTrue(all(x["verification_status"] == "source_unavailable_or_error" for x in manifest))

    def test_dry_run_does_not_write_files(self):
        out = self.root / "dry"
        results = archive_sources(self.csv_path, out, dry_run=True)
        self.assertEqual(len(results), 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()

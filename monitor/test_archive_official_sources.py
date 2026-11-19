import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from monitor.archive_official_sources import archive_sources, official_filename, read_draws, source_candidates


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
        self.assertEqual(official_filename("2023-01-10", "8PM"), "ED100123.pdf")
        self.assertEqual(official_filename("2023-01-31", "1PM"), "MD310123.pdf")
        candidates = source_candidates("2023-01-10", "8PM")
        self.assertEqual(candidates[0][0], "official_nagaland_gazette")
        self.assertEqual(candidates[-1][0], "independent_archive_pdf")
        self.assertTrue(any(url.endswith("/2023-01-10/8pm.pdf") for _, url in candidates))
        self.assertTrue(any(url.endswith("EL100123.pdf") for _, url in candidates))
        self.assertTrue(any(url.endswith("ML310123.pdf") for _, url in source_candidates("2023-01-31", "1PM")))
        with self.assertRaises(ValueError):
            official_filename("2023-01-10", "6PM")

    def test_reads_only_nagaland_slots(self):
        self.assertEqual(read_draws(self.csv_path), [
            ("2023-01-10", "8PM"), ("2023-01-31", "1PM")
        ])

    def test_downloads_and_records_hash_without_marking_verified(self):
        payloads = {
            "ED100123.pdf": b"%PDF-1.4 mirror copy A",
            "MD310123.pdf": b"%PDF-1.4 mirror copy B",
        }
        def fake_fetch(url):
            name = url.rsplit("/", 1)[-1]
            if name not in payloads:
                raise FileNotFoundError("simulated official archive 404")
            return payloads[name]

        out = self.root / "official"
        results = archive_sources(self.csv_path, out, fetcher=fake_fetch)
        self.assertEqual(len(results), 2)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(len(manifest), 2)
        for item in manifest:
            self.assertEqual(item["source_type"], "third_party_mirror_copy")
            self.assertEqual(item["verification_status"], "mirror_copy_pending_official_comparison")
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

    def test_offset_and_limit_bound_the_batch(self):
        calls = []
        def fake_fetch(url):
            calls.append(url)
            raise FileNotFoundError("not found")
        results = archive_sources(
            self.csv_path, self.root / "batch", fetcher=fake_fetch,
            offset=1, limit=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["date"], "2023-01-31")
        self.assertEqual(results[0]["draw"], "1PM")
        self.assertEqual(len(calls), 5)

    def test_rejects_invalid_batch_bounds(self):
        with self.assertRaises(ValueError):
            archive_sources(self.csv_path, self.root / "invalid", dry_run=True, offset=-1)
        with self.assertRaises(ValueError):
            archive_sources(self.csv_path, self.root / "invalid", dry_run=True, limit=0)


    def test_date_window_filters_candidates_before_offset_and_limit(self):
        results = archive_sources(
            self.csv_path, self.root / "window", dry_run=True,
            start_date="2023-01-15", end_date="2023-01-31",
            offset=0, limit=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["date"], "2023-01-31")
        self.assertEqual(results[0]["draw"], "1PM")

    def test_rejects_reversed_date_window(self):
        with self.assertRaises(ValueError):
            archive_sources(
                self.csv_path, self.root / "reversed", dry_run=True,
                start_date="2023-02-01", end_date="2023-01-01"
            )

    def test_dry_run_does_not_write_files(self):
        out = self.root / "dry"
        results = archive_sources(self.csv_path, out, dry_run=True)
        self.assertEqual(len(results), 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()

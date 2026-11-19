import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from monitor.archive_official_sources import (
    archive_sources, official_filename, read_draws, source_candidates,
    _extract_links,
)


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

    def test_official_filename_mapping_and_supported_slots(self):
        self.assertEqual(official_filename("2023-01-10", "8PM"), "ED100123.pdf")
        self.assertEqual(official_filename("2023-01-31", "1PM"), "MD310123.pdf")
        with self.assertRaises(ValueError):
            official_filename("2023-01-10", "6PM")

    def test_registry_drives_all_applicable_sources_and_excludes_bad_leads(self):
        candidates = source_candidates("2023-01-10", "8PM")
        urls = [url for _, url in candidates]
        kinds = [kind for kind, _ in candidates]
        self.assertGreaterEqual(len(candidates), 18)
        self.assertTrue(any("nagalandlotteries.com/old_results/EN100123.PDF" in u for u in urls))
        self.assertTrue(any("lotterysambad.co/2023/" in u for u in urls))
        self.assertTrue(any("lotterysambadfax.com/dl/2023-01-10/8pm.pdf" in u for u in urls))
        self.assertTrue(any("dear1crore.com" in u for u in urls))
        self.assertFalse(any("nagalandstatelotteries.in" in u for u in urls))
        self.assertFalse(any("sangbadlottery.com" in u for u in urls))
        self.assertFalse(any("api.sambad.com" in u for u in urls))
        self.assertFalse(any("kllotteryresults.in" in u for u in urls))

    def test_reads_only_nagaland_slots(self):
        self.assertEqual(read_draws(self.csv_path), [
            ("2023-01-10", "8PM"), ("2023-01-31", "1PM")
        ])

    def test_html_calendar_links_are_discovered_for_exact_date(self):
        page = b'<a href="/pdf/ED100123.pdf">8 PM result</a><a href="/pdf/ED110123.pdf">next day</a>'
        links = _extract_links(page, "https://example.test/2023/", "2023-01-10", "8PM")
        self.assertEqual(links, ["https://example.test/pdf/ED100123.pdf"])
        generic = b'<a href="/download/result.pdf">Download 8PM PDF</a>'
        child_links = _extract_links(generic, "https://example.test/results/2023-01-10/", "2023-01-10", "8PM")
        self.assertEqual(child_links, ["https://example.test/download/result.pdf"])
        two_slots = b'<a href="/download/one.pdf">1PM PDF</a><a href="/download/eight.pdf">8PM PDF</a>'
        only_eight = _extract_links(two_slots, "https://example.test/results/2023-01-10/", "2023-01-10", "8PM")
        self.assertEqual(only_eight, ["https://example.test/download/eight.pdf"])

    def test_retains_multiple_source_copies_and_flags_hash_conflict(self):
        calls = []
        def fake_fetch(url):
            calls.append(url)
            if "ED100123.pdf" in url:
                return b"%PDF-1.4 source A"
            if "/2023-01-10/8pm.pdf" in url:
                return b"%PDF-1.4 source B"
            if "MD310123.pdf" in url:
                return b"%PDF-1.4 same 1pm source"
            if "/2023-01-31/1pm.pdf" in url:
                return b"%PDF-1.4 same 1pm source"
            raise FileNotFoundError("simulated source miss")

        out = self.root / "archive"
        results = archive_sources(self.csv_path, out, fetcher=fake_fetch)
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(len(calls), 36)
        eight = next(x for x in results if x["draw"] == "8PM")
        one = next(x for x in results if x["draw"] == "1PM")
        self.assertEqual(eight["successful_pdf_copies"], 2)
        self.assertEqual(eight["distinct_sha256"], 2)
        self.assertEqual(eight["comparison_status"], "source_content_conflict")
        self.assertEqual(one["successful_pdf_copies"], 2)
        self.assertEqual(one["distinct_sha256"], 1)
        self.assertEqual(one["comparison_status"], "identical_copies")

        manifest = json.loads((out / "manifest.json").read_text())
        source_rows = [x for x in manifest if x.get("source_url")]
        self.assertEqual(len(source_rows), 4)
        for item in source_rows:
            data = (out / item["source_file"]).read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(data).hexdigest())
            self.assertTrue(data.startswith(b"%PDF-"))
            self.assertNotEqual(item["verification_status"], "human_verified")
        self.assertTrue(any(x.get("comparison_status") == "source_content_conflict" for x in manifest))

    def test_source_failure_does_not_prevent_later_sources(self):
        reached = []
        def fake_fetch(url):
            reached.append(url)
            if "MD310123.pdf" in url:
                return b"%PDF-1.4 later source"
            raise FileNotFoundError("miss")
        results = archive_sources(
            self.csv_path, self.root / "later", fetcher=fake_fetch,
            offset=1, limit=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["successful_pdf_copies"], 1)
        self.assertGreaterEqual(len(reached), 18)

    def test_dry_run_includes_all_applicable_registry_sources_without_writing(self):
        out = self.root / "dry"
        results = archive_sources(self.csv_path, out, dry_run=True, limit=1)
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(len(results[0]["candidate_sources"]), 18)
        self.assertFalse(out.exists())

    def test_offset_limit_and_date_window(self):
        results = archive_sources(
            self.csv_path, self.root / "window", dry_run=True,
            start_date="2023-01-15", end_date="2023-01-31",
            offset=0, limit=1
        )
        self.assertEqual([(x["date"], x["draw"]) for x in results], [("2023-01-31", "1PM")])

    def test_rejects_invalid_batch_bounds_and_reversed_window(self):
        with self.assertRaises(ValueError):
            archive_sources(self.csv_path, self.root / "invalid", dry_run=True, offset=-1)
        with self.assertRaises(ValueError):
            archive_sources(self.csv_path, self.root / "invalid", dry_run=True, limit=0)
        with self.assertRaises(ValueError):
            archive_sources(self.csv_path, self.root / "reversed", dry_run=True,
                            start_date="2023-02-01", end_date="2023-01-01")


if __name__ == "__main__":
    unittest.main()

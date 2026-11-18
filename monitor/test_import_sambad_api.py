import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_sambad_api import normalize_result
from validate_result import validate_result


def api_payload(draw="1pm", date="18-11-2026"):
    return {
        "success": True,
        "data": {
            "status": "published",
            "lottery": "dear",
            "slot": draw,
            "date": date,
            "first": {"series": "08A", "number": "07390"},
            "prizes": [
                {"tier": "cons", "match": "number", "numbers": ["07390"]},
                {"tier": "2nd", "match": "number", "numbers": [f"{n:05d}" for n in range(1, 11)]},
                {"tier": "3rd", "match": "last4", "numbers": [f"{n:04d}" for n in range(1, 11)]},
                {"tier": "4th", "match": "last4", "numbers": [f"{n:04d}" for n in range(11, 21)]},
                {"tier": "5th", "match": "last4", "numbers": [f"{n:04d}" for n in range(1, 101)]},
            ],
        },
    }


class TestSambadApiNormalization(unittest.TestCase):
    def test_normalizes_complete_1pm_result(self):
        record = normalize_result(api_payload(), "1pm", "2026-11-18")
        self.assertEqual(record["draw"], "1PM")
        self.assertEqual(record["prizes"]["1st"], ["08A 07390"])
        self.assertEqual(record["verification_status"], "API_IMPORTED_NOT_GAZETTE_VERIFIED")
        self.assertEqual(validate_result(record), [])

    def test_normalizes_complete_8pm_result(self):
        record = normalize_result(api_payload(draw="8pm"), "8pm", "2026-11-18")
        self.assertEqual(record["draw"], "8PM")
        self.assertEqual(validate_result(record), [])

    def test_preserves_leading_zeroes(self):
        record = normalize_result(api_payload(), "1pm", "2026-11-18")
        self.assertEqual(record["prizes"]["Consolation"], ["07390"])
        self.assertEqual(record["prizes"]["3rd"][0], "0001")

    def test_rejects_unpublished_result(self):
        payload = api_payload()
        payload["data"]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "not published"):
            normalize_result(payload, "1pm", "2026-11-18")

    def test_rejects_wrong_draw_slot(self):
        with self.assertRaisesRegex(ValueError, "different draw slot"):
            normalize_result(api_payload(draw="8pm"), "1pm", "2026-11-18")

    def test_rejects_wrong_draw_date(self):
        with self.assertRaisesRegex(ValueError, "different draw date"):
            normalize_result(api_payload(), "1pm", "2026-11-17")

    def test_rejects_wrong_lottery(self):
        payload = api_payload()
        payload["data"]["lottery"] = "other"
        with self.assertRaisesRegex(ValueError, "Unexpected lottery"):
            normalize_result(payload, "1pm", "2026-11-18")

    def test_rejects_incomplete_prize_tier(self):
        payload = api_payload()
        payload["data"]["prizes"][-1]["numbers"].pop()
        record = normalize_result(payload, "1pm", "2026-11-18")
        self.assertTrue(validate_result(record))


if __name__ == "__main__":
    unittest.main()

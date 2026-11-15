
import unittest

from monitor.validate_result import validate_result


def sample_result():
    return {
        "date": "2026-11-15",
        "draw": "1PM",
        "prizes": {
            "1st": ["12A 34567"],
            "Consolation": ["34567"],
            "2nd": [f"{i:05d}" for i in range(1, 11)],
            "3rd": [f"{i:04d}" for i in range(1, 11)],
            "4th": [f"{i:04d}" for i in range(11, 21)],
            "5th": [f"{i:04d}" for i in range(1, 101)],
        },
    }


class TestResultValidator(unittest.TestCase):

    def test_valid_1pm_result(self):
        self.assertEqual(validate_result(sample_result()), [])

    def test_valid_8pm_result(self):
        record = sample_result()
        record["draw"] = "8PM"
        self.assertEqual(validate_result(record), [])

    def test_rejects_6pm(self):
        record = sample_result()
        record["draw"] = "6PM"
        self.assertTrue(validate_result(record))

    def test_rejects_wrong_prize_count(self):
        record = sample_result()
        record["prizes"]["2nd"].pop()
        self.assertTrue(validate_result(record))

    def test_rejects_wrong_consolation(self):
        record = sample_result()
        record["prizes"]["Consolation"] = ["99999"]
        self.assertTrue(validate_result(record))

    def test_preserves_leading_zeroes(self):
        record = sample_result()
        record["prizes"]["2nd"][0] = "00001"
        self.assertEqual(validate_result(record), [])

    def test_rejects_invalid_date(self):
        record = sample_result()
        record["date"] = "2026-15-45"
        self.assertTrue(validate_result(record))


if __name__ == "__main__":
    unittest.main()

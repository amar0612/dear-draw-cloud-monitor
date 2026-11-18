import csv
import unittest
from collections import defaultdict
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "human_verified_draws_2023-01.csv"

EXPECTED = {
    "1st": 1,
    "Consolation": 1,
    "2nd": 10,
    "3rd": 10,
    "4th": 10,
    "5th": 100,
}

PATTERNS = {
    "1st": __import__("re").compile(r"^[0-9]{2}[A-Z] [0-9]{5}$"),
    "Consolation": __import__("re").compile(r"^[0-9]{5}$"),
    "2nd": __import__("re").compile(r"^[0-9]{5}$"),
    "3rd": __import__("re").compile(r"^[0-9]{4}$"),
    "4th": __import__("re").compile(r"^[0-9]{4}$"),
    "5th": __import__("re").compile(r"^[0-9]{4}$"),
}


def load_draws():
    grouped = defaultdict(list)
    with ARCHIVE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "draw", "prize_tier", "position", "winning_number",
                    "verification_status", "source_file"}
        if not required.issubset(reader.fieldnames or []):
            raise AssertionError(f"Missing CSV columns: {required - set(reader.fieldnames or [])}")
        for row in reader:
            grouped[(row["date"], row["draw"], row["prize_tier"])].append(row)
    return grouped


class TestHumanVerifiedJanuaryArchive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.draws = load_draws()

    def test_contains_only_the_two_confirmed_nagaland_draws(self):
        keys = {(date, draw) for date, draw, _tier in self.draws}
        self.assertEqual(keys, {("2023-01-10", "8PM"), ("2023-01-31", "1PM")})

    def test_each_draw_has_exactly_132_rows(self):
        for date, draw in (("2023-01-10", "8PM"), ("2023-01-31", "1PM")):
            total = sum(len(rows) for (d, dr, _tier), rows in self.draws.items()
                        if (d, dr) == (date, draw))
            self.assertEqual(total, 132, f"{date} {draw} should contain 132 entries")

    def test_each_prize_tier_has_expected_count_and_sequential_positions(self):
        for (date, draw, tier), rows in self.draws.items():
            self.assertIn(tier, EXPECTED, f"Unexpected tier {tier} in {date} {draw}")
            self.assertEqual(len(rows), EXPECTED[tier], f"{date} {draw} {tier} count")
            positions = sorted(int(row["position"]) for row in rows)
            self.assertEqual(positions, list(range(1, EXPECTED[tier] + 1)),
                             f"{date} {draw} {tier} positions")

    def test_all_numbers_match_tier_format(self):
        for (date, draw, tier), rows in self.draws.items():
            for row in rows:
                self.assertRegex(row["winning_number"], PATTERNS[tier],
                                 f"Bad {tier} number for {date} {draw}: {row['winning_number']}")

    def test_consolation_matches_first_prize_suffix(self):
        for date, draw in (("2023-01-10", "8PM"), ("2023-01-31", "1PM")):
            first = self.draws[(date, draw, "1st")][0]["winning_number"]
            consolation = self.draws[(date, draw, "Consolation")][0]["winning_number"]
            self.assertEqual(first[-5:], consolation, f"{date} {draw} consolation mismatch")

    def test_every_row_is_human_verified_and_has_source_reference(self):
        for rows in self.draws.values():
            for row in rows:
                self.assertEqual(row["verification_status"], "human_verified")
                self.assertTrue(row["source_file"].strip())

    def test_leading_zeroes_are_preserved(self):
        values = {
            row["winning_number"]
            for rows in self.draws.values()
            for row in rows
        }
        self.assertIn("07390", values)
        self.assertIn("0009", values)
        self.assertIn("0035", values)


if __name__ == "__main__":
    unittest.main()

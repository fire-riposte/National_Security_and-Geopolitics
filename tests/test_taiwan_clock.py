import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import taiwan_clock as tc  # noqa: E402

DATA = json.loads((ROOT / "docs" / "_data" / "taiwan_clock.json").read_text(encoding="utf-8"))


def dials(readings):
    return [{"n": i + 1, "reading": r} for i, r in enumerate(readings)]


class ComputeTests(unittest.TestCase):
    def test_baseline_reading(self):
        r = [-2, -1, 1, 1, 1, 1, -1, 1, 2, 1, -2, -1, 0]
        cur = tc.compute(dials(r), [{"level": lv} for lv in [1, 1, 1, 2, 1, 0, 1]])
        self.assertEqual(cur["minutes"], 35)
        self.assertEqual((cur["sooner"], cur["later"], cur["neutral"]), (7, 5, 1))

    def test_motive_alone_stops_at_thirty(self):
        cur = tc.compute(dials([2] * 13), [{"level": 0}] * 7)
        self.assertEqual(cur["minutes"], 30)

    def test_calm_board_is_sixty(self):
        cur = tc.compute(dials([-2] * 13), [{"level": 0}] * 7)
        self.assertEqual(cur["minutes"], 60)

    def test_floor_is_two(self):
        cur = tc.compute(dials([2] * 13), [{"level": 3}] * 7)
        self.assertEqual(cur["minutes"], 2)

    def test_any_warning_caps_at_ten(self):
        cur = tc.compute(dials([0] * 13), [{"level": 3}] + [{"level": 0}] * 6)
        self.assertLessEqual(cur["minutes"], 10)

    def test_requires_thirteen_dials(self):
        with self.assertRaises(ValueError):
            tc.compute(dials([0] * 12), [])


class DataFileTests(unittest.TestCase):
    def test_data_file_is_valid(self):
        self.assertEqual(tc.validate(DATA), [])

    def test_validate_catches_bad_reading(self):
        bad = copy.deepcopy(DATA)
        bad["dials"][0]["reading"] = 3
        self.assertTrue(any("reading" in e for e in tc.validate(bad)))

    def test_validate_catches_em_dash_anywhere(self):
        bad = copy.deepcopy(DATA)
        bad["dates"][0]["what"] = "APEC \u2014 a planned meeting"
        self.assertTrue(any("em dash" in e for e in tc.validate(bad)))

    def test_log_upserts_same_date(self):
        d = copy.deepcopy(DATA)
        tc.log(d, "2099-01-01", "first")
        tc.log(d, "2099-01-01", "second")
        same = [h for h in d["history"] if h["date"] == "2099-01-01"]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0]["note"], "second")
        self.assertEqual(d["current"], tc.compute(d["dials"], d["iw"]))

    def test_log_keeps_moore_reference(self):
        d = copy.deepcopy(DATA)
        for i in range(80):
            tc.log(d, f"2100-{1 + i // 28:02d}-{1 + i % 28:02d}", "x")
        self.assertLessEqual(len(d["history"]), tc.MAX_HISTORY)
        self.assertTrue(any(h["minutes"] is None for h in d["history"]))


if __name__ == "__main__":
    unittest.main()

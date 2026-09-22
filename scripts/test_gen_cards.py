"""Long-lived regressions owned by the card generator: calendar streak semantics."""
import datetime as dt
import unittest

from gen_cards import streaks


class StreakTests(unittest.TestCase):
    """Keep totals and streak dates correct across gaps and the open current day."""

    def test_streaks(self):
        cases = [
            # name, days, today, current, longest, total
            ("empty", [], "2026-01-02", (0, None, None), (0, None, None), 0),
            ("year boundary", [("2025-12-31", 2), ("2026-01-01", 1)], "2026-01-01",
             (2, "2025-12-31", "2026-01-01"), (2, "2025-12-31", "2026-01-01"), 3),
            ("missing year", [("2024-12-31", 1), ("2026-01-01", 1)], "2026-01-01",
             (1, "2026-01-01", "2026-01-01"), (1, "2024-12-31", "2024-12-31"), 2),
            ("missing day", [("2026-01-01", 1), ("2026-01-03", 1)], "2026-01-03",
             (1, "2026-01-03", "2026-01-03"), (1, "2026-01-01", "2026-01-01"), 2),
            ("open today", [("2026-01-01", 1), ("2026-01-02", 0)], "2026-01-02",
             (1, "2026-01-01", "2026-01-01"), (1, "2026-01-01", "2026-01-01"), 1),
            ("today absent", [("2026-01-01", 1)], "2026-01-02",
             (1, "2026-01-01", "2026-01-01"), (1, "2026-01-01", "2026-01-01"), 1),
            ("stale history", [("2026-01-01", 1)], "2026-01-03",
             (0, None, None), (1, "2026-01-01", "2026-01-01"), 1),
            ("zero yesterday", [("2026-01-01", 1), ("2026-01-02", 0)], "2026-01-03",
             (0, None, None), (1, "2026-01-01", "2026-01-01"), 1),
            ("future ignored", [("2026-01-01", 1), ("2026-01-02", 5)], "2026-01-01",
             (1, "2026-01-01", "2026-01-01"), (1, "2026-01-01", "2026-01-01"), 1),
        ]
        for name, days, today, current, longest, total in cases:
            with self.subTest(name=name):
                result = streaks(days, dt.date.fromisoformat(today))
                for key, expected in (("current", current), ("longest", longest)):
                    actual = tuple(v.isoformat() if isinstance(v, dt.date) else v for v in result[key])
                    self.assertEqual(actual, expected)
                self.assertEqual(result["total"], total)
                first = next((day for day, count in days if count > 0 and day <= today), None)
                self.assertEqual(result["first"], dt.date.fromisoformat(first) if first else None)

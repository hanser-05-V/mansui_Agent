import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from test_storage import ROOT, capability


class UsageTests(unittest.TestCase):
    def test_unknown_and_cache_pricing(self):
        estimate = capability("usage").estimate_cny
        p = {
            "currency": "CNY",
            "model": "deepseek-flash",
            "effective_at": "2026-10-27",
            "cache_hit_input_per_million": "1",
            "cache_miss_input_per_million": "2",
            "output_per_million": "3",
        }
        self.assertEqual(estimate(100, 200, 300, p), Decimal("0.0014"))
        for v in (None, {}, dict(p, output_per_million="NaN")):
            self.assertIsNone(estimate(1, 2, 3, v))
        self.assertIsNone(estimate(None, 1, 2, p))

    def test_more_than_200_attempts_retains_unknown_usage(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            s = capability("store").Store(Path(d) / "s.sqlite3")
            u = capability("usage").Usage(s, "deepseek-flash")
            for i in range(205):
                key = u.begin(None, "chat")
                u.finish(key, "ok", None)
            stats = u.summary()
            self.assertEqual(stats["attempts"], 205)
            self.assertEqual(stats["unknown_usage"], 205)
            self.assertEqual(stats["known_input_tokens"], 0)
            s.close()

    def test_cost_reminder_clears_on_new_day_without_limiting_requests(self):
        import time

        p = {
            "currency": "CNY",
            "model": "deepseek-flash",
            "effective_at": "2026-10-27",
            "cache_hit_input_per_million": "1",
            "cache_miss_input_per_million": "2",
            "output_per_million": "3",
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            s = capability("store").Store(Path(d) / "s.sqlite3")
            try:
                u = capability("usage").Usage(s, "deepseek-flash", p, "0.1")
                first = u.begin(None, "chat")
                u.finish(
                    first,
                    "ok",
                    {
                        "prompt_tokens": 100000,
                        "completion_tokens": 10,
                        "prompt_cache_hit_tokens": 0,
                        "prompt_cache_miss_tokens": 100000,
                    },
                )
                self.assertEqual(
                    s.db.execute(
                        "SELECT code FROM local_status WHERE name='cost'"
                    ).fetchone()[0],
                    "reminder_reached",
                )
                with s.db:
                    s.db.execute(
                        "UPDATE usage_attempts SET started_at=? WHERE id=?",
                        (time.time() - 2 * 86400, first),
                    )
                second = u.begin(None, "chat")
                u.finish(
                    second,
                    "ok",
                    {
                        "prompt_tokens": 10,
                        "completion_tokens": 10,
                        "prompt_cache_hit_tokens": 0,
                        "prompt_cache_miss_tokens": 10,
                    },
                )
                self.assertEqual(
                    s.db.execute(
                        "SELECT code FROM local_status WHERE name='cost'"
                    ).fetchone()[0],
                    "below_reminder",
                )
            finally:
                s.close()

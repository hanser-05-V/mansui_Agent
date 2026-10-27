import importlib
import unittest
from datetime import datetime, timedelta, timezone


def capability():
    try:
        return importlib.import_module("plugins.mansui_companion.affinity")
    except ModuleNotFoundError as exc:
        raise AssertionError("Affinity capability missing") from exc


class AffinityTests(unittest.TestCase):
    def test_interval_daily_caps_and_midnight(self):
        a = capability()
        now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
        state = a.AffinityState()
        state, delta = a.apply_change(state, 1, now)
        self.assertEqual((state.score, delta), (21, 1))
        state, delta = a.apply_change(state, 1, now + timedelta(seconds=599))
        self.assertEqual(delta, 0)
        for minutes in (10, 20):
            state, _ = a.apply_change(state, 1, now + timedelta(minutes=minutes))
        state, delta = a.apply_change(state, 1, now + timedelta(minutes=30))
        self.assertEqual((state.score, delta), (23, 0))
        state, delta = a.apply_change(state, 1, now + timedelta(hours=1))
        self.assertEqual((state.score, delta, state.gained), (24, 1, 1))

    def test_bounds_types_and_no_absence_penalty(self):
        a = capability()
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        for score, proposal, want in (
            (100, 1, 100),
            (0, -1, 0),
            (20, True, 20),
            (20, 7, 20),
            (20, "1", 20),
        ):
            state, delta = a.apply_change(a.AffinityState(score=score), proposal, now)
            self.assertEqual((state.score, delta), (want, 0))
        state, _ = a.apply_change(
            a.AffinityState(score=75), 0, now + timedelta(days=90)
        )
        self.assertEqual(state.score, 75)

    def test_up_and_down_caps_are_separate(self):
        a = capability()
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        state = a.AffinityState()
        for index, delta in enumerate((1, 1, 1, -1, -1, -1, -1)):
            state, _ = a.apply_change(state, delta, now + timedelta(minutes=10 * index))
        self.assertEqual((state.score, state.gained, state.lost), (20, 3, 3))


if __name__ == "__main__":
    unittest.main()

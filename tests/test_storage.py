import importlib
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from plugins.mansui_companion.domain import Message, Route

ROOT = Path(r"E:\QQAgent\runtime\test-state")


def capability(name):
    try:
        return importlib.import_module("plugins.mansui_companion." + name)
    except ModuleNotFoundError as exc:
        raise AssertionError("Missing implementation: " + name) from exc


def msg(mid="1", group=None, text="hello", sender="10001"):
    return Message("90001", sender, group, mid, text, frozenset(), 1760000000.0)


class StorageTests(unittest.TestCase):
    def setUp(self):
        ROOT.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.path = Path(self.tmp.name) / "state.sqlite3"
        self.store = None

    def tearDown(self):
        if self.store:
            self.store.close()
        self.tmp.cleanup()

    def open(self):
        self.store = capability("store").Store(self.path)
        return self.store

    def test_claim_identity_deduplicates_platform_id_not_text(self):
        s = self.open()
        a = msg()
        self.assertTrue(s.claim(a, Route.REQUIRED))
        self.assertIsNone(s.claim(a, Route.REQUIRED))
        self.assertTrue(s.claim(msg("2"), Route.REQUIRED))
        self.assertTrue(s.claim(msg(group="80001"), Route.REQUIRED))
        self.assertEqual(s.db.execute("select count(*) from events").fetchone()[0], 3)
        with self.assertRaises(ValueError):
            s.claim(msg("3"), Route.DROP)

    def test_context_excludes_other_scopes_and_future_messages(self):
        s = self.open()
        a = msg(text="private sentinel")
        seq = s.claim(a, Route.REQUIRED)
        s.claim(msg("2", text="future sentinel"), Route.REQUIRED)
        b = msg(group="80001", text="group sentinel")
        other = s.claim(b, Route.REQUIRED)
        self.assertEqual(
            [r["content"] for r in s.context(a.scope, seq)], ["private sentinel"]
        )
        self.assertEqual(
            [r["content"] for r in s.context(b.scope, other)], ["group sentinel"]
        )

    def test_sent_transaction_and_affinity_applied_once(self):
        s = self.open()
        a = msg()
        s.claim(a, Route.REQUIRED)
        self.assertTrue(s.transition(a.key, "received", "queued"))
        self.assertFalse(s.transition(a.key, "received", "queued"))
        s.transition(a.key, "queued", "processing")
        s.transition(a.key, "processing", "sending")
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.assertTrue(s.commit_sent(a.key, "你好", "sent-1", 1, "友善交流", now))
        self.assertFalse(s.commit_sent(a.key, "你好", "sent-1", 1, "友善交流", now))
        self.assertEqual(s.relation(a.scope, a.sender).score, 21)
        self.assertEqual(
            s.db.execute(
                "select count(*) from messages where role='assistant'"
            ).fetchone()[0],
            1,
        )

    def test_restart_does_not_resend_ambiguous_delivery(self):
        s = self.open()
        a = msg()
        s.claim(a, Route.REQUIRED)
        for old, new in [
            ("received", "queued"),
            ("queued", "processing"),
            ("processing", "sending"),
        ]:
            s.transition(a.key, old, new)
        s.close()
        self.store = None
        s = self.open()
        self.assertEqual(s.event(a.key)["state"], "unknown_delivery")
        self.assertIsNone(s.claim(a, Route.REQUIRED))

    def test_corrupt_database_preserved(self):
        bad = b"not a database"
        self.path.write_bytes(bad)
        with self.assertRaises(Exception):
            self.open()
        self.assertEqual(self.path.read_bytes(), bad)

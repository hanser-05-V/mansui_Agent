import tempfile
import unittest
from pathlib import Path
from test_storage import capability, msg, ROOT
from plugins.mansui_companion.domain import Route


class MemoryTests(unittest.TestCase):
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

    def test_memory_scope_and_source_validation(self):
        s = self.open()
        a = msg(text="喜欢茶")
        seq = s.claim(a, Route.REQUIRED)
        mem = capability("memory").Memory(s)
        item = mem.add(a.scope, a.sender, "喜欢茶", [seq])
        self.assertEqual(mem.list(a.scope, a.sender)[0]["id"], item)
        self.assertEqual(mem.list(msg(group="80001").scope, a.sender), [])
        with self.assertRaises(ValueError):
            mem.add(msg(group="80001").scope, a.sender, "泄漏", [seq])

    def test_forget_invalidates_summary_and_source_text_after_restart(self):
        s = self.open()
        a = msg(text="secret favorite")
        seq = s.claim(a, Route.REQUIRED)
        mem = capability("memory").Memory(s)
        item = mem.add(a.scope, a.sender, "secret favorite", [seq])
        mem.add(a.scope, a.sender, "summary secret", [seq], kind="summary")
        mem.forget(a.scope, a.sender, item)
        self.assertEqual(mem.list(a.scope, a.sender), [])
        self.assertNotIn("secret", str(s.context(a.scope, seq)))
        s.close()
        self.store = None
        s = self.open()
        self.assertEqual(capability("memory").Memory(s).list(a.scope, a.sender), [])

    def test_correction_invalidates_old_sources_and_summary(self):
        s = self.open()
        a = msg(text="old place")
        seq = s.claim(a, Route.REQUIRED)
        mem = capability("memory").Memory(s)
        item = mem.add(a.scope, a.sender, "old place", [seq])
        mem.add(a.scope, a.sender, "old summary", [seq], kind="summary")
        mem.correct(a.scope, a.sender, item, "new place")
        self.assertEqual(
            [r["text"] for r in mem.list(a.scope, a.sender)], ["new place"]
        )
        self.assertNotIn("old", str(s.context(a.scope, seq)))

    def test_retention_prunes_raw_but_keeps_explicit_memory(self):
        s = self.open()
        a = msg()
        seq = s.claim(a, Route.REQUIRED)
        mem = capability("memory").Memory(s)
        mem.add(a.scope, a.sender, "remember", [seq])
        s.prune_raw(a.received_at + 31 * 86400)
        self.assertEqual(s.context(a.scope, seq), [])
        self.assertEqual(mem.list(a.scope, a.sender)[0]["text"], "remember")

    def test_forget_clears_derived_later_context_but_keeps_independent_fact(self):
        s = self.open()
        a = msg(text="old fact")
        seq = s.claim(a, Route.REQUIRED)
        mem = capability("memory").Memory(s)
        item = mem.add(a.scope, a.sender, "old fact", [seq])
        keep = mem.add(a.scope, a.sender, "independent fact", [seq])
        b = msg("2", text="please repeat it")
        seq2 = s.claim(b, Route.REQUIRED)
        s.record_sources(seq2, [seq])
        s.db.execute(
            "INSERT INTO messages(event_seq,scope,role,content,created_at) VALUES(?,?,'assistant','old fact paraphrase',?)",
            (seq2, a.scope, a.received_at),
        )
        s.db.commit()
        mem.forget(a.scope, a.sender, item)
        self.assertNotIn("old", str(s.context(a.scope, seq2)))
        self.assertEqual([r["id"] for r in mem.list(a.scope, a.sender)], [keep])

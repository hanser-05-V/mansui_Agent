import json
import time


class Memory:
    def __init__(self, store):
        self.store = store

    def list(self, scope, subject, limit=30):
        rows = self.store.db.execute(
            "SELECT * FROM memories WHERE scope=? AND subject=? ORDER BY id DESC LIMIT ?",
            (scope, subject, min(30, limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def add(self, scope, subject, text, sources, kind="explicit"):
        if kind not in ("explicit", "summary") or not text.strip() or not sources:
            raise ValueError("invalid_memory")
        for seq in sources:
            row = self.store.db.execute(
                "SELECT scope,sender FROM events WHERE seq=?", (seq,)
            ).fetchone()
            if not row or row["scope"] != scope or row["sender"] != subject:
                raise ValueError("memory_source_scope_mismatch")
        with self.store.db:
            if kind == "summary":
                self.store.db.execute(
                    "DELETE FROM memories WHERE scope=? AND subject=? AND kind='summary'",
                    (scope, subject),
                )
            cur = self.store.db.execute(
                "INSERT INTO memories(scope,subject,kind,text,sources,created_at) VALUES(?,?,?,?,?,?)",
                (scope, subject, kind, text[:1000], json.dumps(sources), time.time()),
            )
            return cur.lastrowid

    def _invalidate(self, scope, subject, item_id):
        db = self.store.db
        row = db.execute(
            "SELECT * FROM memories WHERE id=? AND scope=? AND subject=?",
            (item_id, scope, subject),
        ).fetchone()
        if not row:
            raise ValueError("memory_not_found")
        sources = set(json.loads(row["sources"]))
        frontier = set(sources)
        while frontier:
            found = {
                r[0]
                for source in frontier
                for r in db.execute(
                    "SELECT event_seq FROM event_sources WHERE source_seq=?", (source,)
                )
            } - sources
            sources.update(found)
            frontier = found
        for item in db.execute(
            "SELECT id,kind,sources FROM memories WHERE scope=? AND subject=?",
            (scope, subject),
        ).fetchall():
            if item["id"] == item_id or (
                item["kind"] == "summary"
                and sources.intersection(json.loads(item["sources"]))
            ):
                db.execute("DELETE FROM memories WHERE id=?", (item["id"],))
        for seq in sources:
            db.execute("DELETE FROM messages WHERE event_seq=?", (seq,))
        return dict(row)

    def forget(self, scope, subject, item_id):
        with self.store.db:
            self._invalidate(scope, subject, item_id)
        self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def correct(self, scope, subject, item_id, text):
        if not text.strip():
            raise ValueError("empty_memory")
        with self.store.db:
            row = self._invalidate(scope, subject, item_id)
            self.store.db.execute(
                "INSERT INTO memories(id,scope,subject,kind,text,sources,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    item_id,
                    scope,
                    subject,
                    row["kind"],
                    text[:1000],
                    row["sources"],
                    time.time(),
                ),
            )
        self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

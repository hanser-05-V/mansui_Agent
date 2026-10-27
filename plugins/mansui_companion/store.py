import sqlite3
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from .affinity import AffinityState, apply_change
from .domain import Route


class Store:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            probe = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            try:
                if probe.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("database_integrity_failed")
                if probe.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ValueError("unknown_database_version")
            finally:
                probe.close()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript(
            Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        with self.db:
            self.db.execute(
                "UPDATE events SET state='unknown_delivery',reason='restart_during_send' WHERE state='sending'"
            )
            self.db.execute(
                "UPDATE events SET state=CASE WHEN route='required' THEN 'awaiting_retry' ELSE 'skipped' END,reason='restart_before_send' WHERE state IN ('received','queued','processing')"
            )

    def close(self):
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close()

    def event(self, key):
        row = self.db.execute(
            "SELECT * FROM events WHERE bot=? AND scope=? AND message_id=?", key
        ).fetchone()
        return dict(row) if row else None

    def claim(self, message, route):
        if route not in (Route.REQUIRED, Route.OPTIONAL):
            raise ValueError("route_not_admitted")
        with self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO events(bot,scope,message_id,sender,group_id,route,received_at) VALUES(?,?,?,?,?,?,?)",
                (
                    *message.key,
                    message.sender,
                    message.group,
                    route.value,
                    message.received_at,
                ),
            )
            if not cur.rowcount:
                return None
            seq = cur.lastrowid
            text = message.text[:4000]
            if len(message.text) > 4000:
                text += "\n[输入过长，已截断到前 4000 字]"
            self.db.execute(
                "INSERT INTO messages(event_seq,scope,role,content,created_at) VALUES(?,?,'user',?,?)",
                (seq, message.scope, text, message.received_at),
            )
            return seq

    def transition(self, key, old, new, reason=None):
        allowed = {
            "received": {"queued", "overloaded", "awaiting_retry"},
            "queued": {"processing", "skipped", "awaiting_retry"},
            "processing": {"sending", "skipped", "awaiting_retry", "failed"},
            "sending": {"sent", "failed", "unknown_delivery"},
            "awaiting_retry": {"queued"},
            "overloaded": {"queued"},
            "failed": {"queued"},
        }
        if new not in allowed.get(old, set()):
            raise ValueError("illegal_state_transition")
        with self.db:
            return bool(
                self.db.execute(
                    "UPDATE events SET state=?,reason=? WHERE bot=? AND scope=? AND message_id=? AND state=?",
                    (new, reason, *key, old),
                ).rowcount
            )

    def relation(self, scope, subject):
        row = self.db.execute(
            "SELECT score,local_day,gained,lost,last_change FROM relations WHERE scope=? AND subject=?",
            (scope, subject),
        ).fetchone()
        return AffinityState(**dict(row)) if row else AffinityState()

    def commit_sent(self, key, text, sent_id, proposal, reason, now: datetime):
        if not sent_id:
            raise ValueError("receipt_required")
        with self.db:
            event = self.event(key)
            if not event or event["state"] != "sending":
                return False
            if not self.db.execute(
                "UPDATE events SET state='sent',sent_id=?,reason=NULL WHERE seq=? AND state='sending'",
                (str(sent_id), event["seq"]),
            ).rowcount:
                return False
            self.db.execute(
                "INSERT INTO messages(event_seq,scope,role,content,created_at) VALUES(?,?,'assistant',?,?)",
                (event["seq"], event["scope"], text, now.timestamp()),
            )
            state, _ = apply_change(
                self.relation(event["scope"], event["sender"]), proposal, now
            )
            self.db.execute(
                "INSERT INTO relations(scope,subject,score,local_day,gained,lost,last_change,reason) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(scope,subject) DO UPDATE SET score=excluded.score,local_day=excluded.local_day,gained=excluded.gained,lost=excluded.lost,last_change=excluded.last_change,reason=excluded.reason",
                (
                    event["scope"],
                    event["sender"],
                    *asdict(state).values(),
                    reason[:100],
                ),
            )
            return True

    def context(self, scope, before_seq, limit=24):
        rows = self.db.execute(
            "SELECT m.role,m.content,e.sender,m.event_seq FROM messages m JOIN events e ON e.seq=m.event_seq WHERE m.scope=? AND m.event_seq<=? ORDER BY m.event_seq DESC,m.id DESC LIMIT ?",
            (scope, before_seq, min(24, limit)),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def prune_raw(self, now=None, days=30):
        with self.db:
            return self.db.execute(
                "DELETE FROM messages WHERE created_at<?",
                ((time.time() if now is None else now) - days * 86400,),
            ).rowcount

    def status(self, name, code):
        with self.db:
            self.db.execute(
                "INSERT INTO local_status VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET code=excluded.code,updated_at=excluded.updated_at",
                (name, code, time.time()),
            )

    def pending(self):
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT seq,state,reason FROM events WHERE state IN ('awaiting_retry','overloaded','failed','unknown_delivery') ORDER BY seq DESC LIMIT 30"
            )
        ]

    def record_sources(self, seq, sources):
        scope = self.db.execute(
            "SELECT scope FROM events WHERE seq=?", (seq,)
        ).fetchone()[0]
        with self.db:
            for source in set(sources):
                if source == seq:
                    continue
                row = self.db.execute(
                    "SELECT scope FROM events WHERE seq=?", (source,)
                ).fetchone()
                if not row or row[0] != scope or source >= seq:
                    raise ValueError("invalid_context_source")
                self.db.execute(
                    "INSERT OR IGNORE INTO event_sources VALUES(?,?)", (seq, source)
                )

PRAGMA user_version=1;
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL, scope TEXT NOT NULL,
 message_id TEXT NOT NULL, sender TEXT NOT NULL, group_id TEXT, route TEXT NOT NULL,
 received_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'received', reason TEXT,
 sent_id TEXT, UNIQUE(bot,scope,message_id)
);
CREATE TABLE IF NOT EXISTS messages(
 id INTEGER PRIMARY KEY, event_seq INTEGER NOT NULL REFERENCES events(seq),
 scope TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL,
 UNIQUE(event_seq,role)
);
CREATE INDEX IF NOT EXISTS messages_scope ON messages(scope,event_seq);
CREATE TABLE IF NOT EXISTS relations(
 scope TEXT NOT NULL, subject TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 20,
 local_day TEXT NOT NULL DEFAULT '', gained INTEGER NOT NULL DEFAULT 0,
 lost INTEGER NOT NULL DEFAULT 0, last_change REAL, reason TEXT,
 PRIMARY KEY(scope,subject)
);
CREATE TABLE IF NOT EXISTS memories(
 id INTEGER PRIMARY KEY, scope TEXT NOT NULL, subject TEXT NOT NULL,
 kind TEXT NOT NULL, text TEXT NOT NULL, sources TEXT NOT NULL,
 created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_attempts(
 id INTEGER PRIMARY KEY, event_seq INTEGER REFERENCES events(seq), purpose TEXT NOT NULL,
 model TEXT NOT NULL, started_at REAL NOT NULL, status TEXT NOT NULL, error_code TEXT,
 input_tokens INTEGER, output_tokens INTEGER, cache_hit INTEGER, cache_miss INTEGER,
 estimated_cny TEXT, pricing_snapshot TEXT
);
CREATE TABLE IF NOT EXISTS local_status(
 name TEXT PRIMARY KEY, code TEXT NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS event_sources(
 event_seq INTEGER NOT NULL REFERENCES events(seq), source_seq INTEGER NOT NULL REFERENCES events(seq),
 PRIMARY KEY(event_seq,source_seq)
);
CREATE INDEX IF NOT EXISTS source_lookup ON event_sources(source_seq);
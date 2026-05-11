CREATE TABLE IF NOT EXISTS credentials (
    platform    TEXT PRIMARY KEY,
    data        BLOB NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS play_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    track_id    TEXT NOT NULL,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL,
    cover_url   TEXT,
    played_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);

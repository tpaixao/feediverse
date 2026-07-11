"""SQLite database layer for Feediverse."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "feediverse.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    description TEXT,
    site_url TEXT,
    icon_url TEXT,
    last_fetched TEXT,
    etag TEXT,
    last_modified TEXT,
    fetch_error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    title TEXT,
    summary TEXT,
    content TEXT,
    url TEXT,
    author TEXT,
    published_at TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    UNIQUE(feed_id, guid)
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT
);

CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_feed ON posts(feed_id);
CREATE INDEX IF NOT EXISTS idx_attachments_post ON attachments(post_id);
"""


def init_db():
    """Initialize database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    """Get a SQLite connection with WAL mode and foreign keys."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_feed(url, title, description, site_url, icon_url):
    """Insert a new feed, return its id. Ignores if already exists."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO feeds (url, title, description, site_url, icon_url) VALUES (?, ?, ?, ?, ?)",
                (url, title, description, site_url, icon_url),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            row = conn.execute("SELECT id FROM feeds WHERE url = ?", (url,)).fetchone()
            return row["id"] if row else None


def get_feed_by_id(feed_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        return dict(row) if row else None


def get_feed_by_url(url):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM feeds WHERE url = ?", (url,)).fetchone()
        return dict(row) if row else None


def get_all_feeds():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM feeds ORDER BY title").fetchall()
        return [dict(r) for r in rows]


def delete_feed(feed_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))


def update_feed_fetched(feed_id, etag, last_modified, error=None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE feeds SET last_fetched = datetime('now'), etag = ?, last_modified = ?, fetch_error = ? WHERE id = ?",
            (etag, last_modified, error, feed_id),
        )


def update_feed_meta(feed_id, title, description, site_url, icon_url):
    with get_conn() as conn:
        conn.execute(
            "UPDATE feeds SET title = ?, description = ?, site_url = ?, icon_url = ? WHERE id = ?",
            (title, description, site_url, icon_url, feed_id),
        )


def add_post(feed_id, guid, title, summary, content, url, author, published_at):
    """Insert a post, ignore if already exists (by guid). Return post id or None."""
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO posts (feed_id, guid, title, summary, content, url, author, published_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (feed_id, guid, title, summary, content, url, author, published_at),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


def add_attachment(post_id, att_type, url, title):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO attachments (post_id, type, url, title) VALUES (?, ?, ?, ?)",
            (post_id, att_type, url, title),
        )


def get_timeline(limit=50, offset=0, feed_id=None):
    """Get posts reverse-chronologically, with feed info attached."""
    with get_conn() as conn:
        if feed_id:
            rows = conn.execute(
                "SELECT p.*, f.title as feed_title, f.icon_url as feed_icon, f.site_url as feed_site "
                "FROM posts p JOIN feeds f ON p.feed_id = f.id "
                "WHERE f.id = ? ORDER BY p.published_at DESC NULLS LAST LIMIT ? OFFSET ?",
                (feed_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT p.*, f.title as feed_title, f.icon_url as feed_icon, f.site_url as feed_site "
                "FROM posts p JOIN feeds f ON p.feed_id = f.id "
                "ORDER BY p.published_at DESC NULLS LAST LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        posts = [dict(r) for r in rows]
        # Attach media
        for post in posts:
            atts = conn.execute(
                "SELECT type, url, title FROM attachments WHERE post_id = ?", (post["id"],)
            ).fetchall()
            post["attachments"] = [dict(a) for a in atts]
        return posts


def get_post_count(feed_id=None):
    with get_conn() as conn:
        if feed_id:
            row = conn.execute("SELECT COUNT(*) as c FROM posts WHERE feed_id = ?", (feed_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()
        return row["c"]


def search_posts(query, limit=50, offset=0):
    """Full-text search in post title and summary using LIKE."""
    with get_conn() as conn:
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT p.*, f.title as feed_title, f.icon_url as feed_icon, f.site_url as feed_site "
            "FROM posts p JOIN feeds f ON p.feed_id = f.id "
            "WHERE p.title LIKE ? OR p.summary LIKE ? OR p.content LIKE ? "
            "ORDER BY p.published_at DESC NULLS LAST LIMIT ? OFFSET ?",
            (pattern, pattern, pattern, limit, offset),
        ).fetchall()
        posts = [dict(r) for r in rows]
        for post in posts:
            atts = conn.execute(
                "SELECT type, url, title FROM attachments WHERE post_id = ?", (post["id"],)
            ).fetchall()
            post["attachments"] = [dict(a) for a in atts]
        return posts


def get_stats():
    with get_conn() as conn:
        feeds_count = conn.execute("SELECT COUNT(*) as c FROM feeds").fetchone()["c"]
        posts_count = conn.execute("SELECT COUNT(*) as c FROM posts").fetchone()["c"]
        last_fetch = conn.execute("SELECT MAX(last_fetched) as l FROM feeds").fetchone()["l"]
        return {"feeds": feeds_count, "posts": posts_count, "last_fetch": last_fetch}


def add_opml_feeds(feeds_data):
    """
    Batch-add feeds from parsed OPML data.
    feeds_data: list of {"url": ..., "title": ...}
    Returns {"added": int, "failed": int, "errors": [...]}.
    """
    # Avoid circular import
    from feed_fetcher import fetch_feed

    added = 0
    failed = 0
    errors = []

    for feed_info in feeds_data:
        url = feed_info.get("url", "").strip()
        if not url:
            continue
        existing = get_feed_by_url(url)
        if existing:
            continue
        try:
            result = fetch_feed(url)
            if result.get("error"):
                failed += 1
                errors.append({"url": url, "error": result["error"]})
                continue
            feed_id = add_feed(url, result["title"], result["description"],
                               result["site_url"], result["icon_url"])
            for entry in result["entries"]:
                post_id = add_post(feed_id, entry["guid"], entry["title"],
                                   entry["summary"], entry["content"],
                                   entry["url"], entry["author"], entry["published_at"])
                if post_id:
                    for att in entry["attachments"]:
                        add_attachment(post_id, att["type"], att["url"], att["title"])
            update_feed_fetched(feed_id, result.get("etag", ""), result.get("last_modified", ""))
            added += 1
        except Exception as e:
            failed += 1
            errors.append({"url": url, "error": str(e)})

    return {"added": added, "failed": failed, "errors": errors}


def get_feed_post_count(feed_id):
    """Get post count for a single feed."""
    return get_post_count(feed_id=feed_id)


def get_feed_media(feed_id, limit=50):
    """Get all media attachments for a feed's posts."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT a.*, p.title as post_title, p.id as post_id, p.published_at "
            "FROM attachments a JOIN posts p ON a.post_id = p.id "
            "WHERE p.feed_id = ? ORDER BY p.published_at DESC NULLS LAST LIMIT ?",
            (feed_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

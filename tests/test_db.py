"""Tests for the database layer (db.py)."""
import sqlite3
import pytest
from unittest.mock import patch

import db


class TestInitDb:
    def test_init_creates_tables(self, temp_db):
        """init_db should create feeds, posts, attachments tables."""
        with sqlite3.connect(str(temp_db)) as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        assert "feeds" in tables
        assert "posts" in tables
        assert "attachments" in tables

    def test_init_is_idempotent(self, temp_db):
        """Calling init_db twice should not error."""
        db.init_db()
        db.init_db()  # should not raise


class TestAddFeed:
    def test_add_feed_returns_id(self, temp_db):
        fid = db.add_feed("https://example.com/feed", "Title", "Desc",
                          "https://example.com", "icon.png")
        assert fid is not None
        assert isinstance(fid, int)

    def test_add_feed_duplicate_returns_same_id(self, temp_db):
        fid1 = db.add_feed("https://example.com/feed", "Title", "Desc",
                           "https://example.com", "icon.png")
        fid2 = db.add_feed("https://example.com/feed", "Other", "Other",
                           "https://other.com", "other.png")
        assert fid1 == fid2

    def test_add_feed_empty_fields(self, temp_db):
        fid = db.add_feed("https://example.com/feed", None, None, None, None)
        assert fid is not None


class TestGetFeed:
    def test_get_feed_by_id(self, sample_feed_id):
        feed = db.get_feed_by_id(sample_feed_id)
        assert feed is not None
        assert feed["title"] == "Example Blog"
        assert feed["url"] == "https://example.com/feed.xml"

    def test_get_feed_by_id_not_found(self, temp_db):
        assert db.get_feed_by_id(99999) is None

    def test_get_feed_by_url(self, sample_feed_id):
        feed = db.get_feed_by_url("https://example.com/feed.xml")
        assert feed is not None
        assert feed["id"] == sample_feed_id

    def test_get_feed_by_url_not_found(self, temp_db):
        assert db.get_feed_by_url("https://nonexistent.com/feed") is None

    def test_get_all_feeds(self, sample_feed_id, second_feed_id):
        feeds = db.get_all_feeds()
        assert len(feeds) == 2
        # Should be ordered by title
        titles = [f["title"] for f in feeds]
        assert titles == sorted(titles)

    def test_get_all_feeds_empty(self, temp_db):
        assert db.get_all_feeds() == []


class TestDeleteFeed:
    def test_delete_feed(self, sample_feed_id):
        db.delete_feed(sample_feed_id)
        assert db.get_feed_by_id(sample_feed_id) is None

    def test_delete_feed_cascades_posts(self, sample_feed_id, sample_posts):
        db.delete_feed(sample_feed_id)
        assert db.get_post_count(feed_id=sample_feed_id) == 0

    def test_delete_nonexistent_feed(self, temp_db):
        # Should not raise
        db.delete_feed(99999)


class TestUpdateFeed:
    def test_update_feed_fetched(self, sample_feed_id):
        db.update_feed_fetched(sample_feed_id, "etag123", "Wed, 01 Jan 2026 00:00:00 GMT")
        feed = db.get_feed_by_id(sample_feed_id)
        assert feed["etag"] == "etag123"
        assert feed["last_modified"] == "Wed, 01 Jan 2026 00:00:00 GMT"
        assert feed["last_fetched"] is not None
        assert feed["fetch_error"] is None

    def test_update_feed_fetched_with_error(self, sample_feed_id):
        db.update_feed_fetched(sample_feed_id, "", "", error="Timeout")
        feed = db.get_feed_by_id(sample_feed_id)
        assert feed["fetch_error"] == "Timeout"

    def test_update_feed_meta(self, sample_feed_id):
        db.update_feed_meta(sample_feed_id, "New Title", "New Desc",
                            "https://newsite.com", "new_icon.png")
        feed = db.get_feed_by_id(sample_feed_id)
        assert feed["title"] == "New Title"
        assert feed["description"] == "New Desc"
        assert feed["site_url"] == "https://newsite.com"
        assert feed["icon_url"] == "new_icon.png"


class TestAddPost:
    def test_add_post_returns_id(self, sample_feed_id):
        pid = db.add_post(sample_feed_id, "guid-1", "Title", "Summary",
                          "Content", "https://example.com/1", "Author",
                          "2026-07-10T12:00:00")
        assert pid is not None
        assert isinstance(pid, int)

    def test_add_post_duplicate_returns_none(self, sample_feed_id):
        pid1 = db.add_post(sample_feed_id, "guid-1", "Title", "Summary",
                           "Content", "https://example.com/1", "Author",
                           "2026-07-10T12:00:00")
        pid2 = db.add_post(sample_feed_id, "guid-1", "Different", "Different",
                           "Different", "https://different.com", "Different",
                           "2026-07-11T12:00:00")
        assert pid1 is not None
        assert pid2 is None

    def test_add_post_same_guid_different_feed(self, sample_feed_id, second_feed_id):
        pid1 = db.add_post(sample_feed_id, "shared-guid", "Title", "Summary",
                           "Content", "url1", "Author", "2026-07-10T12:00:00")
        pid2 = db.add_post(second_feed_id, "shared-guid", "Title", "Summary",
                           "Content", "url2", "Author", "2026-07-10T12:00:00")
        assert pid1 is not None
        assert pid2 is not None
        assert pid1 != pid2


class TestAddAttachment:
    def test_add_attachment(self, sample_feed_id, sample_posts):
        db.add_attachment(sample_posts[0], "image", "https://example.com/new.png", "New")
        posts = db.get_timeline(limit=1)
        post = next(p for p in posts if p["id"] == sample_posts[0])
        atts = post["attachments"]
        assert any(a["url"] == "https://example.com/new.png" for a in atts)

    def test_add_attachment_multiple_types(self, sample_feed_id, sample_posts):
        pid = sample_posts[2]
        db.add_attachment(pid, "image", "https://example.com/a.png", "A")
        db.add_attachment(pid, "audio", "https://example.com/b.mp3", "B")
        db.add_attachment(pid, "video", "https://example.com/c.mp4", "C")
        posts = db.get_timeline()
        post = next(p for p in posts if p["id"] == pid)
        types = {a["type"] for a in post["attachments"]}
        assert types == {"image", "audio", "video"}


class TestGetTimeline:
    def test_get_timeline_returns_posts(self, sample_feed_id, sample_posts):
        posts = db.get_timeline()
        assert len(posts) == 3

    def test_get_timeline_includes_feed_info(self, sample_feed_id, sample_posts):
        posts = db.get_timeline()
        assert posts[0]["feed_title"] == "Example Blog"
        assert posts[0]["feed_icon"] == "https://example.com/icon.png"

    def test_get_timeline_includes_attachments(self, sample_feed_id, sample_posts):
        posts = db.get_timeline()
        post1 = next(p for p in posts if p["id"] == sample_posts[0])
        assert len(post1["attachments"]) == 2

    def test_get_timeline_limit(self, sample_feed_id, sample_posts):
        posts = db.get_timeline(limit=2)
        assert len(posts) == 2

    def test_get_timeline_offset(self, sample_feed_id, sample_posts):
        page1 = db.get_timeline(limit=2, offset=0)
        page2 = db.get_timeline(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 1
        assert page1[0]["id"] != page2[0]["id"]

    def test_get_timeline_by_feed_id(self, sample_feed_id, second_feed_id):
        # Add a post to second feed
        db.add_post(second_feed_id, "other-guid", "Other", "Other",
                    "Other", "https://another.com/1", "Other", "2026-07-10T12:00:00")
        posts = db.get_timeline(feed_id=sample_feed_id)
        assert len(posts) == 0  # no posts in sample_feed_id yet
        posts2 = db.get_timeline(feed_id=second_feed_id)
        assert len(posts2) == 1

    def test_get_timeline_empty(self, temp_db):
        assert db.get_timeline() == []

    def test_get_timeline_ordered_by_date_desc(self, sample_feed_id, sample_posts):
        posts = db.get_timeline()
        dates = [p["published_at"] for p in posts if p["published_at"]]
        assert dates == sorted(dates, reverse=True)

    def test_get_timeline_sort_by_added(self, sample_feed_id, sample_posts):
        """sort_by='added' should order by fetched_at instead of published_at."""
        posts = db.get_timeline(sort_by="added")
        assert len(posts) == 3
        # fetched_at is auto-set on insert; should be descending
        fetched = [p["fetched_at"] for p in posts if p["fetched_at"]]
        assert fetched == sorted(fetched, reverse=True)

    def test_get_timeline_sort_default_is_published(self, sample_feed_id, sample_posts):
        """Default sort_by should be 'published'."""
        posts_default = db.get_timeline()
        posts_pub = db.get_timeline(sort_by="published")
        ids_default = [p["id"] for p in posts_default]
        ids_pub = [p["id"] for p in posts_pub]
        assert ids_default == ids_pub


class TestGetPostCount:
    def test_post_count_all(self, sample_feed_id, sample_posts):
        assert db.get_post_count() == 3

    def test_post_count_by_feed(self, sample_feed_id, sample_posts, second_feed_id):
        db.add_post(second_feed_id, "x", "x", "x", "x", "x", "x", "2026-07-10T12:00:00")
        assert db.get_post_count(feed_id=sample_feed_id) == 3
        assert db.get_post_count(feed_id=second_feed_id) == 1

    def test_post_count_empty(self, temp_db):
        assert db.get_post_count() == 0

    def test_feed_post_count(self, sample_feed_id, sample_posts):
        assert db.get_feed_post_count(sample_feed_id) == 3


class TestSearchPosts:
    def test_search_by_title(self, sample_feed_id, sample_posts):
        results = db.search_posts("Python")
        assert len(results) == 2  # "First Post About Python" + "Testing strategies for Python apps"
        titles = [r["title"] for r in results]
        assert "First Post About Python" in titles

    def test_search_by_summary(self, sample_feed_id, sample_posts):
        results = db.search_posts("testing strategies")
        assert len(results) == 1
        assert results[0]["title"] == "Second Post About Testing"

    def test_search_by_content(self, sample_feed_id, sample_posts):
        results = db.search_posts("Plain text content")
        assert len(results) == 1
        assert results[0]["title"] == "Third Post No Attachments"

    def test_search_no_results(self, sample_feed_id, sample_posts):
        results = db.search_posts("nonexistentterm12345")
        assert results == []

    def test_search_case_insensitive(self, sample_feed_id, sample_posts):
        # SQLite LIKE is case-insensitive by default for ASCII
        results = db.search_posts("python")
        assert len(results) >= 1

    def test_search_includes_attachments(self, sample_feed_id, sample_posts):
        results = db.search_posts("Python")
        post = next(r for r in results if r["title"] == "First Post About Python")
        assert len(post["attachments"]) == 2

    def test_search_limit(self, sample_feed_id, sample_posts):
        results = db.search_posts("Post", limit=2)
        assert len(results) == 2

    def test_search_offset(self, sample_feed_id, sample_posts):
        page1 = db.search_posts("Post", limit=2, offset=0)
        page2 = db.search_posts("Post", limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 1


class TestGetStats:
    def test_stats_empty(self, temp_db):
        stats = db.get_stats()
        assert stats["feeds"] == 0
        assert stats["posts"] == 0
        assert stats["last_fetch"] is None

    def test_stats_with_data(self, sample_feed_id, sample_posts):
        db.update_feed_fetched(sample_feed_id, "etag", "mod")
        stats = db.get_stats()
        assert stats["feeds"] == 1
        assert stats["posts"] == 3
        assert stats["last_fetch"] is not None


class TestGetFeedMedia:
    def test_get_feed_media(self, sample_feed_id, sample_posts):
        media = db.get_feed_media(sample_feed_id)
        assert len(media) == 3  # 2 from post 1 + 1 from post 2

    def test_get_feed_media_types(self, sample_feed_id, sample_posts):
        media = db.get_feed_media(sample_feed_id)
        types = {m["type"] for m in media}
        assert "image" in types
        assert "link" in types

    def test_get_feed_media_includes_post_info(self, sample_feed_id, sample_posts):
        media = db.get_feed_media(sample_feed_id)
        assert "post_title" in media[0]
        assert "post_id" in media[0]
        assert "published_at" in media[0]

    def test_get_feed_media_limit(self, sample_feed_id, sample_posts):
        media = db.get_feed_media(sample_feed_id, limit=2)
        assert len(media) == 2

    def test_get_feed_media_empty(self, sample_feed_id):
        media = db.get_feed_media(sample_feed_id)
        assert media == []

    def test_get_feed_media_wrong_feed(self, sample_feed_id, second_feed_id, sample_posts):
        media = db.get_feed_media(second_feed_id)
        assert media == []


class TestAddOpmlFeeds:
    def test_add_opml_feeds_success(self, temp_db):
        feeds_data = [{"url": "https://example.com/feed.xml", "title": "Test"}]
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Test Feed",
                "description": "Desc",
                "site_url": "https://example.com",
                "icon_url": "",
                "etag": "",
                "last_modified": "",
                "entries": [{
                    "guid": "g1", "title": "Post 1", "summary": "S",
                    "content": "C", "url": "https://example.com/1",
                    "author": "A", "published_at": "2026-07-10T12:00:00",
                    "attachments": [],
                }],
            }
            result = db.add_opml_feeds(feeds_data)

        assert result["added"] == 1
        assert result["failed"] == 0
        assert len(result["errors"]) == 0

    def test_add_opml_feeds_skip_existing(self, sample_feed_id):
        feeds_data = [{"url": "https://example.com/feed.xml", "title": "Test"}]
        result = db.add_opml_feeds(feeds_data)
        assert result["added"] == 0  # already exists

    def test_add_opml_feeds_fetch_error(self, temp_db):
        feeds_data = [{"url": "https://broken.com/feed.xml", "title": "Broken"}]
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {"error": "Connection refused"}
            result = db.add_opml_feeds(feeds_data)

        assert result["added"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) == 1
        assert "Connection refused" in result["errors"][0]["error"]

    def test_add_opml_feeds_exception(self, temp_db):
        feeds_data = [{"url": "https://crash.com/feed.xml", "title": "Crash"}]
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.side_effect = Exception("Unexpected error")
            result = db.add_opml_feeds(feeds_data)

        assert result["added"] == 0
        assert result["failed"] == 1

    def test_add_opml_feeds_empty_url_skipped(self, temp_db):
        feeds_data = [{"url": "", "title": "Empty"}, {"url": "  ", "title": "Blank"}]
        result = db.add_opml_feeds(feeds_data)
        assert result["added"] == 0
        assert result["failed"] == 0

    def test_add_opml_feeds_mixed(self, sample_feed_id):
        """Mix of existing, new (mocked), and failing feeds."""
        feeds_data = [
            {"url": "https://example.com/feed.xml", "title": "Existing"},  # exists
            {"url": "https://new.com/feed.xml", "title": "New"},  # new
            {"url": "https://broken.com/feed.xml", "title": "Broken"},  # fails
        ]
        call_count = [0]

        def mock_fetch_fn(url, *args, **kwargs):
            call_count[0] += 1
            if "new.com" in url:
                return {"title": "New", "description": "", "site_url": "",
                        "icon_url": "", "etag": "", "last_modified": "",
                        "entries": []}
            return {"error": "Failed"}

        with patch("feed_fetcher.fetch_feed", side_effect=mock_fetch_fn):
            result = db.add_opml_feeds(feeds_data)

        assert result["added"] == 1
        assert result["failed"] == 1

class TestFTS5Search:
    """Tests for FTS5-based search: ranking, snippets, prefix, special chars."""

    def test_fts_ranking_relevance(self, sample_feed_id, sample_posts):
        """Post with query in title should rank higher than post with query only in summary."""
        db.add_post(sample_feed_id, "rank-title", "Python Python Python",
                    "other stuff", "other content",
                    "https://example.com/rank1", "A", "2026-07-10T12:00:00")
        db.add_post(sample_feed_id, "rank-summary", "Other title",
                    "Python is mentioned here",
                    "content without keyword",
                    "https://example.com/rank2", "B", "2026-07-09T12:00:00")
        results = db.search_posts("Python")
        # Post with Python in title 3 times should be more relevant
        titles = [r["title"] for r in results]
        assert "Python Python Python" in titles
        rank_title_idx = titles.index("Python Python Python")
        rank_summary_idx = titles.index("Other title")
        assert rank_title_idx < rank_summary_idx

    def test_fts_multi_word_and_semantics(self, sample_feed_id, sample_posts):
        """Multi-word query should match posts containing all tokens (AND semantics)."""
        results = db.search_posts("Python testing")
        # Should match posts containing both Python AND testing
        # 'Second Post About Testing' has 'Testing strategies for Python apps' in summary
        titles = [r["title"] for r in results]
        assert "Second Post About Testing" in titles

    def test_fts_prefix_matching(self, sample_feed_id, sample_posts):
        """FTS5 prefix matching with * wildcard should work."""
        results = db.search_posts("Pyth*")
        titles = [r["title"] for r in results]
        assert "First Post About Python" in titles

    def test_fts_special_chars_safe(self, sample_feed_id, sample_posts):
        """Query with FTS5 special characters should not crash (escaped)."""
        # These would be syntax errors in raw FTS5; _fts5_escape handles them
        for q in ['test(', 'test)', 'a:b', 'test"', 'foo AND bar']:
            results = db.search_posts(q)
            assert isinstance(results, list)  # should not raise

    def test_fts_empty_results(self, sample_feed_id, sample_posts):
        """Search for nonexistent term returns empty list."""
        results = db.search_posts("zzznonexistentzzz")
        assert results == []

    def test_fts_search_post_count(self, sample_feed_id, sample_posts):
        """search_post_count returns correct count for FTS5 query."""
        count = db.search_post_count("Python")
        assert count >= 2  # at least 2 posts mention Python
        count_none = db.search_post_count("zzznonexistentzzz")
        assert count_none == 0

    def test_fts_search_post_count_special_chars(self, sample_feed_id, sample_posts):
        """search_post_count handles special characters gracefully."""
        for q in ['test(', 'a:b', 'foo"bar']:
            count = db.search_post_count(q)
            assert isinstance(count, int)

    def test_fts_trigger_on_insert(self, sample_feed_id):
        """Newly inserted posts should be immediately searchable via FTS trigger."""
        db.add_post(sample_feed_id, "new-guid", "Freshly Inserted",
                    "Unique searchable phrase",
                    "Content here",
                    "https://example.com/new", "A", "2026-07-10T12:00:00")
        results = db.search_posts("Freshly")
        titles = [r["title"] for r in results]
        assert "Freshly Inserted" in titles

    def test_fts_trigger_on_delete(self, sample_feed_id, sample_posts):
        """Deleted posts should be removed from FTS index."""
        pid = sample_posts[0]  # "First Post About Python"
        with db.get_conn() as conn:
            conn.execute("DELETE FROM posts WHERE id = ?", (pid,))
        results = db.search_posts("First Post About Python")
        titles = [r["title"] for r in results]
        assert "First Post About Python" not in titles

    def test_fts_trigger_on_update(self, sample_feed_id, sample_posts):
        """Updated post content should be re-indexed."""
        pid = sample_posts[2]  # "Third Post No Attachments"
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE posts SET title = 'Renamed Title XYZ' WHERE id = ?", (pid,)
            )
        results = db.search_posts("XYZ")
        titles = [r["title"] for r in results]
        assert "Renamed Title XYZ" in titles
        # Old title should no longer match
        results_old = db.search_posts("Third Post No Attachments")
        assert all(r["id"] != pid for r in results_old)


class TestReadUnread:
    """Tests for post read/unread state."""

    def test_new_post_is_unread(self, sample_feed_id, sample_posts):
        post = db.get_timeline(limit=1)[0]
        assert post["read_at"] is None

    def test_mark_post_read(self, sample_feed_id, sample_posts):
        pid = sample_posts[0]
        db.mark_post_read(pid)
        post = db.get_timeline(limit=1)[0]
        assert post["read_at"] is not None

    def test_mark_post_unread(self, sample_feed_id, sample_posts):
        pid = sample_posts[0]
        db.mark_post_read(pid)
        assert db.get_timeline(limit=1)[0]["read_at"] is not None
        db.mark_post_unread(pid)
        post = db.get_timeline(limit=1)[0]
        assert post["read_at"] is None

    def test_mark_feed_read(self, sample_feed_id, sample_posts, second_feed_id):
        # Add a post to second feed
        db.add_post(second_feed_id, "second-feed-post", "Second Feed Post",
                    "summary", "content", "https://another.com/post",
                    "A", "2026-07-10T12:00:00")
        db.mark_feed_read(sample_feed_id)
        # All sample_posts should be read
        with db.get_conn() as conn:
            read_count = conn.execute(
                "SELECT COUNT(*) as c FROM posts WHERE feed_id = ? AND read_at IS NOT NULL",
                (sample_feed_id,),
            ).fetchone()["c"]
            assert read_count == len(sample_posts)
        # Second feed post should still be unread
        unread = db.get_unread_count(feed_id=second_feed_id)
        assert unread == 1

    def test_mark_all_read(self, sample_feed_id, sample_posts, second_feed_id):
        db.add_post(second_feed_id, "second-feed-post", "Second Feed Post",
                    "summary", "content", "https://another.com/post",
                    "A", "2026-07-10T12:00:00")
        db.mark_all_read()
        assert db.get_unread_count() == 0

    def test_get_unread_count(self, sample_feed_id, sample_posts):
        assert db.get_unread_count() == 3
        db.mark_post_read(sample_posts[0])
        assert db.get_unread_count() == 2
        assert db.get_unread_count(feed_id=sample_feed_id) == 2

    def test_stats_includes_unread(self, sample_feed_id, sample_posts):
        stats = db.get_stats()
        assert "unread" in stats
        assert stats["unread"] == 3
        db.mark_post_read(sample_posts[0])
        stats = db.get_stats()
        assert stats["unread"] == 2

    def test_read_at_in_timeline(self, sample_feed_id, sample_posts):
        pid = sample_posts[0]
        db.mark_post_read(pid)
        posts = db.get_timeline()
        post = next(p for p in posts if p["id"] == pid)
        assert post["read_at"] is not None
        # Other posts should still be unread
        other = next(p for p in posts if p["id"] != pid)
        assert other["read_at"] is None

    def test_read_at_in_search(self, sample_feed_id, sample_posts):
        pid = sample_posts[0]  # "First Post About Python"
        db.mark_post_read(pid)
        results = db.search_posts("Python")
        post = next(p for p in results if p["id"] == pid)
        assert post["read_at"] is not None

    def test_read_at_in_feed_posts(self, sample_feed_id, sample_posts):
        pid = sample_posts[0]
        db.mark_post_read(pid)
        posts = db.get_timeline(feed_id=sample_feed_id)
        post = next(p for p in posts if p["id"] == pid)
        assert post["read_at"] is not None

    def test_migration_adds_read_at(self, tmp_path, monkeypatch):
        """init_db should add read_at column to existing tables without it."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(db, "DB_PATH", db_path)
        # Create DB with old schema (no read_at)
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE feeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    site_url TEXT,
                    icon_url TEXT,
                    etag TEXT,
                    last_modified TEXT,
                    last_fetched TEXT,
                    fetch_error TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_id INTEGER NOT NULL REFERENCES feeds(id),
                    guid TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    content TEXT,
                    url TEXT,
                    author TEXT,
                    published_at TEXT,
                    fetched_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(feed_id, guid)
                )
            """)
            conn.execute("INSERT INTO feeds (url, title) VALUES ('https://example.com/feed.xml', 'Test')")
            conn.execute("INSERT INTO posts (feed_id, guid, title) VALUES (1, 'g1', 'Post 1')")
        # Now run init_db which should migrate
        db.init_db()
        with db.get_conn() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(posts)").fetchall()}
            assert "read_at" in cols
            # Existing data preserved
            row = conn.execute("SELECT title, read_at FROM posts WHERE id = 1").fetchone()
            assert row["title"] == "Post 1"
            assert row["read_at"] is None

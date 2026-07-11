"""Tests for the FastAPI app endpoints (app.py)."""
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

import app as app_module
import db


class TestIndex:
    def test_index_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Feediverse" in resp.text
        assert "text/html" in resp.headers.get("content-type", "")

    def test_manifest_json(self, client):
        resp = client.get("/static/manifest.json")
        assert resp.status_code == 200


class TestStats:
    def test_stats_empty(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feeds"] == 0
        assert data["posts"] == 0

    def test_stats_with_data(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/stats")
        data = resp.json()
        assert data["feeds"] == 1
        assert data["posts"] == 3


class TestListFeeds:
    def test_list_feeds_empty(self, client):
        resp = client.get("/api/feeds")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_feeds_with_data(self, client, sample_feed_id, second_feed_id):
        resp = client.get("/api/feeds")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["title"] in ("Another Feed", "Example Blog")


class TestGetFeed:
    def test_get_feed_by_id(self, client, sample_feed_id, sample_posts):
        resp = client.get(f"/api/feeds/{sample_feed_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feed"]["title"] == "Example Blog"
        assert len(data["posts"]) == 3

    def test_get_feed_not_found(self, client):
        resp = client.get("/api/feeds/99999")
        assert resp.status_code == 404

    def test_get_feed_empty(self, client, sample_feed_id):
        resp = client.get(f"/api/feeds/{sample_feed_id}")
        data = resp.json()
        assert data["posts"] == []


class TestAddFeed:
    def test_add_feed_empty_url(self, client):
        resp = client.post("/api/feeds", json={"url": ""})
        assert resp.status_code == 400

    def test_add_feed_already_following(self, client, sample_feed_id):
        resp = client.post("/api/feeds", json={"url": "https://example.com/feed.xml"})
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert data["feed"]["id"] == sample_feed_id

    def test_add_feed_normalizes_url(self, client):
        """URL without scheme should get https:// prepended."""
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = []
            resp = client.post("/api/feeds", json={"url": "example.com"})
        assert resp.status_code == 404  # no feed found
        # Verify discover_feeds was called with normalized URL
        called_url = mock_discover.call_args[0][0]
        assert called_url.startswith("https://")

    def test_add_feed_no_feeds_found(self, client):
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = []
            resp = client.post("/api/feeds", json={"url": "https://nofeed.com"})
        assert resp.status_code == 404

    def test_add_feed_single_feed_found(self, client):
        mock_feed_result = {
            "title": "Test Feed", "description": "Desc",
            "site_url": "https://test.com", "icon_url": "",
            "etag": "etag1", "last_modified": "mod1",
            "entries": [{
                "guid": "g1", "title": "Post 1", "summary": "S",
                "content": "C", "url": "https://test.com/1",
                "author": "A", "published_at": "2026-07-10T12:00:00",
                "attachments": [],
            }],
        }
        with patch("app.discover_feeds") as mock_discover, \
             patch("app.fetch_feed") as mock_fetch:
            mock_discover.return_value = [{"url": "https://test.com/feed.xml", "title": "Test"}]
            mock_fetch.return_value = mock_feed_result
            resp = client.post("/api/feeds", json={"url": "https://test.com"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["feed"]["title"] == "Test Feed"
        assert data["posts_added"] == 1

    def test_add_feed_multiple_feeds_found(self, client):
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = [
                {"url": "https://test.com/rss", "title": "RSS"},
                {"url": "https://test.com/atom", "title": "Atom"},
            ]
            resp = client.post("/api/feeds", json={"url": "https://test.com"})

        assert resp.status_code == 200
        data = resp.json()
        assert "discovered" in data
        assert len(data["discovered"]) == 2

    def test_add_feed_fetch_error(self, client):
        with patch("app.discover_feeds") as mock_discover, \
             patch("app.fetch_feed") as mock_fetch:
            mock_discover.return_value = [{"url": "https://test.com/feed.xml", "title": "Test"}]
            mock_fetch.return_value = {"error": "Parse error"}
            resp = client.post("/api/feeds", json={"url": "https://test.com"})

        assert resp.status_code == 400

    def test_add_feed_fetch_exception(self, client):
        with patch("app.discover_feeds") as mock_discover, \
             patch("app.fetch_feed") as mock_fetch:
            mock_discover.return_value = [{"url": "https://test.com/feed.xml", "title": "Test"}]
            mock_fetch.side_effect = Exception("Network failure")
            resp = client.post("/api/feeds", json={"url": "https://test.com"})

        assert resp.status_code == 400
        assert "Network failure" in resp.json()["detail"]


class TestAddFeedDirect:
    def test_add_feed_direct_already_following(self, client, sample_feed_id):
        resp = client.post("/api/feeds/add-direct", json={"url": "https://example.com/feed.xml"})
        assert resp.status_code == 200
        assert "message" in resp.json()

    def test_add_feed_direct_success(self, client):
        mock_feed_result = {
            "title": "Direct Feed", "description": "D",
            "site_url": "https://direct.com", "icon_url": "",
            "etag": "", "last_modified": "",
            "entries": [],
        }
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.return_value = mock_feed_result
            resp = client.post("/api/feeds/add-direct", json={"url": "https://direct.com/feed.xml"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["feed"]["title"] == "Direct Feed"
        assert data["posts_added"] == 0

    def test_add_feed_direct_fetch_error(self, client):
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {"error": "404 Not Found"}
            resp = client.post("/api/feeds/add-direct", json={"url": "https://broken.com/feed"})

        assert resp.status_code == 400

    def test_add_feed_direct_exception(self, client):
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.side_effect = ConnectionError("Refused")
            resp = client.post("/api/feeds/add-direct", json={"url": "https://crash.com/feed"})

        assert resp.status_code == 400


class TestDeleteFeed:
    def test_delete_feed_success(self, client, sample_feed_id):
        resp = client.delete(f"/api/feeds/{sample_feed_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_feed_not_found(self, client):
        resp = client.delete("/api/feeds/99999")
        assert resp.status_code == 404

    def test_delete_feed_removes_posts(self, client, sample_feed_id, sample_posts):
        resp = client.delete(f"/api/feeds/{sample_feed_id}")
        assert resp.status_code == 200
        # Verify posts are gone
        stats = client.get("/api/stats").json()
        assert stats["posts"] == 0


class TestDiscover:
    def test_discover_normalizes_url(self, client):
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = []
            resp = client.get("/api/discover", params={"url": "example.com"})
        assert resp.status_code == 200
        called_url = mock_discover.call_args[0][0]
        assert called_url.startswith("https://")

    def test_discover_returns_feeds(self, client):
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = [{"url": "https://test.com/rss", "title": "RSS"}]
            resp = client.get("/api/discover", params={"url": "https://test.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["feeds"]) == 1

    def test_discover_no_feeds(self, client):
        with patch("app.discover_feeds") as mock_discover:
            mock_discover.return_value = []
            resp = client.get("/api/discover", params={"url": "https://nofeed.com"})
        assert resp.status_code == 200
        assert resp.json()["feeds"] == []


class TestTimeline:
    def test_timeline_empty(self, client):
        resp = client.get("/api/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["posts"] == []
        assert data["total"] == 0

    def test_timeline_with_posts(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/timeline")
        data = resp.json()
        assert len(data["posts"]) == 3
        assert data["total"] == 3

    def test_timeline_limit(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/timeline", params={"limit": 2})
        data = resp.json()
        assert len(data["posts"]) == 2
        assert data["limit"] == 2

    def test_timeline_offset(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/timeline", params={"limit": 2, "offset": 2})
        data = resp.json()
        assert len(data["posts"]) == 1

    def test_timeline_includes_attachments(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/timeline")
        posts = resp.json()["posts"]
        post1 = next(p for p in posts if p["title"] == "First Post About Python")
        assert len(post1["attachments"]) == 2

    def test_timeline_feed_specific(self, client, sample_feed_id, sample_posts, second_feed_id):
        resp = client.get(f"/api/timeline/{sample_feed_id}")
        data = resp.json()
        assert len(data["posts"]) == 3
        assert data["total"] == 3

    def test_timeline_feed_specific_empty(self, client, second_feed_id):
        resp = client.get(f"/api/timeline/{second_feed_id}")
        data = resp.json()
        assert data["posts"] == []
        assert data["total"] == 0


class TestSearch:
    def test_search_too_short(self, client):
        resp = client.get("/api/search", params={"q": "a"})
        assert resp.status_code == 400

    def test_search_empty_query(self, client):
        resp = client.get("/api/search", params={"q": ""})
        assert resp.status_code == 400

    def test_search_success(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/search", params={"q": "Python"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["posts"]) >= 1
        assert data["query"] == "Python"

    def test_search_no_results(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/search", params={"q": "nonexistentterm99999"})
        assert resp.status_code == 200
        assert resp.json()["posts"] == []

    def test_search_includes_feed_info(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/search", params={"q": "Python"})
        post = resp.json()["posts"][0]
        assert "feed_title" in post
        assert "feed_icon" in post

    def test_search_with_limit(self, client, sample_feed_id, sample_posts):
        resp = client.get("/api/search", params={"q": "Post", "limit": 2})
        assert len(resp.json()["posts"]) == 2


class TestFeedMedia:
    def test_feed_media_success(self, client, sample_feed_id, sample_posts):
        resp = client.get(f"/api/feeds/{sample_feed_id}/media")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feed_id"] == sample_feed_id
        assert len(data["media"]) == 3

    def test_feed_media_not_found(self, client):
        resp = client.get("/api/feeds/99999/media")
        assert resp.status_code == 404

    def test_feed_media_empty(self, client, sample_feed_id):
        resp = client.get(f"/api/feeds/{sample_feed_id}/media")
        data = resp.json()
        assert data["media"] == []

    def test_feed_media_limit(self, client, sample_feed_id, sample_posts):
        resp = client.get(f"/api/feeds/{sample_feed_id}/media", params={"limit": 2})
        assert len(resp.json()["media"]) == 2


class TestOpmlExport:
    def test_opml_export_empty(self, client):
        resp = client.get("/api/opml/export")
        assert resp.status_code == 200
        assert "xml" in resp.headers.get("content-type", "")
        assert "<opml" in resp.text
        assert "</opml>" in resp.text

    def test_opml_export_with_feeds(self, client, sample_feed_id, second_feed_id):
        resp = client.get("/api/opml/export")
        assert resp.status_code == 200
        assert "example.com/feed.xml" in resp.text
        assert "another.com/rss.xml" in resp.text
        assert "Feediverse Subscriptions" in resp.text

    def test_opml_export_has_disposition(self, client):
        resp = client.get("/api/opml/export")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "feediverse.opml" in resp.headers.get("content-disposition", "")

    def test_opml_export_escapes_special_chars(self, client):
        db.add_feed("https://test.com/feed?a=1&b=2", "Test <Feed> & Co",
                    None, None, None)
        resp = client.get("/api/opml/export")
        assert "&amp;" in resp.text
        assert "&lt;" in resp.text
        assert "&gt;" in resp.text


class TestOpmlImport:
    SAMPLE_OPML = '''<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
  <head><title>Test Subscriptions</title></head>
  <body>
    <outline text="Feeds" title="Feeds">
      <outline type="rss" text="Feed 1" title="Feed 1"
               xmlUrl="https://feed1.com/rss" htmlUrl="https://feed1.com"/>
      <outline type="rss" text="Feed 2" title="Feed 2"
               xmlUrl="https://feed2.com/atom" htmlUrl="https://feed2.com"/>
    </outline>
  </body>
</opml>'''

    def test_opml_import_success(self, client):
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Mock", "description": "", "site_url": "",
                "icon_url": "", "etag": "", "last_modified": "",
                "entries": [],
            }
            resp = client.post("/api/opml/import",
                               content=self.SAMPLE_OPML,
                               headers={"Content-Type": "application/xml"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["added"] == 2
        assert data["failed"] == 0

    def test_opml_import_invalid_xml(self, client):
        resp = client.post("/api/opml/import",
                           content="<not valid xml<<<",
                           headers={"Content-Type": "application/xml"})
        assert resp.status_code == 400
        assert "Invalid OPML" in resp.json()["detail"]

    def test_opml_import_no_feeds(self, client):
        opml = '''<?xml version="1.0"?>
<opml version="2.0"><head><title>Empty</title></head>
<body><outline text="Nothing" title="Nothing"/></body></opml>'''
        resp = client.post("/api/opml/import",
                           content=opml,
                           headers={"Content-Type": "application/xml"})
        assert resp.status_code == 400
        assert "No feeds" in resp.json()["detail"]

    def test_opml_import_skips_existing(self, client, sample_feed_id):
        opml = f'''<?xml version="1.0"?>
<opml version="2.0"><body>
<outline type="rss" text="Existing" title="Existing"
         xmlUrl="https://example.com/feed.xml" htmlUrl="https://example.com"/>
</body></opml>'''
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Mock", "description": "", "site_url": "",
                "icon_url": "", "etag": "", "last_modified": "",
                "entries": [],
            }
            resp = client.post("/api/opml/import",
                               content=opml,
                               headers={"Content-Type": "application/xml"})

        assert resp.status_code == 200
        assert resp.json()["added"] == 0  # already exists

    def test_opml_import_nested_folders(self, client):
        """OPML with nested folder outlines should still find feeds."""
        opml = '''<?xml version="1.0"?>
<opml version="2.0"><body>
<outline text="Tech" title="Tech">
  <outline text="Blogs" title="Blogs">
    <outline type="rss" text="Blog 1" title="Blog 1"
             xmlUrl="https://blog1.com/feed" htmlUrl="https://blog1.com"/>
  </outline>
</outline>
</body></opml>'''
        with patch("feed_fetcher.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Mock", "description": "", "site_url": "",
                "icon_url": "", "etag": "", "last_modified": "",
                "entries": [],
            }
            resp = client.post("/api/opml/import",
                               content=opml,
                               headers={"Content-Type": "application/xml"})
        assert resp.status_code == 200
        assert resp.json()["added"] == 1


class TestPreview:
    def test_preview_normalizes_url(self, client):
        with patch("feed_fetcher.fetch_og_metadata") as mock_og:
            mock_og.return_value = {"url": "https://example.com", "title": "Example"}
            resp = client.get("/api/preview", params={"url": "example.com"})
        assert resp.status_code == 200
        called_url = mock_og.call_args[0][0]
        assert called_url.startswith("https://")

    def test_preview_returns_metadata(self, client):
        with patch("feed_fetcher.fetch_og_metadata") as mock_og:
            mock_og.return_value = {
                "url": "https://example.com",
                "title": "Example Site",
                "description": "An example",
                "image": "https://example.com/og.png",
                "site_name": "Example",
            }
            resp = client.get("/api/preview", params={"url": "https://example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Example Site"
        assert data["image"] == "https://example.com/og.png"

    def test_preview_error_handled(self, client):
        with patch("feed_fetcher.fetch_og_metadata") as mock_og:
            mock_og.return_value = {"url": "https://broken.com", "title": "broken.com",
                                     "error": "Connection refused"}
            resp = client.get("/api/preview", params={"url": "https://broken.com"})
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestRefresh:
    def test_refresh_no_feeds(self, client):
        resp = client.post("/api/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feeds"] == 0

    def test_refresh_with_feeds(self, client, sample_feed_id, sample_posts):
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {"not_modified": True, "etag": "", "last_modified": ""}
            resp = client.post("/api/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["feeds"] == 1

    def test_refresh_fetch_error_logged(self, client, sample_feed_id):
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.return_value = {"error": "Timeout"}
            resp = client.post("/api/refresh")
        assert resp.status_code == 200
        # Feed should have error recorded
        feed = db.get_feed_by_id(sample_feed_id)
        assert feed["fetch_error"] == "Timeout"

    def test_refresh_fetch_exception(self, client, sample_feed_id):
        with patch("app.fetch_feed") as mock_fetch:
            mock_fetch.side_effect = Exception("Unexpected crash")
            resp = client.post("/api/refresh")
        assert resp.status_code == 200  # refresh should not crash
        feed = db.get_feed_by_id(sample_feed_id)
        assert "Unexpected crash" in (feed["fetch_error"] or "")
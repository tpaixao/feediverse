"""Tests for feed_fetcher.py — feed parsing, discovery, and OG metadata."""
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest

import feed_fetcher
from feed_fetcher import (
    parse_date, extract_content, extract_attachments,
    extract_feed_icon, fetch_og_metadata, discover_feeds,
    fetch_feed, fetch_url,
)


class TestParseDate:
    def test_parse_date_published(self):
        entry = {"published_parsed": (2026, 7, 10, 12, 0, 0, 0, 0, 0)}
        result = parse_date(entry)
        assert result == "2026-07-10T12:00:00"

    def test_parse_date_updated_fallback(self):
        entry = {"updated_parsed": (2026, 7, 9, 10, 30, 0, 0, 0, 0)}
        result = parse_date(entry)
        assert result == "2026-07-09T10:30:00"

    def test_parse_date_created_fallback(self):
        entry = {"created_parsed": (2026, 7, 8, 8, 0, 0, 0, 0, 0)}
        result = parse_date(entry)
        assert result == "2026-07-08T08:00:00"

    def test_parse_date_no_date(self):
        assert parse_date({}) is None

    def test_parse_date_invalid(self):
        entry = {"published_parsed": (0, 0, 0, 0, 0, 0, 0, 0, 0)}
        # Should not raise, should return None or a valid date
        result = parse_date(entry)
        # datetime(0,0,0,...) will raise, caught and returns None
        assert result is None


class TestExtractContent:
    def test_extract_content_with_content(self):
        entry = {"content": [{"value": "<p>Full content</p>"}], "summary": "Short"}
        summary, content = extract_content(entry)
        assert content == "<p>Full content</p>"
        assert summary == "Short"

    def test_extract_content_summary_only(self):
        entry = {"summary": "<p>Just a summary</p>"}
        summary, content = extract_content(entry)
        assert content == "<p>Just a summary</p>"
        assert summary == "<p>Just a summary</p>"

    def test_extract_content_empty(self):
        summary, content = extract_content({})
        assert summary == ""
        assert content == ""

    def test_extract_content_generates_summary_from_content(self):
        entry = {"content": [{"value": "<p>This is a long piece of content " * 20 + "</p>"}]}
        summary, content = extract_content(entry)
        assert "..." in summary
        assert len(summary) <= 303  # 300 + "..."

    def test_extract_content_summary_no_html(self):
        entry = {"content": [{"value": "<p>Hello world</p>"}]}
        summary, content = extract_content(entry)
        # Summary is generated from content as plain text
        assert "Hello world" in summary


class TestExtractAttachments:
    def test_extract_enclosure_image(self):
        entry = {"enclosures": [{"href": "https://example.com/img.png", "type": "image/png"}]}
        atts = extract_attachments(entry, "https://example.com")
        assert len(atts) == 1
        assert atts[0]["type"] == "image"
        assert atts[0]["url"] == "https://example.com/img.png"

    def test_extract_enclosure_audio(self):
        entry = {"enclosures": [{"href": "https://example.com/pod.mp3", "type": "audio/mpeg"}]}
        atts = extract_attachments(entry, "https://example.com")
        assert atts[0]["type"] == "audio"

    def test_extract_enclosure_video(self):
        entry = {"enclosures": [{"href": "https://example.com/vid.mp4", "type": "video/mp4"}]}
        atts = extract_attachments(entry, "https://example.com")
        assert atts[0]["type"] == "video"

    def test_extract_enclosure_link(self):
        entry = {"enclosures": [{"href": "https://example.com/doc.pdf", "type": "application/pdf"}]}
        atts = extract_attachments(entry, "https://example.com")
        assert atts[0]["type"] == "link"

    def test_extract_media_content(self):
        entry = {"media_content": [{"url": "https://example.com/media.jpg", "type": "image/jpeg"}]}
        atts = extract_attachments(entry, "https://example.com")
        assert len(atts) == 1
        assert atts[0]["type"] == "image"

    def test_extract_images_from_content(self):
        entry = {"content": [{"value": '<p><img src="/relative/img.png" alt="Alt"></p>'}]}
        atts = extract_attachments(entry, "https://example.com")
        assert len(atts) == 1
        assert atts[0]["url"] == "https://example.com/relative/img.png"
        assert atts[0]["title"] == "Alt"

    def test_extract_deduplicates_urls(self):
        entry = {
            "enclosures": [{"href": "https://example.com/img.png", "type": "image/png"}],
            "content": [{"value": '<img src="https://example.com/img.png">'}],
        }
        atts = extract_attachments(entry, "https://example.com")
        urls = [a["url"] for a in atts]
        assert urls.count("https://example.com/img.png") == 1

    def test_extract_empty(self):
        atts = extract_attachments({}, "https://example.com")
        assert atts == []

    def test_extract_links(self):
        entry = {
            "links": [{"rel": "enclosure", "href": "https://example.com/file.zip",
                       "type": "application/zip"}],
        }
        atts = extract_attachments(entry, "https://example.com")
        assert len(atts) == 1
        assert atts[0]["type"] == "link"


class TestExtractFeedIcon:
    def test_icon_from_feed_image_dict(self):
        feed = {"image": {"href": "https://example.com/icon.png"}}
        result = extract_feed_icon(feed, "https://example.com")
        assert result == "https://example.com/icon.png"

    def test_icon_from_feed_image_url(self):
        feed = {"image": {"url": "https://example.com/logo.png"}}
        result = extract_feed_icon(feed, "https://example.com")
        assert result == "https://example.com/logo.png"

    def test_icon_favicon_fallback(self):
        feed = {}
        result = extract_feed_icon(feed, "https://example.com")
        assert "favicons" in result
        assert "example.com" in result

    def test_icon_no_site_url(self):
        feed = {}
        result = extract_feed_icon(feed, "")
        assert result == ""

    def test_icon_no_netloc(self):
        feed = {}
        result = extract_feed_icon(feed, "not-a-url")
        assert result == ""


class TestFetchUrl:
    def test_fetch_url_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = fetch_url("https://example.com")

        assert result is mock_response

    def test_fetch_url_raises_on_error(self):
        import httpx
        with patch("feed_fetcher.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                fetch_url("https://example.com/404")


class TestFetchFeed:
    def test_fetch_feed_304_not_modified(self):
        mock_response = MagicMock()
        mock_response.status_code = 304
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = fetch_feed("https://example.com/feed.xml",
                                etag="etag123", last_modified="mod123")

        assert result["not_modified"] is True
        assert result["etag"] == "etag123"

    def test_fetch_feed_success(self):
        mock_parsed = MagicMock()
        mock_parsed.feed = {
            "title": "Test Feed", "subtitle": "A test",
            "link": "https://example.com", "image": None,
        }
        mock_parsed.entries = []
        mock_parsed.bozo = 0

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<rss></rss>"
        mock_response.headers = {"etag": "new-etag", "last-modified": "new-mod"}
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.httpx.Client") as mock_client_cls, \
             patch("feed_fetcher.feedparser.parse", return_value=mock_parsed):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = fetch_feed("https://example.com/feed.xml")

        assert result["title"] == "Test Feed"
        assert result["etag"] == "new-etag"
        assert result["entries"] == []

    def test_fetch_feed_parse_error(self):
        mock_parsed = MagicMock()
        mock_parsed.feed = {}
        mock_parsed.entries = []

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"not a feed"
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.httpx.Client") as mock_client_cls, \
             patch("feed_fetcher.feedparser.parse", return_value=mock_parsed):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = fetch_feed("https://example.com/broken")

        assert "error" in result

    def test_fetch_feed_with_entries(self):
        mock_entry = {
            "id": "guid-1",
            "title": "Post 1",
            "summary": "Summary",
            "content": [{"value": "<p>Content</p>"}],
            "link": "https://example.com/1",
            "author": "Author",
            "published_parsed": (2026, 7, 10, 12, 0, 0, 0, 0, 0),
            "enclosures": [],
            "media_content": [],
            "links": [],
        }
        mock_parsed = MagicMock()
        mock_parsed.feed = {"title": "Test", "subtitle": "", "link": "https://example.com"}
        mock_parsed.entries = [mock_entry]
        mock_parsed.bozo = 0

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<rss></rss>"
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.httpx.Client") as mock_client_cls, \
             patch("feed_fetcher.feedparser.parse", return_value=mock_parsed):
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value = mock_client

            result = fetch_feed("https://example.com/feed.xml")

        assert len(result["entries"]) == 1
        entry = result["entries"][0]
        assert entry["guid"] == "guid-1"
        assert entry["title"] == "Post 1"
        assert entry["published_at"] == "2026-07-10T12:00:00"


class TestDiscoverFeeds:
    def test_discover_already_feed(self):
        """URL that is already a feed should return itself."""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/rss+xml"}
        mock_response.content = b"<rss></rss>"
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        mock_parsed = MagicMock()
        mock_parsed.bozo = 0
        mock_parsed.entries = [MagicMock()]
        mock_parsed.feed = {"title": "Direct Feed"}

        with patch("feed_fetcher.fetch_url", return_value=mock_response), \
             patch("feed_fetcher.feedparser.parse", return_value=mock_parsed):
            result = discover_feeds("https://example.com/feed.xml")

        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/feed.xml"

    def test_discover_html_with_link_tags(self):
        html = '''<html><head>
        <link rel="alternate" type="application/rss+xml" href="/feed.xml" title="RSS">
        </head><body></body></html>'''

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.content = b"<html></html>"
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = discover_feeds("https://example.com")

        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/feed.xml"

    def test_discover_html_with_atom_link(self):
        html = '''<html><head>
        <link rel="alternate" type="application/atom+xml" href="/atom.xml" title="Atom">
        </head><body></body></html>'''

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = discover_feeds("https://example.com")

        assert len(result) == 1
        assert "atom" in result[0]["url"]

    def test_discover_no_feeds_found(self):
        html = "<html><head></head><body>No feeds here</body></html>"
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        # Mock the probe paths to all fail
        def mock_fetch_url(url, timeout=15):
            if url == "https://example.com":
                return mock_response
            raise Exception("404")

        with patch("feed_fetcher.fetch_url", side_effect=mock_fetch_url):
            result = discover_feeds("https://example.com")

        assert result == []

    def test_discover_connection_error(self):
        with patch("feed_fetcher.fetch_url", side_effect=Exception("Connection refused")):
            result = discover_feeds("https://broken.com")
        assert result == []

    def test_discover_multiple_feeds(self):
        html = '''<html><head>
        <link rel="alternate" type="application/rss+xml" href="/rss" title="RSS">
        <link rel="alternate" type="application/atom+xml" href="/atom" title="Atom">
        </head><body></body></html>'''

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = discover_feeds("https://example.com")

        assert len(result) == 2


class TestFetchOgMetadata:
    def test_fetch_og_with_og_tags(self):
        html = '''<html><head>
        <meta property="og:title" content="Example Page">
        <meta property="og:description" content="An example description">
        <meta property="og:image" content="https://example.com/og.png">
        <meta property="og:site_name" content="ExampleSite">
        </head><body></body></html>'''

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["title"] == "Example Page"
        assert result["description"] == "An example description"
        assert result["image"] == "https://example.com/og.png"
        assert result["site_name"] == "ExampleSite"
        assert result["url"] == "https://example.com"

    def test_fetch_og_twitter_fallback(self):
        html = '''<html><head>
        <meta name="twitter:title" content="Twitter Title">
        <meta name="twitter:image" content="https://example.com/tw.png">
        </head><body></body></html>'''

        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["title"] == "Twitter Title"
        assert result["image"] == "https://example.com/tw.png"

    def test_fetch_og_title_fallback(self):
        html = "<html><head><title>Plain Title</title></head><body></body></html>"
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["title"] == "Plain Title"

    def test_fetch_og_favicon_fallback(self):
        html = '''<html><head>
        <link rel="icon" href="/favicon.ico">
        </head><body></body></html>'''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert "favicon.ico" in result.get("image", "")

    def test_fetch_og_description_fallback(self):
        html = '''<html><head>
        <meta name="description" content="Meta description">
        </head><body></body></html>'''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["description"] == "Meta description"

    def test_fetch_og_connection_error(self):
        with patch("feed_fetcher.fetch_url", side_effect=Exception("Timeout")):
            result = fetch_og_metadata("https://broken.com")

        assert "error" in result
        assert result["url"] == "https://broken.com"

    def test_fetch_og_og_overrides_twitter(self):
        html = '''<html><head>
        <meta property="og:title" content="OG Title">
        <meta name="twitter:title" content="Twitter Title">
        </head><body></body></html>'''
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["title"] == "OG Title"

    def test_fetch_og_empty_page(self):
        html = "<html><head></head><body></body></html>"
        mock_response = MagicMock()
        mock_response.text = html
        mock_response.raise_for_status = MagicMock()

        with patch("feed_fetcher.fetch_url", return_value=mock_response):
            result = fetch_og_metadata("https://example.com")

        assert result["url"] == "https://example.com"
        assert "title" in result  # should have at least the URL as title
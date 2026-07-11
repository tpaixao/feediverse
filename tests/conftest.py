"""Pytest configuration and fixtures for Feediverse tests."""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Set test env before importing app
os.environ["FEEDIVERSE_INTERVAL"] = "9999"
os.environ["FEEDIVERSE_TEST"] = "1"

# We need to patch the scheduler BEFORE importing app, because app creates
# BackgroundScheduler and adds jobs at module level.
_scheduler_patcher = patch("apscheduler.schedulers.background.BackgroundScheduler")
_mock_scheduler_cls = _scheduler_patcher.start()
_mock_scheduler = MagicMock()
_mock_scheduler_cls.return_value = _mock_scheduler

# Now import app and db
sys.path.insert(0, str(Path(__file__).parent))
import db
import app as app_module


# --- Temp database fixture ---

@pytest.fixture
def temp_db(tmp_path):
    """Replace the DB_PATH with a temp file, init schema, yield, cleanup."""
    test_db_path = tmp_path / "test_feediverse.db"
    original_path = db.DB_PATH
    db.DB_PATH = test_db_path

    db.init_db()
    yield test_db_path

    db.DB_PATH = original_path


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient with temp database and mocked scheduler."""
    from fastapi.testclient import TestClient
    tc = TestClient(app_module.app)
    yield tc


# --- Sample data fixtures ---

@pytest.fixture
def sample_feed_id(temp_db):
    """Insert a sample feed and return its id."""
    feed_id = db.add_feed(
        "https://example.com/feed.xml",
        "Example Blog",
        "A test blog",
        "https://example.com",
        "https://example.com/icon.png",
    )
    return feed_id


@pytest.fixture
def sample_posts(sample_feed_id):
    """Insert sample posts with attachments into the temp DB."""
    posts_data = [
        {
            "guid": "post-1",
            "title": "First Post About Python",
            "summary": "A summary about Python programming",
            "content": "<p>Full content about <a href='https://python.org'>Python</a></p>",
            "url": "https://example.com/post-1",
            "author": "Alice",
            "published_at": "2026-07-10T12:00:00",
            "attachments": [
                {"type": "image", "url": "https://example.com/img1.png", "title": "Image 1"},
                {"type": "link", "url": "https://python.org", "title": "Python"},
            ],
        },
        {
            "guid": "post-2",
            "title": "Second Post About Testing",
            "summary": "Testing strategies for Python apps",
            "content": "<p>Content about <b>testing</b></p>",
            "url": "https://example.com/post-2",
            "author": "Bob",
            "published_at": "2026-07-09T10:00:00",
            "attachments": [
                {"type": "image", "url": "https://example.com/img2.png", "title": "Image 2"},
            ],
        },
        {
            "guid": "post-3",
            "title": "Third Post No Attachments",
            "summary": "A post with no media",
            "content": "Plain text content",
            "url": "https://example.com/post-3",
            "author": "Alice",
            "published_at": "2026-07-08T08:00:00",
            "attachments": [],
        },
    ]

    post_ids = []
    for p in posts_data:
        pid = db.add_post(
            sample_feed_id, p["guid"], p["title"], p["summary"],
            p["content"], p["url"], p["author"], p["published_at"],
        )
        assert pid is not None, f"Failed to insert post {p['guid']}"
        for att in p["attachments"]:
            db.add_attachment(pid, att["type"], att["url"], att["title"])
        post_ids.append(pid)

    return post_ids


@pytest.fixture
def second_feed_id(temp_db):
    """Insert a second feed for multi-feed tests."""
    feed_id = db.add_feed(
        "https://another.com/rss.xml",
        "Another Feed",
        "Second test feed",
        "https://another.com",
        "",
    )
    return feed_id
"""FastAPI application for Feediverse — read-only RSS reader PWA."""
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
from feed_fetcher import discover_feeds, fetch_feed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
log = logging.getLogger("feediverse")

app = FastAPI(title="Feediverse", docs_url="/api/docs")

STATIC_DIR = Path(__file__).parent / "static"
FETCH_INTERVAL_MIN = int(os.environ.get("FEEDIVERSE_INTERVAL", "30"))


# --- Scheduler ---

def refresh_all_feeds():
    """Background job: fetch all feeds and update posts."""
    feeds = db.get_all_feeds()
    if not feeds:
        return

    log.info(f"Refreshing {len(feeds)} feeds...")
    new_count = 0
    for feed in feeds:
        try:
            result = fetch_feed(feed["url"], feed["etag"], feed["last_modified"])
            if result.get("not_modified"):
                db.update_feed_fetched(feed["id"], feed["etag"], feed["last_modified"])
                continue
            if result.get("error"):
                db.update_feed_fetched(feed["id"], "", "", error=result["error"])
                log.warning(f"Feed {feed['url']}: {result['error']}")
                continue

            db.update_feed_meta(feed["id"], result["title"], result["description"],
                                result["site_url"], result["icon_url"])
            db.update_feed_fetched(feed["id"], result.get("etag", ""),
                                    result.get("last_modified", ""))

            for entry in result["entries"]:
                post_id = db.add_post(
                    feed["id"], entry["guid"], entry["title"], entry["summary"],
                    entry["content"], entry["url"], entry["author"], entry["published_at"],
                )
                if post_id:
                    new_count += 1
                    for att in entry["attachments"]:
                        db.add_attachment(post_id, att["type"], att["url"], att["title"])

        except Exception as e:
            db.update_feed_fetched(feed["id"], "", "", error=str(e))
            log.error(f"Failed to fetch {feed['url']}: {e}")

    log.info(f"Refresh complete: {new_count} new posts from {len(feeds)} feeds")


scheduler = BackgroundScheduler()
scheduler.add_job(refresh_all_feeds, "interval", minutes=FETCH_INTERVAL_MIN,
                  id="refresh", next_run_time=None)
scheduler.add_job(refresh_all_feeds, "date", id="initial_refresh")  # run once on startup


@app.on_event("startup")
def on_startup():
    db.init_db()
    scheduler.start()
    log.info(f"Feediverse started — fetching every {FETCH_INTERVAL_MIN} min")


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown(wait=False)


# --- API Models ---

class AddFeedRequest(BaseModel):
    url: str


# --- OPML Import/Export ---

@app.get("/api/opml/export")
def api_opml_export():
    """Export all followed feeds as OPML XML."""
    feeds = db.get_all_feeds()
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<opml version="2.0">',
        '  <head>',
        '    <title>Feediverse Subscriptions</title>',
        f'    <dateCreated>{datetime.now(timezone.utc).isoformat()}</dateCreated>',
        '  </head>',
        '  <body>',
        '    <outline text="Feeds" title="Feeds">',
    ]
    for feed in feeds:
        title = (feed["title"] or feed["url"]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', '&quot;')
        url = feed["url"].replace("&", "&amp;").replace('"', '&quot;')
        site = (feed["site_url"] or "").replace("&", "&amp;").replace('"', '&quot;')
        xml_lines.append(
            f'      <outline type="rss" text="{title}" title="{title}" '
            f'xmlUrl="{url}" htmlUrl="{site}"/>'
        )
    xml_lines.extend(['    </outline>', '  </body>', '</opml>'])
    opml = '\n'.join(xml_lines)
    return Response(
        content=opml,
        media_type="application/xml",
        headers={"Content-Disposition": "attachment; filename=feediverse.opml"}
    )


@app.post("/api/opml/import")
async def api_opml_import(req: Request):
    """Import feeds from an uploaded OPML file."""
    from xml.etree import ElementTree as ET

    body_bytes = await req.body()
    try:
        root = ET.fromstring(body_bytes)
    except ET.ParseError as e:
        raise HTTPException(400, f"Invalid OPML: {e}")

    feeds_data = []
    for outline in root.iter("outline"):
        xml_url = outline.get("xmlUrl")
        if xml_url:
            feeds_data.append({
                "url": xml_url,
                "title": outline.get("title") or outline.get("text") or xml_url,
            })

    if not feeds_data:
        raise HTTPException(400, "No feeds found in OPML file")

    result = db.add_opml_feeds(feeds_data)
    return result


# --- API Routes ---

@app.get("/api/stats")
def api_stats():
    return db.get_stats()


@app.get("/api/feeds")
def api_list_feeds():
    return db.get_all_feeds()


@app.get("/api/feeds/{feed_id}")
def api_get_feed(feed_id: int):
    feed = db.get_feed_by_id(feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    posts = db.get_timeline(limit=100, feed_id=feed_id)
    return {"feed": feed, "posts": posts}


@app.post("/api/feeds")
def api_add_feed(req: AddFeedRequest):
    """Add a feed by URL. Discovers feed URL if needed."""
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL required")

    # Normalize — add scheme if missing
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    # Check if already followed
    existing = db.get_feed_by_url(url)
    if existing:
        return {"feed": existing, "message": "Already following this feed"}

    # Discover feeds from the URL
    discovered = discover_feeds(url)

    if not discovered:
        raise HTTPException(404, "No RSS/Atom feed found at this URL")

    if len(discovered) == 1:
        # Single feed found — add it directly
        feed_url = discovered[0]["url"]
        # Fetch it once to get metadata
        try:
            result = fetch_feed(feed_url)
            if result.get("error"):
                raise HTTPException(400, result["error"])
            feed_id = db.add_feed(
                feed_url, result["title"], result["description"],
                result["site_url"], result["icon_url"],
            )
            # Store initial posts
            for entry in result["entries"]:
                post_id = db.add_post(
                    feed_id, entry["guid"], entry["title"], entry["summary"],
                    entry["content"], entry["url"], entry["author"], entry["published_at"],
                )
                if post_id:
                    for att in entry["attachments"]:
                        db.add_attachment(post_id, att["type"], att["url"], att["title"])

            feed = db.get_feed_by_id(feed_id)
            db.update_feed_fetched(feed_id, result.get("etag", ""),
                                    result.get("last_modified", ""))
            return {"feed": feed, "posts_added": len(result["entries"])}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Failed to fetch feed: {e}")

    # Multiple feeds found — return options for user to choose
    return {"discovered": discovered}


@app.post("/api/feeds/add-direct")
def api_add_feed_direct(req: AddFeedRequest):
    """Add a specific feed URL directly (when user picks from discovered list)."""
    feed_url = req.url.strip()
    existing = db.get_feed_by_url(feed_url)
    if existing:
        return {"feed": existing, "message": "Already following"}

    try:
        result = fetch_feed(feed_url)
        if result.get("error"):
            raise HTTPException(400, result["error"])
        feed_id = db.add_feed(
            feed_url, result["title"], result["description"],
            result["site_url"], result["icon_url"],
        )
        for entry in result["entries"]:
            post_id = db.add_post(
                feed_id, entry["guid"], entry["title"], entry["summary"],
                entry["content"], entry["url"], entry["author"], entry["published_at"],
            )
            if post_id:
                for att in entry["attachments"]:
                    db.add_attachment(post_id, att["type"], att["url"], att["title"])

        feed = db.get_feed_by_id(feed_id)
        db.update_feed_fetched(feed_id, result.get("etag", ""),
                                result.get("last_modified", ""))
        return {"feed": feed, "posts_added": len(result["entries"])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch feed: {e}")


@app.delete("/api/feeds/{feed_id}")
def api_delete_feed(feed_id: int):
    feed = db.get_feed_by_id(feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    db.delete_feed(feed_id)
    return {"deleted": True}


@app.get("/api/discover")
def api_discover(url: str = Query(...)):
    """Discover feeds at a URL without adding them."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    feeds = discover_feeds(url)
    return {"url": url, "feeds": feeds}


@app.get("/api/timeline")
def api_timeline(limit: int = 50, offset: int = 0, sort: str = "published"):
    posts = db.get_timeline(limit=limit, offset=offset, sort_by=sort)
    total = db.get_post_count()
    return {"posts": posts, "total": total, "limit": limit, "offset": offset}


@app.get("/api/timeline/{feed_id}")
def api_timeline_feed(feed_id: int, limit: int = 50, offset: int = 0, sort: str = "published"):
    posts = db.get_timeline(limit=limit, offset=offset, feed_id=feed_id, sort_by=sort)
    total = db.get_post_count(feed_id=feed_id)
    return {"posts": posts, "total": total, "limit": limit, "offset": offset}


@app.get("/api/search")
def api_search(q: str = Query(...), limit: int = 50, offset: int = 0):
    if len(q.strip()) < 2:
        raise HTTPException(400, "Query too short")
    posts = db.search_posts(q, limit=limit, offset=offset)
    total = db.search_post_count(q)
    return {"posts": posts, "query": q, "total": total, "limit": limit, "offset": offset}


@app.get("/api/feeds/{feed_id}/media")
def api_feed_media(feed_id: int, limit: int = 50):
    """Get media attachments for a feed (for the media tab)."""
    feed = db.get_feed_by_id(feed_id)
    if not feed:
        raise HTTPException(404, "Feed not found")
    media = db.get_feed_media(feed_id, limit=limit)
    return {"feed_id": feed_id, "media": media}


@app.get("/api/preview")
def api_preview(url: str = Query(...)):
    """Fetch OpenGraph metadata for a URL to generate link previews."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    from feed_fetcher import fetch_og_metadata
    og = fetch_og_metadata(url)
    return og


@app.post("/api/refresh")
def api_refresh():
    """Manually trigger a feed refresh."""
    refresh_all_feeds()
    return db.get_stats()


# --- Static files & PWA ---

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)

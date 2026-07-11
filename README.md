# Feediverse

A read-only PWA RSS reader with a social-media-style feed UI. Inspired by HyperTexting (iOS-only) — brings the same open-web reading experience to Android and web browsers.

## Features

- **Social-media-style timeline** — reverse-chronological feed of posts from all followed sites
- **Feed discovery** — paste any website URL; automatically finds RSS/Atom feeds via `<link>` tags and common path probing
- **Follow / unfollow** — manage your subscriptions from the Explore tab
- **Rich post view** — full content rendering with images, links, and formatting
- **PWA installable** — add to home screen on Android for a native app experience
- **Offline reading** — service worker caches recent posts for offline access
- **No backend tracking** — all data stored locally on your server
- **Self-hosted** — runs on a Raspberry Pi or any Linux box

## Tech Stack

- **Backend**: FastAPI + feedparser + SQLite + APScheduler
- **Frontend**: Alpine.js + vanilla CSS (no build step)
- **Deploy**: systemd service

## Quick Start

```bash
cd projects/feediverse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Server runs on port 8090. Open `http://localhost:8090` in your browser.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/timeline` | Paginated reverse-chronological posts |
| GET | `/api/feeds` | List all followed feeds |
| GET | `/api/feeds/{id}` | Feed details + its posts |
| POST | `/api/feeds` | Add feed by URL (auto-discovers RSS) |
| POST | `/api/feeds/add-direct` | Add a specific feed URL directly |
| DELETE | `/api/feeds/{id}` | Unfollow a feed |
| GET | `/api/discover?url=` | Discover feeds at a URL without adding |
| GET | `/api/search?q=` | Search across all posts |
| GET | `/api/stats` | Feed/post counts and last fetch time |
| POST | `/api/refresh` | Manually trigger a feed refresh |

API docs available at `/api/docs`.

## Architecture

```
feed_fetcher.py    RSS/Atom parsing, feed discovery, media extraction
db.py              SQLite layer (feeds, posts, attachments)
app.py             FastAPI app, scheduler, API routes, static serving
static/            Frontend (Alpine.js SPA, CSS, PWA manifest, service worker)
```

The scheduler polls all followed feeds every 30 minutes (configurable via `FEEDIVERSE_INTERVAL` env var). Conditional GETs with ETag/Last-Modified headers minimize bandwidth.

## Feed Discovery

When you add a website URL, Feediverse:

1. Parses HTML for `<link rel="alternate" type="application/rss+xml">` tags
2. Probes common feed paths (`/feed`, `/rss`, `/atom.xml`, `/feed.xml`, etc.)
3. If the URL itself is a feed, detects and adds it directly
4. If multiple feeds are found, presents options for you to choose from

## Deployment (systemd)

```bash
# Copy service file
cp feediverse.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable feediverse
systemctl --user start feediverse
```

Requires user lingering enabled (`loginctl enable-linger $USER`) for the service to survive logout/reboot.

## Roadmap

- **Phase 2**: Site profile pages, rich link previews, search UI, OPML import/export
- **Phase 3**: RSS Bridge integration for feedless sites, trending links, push notifications, bookmarks

## License

MIT
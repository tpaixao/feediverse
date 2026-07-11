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
| GET | `/api/feeds/{id}/media` | Get media attachments for a feed |
| GET | `/api/discover?url=` | Discover feeds at a URL without adding |
| GET | `/api/search?q=` | Search across all posts |
| GET | `/api/preview?url=` | Fetch OpenGraph metadata for link previews |
| GET | `/api/opml/export` | Export all feeds as OPML XML |
| POST | `/api/opml/import` | Import feeds from OPML (upload XML body) |
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

## Installation

### From source (any Linux box)

```bash
git clone https://github.com/tpaixao/feediverse.git
cd feediverse
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Server runs on port 8090. Open `http://localhost:8090` in your browser.

### Deploy as a systemd service (recommended)

The service file assumes the repo lives at the path shown in `WorkingDirectory` and `ExecStart`. If you cloned elsewhere, edit those lines in `feediverse.service` first.

```bash
# 1. Ensure your user services survive logout/reboot (one-time)
loginctl enable-linger $USER

# 2. Create the user systemd directory if it doesn't exist
mkdir -p ~/.config/systemd/user

# 3. Copy the service file
cp feediverse.service ~/.config/systemd/user/

# 4. Reload systemd, enable and start
systemctl --user daemon-reload
systemctl --user enable feediverse
systemctl --user start feediverse

# 5. Verify it's running
systemctl --user status feediverse
```

Logs: `journalctl --user -u feediverse -f`

### Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `FEEDIVERSE_INTERVAL` | `30` | Feed polling interval in minutes |

Set in the `Environment=` line of the service file.

### Access from other devices

Once running, the server listens on `0.0.0.0:8090`. From any device on the same network:

```
http://<your-server-ip>:8090
```

### Install as a PWA (Android)

1. Open the URL above in Chrome on your Android device
2. Tap the menu (⋮) → **Add to Home screen**
3. Feediverse launches full-screen with its own icon, no browser chrome

### Install as a PWA (Desktop Chrome/Edge)

1. Open the URL in Chrome or Edge
2. Click the install icon (⊕) in the address bar, or menu → **Install Feediverse**

## Roadmap

### Phase 1 (MVP) ✅
- [x] Backend: feed fetcher, parser, SQLite storage, basic API
- [x] Frontend: timeline view, add feed by URL with discovery, follow/unfollow
- [x] PWA manifest + service worker + offline caching
- [x] Deploy on Pi

### Phase 2 ✅
- [x] Site profile pages with media tabs
- [x] Rich content rendering (images, audio/video players, link sanitization)
- [x] Search across posts (full UI + debounce)
- [x] OPML import/export
- [x] OpenGraph link preview API (`/api/preview`)

### Phase 3 (Future)
- [ ] RSS Bridge integration for feedless sites
- [ ] Hot HyperLinks — trending links from followed feeds
- [ ] Notifications for new posts (Web Push API)
- [ ] Bookmark/save posts
- [ ] OpenGraph card rendering in timeline (rich link previews)

## License

MIT
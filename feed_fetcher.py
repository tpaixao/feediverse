"""Feed fetching, parsing, and discovery logic."""
import re
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("feediverse.fetcher")

# Common feed paths to probe when no <link> tag is found
FEED_PATHS = [
    "/feed", "/feed/", "/rss", "/rss/", "/atom.xml", "/feed.xml",
    "/index.xml", "/rss.xml", "/feeds/posts/default",
    "/blog/feed", "/blog/rss",
]

USER_AGENT = "Feediverse/0.1 (RSS Reader; +https://github.com/feediverse)"


def fetch_url(url, timeout=15):
    """Fetch URL content with proper headers."""
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp


def discover_feeds(site_url):
    """
    Discover RSS/Atom feeds from a URL.
    Returns list of {"url": ..., "title": ...} dicts.

    Strategy:
    1. Parse HTML for <link rel="alternate" type="application/rss+xml"> tags
    2. If none found, probe common feed paths
    3. If the URL itself looks like a feed, return it directly
    """
    feeds = []

    # First, check if the URL is already a feed
    try:
        resp = fetch_url(site_url)
        content_type = resp.headers.get("content-type", "")

        # If it's already XML/feed content, parse it directly
        if "xml" in content_type or "rss" in content_type or "atom" in content_type:
            parsed = feedparser.parse(resp.content)
            if parsed.bozo == 0 or parsed.entries:
                title = parsed.feed.get("title", site_url)
                return [{"url": site_url, "title": title}]

        # Parse HTML for <link> tags
        soup = BeautifulSoup(resp.text, "lxml")

        # Look for RSS/Atom link tags
        for link in soup.find_all("link", attrs={"rel": "alternate"}):
            link_type = link.get("type", "")
            href = link.get("href", "")
            if not href:
                continue
            if "rss" in link_type or "atom" in link_type or "rdf" in link_type:
                full_url = urljoin(site_url, href)
                title = link.get("title", full_url)
                feeds.append({"url": full_url, "title": title})

        if feeds:
            return feeds

        # Probe common paths
        parsed_url = urlparse(site_url)
        base = f"{parsed_url.scheme}://{parsed_url.netloc}"

        for path in FEED_PATHS:
            probe_url = base + path
            try:
                probe_resp = fetch_url(probe_url, timeout=10)
                probe_ct = probe_resp.headers.get("content-type", "")
                if "xml" in probe_ct or "rss" in probe_ct:
                    parsed = feedparser.parse(probe_resp.content)
                    if parsed.entries:
                        title = parsed.feed.get("title", probe_url)
                        feeds.append({"url": probe_url, "title": title})
            except Exception:
                continue

    except Exception as e:
        log.warning(f"Discovery failed for {site_url}: {e}")

    return feeds


def parse_date(entry):
    """Parse entry date from feedparser entry, return ISO string."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        dt = entry.get(field)
        if dt:
            try:
                return datetime(*dt[:6]).isoformat()
            except Exception:
                pass
    return None


def extract_content(entry):
    """Extract best available content/summary from a feedparser entry."""
    content = ""
    summary = ""

    # Prefer full content
    if entry.get("content"):
        content = entry.content[0].get("value", "")
    elif entry.get("summary"):
        content = entry.get("summary", "")

    # Summary (may be same as content)
    summary = entry.get("summary", "")
    if not summary and content:
        # Generate a plain-text snippet from content
        soup = BeautifulSoup(content, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        summary = text[:300] + ("..." if len(text) > 300 else "")

    return summary, content


def extract_attachments(entry, base_url):
    """Extract media attachments (images, audio, video, links) from entry."""
    attachments = []

    # Enclosures
    for enc in entry.get("enclosures", []):
        href = enc.get("href", "")
        if not href:
            continue
        enc_type = enc.get("type", "")
        if enc_type.startswith("image"):
            attachments.append({"type": "image", "url": href, "title": enc.get("title", "")})
        elif enc_type.startswith("audio"):
            attachments.append({"type": "audio", "url": href, "title": enc.get("title", "")})
        elif enc_type.startswith("video"):
            attachments.append({"type": "video", "url": href, "title": enc.get("title", "")})
        else:
            attachments.append({"type": "link", "url": href, "title": enc.get("title", "")})

    # Media content (media: namespace)
    for media in entry.get("media_content", []):
        url = media.get("url", "")
        if url:
            mtype = media.get("type", "")
            atype = "image" if "image" in mtype else "video" if "video" in mtype else "link"
            attachments.append({"type": atype, "url": url, "title": media.get("title", "")})

    # Images in content
    _, content = extract_content(entry)
    if content:
        soup = BeautifulSoup(content, "lxml")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                full_url = urljoin(base_url, src)
                if not any(a["url"] == full_url for a in attachments):
                    attachments.append({"type": "image", "url": full_url, "title": img.get("alt", "")})

    # Links
    for link in entry.get("links", []):
        rel = link.get("rel", "")
        href = link.get("href", "")
        if href and rel not in ("self", "alternate") and not any(a["url"] == href for a in attachments):
            ltype = link.get("type", "")
            if ltype.startswith("image"):
                attachments.append({"type": "image", "url": href, "title": link.get("title", "")})
            elif ltype.startswith("audio"):
                attachments.append({"type": "audio", "url": href, "title": link.get("title", "")})
            elif ltype.startswith("video"):
                attachments.append({"type": "video", "url": href, "title": link.get("title", "")})

    return attachments


def fetch_feed(feed_url, etag=None, last_modified=None):
    """
    Fetch and parse a feed. Returns dict with feed metadata and entries.
    Uses conditional GET with etag/last_modified for bandwidth efficiency.
    """
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    with httpx.Client(follow_redirects=True, timeout=20, headers=headers) as client:
        resp = client.get(feed_url)

        # 304 Not Modified — no new content
        if resp.status_code == 304:
            return {"not_modified": True, "etag": etag, "last_modified": last_modified}

        resp.raise_for_status()

        parsed = feedparser.parse(resp.content)

        if not parsed.feed:
            return {"error": "Could not parse feed"}

        feed_info = {
            "title": parsed.feed.get("title", feed_url),
            "description": parsed.feed.get("subtitle", parsed.feed.get("description", "")),
            "site_url": parsed.feed.get("link", ""),
            "icon_url": extract_feed_icon(parsed.feed, parsed.feed.get("link", "")),
            "etag": resp.headers.get("etag", ""),
            "last_modified": resp.headers.get("last-modified", ""),
            "entries": [],
        }

        for entry in parsed.entries:
            guid = entry.get("id", entry.get("link", entry.get("title", "")))
            if not guid:
                continue

            summary, content = extract_content(entry)
            published = parse_date(entry)
            attachments = extract_attachments(entry, parsed.feed.get("link", ""))

            feed_info["entries"].append({
                "guid": guid,
                "title": entry.get("title", ""),
                "summary": summary,
                "content": content,
                "url": entry.get("link", ""),
                "author": entry.get("author", entry.get("dc_creator", "")),
                "published_at": published,
                "attachments": attachments,
            })

        return feed_info


def extract_feed_icon(feed, site_url):
    """Try to extract a feed/site icon URL."""
    # feedparser may have image
    if feed.get("image"):
        img = feed["image"]
        if isinstance(img, dict):
            return img.get("href", img.get("url", ""))
        return str(img)

    # Try favicon
    if site_url:
        parsed = urlparse(site_url)
        if parsed.netloc:
            return f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=64"

    return ""


def fetch_og_metadata(url, timeout=10):
    """
    Fetch OpenGraph metadata for a URL.
    Returns dict with title, description, image, site_name, url.
    """
    try:
        resp = fetch_url(url, timeout=timeout)
        soup = BeautifulSoup(resp.text, "lxml")

        og = {}
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "")
            name = meta.get("name", "")
            content = meta.get("content", "")
            if not content:
                continue
            if prop.startswith("og:"):
                key = prop[3:]  # strip 'og:' prefix
                og[key] = content
            elif prop.startswith("twitter:"):
                key = prop[8:]  # strip 'twitter:' prefix
                if key not in og:  # don't override OG with Twitter
                    og[key] = content
            elif name == "description" and "description" not in og:
                og["description"] = content
            elif name == "author" and "author" not in og:
                og["author"] = content

        # Fallbacks: use <title> if no og:title
        if "title" not in og:
            title_tag = soup.find("title")
            if title_tag:
                og["title"] = title_tag.get_text(strip=True)

        # Favicon fallback for image
        if "image" not in og:
            icon_link = soup.find("link", attrs={"rel": "icon"}) or \
                        soup.find("link", attrs={"rel": "shortcut icon"}) or \
                        soup.find("link", attrs={"rel": "apple-touch-icon"})
            if icon_link and icon_link.get("href"):
                og["image"] = urljoin(url, icon_link.get("href"))

        og["url"] = url
        return og
    except Exception as e:
        log.warning(f"OG metadata fetch failed for {url}: {e}")
        return {"url": url, "title": url, "error": str(e)}


def _extract_feed_icon_impl(feed, site_url):
    """Try to extract a feed/site icon URL."""
    # feedparser may have image
    if feed.get("image"):
        img = feed["image"]
        if isinstance(img, dict):
            return img.get("href", img.get("url", ""))
        return str(img)

    # Try favicon
    if site_url:
        parsed = urlparse(site_url)
        if parsed.netloc:
            return f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=64"

    return ""


# Alias for backwards compat
extract_feed_icon = _extract_feed_icon_impl

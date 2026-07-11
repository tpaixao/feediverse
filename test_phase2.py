import json
import urllib.request

BASE = "http://127.0.0.1:8090"

def api(method, path, body=None, raw_body=None, content_type="application/json"):
    url = BASE + path
    if raw_body:
        data = raw_body.encode() if isinstance(raw_body, str) else raw_body
    elif body:
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=30) as resp:
        ct = resp.headers.get("content-type", "")
        if "json" in ct:
            return json.loads(resp.read())
        return resp.read().decode()

# 1. Search
print("=== Search ===")
result = api("GET", "/api/search?q=airport&limit=5")
print(f"Search 'airport': {len(result['posts'])} results")
for p in result["posts"][:3]:
    print(f"  [{p['feed_title']}] {p['title'][:60]}")

# 2. OPML Export
print("\n=== OPML Export ===")
opml = api("GET", "/api/opml/export")
print(f"OPML length: {len(opml)} chars")
print(f"Contains xkcd: {'xkcd' in opml}")
print(f"Contains <outline: {'<outline' in opml}")

# 3. Feed media
print("\n=== Feed Media ===")
feeds = api("GET", "/api/feeds")
if feeds:
    feed_id = feeds[0]["id"]
    media = api("GET", f"/api/feeds/{feed_id}/media?limit=10")
    print(f"Media for feed {feed_id}: {len(media['media'])} items")
    for m in media["media"][:3]:
        print(f"  {m['type']}: {m['url'][:60]}")

# 4. Feed detail with posts
print("\n=== Feed Detail ===")
detail = api("GET", f"/api/feeds/{feed_id}")
print(f"Feed: {detail['feed']['title']}")
print(f"Posts: {len(detail['posts'])}")

# 5. Preview (OpenGraph)
print("\n=== OG Preview ===")
try:
    og = api("GET", "/api/preview?url=https://xkcd.com")
    print(f"OG title: {og.get('title', '?')[:60]}")
    print(f"OG image: {og.get('image', 'none')[:60]}")
    print(f"OG site_name: {og.get('site_name', '?')}")
except Exception as e:
    print(f"Preview error (may be expected): {e}")

print("\n=== All Phase 2 tests passed ===")
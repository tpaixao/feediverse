"""Integration test: discover and add a feed, verify timeline."""
import json
import urllib.request

BASE = "http://127.0.0.1:8090"

def api(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

# 1. Discover feeds on a well-known blog
print("=== Testing feed discovery ===")
result = api("GET", "/api/discover?url=https://blog.kagi.com")
print(f"Discovered: {json.dumps(result, indent=2)}")

# 2. Add a feed
print("\n=== Testing add feed ===")
result = api("POST", "/api/feeds", {"url": "https://blog.kagi.com"})
print(f"Add result: {json.dumps(result, indent=2)[:500]}")

# 3. Check timeline
print("\n=== Testing timeline ===")
result = api("GET", "/api/timeline?limit=5")
print(f"Posts: {len(result['posts'])}, Total: {result['total']}")
if result['posts']:
    p = result['posts'][0]
    print(f"First post: {p['title'][:80]}")
    print(f"  From: {p['feed_title']}")
    print(f"  Date: {p['published_at']}")
    print(f"  Attachments: {len(p.get('attachments', []))}")

# 4. Check stats
print("\n=== Testing stats ===")
result = api("GET", "/api/stats")
print(f"Stats: {json.dumps(result)}")

# 5. Check feeds list
print("\n=== Testing feeds list ===")
result = api("GET", "/api/feeds")
print(f"Feeds: {json.dumps(result, indent=2)[:300]}")
import json, urllib.request
BASE = "http://127.0.0.1:8090"

# Test a site with multiple feeds
req = urllib.request.Request(BASE + "/api/discover?url=https://www.theverge.com")
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())
    print(f"The Verge discovery: {len(data['feeds'])} feeds found")
    for f in data["feeds"][:5]:
        print(f"  {f['title']}: {f['url'][:80]}")

# Test a site with no obvious feed
print()
req = urllib.request.Request(BASE + "/api/discover?url=https://example.com")
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read())
    print(f"example.com discovery: {len(data['feeds'])} feeds found")

# Test direct feed URL
print()
req = urllib.request.Request(BASE + "/api/discover?url=https://xkcd.com/rss.xml")
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read())
    print(f"XKCD direct feed: {len(data['feeds'])} feeds found")
    for f in data["feeds"]:
        print(f"  {f['title']}: {f['url'][:80]}")

# Test adding XKCD
print()
req = urllib.request.Request(
    BASE + "/api/feeds", 
    data=json.dumps({"url": "https://xkcd.com/rss.xml"}).encode(),
    method="POST",
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.loads(resp.read())
    print(f"Added XKCD: {data.get('feed', {}).get('title', '?')} - {data.get('posts_added', 0)} posts")

# Final timeline check
print()
req = urllib.request.Request(BASE + "/api/timeline?limit=3")
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
    print(f"Timeline: {data['total']} total posts")
    for p in data["posts"][:3]:
        print(f"  [{p['feed_title']}] {p['title'][:60]}")
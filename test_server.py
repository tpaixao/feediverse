import socket
import json

def port_check(host, port, timeout=3):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False

# Check if port 8090 is listening
if port_check("127.0.0.1", 8090):
    print("Port 8090 is listening - server is up")
else:
    print("Port 8090 is NOT listening")

# Try a basic HTTP request via socket
import urllib.request
try:
    req = urllib.request.Request("http://127.0.0.1:8090/api/stats")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
        print(f"API stats: {json.dumps(data)}")
except Exception as e:
    print(f"API request failed: {e}")

# Try fetching the homepage
try:
    req = urllib.request.Request("http://127.0.0.1:8090/")
    with urllib.request.urlopen(req, timeout=5) as resp:
        html = resp.read().decode()
        print(f"Homepage loaded: {len(html)} bytes, contains 'Feediverse': {'Feediverse' in html}")
except Exception as e:
    print(f"Homepage request failed: {e}")
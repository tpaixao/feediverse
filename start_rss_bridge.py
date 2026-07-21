#!/usr/bin/env python3
"""Start RSS Bridge Docker container with volume at /mnt/ssd1tb/rss-bridge."""
import subprocess
import sys

VOLUME_PATH = "/mnt/ssd1tb/rss-bridge"
PORT = "3002:80"
IMAGE = "rssbridge/rss-bridge:latest"
CONTAINER_NAME = "rss-bridge"

# Create the volume directory
subprocess.run(["mkdir", "-p", VOLUME_PATH], check=True)

# Check if container already exists
result = subprocess.run(
    ["docker", "ps", "-a", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
    capture_output=True, text=True
)
existing = result.stdout.strip()

if existing == CONTAINER_NAME:
    # Check if it's running
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    if result.stdout.strip() == CONTAINER_NAME:
        print(f"Container {CONTAINER_NAME} is already running")
        sys.exit(0)
    else:
        print(f"Starting existing container {CONTAINER_NAME}...")
        subprocess.run(["docker", "start", CONTAINER_NAME], check=True)
        print("Started.")
        sys.exit(0)

# Run new container
print(f"Creating container {CONTAINER_NAME} from {IMAGE}...")
cmd = [
    "docker", "run", "-d",
    "--name", CONTAINER_NAME,
    "--restart", "unless-stopped",
    "-p", PORT,
    "-v", f"{VOLUME_PATH}:/app/data",
    IMAGE
]
print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"ERROR: {result.stderr}", file=sys.stderr)
    sys.exit(1)
print(f"Container created: {result.stdout.strip()}")

# Verify it's running
result = subprocess.run(
    ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}} {{.Status}} {{.Ports}}"],
    capture_output=True, text=True
)
print(f"Status: {result.stdout.strip()}")
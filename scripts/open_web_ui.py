#!/usr/bin/env python3
import json, sys, os, urllib.parse, webbrowser

path = sys.argv[1] if len(sys.argv) > 1 else "ports.json"

with open(path, "r") as f:
    data = json.load(f)

urls = []
for name, url in data.items():
    # only allow spamoor and prometheus
    if name.lower() not in ("grafana"):
        continue

    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        url = "http://" + url  # default if scheme missing
        parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        urls.append(url)

if not urls:
    print("No URLs to open.")
    sys.exit(0)

first = True
for u in urls:
    if first:
        webbrowser.open_new(u)      # new window (or reuse)
        first = False
    else:
        webbrowser.open_new_tab(u)  # new tabs

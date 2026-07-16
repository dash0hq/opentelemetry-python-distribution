"""Sends a few requests to the Flask app to generate trace data."""
import time

import requests

time.sleep(3)
for path in ["/", "/items/1", "/items/2", "/items/42"]:
    response = requests.get(f"http://app:5000{path}")
    print(f"traffic: {path} -> {response.status_code}", flush=True)
print("traffic: done", flush=True)

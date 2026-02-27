import os
import json
import requests

token = os.environ["MRSCRAPER_API_TOKEN"]
scraper_id = "45519a23-9109-4692-a13e-5d9e4695790b"
url = "https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3"

response = requests.post(
    "https://api.app.mrscraper.com/api/v1/scrapers-ai-rerun",
    headers={"x-api-token": token, "Content-Type": "application/json"},
    json={
        "scraperId": scraper_id,
        "url": url,
        "maxRetry": 3,
        "maxPages": 1,
        "timeout": 300,
        "stream": False,
    },
    timeout=360,
)

data = response.json()
print("TOP-LEVEL KEYS:", list(data.keys()))
print()
print("MESSAGE:", data.get("message"))
print()
print("DATA TYPE:", type(data.get("data")))
print()

# Print the full structure, truncated
raw = json.dumps(data, indent=2, default=str)
print(raw[:3000])
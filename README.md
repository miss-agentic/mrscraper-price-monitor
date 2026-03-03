# 🏷️ Enterprise Price Monitor — Built with MrScraper

> Automated price tracking pipeline that monitors products across retailers, detects changes, and sends alerts.

**Use case:** Track the same product across different retailers (eg., Amazon, Best Buy, and Walmart). Detect price drops, increases, and stock changes automatically. Runs on GitHub Actions with zero infrastructure.

---

## How It Works

<img width="963" height="903" alt="image" src="https://github.com/user-attachments/assets/7e194638-f0d2-4197-815b-aaba6f7a659e" />


1. **Scrape** — GitHub Actions triggers the pipeline on a cron schedule (eg., very 6 hours). The pipeline calls MrScraper's Scraper Rerun API to extract pricing data from each retailer.
2. **Store** — Prices are stored in SQLite with full history. Every data point is timestamped.
3. **Detect** — A SQL-based change detection engine compares the latest scrape with previous data, flagging price drops, increases, and stock changes above a configurable threshold.
4. **Alert** — Changes are routed to configured channels: console logs, GitHub Actions summary, Slack/Discord webhooks, or email.

## Quick Start

### Prerequisites

- Python 3.10+
- A [MrScraper account](https://app.mrscraper.com) (free tier available)
- A GitHub account

### 1. Set Up Your MrScraper Scraper

Create a scraper in the MrScraper dashboard:

1. Log in to [MrScraper](https://v3.app.mrscraper.com/auth/login)
2. Click **Scraper** → **New Scraper +**
3. Select **General Agent** (for individual product pages)
4. Enter a retailer URL, e.g.: `https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3`
5. Set scraper type to **Super** for higher accuracy
6. Enter a prompt: *"Extract the product name, current price, original price, currency, availability status, and product URL from this page"*
7. Click **Submit** and verify the results
8. Go to **Settings** → enable **AI Scraper API Access**
9. Copy the **Scraper ID** (UUID) — you'll need this for config.json

Repeat for each retailer you want to track.

### 2. Clone and Install

```bash
git clone https://github.com/miss-agentic/mrscraper-price-monitor.git
cd mrscraper-price-monitor
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — add your MRSCRAPER_API_TOKEN
```

Edit `config.json` — add the scraper IDs you copied from the dashboard:

```json
{
  "retailers": [
    {
      "retailer": "Amazon",
      "url": "https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3",
      "category": "headphones",
      "scraper_id": "your-scraper-uuid-here"
    }
  ]
}
```

Create a separate scraper per retailer for best results.

### 4. Run Locally

```bash
# Full pipeline
python -m src.pipeline

# Dry run (scrape only, don't store)
python -m src.pipeline --dry-run

# Custom alert threshold (percentage)
python -m src.pipeline --threshold 10
```

### 5. Deploy to GitHub Actions

1. Push to GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Add secret: `MRSCRAPER_API_TOKEN` = your token
4. (Optional) Add `ALERT_WEBHOOK_URL` for Slack/Discord alerts
5. The workflow runs automatically every 6 hours, or trigger manually from **Actions** → **Price Monitor** → **Run workflow**

## Project Structure

```
mrscraper-price-monitor/
├── .github/
│   └── workflows/
│       └── price-monitor.yml   # GitHub Actions scheduled pipeline
├── src/
│   ├── __init__.py
│   ├── scraper.py              # MrScraper API integration + response normalization
│   ├── database.py             # Price history storage + change detection
│   ├── alerts.py               # Multi-channel alert routing
│   └── pipeline.py             # Main orchestrator
├── config.json                 # Retailer targets + scraping parameters
├── data/                       # SQLite database (auto-created, gitignored)
├── .env.example                # Environment variable template
├── .gitignore
├── requirements.txt
└── README.md
```

## Configuration

### Retailer Targets (config.json)

```json
{
  "retailers": [
    {
      "retailer": "Amazon",
      "url": "https://www.amazon.com/...",
      "category": "headphones",
      "scraper_id": "uuid-from-mrscraper-dashboard"
    }
  ],
  "scraping": {
    "max_retry": 3,
    "max_pages": 1,
    "timeout": 300,
    "stream": false
  },
  "alerts": {
    "threshold_pct": 5.0
  }
}
```

### Scraper ID Resolution

The code resolves scraper IDs in this order:

1. **Per-retailer `scraper_id`** in config.json (recommended)
2. **Global `MRSCRAPER_SCRAPER_ID`** environment variable (fallback)
3. **Direct AI API** if no scraper ID is found (with a warning — less control over extraction)

### Notification Channels

| Channel | Configuration | Notes |
|---------|--------------|-------|
| Console | Always on | Visible in CI/CD logs |
| GitHub Summary | Automatic in Actions | Renders as Markdown table in the run UI |
| Slack | `ALERT_WEBHOOK_URL` | Incoming webhook URL |
| Discord | `ALERT_WEBHOOK_URL` + `ALERT_WEBHOOK_FORMAT=discord` | Webhook URL |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` | Any SMTP provider |

## API Integration

### Scraper Rerun API (Primary)

```bash
POST https://api.app.mrscraper.com/api/v1/scrapers-ai-rerun
x-api-token: YOUR_TOKEN
Content-Type: application/json

{
  "scraperId": "your-general-agent-scraper-uuid",
  "url": "https://www.amazon.com/...",
  "maxRetry": 3,
  "maxPages": 1,
  "timeout": 300,
  "stream": false
}
```

The Rerun API triggers a pre-configured scraper from the dashboard against any URL. The scraper's agent type, prompt, and settings are reused — your code just sends the target URL.

### Direct AI API (Fallback)

```bash
POST https://app.mrscraper.com/api/ai
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "urls": ["https://retailer.com/products"],
  "schema": { ... },
  "min": 5,
  "max": 50,
  "timeout": 180
}
```

Used automatically when no scraper ID is configured. Sends a JSON schema directly to MrScraper's AI endpoint. Less control over extraction compared to a pre-configured scraper.

## Extending This Project

This is a reference architecture. Common extensions:

- **Dashboard** — Grafana for visual price trend analysis
- **Dynamic Pricing** — Feed alerts into a pricing engine for automated adjustments
- **MAP Monitoring** — Track Minimum Advertised Price violations across resellers
- **Multi-Region** — Monitor prices across country-specific storefronts using MrScraper's proxy settings
- **Production Database** — Swap SQLite for PostgreSQL or TimescaleDB at scale
- **MrScraper Integrations** — Use built-in Webhook, Database, or Zapier integrations for additional routing

## License

MIT

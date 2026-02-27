# 🏷️ Enterprise Price Monitor — Built with MrScraper

> Automated competitive price intelligence pipeline that tracks product prices across retailers, detects changes, and sends real-time alerts.

**Use case:** Enterprise pricing teams need to monitor thousands of SKUs across dozens of competitors. This reference architecture shows how to build a production-grade price monitoring system using [MrScraper's Scraper API](https://docs.mrscraper.com/docs/features/activating-api) and GitHub Actions — no infrastructure to manage.

---

## How It Works

```
┌─────────────────┐    ┌───────────────────────┐    ┌─────────────────┐
│  GitHub Actions  │───▶│  MrScraper Scraper API │───▶│  Price History   │
│  (Scheduled)     │    │  (Rerun pre-configured │    │  (SQLite DB)     │
│                  │    │   General Agent)       │    │                  │
└─────────────────┘    └───────────────────────┘    └────────┬────────┘
                                                              │
                                                              ▼
                                                     ┌─────────────────┐
                                                     │  Change Detection │
                                                     │  Engine           │
                                                     └────────┬────────┘
                                                              │
                                                   ┌──────────┼──────────┐
                                                   ▼          ▼          ▼
                                               ┌───────┐ ┌────────┐ ┌───────┐
                                               │ Slack  │ │ Email  │ │GitHub │
                                               │Webhook │ │ Alert  │ │Summary│
                                               └───────┘ └────────┘ └───────┘
```

1. **Scrape** — GitHub Actions triggers the pipeline on a cron schedule (every 6 hours). The pipeline calls MrScraper's **Scraper Rerun API** to trigger pre-configured General Agent scrapers against each retailer URL.
2. **Store** — Scraped prices are stored in SQLite with full history. Every price point is timestamped for trend analysis.
3. **Detect** — A SQL-based change detection engine compares the latest scrape with previous data, flagging price drops, increases, and stock changes above a configurable threshold.
4. **Alert** — Changes are routed to Slack, Discord, email, or the GitHub Actions summary UI.

## Why the Scraper API (Not Manual Scraper)?

MrScraper offers two approaches. We use the **Scraper API** because it is built for automation:

| | Scraper API (our approach) | Manual Scraper |
|---|---|---|
| **How it works** | Create and tune a scraper once in the dashboard, then trigger it programmatically via API | Build step-by-step scraping workflows with explicit selectors and actions |
| **CI/CD friendly** | Yes — one API call triggers a full scrape | No — designed for interactive, hands-on use |
| **Maintenance** | AI-powered extraction adapts to layout changes | CSS selectors break when sites update |
| **Best for** | Automated pipelines, scheduled monitoring, programmatic integration | Complex sites needing precise control over navigation |

Within the Scraper API, we use the **General Agent** because we are scraping individual product detail pages (one specific SKU per URL). The Listing Agent would be the choice if we were scraping search/catalog pages with many products.

## Quick Start

### Prerequisites

- Python 3.10+
- A [MrScraper account](https://app.mrscraper.com) (free tier available)
- A GitHub account

### 1. Set Up Your MrScraper Scraper

Before running the code, create a scraper in the MrScraper dashboard:

1. Log in to [MrScraper](https://v3.app.mrscraper.com/auth/login)
2. Click **Scraper** in the left sidebar, then **New Scraper +**
3. Select **General Agent** (for individual product detail pages (one product per URL))
4. Enter a retailer URL, e.g.: `https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3`
5. Set scraper type to **Super** for higher accuracy
6. Enter a prompt like: *"Extract the product name, current price, original price, currency, availability, and product URL from this page"*
7. Click **Submit** and verify the results look correct
8. Go to **Settings** and enable **AI Scraper API Access**
9. Copy the **Scraper ID** (UUID) — you will need this next

### 2. Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/mrscraper-price-monitor.git
cd mrscraper-price-monitor
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — add your MRSCRAPER_API_TOKEN
```

Then edit `config.json` — add the scraper ID(s) you copied from the dashboard:

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

You can use one scraper for all retailers (if the prompt is generic enough) or create a separate scraper per retailer for best results.

### 4. Run Locally

```bash
# Full pipeline
python -m src.pipeline

# Dry run (scrape only, don't store)
python -m src.pipeline --dry-run

# Custom alert threshold
python -m src.pipeline --threshold 10
```

### 5. Deploy to GitHub Actions

1. Push to GitHub
2. Go to **Settings** then **Secrets and variables** then **Actions**
3. Add secret: `MRSCRAPER_API_TOKEN` = your token
4. Add secret: `MRSCRAPER_SCRAPER_ID` = your scraper UUID (or set per-retailer in config.json)
5. (Optional) Add `ALERT_WEBHOOK_URL` for Slack/Discord alerts
6. The workflow runs automatically every 6 hours, or trigger manually from **Actions** then **Price Monitor** then **Run workflow**

## Project Structure

```
mrscraper-price-monitor/
├── .github/
│   └── workflows/
│       └── price-monitor.yml   # GitHub Actions scheduled pipeline
├── src/
│   ├── __init__.py
│   ├── scraper.py              # MrScraper API integration (Rerun API primary)
│   ├── database.py             # Price history storage & change detection
│   ├── alerts.py               # Multi-channel alert notifications
│   └── pipeline.py             # Main orchestrator (entry point)
├── config.json                 # Retailer targets & scraping parameters
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
      "url": "https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3",
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

**Tip:** For multi-page listings, set `max_pages` > 1 and `stream: true` to prevent data loss if the connection is interrupted.

### Scraper ID Resolution

The code resolves scraper IDs in this priority order:

1. **Per-retailer `scraper_id`** in `config.json` (highest priority)
2. **Global `MRSCRAPER_SCRAPER_ID`** environment variable
3. **Fallback to Direct AI API** if no scraper ID is found (with a warning)

### Notification Channels

| Channel | Required Secrets | Notes |
|---------|-----------------|-------|
| Console | (none) | Always on, visible in CI logs |
| GitHub Summary | (none) | Auto-renders in Actions UI |
| Slack | `ALERT_WEBHOOK_URL` | Use incoming webhook URL |
| Discord | `ALERT_WEBHOOK_URL` + `ALERT_WEBHOOK_FORMAT=discord` | Use webhook URL |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `ALERT_EMAIL_TO` | Any SMTP provider |

## API Integration

### Primary: Scraper Rerun API

```bash
POST https://api.app.mrscraper.com/api/v1/scrapers-ai-rerun
x-api-token: YOUR_TOKEN
Content-Type: application/json

{
  "scraperId": "your-general-agent-scraper-uuid",
  "url": "https://www.amazon.com/Beats-Powerbeats-Wireless-Bluetooth-Earbuds/dp/B0DT2344N3",
  "maxRetry": 3,
  "maxPages": 1,
  "timeout": 300,
  "stream": false
}
```

### Fallback: Direct AI API

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

## Extending This Project

This is a reference architecture. Here is how enterprises typically extend it:

- **Dashboard**: Add Streamlit or Grafana for visual price trend analysis
- **Dynamic Pricing**: Feed alerts into your pricing engine for automated adjustments
- **MAP Monitoring**: Track Minimum Advertised Price violations across resellers
- **Multi-Region**: Monitor prices across country-specific storefronts
- **Production Database**: Swap SQLite for PostgreSQL/TimescaleDB for higher volume
- **Data Warehouse**: Export to Snowflake, BigQuery, or Redshift for cross-team analytics
- **MrScraper Integrations**: Use built-in Webhook, SQL/Database, or Zapier integrations for additional data routing

## License

MIT

---

Built with [MrScraper](https://mrscraper.com) — AI-powered web scraping that just works.

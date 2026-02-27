"""
MrScraper Price Extraction Module

Extracts structured price data from e-commerce retailer pages using
MrScraper's Scraper API.

PRIMARY METHOD — Scraper Rerun API:
    You create and tune a scraper once in the MrScraper dashboard
    (using the General Agent for individual product pages), enable
    "AI Scraper API Access" in its Settings, then trigger it
    programmatically here with any target URL. This is the
    recommended approach for automation and CI/CD pipelines
    because the scraper's prompt, agent type, and output format
    are pre-configured in the dashboard — your code just triggers it.

    Agent selection guide:
      - General Agent: Individual product pages (our use case —
        tracking the same SKU across retailers like Amazon, Best Buy,
        Walmart). Each URL is a single product detail page.
      - Listing Agent: Search/catalog pages with multiple products.
      - Map Agent: Crawling a site to discover URLs.

FALLBACK METHOD — Direct AI API:
    Sends a URL + JSON schema directly to MrScraper's AI endpoint.
    No dashboard setup required. Useful for quick prototyping or
    when you cannot create scrapers in the dashboard ahead of time.
    Less control over agent selection and prompt tuning.

Enterprise Use Case: Automated competitive price monitoring — tracking
the exact same product (e.g., Beats Powerbeats Pro 2) across Amazon,
Best Buy, and Walmart to detect price drops, increases, and stock changes.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MRSCRAPER_API_TOKEN = os.environ.get("MRSCRAPER_API_TOKEN", "")

# A single shared scraper ID can be set via env var as a convenience.
# Per-retailer scraper IDs in config.json take precedence over this.
MRSCRAPER_SCRAPER_ID = os.environ.get("MRSCRAPER_SCRAPER_ID", "")

# API endpoints
RERUN_API_URL = "https://api.app.mrscraper.com/api/v1/scrapers-ai-rerun"
AI_API_URL = "https://app.mrscraper.com/api/ai"

# Config file path
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "config.json"))

# ---------------------------------------------------------------------------
# Fallback: JSON schema for the direct AI API
# ---------------------------------------------------------------------------
# Only used when falling back to the direct AI API (no scraper_id).
# When using the Rerun API, the scraper's own prompt defines the output.
PRICE_SCHEMA = {
    "type": "array",
    "description": "List of products with pricing information",
    "items": {
        "type": "object",
        "description": "Individual product pricing data",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "Full product name/title",
            },
            "current_price": {
                "type": "number",
                "description": "Current selling price (after discounts)",
            },
            "original_price": {
                "type": "number",
                "description": "Original/list price before discounts (if available)",
            },
            "currency": {
                "type": "string",
                "description": "Price currency code (e.g. USD, EUR)",
            },
            "in_stock": {
                "type": "boolean",
                "description": "Whether the product is currently in stock",
            },
            "product_url": {
                "type": "string",
                "description": "Direct URL to the product page",
            },
            "seller": {
                "type": "string",
                "description": "Seller or retailer name if shown on the page",
            },
        },
        "required": ["product_name", "current_price", "currency"],
    },
}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_config(config_path: Optional[Path] = None) -> dict:
    """
    Load retailer targets and scraping parameters from config.json.

    Separating configuration from code is a best practice:
      - Users add/remove retailers by editing JSON, not Python.
      - CI/CD can inject different configs per environment.
      - The config file is human-readable and version-controlled.

    Args:
        config_path: Path to the JSON config file.

    Returns:
        Parsed config dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        json.JSONDecodeError: If the config file is invalid JSON.
    """
    path = config_path or CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path}. "
            f"Copy config.json to your project root and fill in your scraper IDs."
        )

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Validate required structure
    if "retailers" not in config or not isinstance(config["retailers"], list):
        raise ValueError("config.json must contain a 'retailers' array.")

    if not config["retailers"]:
        raise ValueError("config.json 'retailers' array is empty. Add at least one target.")

    logger.info("Loaded config: %d retailer target(s) from %s", len(config["retailers"]), path)
    return config


def _validate_token() -> None:
    """Validate that the API token is set."""
    if not MRSCRAPER_API_TOKEN:
        raise ValueError(
            "MRSCRAPER_API_TOKEN environment variable is required.\n"
            "Get your token at: https://app.mrscraper.com → Profile → API Tokens\n"
            "Then set it:  export MRSCRAPER_API_TOKEN='your_token_here'\n"
            "Or in GitHub Actions:  Settings → Secrets → MRSCRAPER_API_TOKEN"
        )


# ---------------------------------------------------------------------------
# Primary: Scraper Rerun API
# ---------------------------------------------------------------------------
def scrape_with_rerun_api(
    scraper_id: str,
    url: str,
    max_pages: int = 1,
    max_retry: int = 3,
    timeout: int = 300,
    stream: bool = False,
) -> list[dict]:
    """
    Rerun a pre-configured MrScraper scraper against a target URL.

    This is the PRIMARY and RECOMMENDED method for automated pipelines.

    Prerequisites:
      1. Create a scraper in the MrScraper dashboard using the General Agent
         (ideal for individual product detail pages — one product per URL).
      2. Tune the prompt, e.g.: "Extract the product name, current price,
         original price, currency, availability, and product URL."
      3. Go to Settings → Enable "AI Scraper API Access".
      4. Copy the scraper ID (UUID) into config.json.

    Agent selection:
      - General Agent: For individual product pages (our use case). Each
        URL is a specific product like amazon.com/dp/B0DT2344N3.
      - Listing Agent: For search/catalog pages with many products.
      - Map Agent: For crawling a site to discover product URLs.

    Args:
        scraper_id: UUID of the scraper from the MrScraper dashboard.
        url: The retailer page URL to scrape.
        max_pages: Maximum pages to scrape for paginated listings.
        max_retry: Number of retry attempts on failure.
        timeout: Timeout in seconds. Increase for multi-page scrapes
                 (MrScraper docs recommend proportional to max_pages).
        stream: Enable streaming for long-running multi-page scrapes.
                Recommended when max_pages > 1 to prevent data loss
                if the connection is interrupted mid-process.

    Returns:
        List of product dictionaries extracted by the scraper.

    Raises:
        ValueError: If API token is missing.
        requests.HTTPError: If the API returns a non-2xx status.
    """
    _validate_token()

    payload = {
        "scraperId": scraper_id,
        "url": url,
        "maxRetry": max_retry,
        "maxPages": max_pages,
        "timeout": timeout,
        "stream": stream,
    }

    logger.info(
        "Rerun API → scraper=%s url=%s (maxPages=%d, timeout=%ds)",
        scraper_id[:8] + "...",
        url[:80],
        max_pages,
        timeout,
    )

    response = requests.post(
        RERUN_API_URL,
        headers={
            "x-api-token": MRSCRAPER_API_TOKEN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=timeout + 60,  # HTTP client timeout above MrScraper's internal timeout
    )
    response.raise_for_status()

    data = response.json()
    products = _normalize_rerun_response(data)

    logger.info("Rerun API → extracted %d products", len(products))
    return products


def _normalize_rerun_response(data: dict) -> list[dict]:
    """
    Normalize the Rerun API response into a flat list of product dicts.

    The actual Rerun API response structure (confirmed via live testing):

    {
      "message": "Successful operation!",
      "data": {
        "id": "run-uuid",
        "scraperId": "scraper-uuid",
        "status": "Finished",
        "data": {                          ← product data lives HERE
          "product_name": "...",
          "current_price": 249,
          ...
        }
      }
    }

    The inner "data" field can be:
      - A dict: single product (Amazon, Best Buy product pages)
      - A list: multiple products
      - A dict with a nested array: {"products": [...]} (Walmart)
      - A JSON string that needs parsing

    This function handles all cases and returns a consistent list of dicts.
    """
    # ---------------------------------------------------------------
    # Primary path: Rerun API response → data.data
    # ---------------------------------------------------------------
    outer_data = data.get("data")

    if isinstance(outer_data, dict):
        # The actual product data is nested under data.data
        inner_data = outer_data.get("data")

        if inner_data is not None:
            return _unwrap_product_data(inner_data)

        # Fallback: maybe data.results[] structure (older API version?)
        results = outer_data.get("results", [])
        if results:
            return _extract_products_from_results(results)

    # ---------------------------------------------------------------
    # Fallback paths for other response structures
    # ---------------------------------------------------------------

    # Direct "result" key (AI API format)
    if "result" in data and isinstance(data["result"], list):
        return data["result"]

    # Top-level list
    if isinstance(data, list):
        return data

    logger.warning(
        "Unexpected API response structure. Keys: %s. Returning empty list.",
        list(data.keys()) if isinstance(data, dict) else type(data).__name__,
    )
    return []


def _unwrap_product_data(inner_data) -> list[dict]:
    """
    Unwrap the inner 'data' field from the Rerun API response into a list.

    Handles:
      - dict with product fields: {"product_name": "...", "current_price": 249}
        → returns [dict]
      - dict with nested array: {"products": [...]} or {"items": [...]}
        → returns the array
      - list of product dicts: [{...}, {...}]
        → returns as-is
      - JSON string: '[{"product_name": "..."}]'
        → parses and returns
    """
    # JSON string → parse first
    if isinstance(inner_data, str):
        try:
            inner_data = json.loads(inner_data)
        except json.JSONDecodeError:
            logger.warning("Could not parse inner data as JSON: %s...", inner_data[:100])
            return []

    # List of products → return directly
    if isinstance(inner_data, list):
        return inner_data

    # Dict → could be a single product or a wrapper with a nested array
    if isinstance(inner_data, dict):
        # Check for wrapper keys like {"products": [...]}
        for key in ("products", "items", "data", "listings", "results"):
            if key in inner_data and isinstance(inner_data[key], list):
                return inner_data[key]

        # It's a single product dict — wrap in a list
        # (Verify it looks like product data, not metadata)
        product_indicators = ("product_name", "name", "title", "current_price", "price")
        if any(k in inner_data for k in product_indicators):
            return [inner_data]

    logger.warning("Could not extract products from inner data of type %s", type(inner_data).__name__)
    return []


def _extract_products_from_results(results: list[dict]) -> list[dict]:
    """
    Extract product data from the results array.

    Each result entry may have a "content" field that is either:
      - A dict (single product or structured data)
      - A list of dicts (multiple products)
      - A JSON string that needs parsing
    """
    all_products = []

    for result in results:
        status = result.get("status", "unknown")
        if status not in ("succeeded", "success", "unknown"):
            logger.warning("Skipping result with status '%s'", status)
            continue

        content = result.get("content", result)

        # If content is a JSON string, parse it
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                logger.warning("Could not parse content as JSON: %s...", content[:100])
                continue

        # If content is a list, extend our products
        if isinstance(content, list):
            all_products.extend(content)
        # If content is a dict, it might be a single product or a wrapper
        elif isinstance(content, dict):
            # Check for nested product arrays (e.g. {"products": [...]})
            for key in ("products", "items", "data", "listings"):
                if key in content and isinstance(content[key], list):
                    all_products.extend(content[key])
                    break
            else:
                # Treat the dict itself as a single product if it looks like one
                if "product_name" in content or "name" in content or "title" in content:
                    all_products.append(content)

    return all_products


# ---------------------------------------------------------------------------
# Fallback: Direct AI API
# ---------------------------------------------------------------------------
def scrape_with_ai_api(
    url: str,
    schema: Optional[dict] = None,
    min_results: int = 5,
    max_results: int = 50,
    timeout: int = 180,
) -> list[dict]:
    """
    FALLBACK: Scrape a URL using MrScraper's direct AI API with a JSON schema.

    Use this when:
      - You don't have a scraper_id configured for a retailer.
      - You're prototyping and haven't set up scrapers in the dashboard yet.
      - You need a quick one-off scrape without dashboard configuration.

    For production automated pipelines, prefer scrape_with_rerun_api()
    because it gives you control over agent type, prompt tuning, and
    output format through the dashboard.

    Args:
        url: The retailer page URL to scrape.
        schema: JSON schema defining expected output structure.
                Defaults to PRICE_SCHEMA.
        min_results: Minimum number of results expected.
        max_results: Maximum number of results to return.
        timeout: Request timeout in seconds.

    Returns:
        List of product dictionaries matching the schema.

    Raises:
        requests.HTTPError: If the API returns a non-2xx status.
        ValueError: If the API token is not configured.
    """
    _validate_token()

    if schema is None:
        schema = PRICE_SCHEMA

    payload = {
        "urls": [url],
        "min": min_results,
        "max": max_results,
        "timeout": timeout,
        "schema": schema,
    }

    logger.info("AI API (fallback) → url=%s (timeout=%ds)", url[:80], timeout)

    response = requests.post(
        AI_API_URL,
        headers={
            "Authorization": f"Bearer {MRSCRAPER_API_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=timeout + 30,
    )
    response.raise_for_status()

    data = response.json()
    results = data.get("result", [])

    logger.info("AI API (fallback) → extracted %d products", len(results))
    return results


# ---------------------------------------------------------------------------
# Product normalizer
# ---------------------------------------------------------------------------
def _normalize_product(raw: dict, source_url: str = "") -> dict:
    """
    Normalize a raw product dict into a consistent schema.

    Different scrapers may return different field names AND different
    value formats depending on the retailer's page structure.
    This maps all known variations into our canonical format.

    Known variations discovered during testing:

      Field names:
        - Name:  "product_name", "name", "title"
        - Price: "current_price", "price", "product_price"
          Values may be: 249, 249.99, "$249.00", "249.00"
        - Currency: "USD", "$", "EUR", "€"
        - Stock: true/false, "In Stock", "Unavailable",
                 {"pickup": "Unavailable", "shipping": "Available"},
                 "In 50+ people's carts", "1000+ bought since yesterday"

      URL formats:
        - Absolute: "https://www.amazon.com/dp/B0DT2344N3"
        - Relative: "/dp/B0DT2344N3?ref=..."

    Args:
        raw: Raw product dict from the scraper API.
        source_url: The original URL scraped (used to resolve relative URLs).
    """
    return {
        "product_name": (
            raw.get("product_name")
            or raw.get("name")
            or raw.get("title")
            or "Unknown"
        ),
        "current_price": _parse_price(
            raw.get("current_price")
            or raw.get("price")
            or raw.get("product_price")
            or 0
        ),
        "original_price": _parse_price(
            raw.get("original_price")
            or raw.get("list_price")
            or raw.get("was_price")
        ),
        "currency": _normalize_currency(
            raw.get("currency")
            or raw.get("product_currency")
            or "USD"
        ),
        "in_stock": _parse_availability(raw),
        "product_url": _resolve_url(
            raw.get("product_url")
            or raw.get("url")
            or raw.get("link"),
            source_url,
        ),
        "seller": raw.get("seller"),
    }


def _parse_price(value) -> float:
    """
    Parse price from various formats into a float.

    Handles:
      - int/float: 249, 233.99
      - str: "$249.00", "249.00", "$13.30", "US$249.00"
      - None: returns 0
    """
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Strip currency symbols, commas, whitespace
        cleaned = value.strip()
        for char in ("$", "€", "£", "¥", "US", "USD", "EUR", "GBP", ","):
            cleaned = cleaned.replace(char, "")
        cleaned = cleaned.strip()

        try:
            return float(cleaned)
        except ValueError:
            logger.warning("Could not parse price from string: '%s'", value)
            return 0.0

    return 0.0


def _normalize_currency(value: str) -> str:
    """
    Normalize currency symbols/codes to ISO 4217 codes.

    Handles: "$" → "USD", "€" → "EUR", "£" → "GBP", etc.
    """
    symbol_map = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "us$": "USD",
    }
    lowered = value.strip().lower()
    return symbol_map.get(lowered, value.upper().strip())


def _resolve_url(url: str | None, source_url: str = "") -> str | None:
    """
    Resolve relative URLs to absolute using the source page URL.

    Amazon returns:  "/dp/B0DT2344N3?ref=..."
    We need:         "https://www.amazon.com/dp/B0DT2344N3?ref=..."
    """
    if url is None:
        return None

    # Already absolute
    if url.startswith("http://") or url.startswith("https://"):
        return url

    # Relative — extract base from source_url
    if source_url and url.startswith("/"):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(source_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            return base + url
        except Exception:
            pass

    return url  # Return as-is if we can't resolve


def _parse_availability(raw: dict) -> bool:
    """
    Parse availability/stock status from various formats into a boolean.

    Handles:
      - bool: True/False
      - str: "In Stock", "Available", "Out of Stock", "Unavailable", etc.
      - dict: {"pickup": "Unavailable", "shipping": "Available"} — returns
              True if ANY fulfillment method is available.
      - None/missing: defaults to True (assume in stock if not stated)
    """
    # Check all possible field names in priority order
    value = None
    for field in ("in_stock", "availability_status", "availability"):
        if field in raw:
            value = raw[field]
            break

    if value is None:
        return True  # Default: assume in stock if not reported

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.lower().strip()
        # IMPORTANT: Check negative indicators FIRST because "unavailable"
        # contains the substring "available" and would false-positive.
        if any(keyword in lowered for keyword in ("out of stock", "unavailable", "sold out", "not available")):
            return False
        if any(keyword in lowered for keyword in ("in stock", "available", "add to cart", "buy now")):
            return True
        # Walmart social proof strings imply the product is available:
        #   "In 50+ people's carts", "1000+ bought since yesterday"
        if any(keyword in lowered for keyword in ("people's carts", "bought since", "bought in")):
            return True
        return True  # Unknown string — assume available

    if isinstance(value, dict):
        # Best Buy pattern: {"pickup": "Unavailable", "shipping": "Available"}
        # Product is "in stock" if ANY fulfillment channel is available
        for channel, status in value.items():
            if isinstance(status, str):
                lowered = status.lower().strip()
                # Check negative first (same reason as above)
                if any(kw in lowered for kw in ("unavailable", "out of stock", "sold out", "not available")):
                    continue  # This channel is unavailable, check next
                if any(kw in lowered for kw in ("available", "in stock", "ready")):
                    return True
            elif isinstance(status, bool) and status:
                return True
        return False  # All channels unavailable

    return True  # Fallback for unexpected types


# ---------------------------------------------------------------------------
# Orchestrator: scrape all retailers
# ---------------------------------------------------------------------------
def scrape_all_retailers(config: Optional[dict] = None) -> list[dict]:
    """
    Scrape prices from all configured retailer targets.

    For each retailer:
      1. If a scraper_id is configured (per-retailer or global env var),
         use the Rerun API (primary method).
      2. Otherwise, fall back to the direct AI API with the JSON schema.

    Each product record is enriched with retailer metadata and a
    timestamp before being returned.

    Args:
        config: Parsed config dict. If None, loads from CONFIG_PATH.

    Returns:
        List of enriched, normalized product dictionaries ready for storage.
    """
    if config is None:
        config = load_config()

    retailers = config["retailers"]
    scraping_cfg = config.get("scraping", {})
    scrape_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    all_products: list[dict] = []

    for target in retailers:
        retailer = target["retailer"]
        url = target["url"]
        category = target.get("category", "general")

        # Determine scraper ID: per-retailer config takes priority,
        # then fall back to the global env var.
        scraper_id = target.get("scraper_id", "").strip() or MRSCRAPER_SCRAPER_ID

        try:
            # ----------------------------------------------------------
            # Choose API method based on whether scraper_id is available
            # ----------------------------------------------------------
            if scraper_id:
                raw_products = scrape_with_rerun_api(
                    scraper_id=scraper_id,
                    url=url,
                    max_pages=scraping_cfg.get("max_pages", 1),
                    max_retry=scraping_cfg.get("max_retry", 3),
                    timeout=scraping_cfg.get("timeout", 300),
                    stream=scraping_cfg.get("stream", False),
                )
            else:
                logger.warning(
                    "%s: No scraper_id configured. Using AI API fallback. "
                    "For production, create a General Agent scraper in the "
                    "MrScraper dashboard, enable API Access, and add its ID "
                    "to config.json.",
                    retailer,
                )
                raw_products = scrape_with_ai_api(url)

            # ----------------------------------------------------------
            # Normalize and enrich each product
            # ----------------------------------------------------------
            for raw in raw_products:
                product = _normalize_product(raw, source_url=url)
                product["retailer"] = retailer
                product["category"] = category
                product["scraped_at"] = scrape_time
                product["source_url"] = url
                all_products.append(product)

            logger.info("✓ %s: %d products scraped", retailer, len(raw_products))

        except requests.HTTPError as e:
            logger.error(
                "✗ %s: HTTP %s — %s",
                retailer,
                e.response.status_code if e.response is not None else "?",
                e,
            )
        except requests.ConnectionError:
            logger.error("✗ %s: Connection failed. Check network and API URL.", retailer)
        except requests.Timeout:
            logger.error("✗ %s: Request timed out. Consider increasing timeout in config.", retailer)
        except Exception as e:
            logger.error("✗ %s: Unexpected error: %s", retailer, e, exc_info=True)

    logger.info(
        "Scraping complete: %d total products from %d retailers",
        len(all_products),
        len(retailers),
    )
    return all_products


if __name__ == "__main__":
    # Quick local test: scrape all retailers and print results
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    results = scrape_all_retailers()
    print(json.dumps(results, indent=2, default=str))

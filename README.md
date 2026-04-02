# Webscraper & Product Tracker

A FastAPI service for web content extraction and persistent LEGO set price tracking. Used by the `agent-orchestrator` as a tool backend and by the Discord bot for the LEGO tracking UI.

## Endpoints

### Web Content

`GET /read?url=<url>`

Fetches a URL and converts the page content to clean markdown-style plain text (up to 6000 characters). Used by the agent's `read_url` tool to let the LLM reason about web page content.

### Product Scraping

`GET /scrape?url=<url>`

Extracts the product name, LEGO set number, and current price from a product URL.

Scraping strategy (in order):
1. `requests` + BeautifulSoup — looks for `schema.org` structured data and meta price tags
2. Selenium headless Chromium — fallback for JavaScript-rendered pages, waits up to 15 seconds for dynamic content

```json
{
  "name": "Eiffel Tower",
  "product_number": "10307",
  "price": "629.99"
}
```

### Price Tracking

| Endpoint | Description |
|---|---|
| `POST /track?url=<url>&user_id=<id>` | Start tracking a LEGO set. Scrapes the current price immediately and saves to the database. Deduplicates by product number. |
| `GET /tracked?user_id=<id>` | List tracked sets for a specific user with their latest price and last updated time. Omit `user_id` to return all tracked sets. |
| `DELETE /track/<product_number>` | Stop tracking a set and delete its price history. |

### Health

`GET /health` — database connectivity check, returns `{"status": "healthy", "database": "up"}`

## Background Price Updates

A background task runs every 24 hours and updates the price for every tracked set. Updates are executed in parallel to keep runtime short regardless of how many sets are tracked.

## Database Schema

**`tracked_sets`**
- `product_number` — unique LEGO set identifier (e.g. `10307`)
- `name` — product name
- `url` — source URL
- `user_id` — Discord user ID who added the set
- `created_at` — when tracking started

**`price_history`**
- `set_id` → FK to `tracked_sets`
- `price` — recorded price
- `timestamp` — when the price was captured

## Tech Stack

- **Python 3.12+**
- **FastAPI** + **uvicorn**
- **BeautifulSoup4** — static HTML parsing
- **Selenium** + **Chromium** — headless browser for dynamic pages
- **webdriver-manager** — auto-resolves ChromeDriver for local development; uses system-installed `/usr/bin/chromedriver` in the container
- **html2text** — HTML to plain text conversion
- **SQLAlchemy** — ORM for PostgreSQL (or SQLite in dev)
- **Alembic** — database migrations

## Setup

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./scraper.db` | Database connection string |

For production use PostgreSQL:
```
DATABASE_URL=postgresql://user:password@host:5432/scraper_db
```

### System Requirements

The container image installs `chromium` and `chromium-driver` via apt. For local development outside the container, `webdriver-manager` will automatically download a compatible ChromeDriver.

### Running Locally

```bash
pip install -r requirements.txt
python scraper.py serve
```

### Kubernetes

Deployed to the `webscraper-dev` namespace via ArgoCD. Includes a PostgreSQL StatefulSet.

```bash
kubectl apply -k gitops/webscraper/overlays/dev
```

## Deployment Notes

- Container image built for `linux/arm64` (M1 Mac Mini cluster)
- Pushed to `ghcr.io/wmickeyd/webscraper` on every push to `main`
- ArgoCD detects the manifest update and redeploys automatically
- Database credentials are managed via Kubernetes Sealed Secrets

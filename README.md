# Webscraper & Product Tracker

A FastAPI-based service designed for extracting web content and tracking product prices (specialized for LEGO sets).

## Features

- **`/read`**: Convert any URL's content to readable Markdown-style text for further analysis.
- **`/scrape`**: Extract product name, set number, and current price from a URL. Uses a combination of BeautifulSoup and Selenium (headless) for dynamic pages.
- **`/track`**: Add a URL to a persistent database to track price changes over time.
- **`/tracked`**: List all currently tracked sets with their latest price and historical data.
- **Background Updates**: A daily background task automatically updates the price for all tracked sets.

## Tech Stack

- **Framework**: FastAPI
- **Database**: PostgreSQL (via SQLAlchemy)
- **Scraping**: `BeautifulSoup`, `Selenium` (Chrome/Chromium)
- **Content Conversion**: `html2text`
- **Automation**: `asyncio` for background processing

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **System Requirements**:
   - Google Chrome or Chromium installed.
   - `chromedriver` available in your system PATH or at `/usr/bin/chromedriver`.

3. **Database Configuration**:
   Ensure you have a PostgreSQL instance running or update `database.py` with your connection string.

4. **Run the API**:
   ```bash
   python scraper.py serve
   ```

## Usage

Use the `/track` endpoint to add products by URL. The service will extract information and begin daily price monitoring. Historical data can be accessed via the database or through the `/tracked` endpoint.

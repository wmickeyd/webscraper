from bs4 import BeautifulSoup
import requests
import sys
import json
import re
from urllib.parse import urlparse, unquote

# FastAPI imports
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
    )
}


def _find_price_in_json(obj):
    if isinstance(obj, dict):
        if "offers" in obj:
            offers = obj["offers"]
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = offers.get("price") or (offers.get("priceSpecification") or {}).get("price")
                if price:
                    return str(price)
        for v in obj.values():
            p = _find_price_in_json(v)
            if p:
                return p
    elif isinstance(obj, list):
        for item in obj:
            p = _find_price_in_json(item)
            if p:
                return p
    return None


def get_price(url, timeout=10):
    # 1) Try simple HTTP fetch + JSON-LD/meta parsing
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # JSON-LD
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
            except Exception:
                continue
            price = _find_price_in_json(data)
            if price:
                return price

        # common meta/itemprop fallbacks
        meta = soup.find(attrs={"itemprop": "price"}) or soup.find("meta", attrs={"property": "product:price:amount"})
        if meta:
            return meta.get("content") or (getattr(meta, "text", None) or "").strip()
    except Exception:
        pass

    # 2) Selenium fallback: search a few likely selectors
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = "/usr/bin/chromium" # Point to the Chromium binary
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")

    # Use the pre-installed chromium-driver from the system path
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=opts)
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        selectors = ", ".join([
            ".ds-heading-lg",
            "[itemprop=price]",
            ".product-price",
            ".price",
            ".productPrice",
            "meta[property='product:price:amount']",
        ])

        elems = []
        try:
            elems = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selectors)))
        except Exception:
            elems = driver.find_elements(By.CSS_SELECTOR, selectors)

        for e in elems:
            text = e.get_attribute("content") if e.tag_name.lower() == "meta" else e.text
            if text and text.strip():
                return text.strip()
    finally:
        driver.quit()

    return None


def parse_name_and_number(url):
    """Return (name, product_number) where name is the last path segment
    before the trailing digits and product_number is digits at end of URL.
    Example: .../how-to-train-your-dragon-toothless-10375 ->
    ("how to train your dragon toothless", "10375")
    """
    path = urlparse(url).path.rstrip("/")
    last = unquote(path.split("/")[-1] or "")
    m = re.search(r"-(\d+)$", last)
    if m:
        prod = m.group(1)
        name_part = last[: m.start()]
        name = name_part.replace("-", " ").strip()
        return name, prod
    # fallback: no trailing digits
    return last.replace("-", " ").strip(), None



def get_main_text(url, timeout=10):
    """Extracts the main text content from a webpage."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style", "header", "footer", "nav"]):
            script_or_style.decompose()

        # Get text and clean it up
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit to first 4000 characters for LLM context
        return text[:4000]
    except Exception as e:
        return f"Error reading page: {e}"


from duckduckgo_search import DDGS

# FastAPI app
app = FastAPI()

@app.get("/search")
def search(q: str = Query(..., description="Search query")):
    with DDGS() as ddgs:
        results = [r for r in ddgs.text(q, max_results=5)]
    return JSONResponse({
        "query": q,
        "results": results
    })


@app.get("/read")
def read(url: str = Query(..., description="URL to read")):
    content = get_main_text(url)
    return JSONResponse({
        "url": url,
        "content": content
    })


@app.get("/scrape")
def scrape(url: str = Query(..., description="Product URL")):
    name, product_number = parse_name_and_number(url)
    if name:
        name = name.title()
    price = get_price(url)
    return JSONResponse({
        "name": name or "",
        "product_number": product_number or "",
        "price": price if price is not None else None
    })


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 script.py <URL>")
        sys.exit(1)
    url = sys.argv[1]
    name, product_number = parse_name_and_number(url)
    if name:
        name = name.title()
    price = get_price(url)
    print(f"name: {name or ''}")
    print(f"product number: {product_number or ''}")
    print(f"price: {price if price is not None else []}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        uvicorn.run("scraper:app", host="0.0.0.0", port=8000, reload=True)
    else:
        main()
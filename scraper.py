from bs4 import BeautifulSoup
import requests
import sys
import json
import re
import asyncio
import logging
from urllib.parse import urlparse, unquote
from datetime import datetime
import certifi

# FastAPI imports
from fastapi import FastAPI, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Database imports
from sqlalchemy.orm import Session
import database, models

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database tables
models.Base.metadata.create_all(bind=database.engine)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36"
    )
}

def _clean_price(price_str):
    if not price_str:
        return None
    try:
        # Remove currency symbols and commas
        cleaned = re.sub(r'[^\d.]', '', str(price_str))
        return float(cleaned)
    except (ValueError, TypeError):
        return None

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
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=certifi.where())
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string or "{}")
            except Exception:
                continue
            price = _find_price_in_json(data)
            if price:
                return price
        meta = soup.find(attrs={"itemprop": "price"}) or soup.find("meta", attrs={"property": "product:price:amount"})
        if meta:
            return meta.get("content") or (getattr(meta, "text", None) or "").strip()
    except Exception:
        pass

    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.binary_location = "/usr/bin/chromium"
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
    service = Service("/usr/bin/chromedriver")
    
    try:
        driver = webdriver.Chrome(service=service, options=opts)
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        selectors = ", ".join([".ds-heading-lg", "[itemprop=price]", ".product-price", ".price", ".productPrice", "meta[property='product:price:amount']"])
        elems = []
        try:
            elems = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selectors)))
        except Exception:
            elems = driver.find_elements(By.CSS_SELECTOR, selectors)
        for e in elems:
            text = e.get_attribute("content") if e.tag_name.lower() == "meta" else e.text
            if text and text.strip():
                return text.strip()
    except Exception as e:
        logger.error(f"Selenium error for {url}: {e}")
    finally:
        try: driver.quit()
        except: pass
    return None

def parse_name_and_number(url):
    path = urlparse(url).path.rstrip("/")
    last = unquote(path.split("/")[-1] or "")
    m = re.search(r"-(\d+)$", last)
    if m:
        prod = m.group(1)
        name = last[: m.start()].replace("-", " ").strip()
        return name, prod
    return last.replace("-", " ").strip(), None

def get_main_text(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=certifi.where())
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for s in soup(["script", "style", "header", "footer", "nav"]):
            s.decompose()
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return '\n'.join(chunk for chunk in chunks if chunk)[:4000]
    except Exception as e:
        return f"Error reading page: {e}"

from duckduckgo_search import DDGS

app = FastAPI()

@app.get("/search")
def search(q: str = Query(..., description="Search query")):
    with DDGS() as ddgs:
        results = [r for r in ddgs.text(q, max_results=5)]
    return JSONResponse({"query": q, "results": results})

@app.get("/read")
def read(url: str = Query(..., description="URL to read")):
    return JSONResponse({"url": url, "content": get_main_text(url)})

@app.get("/scrape")
def scrape(url: str = Query(..., description="Product URL")):
    name, product_number = parse_name_and_number(url)
    price = get_price(url)
    return JSONResponse({
        "name": name.title() if name else "",
        "product_number": product_number or "",
        "price": price
    })

@app.post("/track")
async def track_set(url: str = Query(...), db: Session = Depends(database.get_db)):
    name, product_number = parse_name_and_number(url)
    if not product_number:
        return JSONResponse({"error": "Invalid LEGO URL"}, status_code=400)
    
    # Check if already tracking
    existing = db.query(models.TrackedSet).filter(models.TrackedSet.product_number == product_number).first()
    if existing:
        return JSONResponse({"message": f"Already tracking {existing.name}", "id": existing.id})
    
    price_str = get_price(url)
    price_float = _clean_price(price_str)
    
    new_set = models.TrackedSet(name=name.title(), product_number=product_number, url=url)
    db.add(new_set)
    db.commit()
    db.refresh(new_set)
    
    if price_float is not None:
        history = models.PriceHistory(set_id=new_set.id, price=price_float)
        db.add(history)
        db.commit()
        
    return JSONResponse({"message": f"Now tracking {new_set.name}", "price": price_float})

@app.get("/tracked")
def list_tracked(db: Session = Depends(database.get_db)):
    sets = db.query(models.TrackedSet).all()
    results = []
    for s in sets:
        latest_price = db.query(models.PriceHistory).filter(models.PriceHistory.set_id == s.id).order_by(models.PriceHistory.timestamp.desc()).first()
        results.append({
            "name": s.name,
            "product_number": s.product_number,
            "url": s.url,
            "latest_price": latest_price.price if latest_price else None,
            "last_updated": latest_price.timestamp.isoformat() if latest_price else None
        })
    return JSONResponse(results)

async def update_prices_loop():
    while True:
        logger.info("Starting background price update...")
        db = database.SessionLocal()
        try:
            sets = db.query(models.TrackedSet).all()
            for s in sets:
                price_str = get_price(s.url)
                price_float = _clean_price(price_str)
                if price_float is not None:
                    history = models.PriceHistory(set_id=s.id, price=price_float)
                    db.add(history)
                    logger.info(f"Updated price for {s.name}: ${price_float}")
            db.commit()
        except Exception as e:
            logger.error(f"Error in background update: {e}")
        finally:
            db.close()
        await asyncio.sleep(86400) # Wait 24 hours

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_prices_loop())

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        uvicorn.run("scraper:app", host="0.0.0.0", port=8000, reload=True)

from bs4 import BeautifulSoup
import requests
import sys
import os
import json
import re
import asyncio
import logging
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone
import certifi
import html2text

# FastAPI imports
from fastapi import FastAPI, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Database imports
from sqlalchemy.orm import Session
import database, models

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migrations():
    """Run Alembic migrations on startup, stamping existing databases if needed."""
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect, text

    ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini")
    alembic_cfg = Config(ini_path)

    with database.engine.connect() as conn:
        inspector = inspect(conn)
        tables = inspector.get_table_names()
        has_alembic = "alembic_version" in tables
        has_tracked_sets = "tracked_sets" in tables

        if has_tracked_sets and not has_alembic:
            # Existing database predates Alembic — stamp at baseline before migrating
            logger.info("Existing schema detected without alembic_version; stamping at 001")
            command.stamp(alembic_cfg, "001")

    logger.info("Running Alembic migrations...")
    command.upgrade(alembic_cfg, "head")
    logger.info("Migrations complete")

run_migrations()

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
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")

    # Use the system-installed chromedriver when running in the container
    # (installed via apt in the Dockerfile). Fall back to webdriver-manager for local dev.
    system_driver = "/usr/bin/chromedriver"
    if os.path.exists(system_driver):
        service = Service(system_driver)
    else:
        service = Service(ChromeDriverManager().install())
    
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

def parse_url_details(url):
    domain = urlparse(url).netloc.lower()
    retailer = "lego"
    if "amazon" in domain:
        retailer = "amazon"
    elif "walmart" in domain:
        retailer = "walmart"
    elif "target" in domain:
        retailer = "target"
    
    path = urlparse(url).path.rstrip("/")
    last = unquote(path.split("/")[-1] or "")
    
    # LEGO.com pattern: set-name-12345
    m = re.search(r"-(\d+)$", last)
    if m:
        product_number = m.group(1)
        name = last[: m.start()].replace("-", " ").strip()
        return name, product_number, retailer
    
    # Amazon/Walmart often have product IDs in the URL. 
    # For now, we try to find a 5-7 digit number which is typical for LEGO.
    m2 = re.search(r"\b(\d{5,7})\b", url)
    product_number = m2.group(1) if m2 else None
    name = last.replace("-", " ").replace("+", " ").strip()
    
    return name, product_number, retailer

def get_main_text(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, verify=certifi.where())
        r.raise_for_status()
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.bypass_tables = False
        return h.handle(r.text)[:6000]
    except Exception as e:
        return f"Error reading page: {e}"

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background task
    task = asyncio.create_task(update_prices_loop())
    yield
    # Clean up
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.info("Background task cancelled")

from sqlalchemy import text

app = FastAPI(lifespan=lifespan)

@app.get("/health")
def health_check(db: Session = Depends(database.get_db)):
    try:
        # Use text() for SQLAlchemy 2.0 compatibility
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "up"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(status_code=500, content={"status": "unhealthy", "error": str(e)})

@app.get("/read")
def read(url: str = Query(..., description="URL to read")):
    logger.info(f"Received read request for: {url}")
    content = get_main_text(url)
    return JSONResponse({"url": url, "content": content})

@app.get("/scrape")
async def scrape(url: str = Query(..., description="Product URL")):
    logger.info(f"Received scrape request for: {url}")
    name, product_number, retailer = parse_url_details(url)
    # Run blocking Selenium call in a thread
    price = await asyncio.to_thread(get_price, url)
    return JSONResponse({
        "name": name.title() if name else "",
        "product_number": product_number or "",
        "retailer": retailer,
        "price": price
    })

@app.post("/track")
async def track_set(
    url: str = Query(...), 
    user_id: str = Query(None), 
    target_price: float = Query(None),
    db: Session = Depends(database.get_db)
):
    logger.info(f"Received track request for: {url} (user: {user_id}, target: {target_price})")
    name, product_number, retailer = parse_url_details(url)
    if not product_number:
        return JSONResponse({"error": "Could not identify LEGO set number from URL"}, status_code=400)

    existing = db.query(models.TrackedSet).filter(
        models.TrackedSet.product_number == product_number,
        models.TrackedSet.user_id == user_id,
        models.TrackedSet.retailer == retailer
    ).first()
    
    if existing:
        if target_price is not None:
            existing.target_price = target_price
            db.commit()
            return JSONResponse({"message": f"Updated target price for {existing.name} to ${target_price}", "id": existing.id})
        return JSONResponse({"message": f"Already tracking {existing.name} from {retailer}", "id": existing.id})

    # Run blocking Selenium call in a thread
    price_str = await asyncio.to_thread(get_price, url)
    price_float = _clean_price(price_str)
    
    new_set = models.TrackedSet(
        name=name.title(), 
        product_number=product_number, 
        url=url, 
        user_id=user_id,
        retailer=retailer,
        target_price=target_price
    )
    db.add(new_set)
    db.commit()
    db.refresh(new_set)

    if price_float is not None:
        history = models.PriceHistory(set_id=new_set.id, price=price_float)
        db.add(history)
        db.commit()
    return JSONResponse({"message": f"Now tracking {new_set.name} from {retailer}", "price": price_float})

@app.delete("/track/{product_number}")
def delete_tracked(
    product_number: str, 
    user_id: str = Query(None), 
    retailer: str = Query(None), 
    db: Session = Depends(database.get_db)
):
    query = db.query(models.TrackedSet).filter(models.TrackedSet.product_number == product_number)
    if user_id:
        query = query.filter(models.TrackedSet.user_id == user_id)
    if retailer:
        query = query.filter(models.TrackedSet.retailer == retailer)
        
    tracked_set = query.first()
    if not tracked_set:
        return JSONResponse({"error": "Set not found"}, status_code=404)
    
    db.query(models.PriceHistory).filter(models.PriceHistory.set_id == tracked_set.id).delete()
    db.delete(tracked_set)
    db.commit()
    return JSONResponse({"message": f"Deleted set {product_number} from {tracked_set.retailer}"})

@app.get("/tracked")
def list_tracked(user_id: str = Query(None), db: Session = Depends(database.get_db)):
    query = db.query(models.TrackedSet)
    if user_id:
        query = query.filter(models.TrackedSet.user_id == user_id)
    sets = query.all()
    results = []
    for s in sets:
        latest_price = db.query(models.PriceHistory).filter(models.PriceHistory.set_id == s.id).order_by(models.PriceHistory.timestamp.desc()).first()
        results.append({
            "name": s.name,
            "product_number": s.product_number,
            "retailer": s.retailer,
            "url": s.url,
            "latest_price": latest_price.price if latest_price else None,
            "target_price": s.target_price,
            "last_updated": latest_price.timestamp.isoformat() if latest_price else None
        })
    return JSONResponse(results)

@app.get("/track/{product_number}/history")
def get_history(product_number: str, user_id: str = Query(...), retailer: str = Query("lego"), db: Session = Depends(database.get_db)):
    """Returns price history for a specific set."""
    tracked_set = db.query(models.TrackedSet).filter(
        models.TrackedSet.product_number == product_number,
        models.TrackedSet.user_id == user_id,
        models.TrackedSet.retailer == retailer
    ).first()
    
    if not tracked_set:
        return JSONResponse({"error": "Set not found"}, status_code=404)
        
    history = db.query(models.PriceHistory).filter(
        models.PriceHistory.set_id == tracked_set.id
    ).order_by(models.PriceHistory.timestamp.asc()).all()
    
    return JSONResponse({
        "name": tracked_set.name,
        "product_number": tracked_set.product_number,
        "retailer": tracked_set.retailer,
        "history": [
            {"price": h.price, "timestamp": h.timestamp.isoformat()}
            for h in history
        ]
    })

@app.get("/alerts")
def get_alerts(db: Session = Depends(database.get_db)):
    """Returns sets that have hit their target price and haven't been notified for this price yet."""
    results = []
    sets = db.query(models.TrackedSet).filter(models.TrackedSet.target_price.isnot(None)).all()
    for s in sets:
        latest = db.query(models.PriceHistory).filter(models.PriceHistory.set_id == s.id).order_by(models.PriceHistory.timestamp.desc()).first()
        if latest and latest.price <= s.target_price:
            if s.last_notified_price is None or latest.price < s.last_notified_price:
                results.append({
                    "id": s.id,
                    "name": s.name,
                    "product_number": s.product_number,
                    "retailer": s.retailer,
                    "url": s.url,
                    "user_id": s.user_id,
                    "current_price": latest.price,
                    "target_price": s.target_price
                })
    return JSONResponse(results)

@app.post("/track/{set_id}/ack")
def acknowledge_alert(set_id: int, price: float = Query(...), db: Session = Depends(database.get_db)):
    """Updates the last_notified_price for a set to prevent duplicate alerts."""
    tracked_set = db.query(models.TrackedSet).filter(models.TrackedSet.id == set_id).first()
    if not tracked_set:
        return JSONResponse({"error": "Set not found"}, status_code=404)
    tracked_set.last_notified_price = price
    db.commit()
    return JSONResponse({"message": f"Acknowledged alert for {tracked_set.name} at ${price}"})

async def update_prices_loop():
    while True:
        logger.info("Starting background price update...")
        db = database.SessionLocal()
        try:
            sets = db.query(models.TrackedSet).all()
            for s in sets:
                # Run blocking Selenium call in a thread to avoid blocking the event loop
                price_str = await asyncio.to_thread(get_price, s.url)
                price_float = _clean_price(price_str)
                if price_float is not None:
                    history = models.PriceHistory(set_id=s.id, price=price_float)
                    db.add(history)
                    
                    # Log target price hit for monitoring
                    if s.target_price and price_float <= s.target_price:
                        if s.last_notified_price is None or price_float < s.last_notified_price:
                            logger.info(f"ALERT DETECTED for {s.name}: ${price_float} (Target: ${s.target_price})")
            db.commit()
        except Exception as e:
            logger.error(f"Error in background update: {e}")
        finally:
            db.close()
        await asyncio.sleep(86400)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        uvicorn.run("scraper:app", host="0.0.0.0", port=8000, reload=True)

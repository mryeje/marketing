import asyncio
import logging
import sqlite3
from datetime import datetime
from playwright.async_api import async_playwright

# -----------------------------
# Setup logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------
# Database setup
# -----------------------------
DB_FILE = "hashtags.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hashtags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT UNIQUE,
            collected_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_hashtags(hashtags):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for tag in hashtags:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO hashtags (tag, collected_at) VALUES (?, ?)",
                (tag, datetime.utcnow().isoformat())
            )
        except Exception as e:
            logger.warning(f"Failed to insert tag {tag}: {e}")
    conn.commit()
    conn.close()

# -----------------------------
# TikTok fallback scraping
# -----------------------------
async def scrape_tiktok_fallback():
    hashtags = []
    logger.info("Starting Playwright fallback...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-service-autorun",
                "--no-default-browser-check",
                "--homepage=about:blank"
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()

        logger.info("Opening TikTok Discover page...")
        await page.goto("https://www.tiktok.com/discover", timeout=60000)

        # wait for content to load
        await asyncio.sleep(10)

        elements = await page.query_selector_all('a[href*="/tag/"]')
        for el in elements:
            text = await el.inner_text()
            if text.startswith("#"):
                hashtags.append(text.strip())

        logger.info(f"Found {len(hashtags)} hashtags via fallback.")

        await context.close()
        await browser.close()

    return list(set(hashtags))  # remove duplicates

# -----------------------------
# Main async entry
# -----------------------------
async def main():
    init_db()
    
    hashtags = []

    try:
        from TikTokApi import TikTokApi
        api = TikTokApi()
        logger.info("TikTok API initialized successfully.")

        try:
            trending_obj = api.trending()  # returns a Trending object
            # Extract hashtag strings
            hashtags = [item.hashtag for item in trending_obj if hasattr(item, 'hashtag')]
        except Exception:
            logger.warning("Official API trending method not available, using fallback...")
            hashtags = await scrape_tiktok_fallback()

    except ImportError:
        logger.info("TikTokApi not installed, using Playwright fallback...")
        hashtags = await scrape_tiktok_fallback()
    
    if hashtags:
        save_hashtags(hashtags)
        logger.info(f"Saved {len(hashtags)} hashtags to database.")
    else:
        logger.info("No hashtags collected.")

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import sqlite3
from datetime import datetime
from playwright.async_api import async_playwright  # Official Playwright

# -----------------------------
# Logging Setup
# -----------------------------
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------
# Database Setup
# -----------------------------
DB_PATH = "hashtags.db"

def create_table():
    logger.info("Creating database table if it doesn't exist...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hashtags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hashtag TEXT UNIQUE,
            collected_at TEXT
        );
    """)
    conn.commit()
    conn.close()
    logger.info("Database ready.")

def save_hashtags(hashtags):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    saved_count = 0

    for tag in hashtags:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO hashtags (hashtag, collected_at) VALUES (?, ?)",
                (tag, datetime.utcnow().isoformat())
            )
            saved_count += 1
        except sqlite3.Error as e:
            logger.warning(f"Failed to insert tag {tag}: {e}")

    conn.commit()
    conn.close()
    logger.info(f"Saved {saved_count} hashtags to database.")

# -----------------------------
# TikTok Fallback Scraping
# -----------------------------
async def scrape_tiktok_fallback():
    hashtags = []
    try:
        logger.info("Starting Playwright fallback...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            logger.info("Opening TikTok Discover page...")
            await page.goto("https://www.tiktok.com/discover", timeout=60000)
            await page.screenshot(path="debug_initial.png")
            logger.info("Saved initial screenshot: debug_initial.png")

            logger.info("Waiting for hashtags to load (up to 30s)...")
            try:
                await page.wait_for_selector("a[href*='/tag/']", timeout=60000)
            except:
                logger.warning("Timeout waiting for hashtags. Will try scrolling.")

            # Scroll to load more hashtags
            for i in range(15):
                await page.mouse.wheel(0, 1000)
                await asyncio.sleep(1)
                logger.debug(f"Scroll {i+1}/10 completed")

            await page.screenshot(path="debug_scrolled.png")
            logger.info("Saved screenshot after scrolling: debug_scrolled.png")

            # Collect hashtags
            elements = await page.query_selector_all("a[href*='/tag/']")
            logger.info(f"Found {len(elements)} candidate elements for hashtags")
            for el in elements:
                text = await el.inner_text()
                if text.startswith("#"):
                    hashtags.append(text.strip())

            hashtags = list(set(hashtags))
            logger.info(f"Total hashtags collected: {len(hashtags)}")

            await context.close()
            await browser.close()
            logger.info("Browser closed successfully")

    except Exception as e:
        logger.error(f"Playwright scraping failed: {e}")

    return hashtags

# -----------------------------
# Main Async Entry
# -----------------------------
async def main():
    create_table()

    hashtags = []

    # Attempt official API first (if available)
    try:
        from TikTokApi import TikTokApi
        api = TikTokApi()
        logger.info("TikTok API initialized successfully.")

        try:
            trending_obj = api.trending()
            hashtags = [item.hashtag for item in trending_obj if hasattr(item, 'hashtag')]
        except Exception:
            logger.warning("Official API trending method not available, using fallback...")
            hashtags = await scrape_tiktok_fallback()
    except ImportError:
        logger.info("TikTokApi not installed, using Playwright fallback...")
        hashtags = await scrape_tiktok_fallback()

    save_hashtags(hashtags)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())

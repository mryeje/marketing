import asyncio
import logging
import random
import sqlite3
from datetime import datetime
from playwright.async_api import async_playwright
from ai_filter import get_content_filter  # Patched content filter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Expanded list of TikTok URLs to scrape
discovery_urls = [
    "https://www.tiktok.com/discover",
    "https://www.tiktok.com/explore",
    "https://www.tiktok.com/tag/diy",
    "https://www.tiktok.com/tag/tools",
    "https://www.tiktok.com/tag/woodworking",
    "https://www.tiktok.com/tag/homeimprovement",
    "https://www.tiktok.com/tag/renovation",
    "https://www.tiktok.com/tag/construction",
    "https://www.tiktok.com/tag/appliances",
    "https://www.tiktok.com/tag/kitchen",
    "https://www.tiktok.com/tag/homeappliances",
    "https://www.tiktok.com/tag/kitchenappliances",
    "https://www.tiktok.com/tag/landscaping",
    "https://www.tiktok.com/tag/lawncare",
    "https://www.tiktok.com/tag/gardening",
    "https://www.tiktok.com/tag/outdoor",
    "https://www.tiktok.com/tag/yardwork",
    "https://www.tiktok.com/tag/powertools",
    "https://www.tiktok.com/tag/diyprojects",
    "https://www.tiktok.com/tag/woodwork",
    "https://www.tiktok.com/tag/carpentry",
    "https://www.tiktok.com/tag/maker",
    "https://www.tiktok.com/tag/creativity",
    "https://www.tiktok.com/tag/build"
]

random.shuffle(discovery_urls)

# SQLite setup
def init_db():
    conn = sqlite3.connect("hashtags.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hashtags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hashtag TEXT NOT NULL,
            collected_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    return conn

async def scrape_tiktok():
    conn = init_db()
    cursor = conn.cursor()
    ai_filter = get_content_filter()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        for url in discovery_urls:
            try:
                logger.info(f"🌐 Opening TikTok page: {url}")
                await page.goto(url, timeout=60000)

                # Scroll to load more content
                for _ in range(3):
                    await page.mouse.wheel(0, 3000)
                    await asyncio.sleep(2)

                hashtags = set()

                if "/tag/" in url:
                    # Tag page: get the main hashtag header
                    header = await page.query_selector("h1, h2")
                    if header:
                        text = await header.inner_text()
                        if text.startswith("#"):
                            hashtags.add(text.strip())

                    # Related hashtags from video captions
                    caption_links = await page.query_selector_all("a[href*='/tag/']")
                    for link in caption_links:
                        text = await link.inner_text()
                        if text.startswith("#"):
                            hashtags.add(text.strip())
                else:
                    # Discover/Explore: collect hashtag links
                    links = await page.query_selector_all("a[href*='/tag/']")
                    for link in links:
                        text = await link.inner_text()
                        if text.startswith("#"):
                            hashtags.add(text.strip())

                logger.info(f"🔍 Found {len(hashtags)} raw hashtags on {url}")

                # Filter hashtags using AI/fallback filter
                hashtags_list = list(hashtags)
                relevant_mask = ai_filter.filter_irrelevant(hashtags_list)
                filtered_hashtags = [tag for tag, keep in zip(hashtags_list, relevant_mask) if keep]

                logger.info(f"✅ {len(filtered_hashtags)} relevant hashtags after filtering")

                # Save filtered hashtags to DB
                for tag in filtered_hashtags:
                    cursor.execute(
                        "INSERT INTO hashtags (hashtag, collected_at) VALUES (?, ?)",
                        (tag, datetime.utcnow())
                    )
                conn.commit()

            except Exception as e:
                logger.warning(f"⚠️ Error scraping {url}: {e}")

        await browser.close()
        conn.close()

if __name__ == "__main__":
    logger.info("🚀 Starting TikTok hashtag scraping + AI filtering pipeline...")
    asyncio.run(scrape_tiktok())

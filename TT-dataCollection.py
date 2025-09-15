import asyncio, time, sqlite3, aiohttp, json, re, random
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import logging

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
            hashtag TEXT,
            collected_at TEXT,
            source TEXT DEFAULT 'scraper',
            UNIQUE(hashtag, source)
        );
    """)
    conn.commit()
    conn.close()
    logger.info("Database ready.")

def save_hashtags(hashtags, source="scraper"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    saved_count = 0
    for tag in hashtags:
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO hashtags (hashtag, collected_at, source) VALUES (?, ?, ?)",
                (tag, datetime.now(timezone.utc).isoformat(), source)
            )
            saved_count += 1
        except sqlite3.Error as e:
            logger.warning(f"Failed to insert tag {tag}: {e}")
    conn.commit()
    conn.close()
    logger.info(f"Saved {saved_count} hashtags from {source} to database.")

# -----------------------------
# Playwright TikTok Scraper
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

            try:
                await page.wait_for_selector("a[href*='/tag/']", timeout=60000)
            except:
                logger.warning("Timeout waiting for hashtags. Will try scrolling.")

            # -----------------------------
            # Incremental scrolling
            # -----------------------------
            for i in range(25):
                scroll_amount = random.randint(500, 1200)
                await page.evaluate(f"() => window.scrollBy(0, {scroll_amount})")
                await asyncio.sleep(random.uniform(0.8, 1.5))
                logger.debug(f"Scroll {i+1}/25 by {scroll_amount}px completed")

            await page.screenshot(path="debug_scrolled.png")
            logger.info("Saved screenshot after scrolling: debug_scrolled.png")

            elements = await page.query_selector_all("a[href*='/tag/']")
            logger.info(f"Found {len(elements)} candidate elements for hashtags")
            for el in elements:
                text = await el.inner_text()
                if text.startswith("#"):
                    hashtags.append(text.strip())

            hashtags = list(set(hashtags))
            logger.info(f"Total hashtags collected from TikTok fallback: {len(hashtags)}")

            await context.close()
            await browser.close()
            logger.info("Browser closed successfully")
    except Exception as e:
        logger.error(f"Playwright scraping failed: {e}")
    return hashtags

# -----------------------------
# Alternative sources
# -----------------------------
async def scrape_alternative_sources():
    hashtags = []
    alternative_sites = [
        "https://www.influencermarketinghub.com/tiktok-hashtags/",
        "https://blog.hootsuite.com/tiktok-hashtags/",
        "https://www.socialinsider.io/blog/tiktok-hashtags/",
        "https://www.wordstream.com/tiktok-hashtags",
    ]
    try:
        async with aiohttp.ClientSession() as session:
            for url in alternative_sites:
                try:
                    headers = get_headers()
                    async with session.get(url, headers=headers, timeout=20) as response:
                        if response.status == 200:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            text_content = soup.get_text()
                            found = re.findall(r'#\w+', text_content)
                            hashtags.extend(found)
                            logger.info(f"Found {len(found)} hashtags from {url}")
                except Exception as e:
                    logger.warning(f"Error scraping {url}: {e}")
    except Exception as e:
        logger.error(f"Error with alternative sources: {e}")
    return hashtags

async def scrape_additional_sources():
    popular_lists = [
        "#fyp #foryou #viral #trending #tiktok #love #funny #comedy #dance #music",
        "#art #food #travel #fashion #beauty #gaming #sports #fitness #life #happy",
        "#family #friends #nature #photography #style #ootd #makeup #skincare #home",
    ]
    hashtags = []
    for hashtag_list in popular_lists:
        hashtags.extend(re.findall(r'#\w+', hashtag_list))
    return hashtags

def get_headers():
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
    ]
    return {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }

# -----------------------------
# Hybrid Scraper Entry
# -----------------------------
async def main():
    create_table()
    all_hashtags = []

    # Playwright fallback
    tiktok_tags = await scrape_tiktok_fallback()
    if tiktok_tags:
        save_hashtags(tiktok_tags, source="TikTokFallback")
        all_hashtags.extend(tiktok_tags)

    # Alternative sources
    alt_tags = await scrape_alternative_sources()
    if alt_tags:
        save_hashtags(alt_tags, source="AltSites")
        all_hashtags.extend(alt_tags)

    # Additional precompiled sources
    add_tags = await scrape_additional_sources()
    if add_tags:
        save_hashtags(add_tags, source="FallbackLists")
        all_hashtags.extend(add_tags)

    logger.info(f"Total unique hashtags collected across all sources: {len(set(all_hashtags))}")
    logger.info(f"Collected {len(all_hashtags)} hashtags")
    logger.info(f"Unique: {len(set(all_hashtags))}")
    logger.info("Data collection completed at: " + datetime.now(timezone.utc).isoformat())
    

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())

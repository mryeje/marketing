import asyncio, random, time, sqlite3
from nodriver import start
from bs4 import BeautifulSoup
import json

async def scrape():
    try:
        browser = await start(
            headless=False,  # Changed to False to see what's happening
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            browser_executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )

        # open TikTok in a tab
        print("Opening TikTok...")
        tab = await browser.get("https://www.tiktok.com/discover")
        await asyncio.sleep(5)  # Longer wait to see the page
        
        # Let's see what the page actually contains
        print("Getting page content...")
        html = await tab.evaluate("document.documentElement.outerHTML")
        
        # Save the HTML to a file for inspection
        with open("tiktok_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved to tiktok_page.html for inspection")
        
        # Also try to get text content to see what's visible
        visible_text = await tab.evaluate("document.body.textContent")
        with open("tiktok_text.txt", "w", encoding="utf-8") as f:
            f.write(visible_text)
        print("Text content saved to tiktok_text.txt")
        
        # Try to wait for specific elements to load
        print("Waiting for content to load...")
        await asyncio.sleep(3)
        
        # Try scrolling to trigger loading
        await tab.evaluate("window.scrollTo(0, 500)")
        await asyncio.sleep(2)
        
        # Get updated HTML after interactions
        html = await tab.evaluate("document.documentElement.outerHTML")
        
        # parse with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Try to find any trending content
        print("Looking for trending elements...")
        
        # Check for different types of content
        all_links = soup.find_all('a')
        print(f"Total links found: {len(all_links)}")
        
        # Look for hashtags in various ways
        hashtags = []
        
        # Method 1: Look for links containing hashtag-related patterns
        for link in all_links:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            
            if '/tag/' in href or '/hashtag/' in href:
                hashtags.append(text)
                print(f"Found hashtag link: {text} -> {href}")
            elif text.startswith('#'):
                hashtags.append(text)
                print(f"Found text hashtag: {text}")
        
        # Method 2: Look for span/dive with hashtag text
        all_elements = soup.find_all(['span', 'div', 'p'])
        for elem in all_elements:
            text = elem.get_text(strip=True)
            if text.startswith('#') and len(text) > 1:
                hashtags.append(text)
                print(f"Found element with hashtag: {text}")
        
        # Remove duplicates and clean up
        hashtags = list(set(hashtags))
        hashtags = [h for h in hashtags if h and len(h) > 1]
        
        print(f"Total unique hashtags found: {len(hashtags)}")
        if hashtags:
            print(f"Hashtags found: {hashtags}")

        # save to SQLite
        conn = sqlite3.connect("trends.db")
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS hashtags (time INT, tag TEXT)")
        for h in hashtags:
            c.execute("INSERT INTO hashtags VALUES (?, ?)", (int(time.time()), h))
        conn.commit()
        conn.close()
        
        print("Data saved successfully!")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(scrape())
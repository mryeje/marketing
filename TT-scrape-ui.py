import tkinter as tk
from tkinter import messagebox, scrolledtext
import sqlite3
import time
from datetime import datetime, timezone

# --- Database setup ---
conn = sqlite3.connect("hashtags.db")
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS hashtags (
    id INTEGER PRIMARY KEY,
    hashtag TEXT,
    source TEXT,
    timestamp TEXT
)
""")
conn.commit()

# --- Scraper function (placeholder) ---
def scrape_hashtag(hashtag, scrolls, delay, max_posts, source, log_widget):
    log_widget.insert(tk.END, f"Starting scrape for #{hashtag}\n")
    log_widget.see(tk.END)
    for i in range(min(scrolls, max_posts)):
        time.sleep(delay)
        log_widget.insert(tk.END, f"Scraped post {i+1} for #{hashtag}\n")
        log_widget.see(tk.END)
    timestamp = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO hashtags (hashtag, source, timestamp) VALUES (?, ?, ?)",
              (hashtag, source, timestamp))
    conn.commit()
    log_widget.insert(tk.END, f"Finished #{hashtag}\n\n")
    log_widget.see(tk.END)

# --- Tkinter UI ---
root = tk.Tk()
root.title("TikTok Hashtag Scraper")

tk.Label(root, text="Hashtags (comma separated):").grid(row=0, column=0, sticky="w")
hashtag_entry = tk.Entry(root, width=50)
hashtag_entry.grid(row=0, column=1)

tk.Label(root, text="Source:").grid(row=1, column=0, sticky="w")
source_entry = tk.Entry(root, width=50)
source_entry.grid(row=1, column=1)

tk.Label(root, text="Scrolls:").grid(row=2, column=0, sticky="w")
scrolls_entry = tk.Entry(root, width=10)
scrolls_entry.insert(0, "5")
scrolls_entry.grid(row=2, column=1, sticky="w")

tk.Label(root, text="Delay (sec):").grid(row=3, column=0, sticky="w")
delay_entry = tk.Entry(root, width=10)
delay_entry.insert(0, "1")
delay_entry.grid(row=3, column=1, sticky="w")

tk.Label(root, text="Max Posts:").grid(row=4, column=0, sticky="w")
max_posts_entry = tk.Entry(root, width=10)
max_posts_entry.insert(0, "10")
max_posts_entry.grid(row=4, column=1, sticky="w")

log_text = scrolledtext.ScrolledText(root, width=70, height=20)
log_text.grid(row=5, column=0, columnspan=2, pady=10)

def run_scraper():
    hashtags = [tag.strip() for tag in hashtag_entry.get().split(",") if tag.strip()]
    source = source_entry.get().strip() or "unknown"
    
    if not hashtags:
        # Use a default placeholder if none entered
        hashtags = ["default"]

    try:
        scrolls = int(scrolls_entry.get())
        delay = float(delay_entry.get())
        max_posts = int(max_posts_entry.get())
    except ValueError:
        messagebox.showerror("Input Error", "Please enter valid numbers for scrolls, delay, and max posts.")
        return

    for tag in hashtags:
        scrape_hashtag(tag, scrolls, delay, max_posts, source, log_text)

tk.Button(root, text="Run Scraper", command=run_scraper).grid(row=6, column=0, columnspan=2, pady=10)

root.mainloop()

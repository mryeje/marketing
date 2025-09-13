import sqlite3

DB_PATH = "hashtags.db"

def show_hashtags():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, hashtag, collected_at, source FROM hashtags ORDER BY collected_at DESC")
        rows = cursor.fetchall()
        
        if not rows:
            print("No hashtags found in the database.")
            return
        
        print(f"{'ID':<5} {'Hashtag':<30} {'Collected At':<30} {'Source'}")
        print("-" * 80)
        for row in rows:
            _id, hashtag, collected_at, source = row
            print(f"{_id:<5} {hashtag:<30} {collected_at:<30} {source}")
    except Exception as e:
        print(f"Error reading database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    show_hashtags()

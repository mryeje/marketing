import sqlite3
import pandas as pd
import os
from datetime import datetime
from typing import List, Dict, Optional

class HashtagDatabase:
    """SQLite database manager for hashtag data storage and retrieval"""
    
    def __init__(self, db_path: str = "hashtag_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create hashtags table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hashtags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hashtag_name TEXT UNIQUE NOT NULL,
                niche_category TEXT,
                video_count INTEGER DEFAULT 0,
                engagement_score REAL DEFAULT 0.0,
                is_relevant BOOLEAN DEFAULT TRUE,
                topic_id INTEGER,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create hashtag_history table for tracking changes over time
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hashtag_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hashtag_name TEXT NOT NULL,
                video_count INTEGER,
                engagement_score REAL,
                snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (hashtag_name) REFERENCES hashtags (hashtag_name)
            )
        ''')
        
        # Create niche_breakdown table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS niche_breakdown (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                niche_name TEXT UNIQUE NOT NULL,
                hashtag_count INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_path}")
    
    def load_csv_data(self, csv_files: Dict[str, str]) -> Dict[str, pd.DataFrame]:
        """Load data from CSV files"""
        data = {}
        for niche, filepath in csv_files.items():
            if os.path.exists(filepath):
                try:
                    df = pd.read_csv(filepath)
                    # Standardize column names
                    if len(df.columns) >= 2:
                        first_col, second_col = df.columns[0], df.columns[1]
                        df = df.rename(columns={
                            first_col: 'hashtag_name',
                            second_col: 'count'
                        })
                        df['niche_category'] = niche
                        data[niche] = df
                        print(f"Loaded {len(df)} records from {filepath}")
                    else:
                        print(f"Warning: {filepath} has insufficient columns")
                except Exception as e:
                    print(f"Error loading {filepath}: {e}")
        return data
    
    def insert_hashtags(self, hashtags_data: List[Dict]):
        """Insert or update hashtag data"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted_count = 0
        updated_count = 0
        
        for hashtag in hashtags_data:
            # Check if hashtag already exists
            cursor.execute(
                "SELECT id, video_count FROM hashtags WHERE hashtag_name = ?",
                (hashtag['hashtag_name'],)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record
                cursor.execute('''
                    UPDATE hashtags 
                    SET video_count = ?, 
                        engagement_score = ?,
                        niche_category = ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE hashtag_name = ?
                ''', (
                    hashtag.get('video_count', 0),
                    hashtag.get('engagement_score', 0.0),
                    hashtag.get('niche_category', 'unknown'),
                    hashtag['hashtag_name']
                ))
                
                # Insert into history table
                cursor.execute('''
                    INSERT INTO hashtag_history (hashtag_name, video_count, engagement_score)
                    VALUES (?, ?, ?)
                ''', (
                    hashtag['hashtag_name'],
                    hashtag.get('video_count', 0),
                    hashtag.get('engagement_score', 0.0)
                ))
                updated_count += 1
                
            else:
                # Insert new record
                cursor.execute('''
                    INSERT INTO hashtags (
                        hashtag_name, niche_category, video_count, 
                        engagement_score, is_relevant, topic_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    hashtag['hashtag_name'],
                    hashtag.get('niche_category', 'unknown'),
                    hashtag.get('video_count', 0),
                    hashtag.get('engagement_score', 0.0),
                    hashtag.get('is_relevant', True),
                    hashtag.get('topic_id', None)
                ))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        print(f"Database updated: {inserted_count} new hashtags, {updated_count} updated")
    
    def update_niche_breakdown(self, niche_data: Dict[str, int]):
        """Update niche breakdown statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for niche, count in niche_data.items():
            cursor.execute('''
                INSERT OR REPLACE INTO niche_breakdown (niche_name, hashtag_count, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (niche, count))
        
        conn.commit()
        conn.close()
        print(f"Updated niche breakdown for {len(niche_data)} categories")
    
    def get_top_hashtags(self, niche: Optional[str] = None, limit: int = 20) -> pd.DataFrame:
        """Retrieve top hashtags, optionally filtered by niche"""
        conn = sqlite3.connect(self.db_path)
        
        if niche:
            query = '''
                SELECT hashtag_name, niche_category, video_count, engagement_score, 
                       is_relevant, first_seen, last_updated
                FROM hashtags 
                WHERE niche_category = ? AND is_relevant = 1
                ORDER BY video_count DESC, engagement_score DESC
                LIMIT ?
            '''
            df = pd.read_sql_query(query, conn, params=(niche, limit))
        else:
            query = '''
                SELECT hashtag_name, niche_category, video_count, engagement_score,
                       is_relevant, first_seen, last_updated
                FROM hashtags 
                WHERE is_relevant = 1
                ORDER BY video_count DESC, engagement_score DESC
                LIMIT ?
            '''
            df = pd.read_sql_query(query, conn, params=(limit,))
        
        conn.close()
        return df
    
    def get_hashtag_trends(self, hashtag_name: str) -> pd.DataFrame:
        """Get historical data for a specific hashtag"""
        conn = sqlite3.connect(self.db_path)
        query = '''
            SELECT hashtag_name, video_count, engagement_score, snapshot_date
            FROM hashtag_history 
            WHERE hashtag_name = ?
            ORDER BY snapshot_date DESC
        '''
        df = pd.read_sql_query(query, conn, params=(hashtag_name,))
        conn.close()
        return df
    
    def get_niche_summary(self) -> pd.DataFrame:
        """Get summary statistics by niche"""
        conn = sqlite3.connect(self.db_path)
        query = '''
            SELECT 
                niche_category,
                COUNT(*) as total_hashtags,
                SUM(video_count) as total_videos,
                AVG(engagement_score) as avg_engagement,
                MAX(last_updated) as last_updated
            FROM hashtags 
            WHERE is_relevant = 1
            GROUP BY niche_category
            ORDER BY total_videos DESC
        '''
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def export_to_csv(self, output_dir: str = "exports"):
        """Export current data back to CSV files"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Export by niche
        niches = self.get_niche_summary()['niche_category'].tolist()
        
        for niche in niches:
            df = self.get_top_hashtags(niche=niche, limit=50)
            if not df.empty:
                filename = f"{output_dir}/{niche}_hashtags_updated.csv"
                df[['hashtag_name', 'video_count']].to_csv(filename, index=False)
                print(f"Exported {niche} data to {filename}")
        
        # Export overall summary
        summary = self.get_niche_summary()
        summary.to_csv(f"{output_dir}/niche_breakdown_updated.csv", index=False)
        print(f"Exported niche summary to {output_dir}/niche_breakdown_updated.csv")

def main():
    """Main function to load existing CSV data into SQLite"""
    
    # Initialize database
    db = HashtagDatabase()
    
    # Define your CSV files (adjust paths as needed)
    csv_files = {
        'power_tools': 'power_tools_hashtags.csv',
        'appliances': 'appliances_hashtags.csv',
        'ope': 'ope_hashtags.csv',
        'general': 'top_hashtags.csv'
    }
    
    # Load data from CSV files
    print("Loading CSV data...")
    data = db.load_csv_data(csv_files)
    
    if not data:
        print("No CSV files found. Make sure your files exist and try again.")
        return
    
    # Prepare hashtag data for insertion
    all_hashtags = []
    niche_counts = {}
    
    for niche, df in data.items():
        if 'hashtag_name' in df.columns and 'count' in df.columns:
            valid_rows = 0
            for _, row in df.iterrows():
                # Skip rows with empty or null hashtag names
                hashtag_name = str(row['hashtag_name']).strip()
                if not hashtag_name or hashtag_name.lower() in ['nan', 'none', '']:
                    print(f"Skipping empty hashtag in {niche}")
                    continue
                
                # Clean hashtag name (remove # if present)
                if hashtag_name.startswith('#'):
                    hashtag_name = hashtag_name[1:]
                
                count_value = row['count']
                if pd.isna(count_value):
                    count_value = 0
                else:
                    try:
                        count_value = int(float(count_value))
                    except (ValueError, TypeError):
                        count_value = 0
                
                hashtag_record = {
                    'hashtag_name': hashtag_name,
                    'niche_category': niche,
                    'video_count': count_value,
                    'engagement_score': float(count_value) * 1.0,  # Simple scoring
                    'is_relevant': True,
                    'topic_id': None
                }
                all_hashtags.append(hashtag_record)
                valid_rows += 1
            
            niche_counts[niche] = valid_rows
            print(f"Processed {valid_rows} valid hashtags from {niche}")
    
    # Insert data into database
    print("Inserting data into database...")
    db.insert_hashtags(all_hashtags)
    db.update_niche_breakdown(niche_counts)
    
    # Display summary
    print("\nDatabase Summary:")
    summary = db.get_niche_summary()
    print(summary.to_string(index=False))
    
    # Show top hashtags
    print("\nTop 10 Hashtags Overall:")
    top_hashtags = db.get_top_hashtags(limit=10)
    print(top_hashtags[['hashtag_name', 'niche_category', 'video_count']].to_string(index=False))
    
    print(f"\nDatabase saved as: {db.db_path}")
    print("You can now query this database for ongoing hashtag tracking!")

if __name__ == "__main__":
    main()
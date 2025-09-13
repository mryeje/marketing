import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib as mpl

# Set a font that supports English characters only to avoid warnings
mpl.rcParams['font.family'] = 'DejaVu Sans'  # This should prevent the Thai character warnings

def analyze_trends():
    print("🔍 Analyzing TikTok trends data...")
    
    try:
        # Connect to database
        conn = sqlite3.connect('trends.db')
        
        # Read all data
        query = "SELECT time, tag FROM hashtags ORDER BY time DESC"
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print("❌ No data found in the database!")
            return
        
        # Convert timestamp to datetime
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['datetime'].dt.date
        df['hour'] = df['datetime'].dt.hour
        
        print(f"✅ Loaded {len(df)} records from database")
        print(f"📅 Data range: {df['datetime'].min()} to {df['datetime'].max()}")
        
        # Basic analysis
        total_hashtags = len(df)
        unique_hashtags = df['tag'].nunique()
        
        print(f"\n📊 BASIC STATISTICS:")
        print(f"Total hashtag mentions: {total_hashtags}")
        print(f"Unique hashtags: {unique_hashtags}")
        print(f"Average mentions per hashtag: {total_hashtags/unique_hashtags:.1f}")
        
        # Top trending hashtags
        print(f"\n🔥 TOP 15 TRENDING HASHTAGS:")
        top_hashtags = df['tag'].value_counts().head(15)
        for i, (hashtag, count) in enumerate(top_hashtags.items(), 1):
            print(f"{i:2d}. {hashtag}: {count} mentions")
        
        # Save analysis to CSV
        top_hashtags.to_csv('top_hashtags.csv')
        print(f"\n💾 Analysis saved to 'top_hashtags.csv'")
        
        # Create simple visualization without complex fonts
        create_simple_visualization(df, top_hashtags)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analyzing data: {e}")
        import traceback
        traceback.print_exc()

def create_simple_visualization(df, top_hashtags):
    """Create simple visualizations without font issues"""
    try:
        # Create just one simple plot to avoid font issues
        plt.figure(figsize=(12, 8))
        
        # Plot top hashtags
        top_10 = top_hashtags.head(10)
        plt.barh(range(len(top_10)), top_10.values)
        plt.yticks(range(len(top_10)), top_10.index)
        plt.title('Top 10 Trending TikTok Hashtags')
        plt.xlabel('Number of Mentions')
        plt.tight_layout()
        
        plt.savefig('top_hashtags_chart.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print("📊 Simple visualization saved as 'top_hashtags_chart.png'")
        
    except Exception as e:
        print(f"⚠️ Could not create visualization: {e}")

def show_detailed_analysis():
    """Show more detailed analysis without visualizations"""
    try:
        conn = sqlite3.connect('trends.db')
        df = pd.read_sql_query("SELECT time, tag FROM hashtags", conn)
        
        if df.empty:
            return
            
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['datetime'].dt.date
        
        # Show trending over time
        print(f"\n📈 TRENDING OVER TIME:")
        trending_over_time = df.groupby('date').size()
        for date, count in trending_over_time.items():
            print(f"  {date}: {count} mentions")
        
        # Show hashtag frequency distribution
        print(f"\n📋 HASHTAG DISTRIBUTION:")
        counts = df['tag'].value_counts()
        print(f"  Most popular: {counts.iloc[0]} mentions")
        print(f"  Least popular: {counts.iloc[-1]} mentions")
        print(f"  Median mentions: {counts.median():.1f}")
        
        conn.close()
        
    except Exception as e:
        print(f"Detailed analysis error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("           TIKTOK TRENDS ANALYSIS TOOL")
    print("=" * 60)
    
    analyze_trends()
    show_detailed_analysis()
    
    print("\n" + "=" * 60)
    print("✅ Analysis complete! Check the generated files:")
    print("   - top_hashtags.csv (spreadsheet of top hashtags)")
    print("   - top_hashtags_chart.png (visual chart)")
    print("=" * 60)
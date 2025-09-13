import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib as mpl
from typing import List

# Set a font that supports English characters only to avoid warnings
mpl.rcParams['font.family'] = 'DejaVu Sans'

class NicheFilter:
    def __init__(self, niche_keywords: List[str], exclude_keywords: List[str] = None):
        """
        Initialize niche filter with relevant and exclusion keywords
        
        Args:
            niche_keywords: Keywords that indicate relevance to your niche
            exclude_keywords: Keywords that should be filtered out
        """
        self.niche_keywords = [kw.lower() for kw in niche_keywords]
        self.exclude_keywords = [kw.lower() for kw in (exclude_keywords or [])]
    
    def is_relevant(self, hashtag: str, context: str = "") -> bool:
        """
        Check if a hashtag is relevant to your niche
        
        Args:
            hashtag: The hashtag to check (with or without #)
            context: Optional context (video description, etc.)
        
        Returns:
            bool: True if relevant to niche
        """
        # Clean hashtag
        clean_tag = hashtag.lower().replace('#', '')
        full_text = f"{clean_tag} {context}".lower()
        
        # Check for exclusions first
        for exclude in self.exclude_keywords:
            if exclude in full_text:
                return False
        
        # Check for niche relevance
        for keyword in self.niche_keywords:
            if keyword in full_text:
                return True
        
        return False

def analyze_trends():
    print("🔍 Analyzing TikTok trends data...")
    
    # CUSTOMIZE YOUR NICHE HERE:
    # Replace these keywords with terms relevant to your niche
    niche_filter = NicheFilter(
        niche_keywords=['fitness', 'workout', 'gym', 'health', 'exercise', 
                       'muscle', 'cardio', 'strength', 'yoga', 'nutrition',
                       'diet', 'protein', 'weightloss'],  # Add your niche keywords
        exclude_keywords=['casino', 'gambling', 'nsfw', 'adult']  # Add words to exclude
    )
    
    try:
        # Connect to database
        conn = sqlite3.connect('trends.db')
        
        # Read all data
        query = "SELECT time, tag FROM hashtags ORDER BY time DESC"
        df = pd.read_sql_query(query, conn)
        
        if df.empty:
            print("⚠ No data found in the database!")
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
        
        # Top trending hashtags (general)
        print(f"\n🔥 TOP 15 OVERALL TRENDING HASHTAGS:")
        top_hashtags = df['tag'].value_counts().head(15)
        for i, (hashtag, count) in enumerate(top_hashtags.items(), 1):
            print(f"{i:2d}. {hashtag}: {count} mentions")
        
        # NICHE-SPECIFIC ANALYSIS
        print(f"\n🎯 NICHE-SPECIFIC ANALYSIS:")
        
        # Filter hashtags for niche relevance
        niche_mask = df['tag'].apply(lambda x: niche_filter.is_relevant(x))
        niche_df = df[niche_mask]
        
        if niche_df.empty:
            print("❌ No hashtags found relevant to your niche!")
            print("💡 Try adjusting your niche_keywords in the script")
        else:
            niche_count = len(niche_df)
            relevance_ratio = niche_count / total_hashtags * 100
            
            print(f"Niche-relevant mentions: {niche_count}")
            print(f"Relevance ratio: {relevance_ratio:.1f}%")
            
            # Top niche hashtags
            print(f"\n🌟 TOP 10 NICHE HASHTAGS:")
            top_niche = niche_df['tag'].value_counts().head(10)
            for i, (hashtag, count) in enumerate(top_niche.items(), 1):
                print(f"{i:2d}. {hashtag}: {count} mentions")
            
            # Save niche results
            top_niche.to_csv('niche_hashtags.csv')
            print(f"\n💾 Niche analysis saved to 'niche_hashtags.csv'")
            
            # Create niche-focused visualization
            create_niche_visualization(df, niche_df, top_niche, top_hashtags)
        
        # Save general analysis to CSV
        top_hashtags.to_csv('top_hashtags.csv')
        print(f"\n💾 General analysis saved to 'top_hashtags.csv'")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analyzing data: {e}")
        import traceback
        traceback.print_exc()

def create_niche_visualization(df, niche_df, top_niche, top_general):
    """Create visualizations comparing general vs niche trends"""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        
        # 1. Niche vs General comparison pie chart
        general_count = len(df) - len(niche_df)
        niche_count = len(niche_df)
        
        if niche_count > 0:
            axes[0, 0].pie([general_count, niche_count], 
                          labels=['General', 'Niche'], 
                          autopct='%1.1f%%',
                          colors=['#lightgray', '#FF6B6B'])
            axes[0, 0].set_title('Niche vs General Hashtags Distribution')
        else:
            axes[0, 0].text(0.5, 0.5, 'No niche hashtags found', 
                           ha='center', va='center', transform=axes[0, 0].transAxes)
            axes[0, 0].set_title('Niche Analysis - No Data')
        
        # 2. Top general hashtags
        if not top_general.empty:
            top_10_general = top_general.head(10)
            axes[0, 1].barh(range(len(top_10_general)), top_10_general.values, 
                           color='#4ECDC4')
            axes[0, 1].set_yticks(range(len(top_10_general)))
            axes[0, 1].set_yticklabels(top_10_general.index)
            axes[0, 1].set_title('Top 10 Overall Hashtags')
            axes[0, 1].set_xlabel('Mentions')
        
        # 3. Top niche hashtags
        if not top_niche.empty:
            top_10_niche = top_niche.head(10)
            axes[1, 0].barh(range(len(top_10_niche)), top_10_niche.values, 
                           color='#FF6B6B')
            axes[1, 0].set_yticks(range(len(top_10_niche)))
            axes[1, 0].set_yticklabels(top_10_niche.index)
            axes[1, 0].set_title('Top 10 Niche Hashtags')
            axes[1, 0].set_xlabel('Mentions')
        else:
            axes[1, 0].text(0.5, 0.5, 'No niche hashtags to display', 
                           ha='center', va='center', transform=axes[1, 0].transAxes)
            axes[1, 0].set_title('Top Niche Hashtags - No Data')
        
        # 4. Daily activity comparison
        if not niche_df.empty and 'date' in niche_df.columns:
            # General daily activity
            general_daily = df.groupby('date').size()
            niche_daily = niche_df.groupby('date').size()
            
            # Reindex niche_daily to match general_daily dates
            niche_daily = niche_daily.reindex(general_daily.index, fill_value=0)
            
            axes[1, 1].plot(general_daily.index, general_daily.values, 
                           label='All Hashtags', marker='o', alpha=0.7)
            axes[1, 1].plot(niche_daily.index, niche_daily.values, 
                           label='Niche Hashtags', marker='s', color='#FF6B6B')
            axes[1, 1].set_title('Daily Activity: General vs Niche')
            axes[1, 1].set_xlabel('Date')
            axes[1, 1].set_ylabel('Mentions')
            axes[1, 1].legend()
            axes[1, 1].tick_params(axis='x', rotation=45)
        else:
            daily_activity = df.groupby('date').size()
            axes[1, 1].plot(daily_activity.index, daily_activity.values, 
                           marker='o', color='#45B7D1')
            axes[1, 1].set_title('Daily Hashtag Activity')
            axes[1, 1].set_xlabel('Date')
            axes[1, 1].set_ylabel('Mentions')
            axes[1, 1].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.savefig('niche_vs_general_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print("📊 Visualization saved as 'niche_vs_general_analysis.png'")
        
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
    print("     NICHE-FOCUSED TIKTOK TRENDS ANALYSIS TOOL")
    print("=" * 60)
    
    analyze_trends()
    show_detailed_analysis()
    
    print("\n" + "=" * 60)
    print("✅ Analysis complete! Check the generated files:")
    print("   - top_hashtags.csv (all trending hashtags)")
    print("   - niche_hashtags.csv (your niche-specific hashtags)")
    print("   - niche_vs_general_analysis.png (comparison charts)")
    print("=" * 60)
    print("\n💡 To customize for your niche:")
    print("   Edit the 'niche_keywords' list at the top of analyze_trends()")
    print("   Add keywords relevant to your specific use case")
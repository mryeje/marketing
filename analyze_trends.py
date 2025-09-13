import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib as mpl
from typing import List, Dict

# Set a font that supports English characters only to avoid warnings
mpl.rcParams['font.family'] = 'DejaVu Sans'

class MultiNicheFilter:
    def __init__(self):
        """Initialize with all three niche definitions"""
        
        # Power Tools Niche
        self.power_tools_keywords = [
            'powertool', 'powertools', 'cordless', 'drill', 'hammerdrill', 
            'circularsaw', 'impactdriver', 'tools', 'toolreview', 'diyprojects',
            'workshop', 'toolsofthetrade', 'toolcollection', 'milwaukee',
            'dewalt', 'makita', 'ryobi', 'bosch', 'toolsetup', 'woodworking',
            'construction', 'renovation', 'engineering', 'industrial', 'woodwork',
            'concrete', 'carpentry', 'carpenter', 'builder', 'mechanic',
            'festool', 'tradesman', 'toolbox', 'handtools', 'finewoodworking',
            'powerdrill', 'tablesaw', 'mitersaw', 'bandsaw', 'jigsaw',
            'reciprocatingsaw', 'oscillatingtool', 'grinder', 'sander', 'router',
            'planer', 'nailer', 'stapler', 'wrench', 'socket', 'toolbelt',
            'diy', 'homeimprovement', 'garage', 'build', 'remodel', 'renovate', 
            'craftsman', 'professional', 'batterypowered', 'heavyduty',
            'precision', 'ergonomic', 'compact', 'lithium', 'brushless',
            'tooltips', 'howto', 'tutorial', 'project', 'custom', 'make', 
            'create', 'install', 'repair', 'restore'
        ]
        
        # Appliances Niche
        self.appliances_keywords = [
            'appliance', 'appliances', 'homeappliances', 'kitchenappliances',
            'appliancerepair', 'kitchenappliance', 'homeappliance', 'newappliances',
            'stainlesssteelappliances', 'geappliances', 'lgappliances',
            'samsungappliances', 'boschappliances', 'whirlpool', 'maytag',
            'kitchenaid', 'fridge', 'refrigerator', 'oven', 'stove', 'cooktop',
            'dishwasher', 'microwave', 'washer', 'dryer', 'laundry', 'freezer',
            'icemaker', 'waterdispenser', 'smallappliances', 'blender',
            'mixer', 'toaster', 'coffeemaker', 'vacuum', 'applianceparts',
            'replacementparts', 'repairparts', 'servicing', 'technician',
            'home', 'kitchen', 'cleaning', 'cooking', 'baking',
            'diyrepair', 'fix', 'troubleshoot', 'installation', 'upgrade', 
            'smarthome', 'energyefficient', 'stainless', 'modern', 'luxury', 
            'budget', 'sale', 'deal', 'review', 'comparison', 'buyingguide', 
            'maintenance', 'care', 'warranty', 'service', 'diagnose', 
            'errorcode', 'partnumber'
        ]
        
        # OPE (Outdoor Power Equipment) Niche
        self.ope_keywords = [
            'ope', 'outdoorpower', 'outdoorequipment', 'lawncare',
            'landscaping', 'lawnmower', 'ridingmower', 'zeroturn',
            'tractor', 'stringtrimmer', 'weedeater', 'edger',
            'leafblower', 'blower', 'chainsaw', 'hedgetrimmer',
            'polesaw', 'snowblower', 'generator', 'pressurewasher',
            'tiller', 'cultivator', 'yardwork', 'garden', 'toro',
            'honda', 'stihl', 'husqvarna', 'echo', 'egopower',
            'greenworks', 'craftsman', 'lawn', 'yard', 'landscape', 
            'gardening', 'outdoor', 'property', 'maintenance', 
            'commercial', 'residential', 'gas', 'electric', 'powerful', 
            'efficient', 'quiet', 'lightweight', 'maneuverable', 
            'demo', 'tips', 'seasonal', 'spring', 'fall', 'cleanup'
        ]
        
        # Common exclusion keywords for all niches
        self.exclude_keywords = [
            'casino', 'gambling', 'nsfw', 'adult', 'relationship', 'dating',
            'makeup', 'fashion', 'celebrity', 'movie', 'music', 'dance',
            'food', 'cooking', 'recipe', 'travel', 'fitness', 'gaming', 
            'sports', 'art', 'beauty', 'skincare'
        ]
        
        # Normalize all keywords to lowercase
        self.power_tools_keywords = [kw.lower().replace(' ', '') for kw in self.power_tools_keywords]
        self.appliances_keywords = [kw.lower().replace(' ', '') for kw in self.appliances_keywords]
        self.ope_keywords = [kw.lower().replace(' ', '') for kw in self.ope_keywords]
        self.exclude_keywords = [kw.lower() for kw in self.exclude_keywords]
    
    def classify_hashtag(self, hashtag: str) -> str:
        """
        Classify a hashtag into one of the three niches or 'general'
        
        Returns: 'power_tools', 'appliances', 'ope', or 'general'
        """
        clean_tag = hashtag.lower().replace('#', '').replace(' ', '').replace('_', '')
        
        # Check for exclusions first
        for exclude in self.exclude_keywords:
            if exclude in clean_tag:
                return 'general'
        
        # Check each niche (order matters - more specific first)
        if any(keyword in clean_tag for keyword in self.power_tools_keywords):
            return 'power_tools'
        elif any(keyword in clean_tag for keyword in self.appliances_keywords):
            return 'appliances'  
        elif any(keyword in clean_tag for keyword in self.ope_keywords):
            return 'ope'
        
        return 'general'

def analyze_multi_niche_trends():
    print("🔍 Analyzing TikTok trends across Power Tools, Appliances & OPE niches...")
    
    niche_filter = MultiNicheFilter()
    
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
        
        # Classify hashtags by niche
        df['niche'] = df['tag'].apply(niche_filter.classify_hashtag)
        
        print(f"✅ Loaded {len(df)} records from database")
        print(f"📅 Data range: {df['datetime'].min()} to {df['datetime'].max()}")
        
        # Overall statistics
        total_hashtags = len(df)
        unique_hashtags = df['tag'].nunique()
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"Total hashtag mentions: {total_hashtags}")
        print(f"Unique hashtags: {unique_hashtags}")
        
        # Niche breakdown
        niche_counts = df['niche'].value_counts()
        print(f"\n🎯 NICHE BREAKDOWN:")
        for niche, count in niche_counts.items():
            percentage = (count / total_hashtags) * 100
            niche_name = niche.replace('_', ' ').title()
            print(f"{niche_name}: {count} mentions ({percentage:.1f}%)")
        
        # Analyze each niche separately
        analyze_specific_niche(df, 'power_tools', 'Power Tools 🔧')
        analyze_specific_niche(df, 'appliances', 'Appliances 🏠') 
        analyze_specific_niche(df, 'ope', 'OPE (Outdoor Power Equipment) 🌿')
        
        # Create comprehensive visualization
        create_multi_niche_visualization(df, niche_counts)
        
        # Save all results
        save_niche_results(df)
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error analyzing data: {e}")
        import traceback
        traceback.print_exc()

def analyze_specific_niche(df, niche_key, niche_name):
    """Analyze trends for a specific niche"""
    niche_df = df[df['niche'] == niche_key]
    
    if niche_df.empty:
        print(f"\n{niche_name}: No relevant hashtags found")
        return
    
    print(f"\n{niche_name}:")
    print(f"  Total mentions: {len(niche_df)}")
    print(f"  Unique hashtags: {niche_df['tag'].nunique()}")
    
    # Top hashtags for this niche
    top_niche = niche_df['tag'].value_counts().head(10)
    print(f"  Top hashtags:")
    for i, (hashtag, count) in enumerate(top_niche.items(), 1):
        print(f"    {i:2d}. {hashtag}: {count} mentions")
    
    # Recent activity (last 3 days)
    if 'date' in niche_df.columns:
        recent_cutoff = niche_df['date'].max() - timedelta(days=3)
        recent_activity = niche_df[niche_df['date'] > recent_cutoff]
        if not recent_activity.empty:
            print(f"  Recent activity (last 3 days): {len(recent_activity)} mentions")

def create_multi_niche_visualization(df, niche_counts):
    """Create comprehensive visualization for all niches"""
    try:
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        
        # 1. Niche distribution pie chart
        niche_data = niche_counts[niche_counts.index != 'general']  # Exclude general for cleaner view
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D']
        
        if not niche_data.empty:
            axes[0, 0].pie(niche_data.values, labels=niche_data.index, 
                          autopct='%1.1f%%', colors=colors[:len(niche_data)])
            axes[0, 0].set_title('Niche Distribution\n(Excluding General)')
        
        # 2. Top Power Tools hashtags
        power_tools_df = df[df['niche'] == 'power_tools']
        if not power_tools_df.empty:
            top_pt = power_tools_df['tag'].value_counts().head(8)
            axes[0, 1].barh(range(len(top_pt)), top_pt.values, color='#FF6B6B')
            axes[0, 1].set_yticks(range(len(top_pt)))
            axes[0, 1].set_yticklabels(top_pt.index, fontsize=8)
            axes[0, 1].set_title('Top Power Tools Hashtags')
        
        # 3. Top Appliances hashtags  
        appliances_df = df[df['niche'] == 'appliances']
        if not appliances_df.empty:
            top_app = appliances_df['tag'].value_counts().head(8)
            axes[0, 2].barh(range(len(top_app)), top_app.values, color='#4ECDC4')
            axes[0, 2].set_yticks(range(len(top_app)))
            axes[0, 2].set_yticklabels(top_app.index, fontsize=8)
            axes[0, 2].set_title('Top Appliances Hashtags')
        
        # 4. Top OPE hashtags
        ope_df = df[df['niche'] == 'ope']
        if not ope_df.empty:
            top_ope = ope_df['tag'].value_counts().head(8)
            axes[1, 0].barh(range(len(top_ope)), top_ope.values, color='#45B7D1')
            axes[1, 0].set_yticks(range(len(top_ope)))
            axes[1, 0].set_yticklabels(top_ope.index, fontsize=8)
            axes[1, 0].set_title('Top OPE Hashtags')
        
        # 5. Daily activity by niche
        if 'date' in df.columns:
            for i, (niche, color) in enumerate(zip(['power_tools', 'appliances', 'ope'], 
                                                  ['#FF6B6B', '#4ECDC4', '#45B7D1'])):
                niche_daily = df[df['niche'] == niche].groupby('date').size()
                if not niche_daily.empty:
                    axes[1, 1].plot(niche_daily.index, niche_daily.values, 
                                   label=niche.replace('_', ' ').title(), 
                                   marker='o', color=color)
            axes[1, 1].set_title('Daily Activity by Niche')
            axes[1, 1].legend()
            axes[1, 1].tick_params(axis='x', rotation=45)
        
        # 6. Hourly patterns combined
        if 'hour' in df.columns:
            all_niches = ['power_tools', 'appliances', 'ope']
            colors_hour = ['#FF6B6B', '#4ECDC4', '#45B7D1']
            
            for niche, color in zip(all_niches, colors_hour):
                niche_hourly = df[df['niche'] == niche]['hour'].value_counts().sort_index()
                if not niche_hourly.empty:
                    axes[1, 2].plot(niche_hourly.index, niche_hourly.values, 
                                   label=niche.replace('_', ' ').title(), 
                                   marker='s', alpha=0.7, color=color)
            
            axes[1, 2].set_title('Hourly Activity Patterns')
            axes[1, 2].set_xlabel('Hour of Day')
            axes[1, 2].legend()
        
        plt.tight_layout()
        plt.savefig('multi_niche_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        print("📊 Multi-niche visualization saved as 'multi_niche_analysis.png'")
        
    except Exception as e:
        print(f"⚠️ Could not create visualization: {e}")

def save_niche_results(df):
    """Save results for each niche to separate CSV files"""
    try:
        # Save each niche separately
        niches = ['power_tools', 'appliances', 'ope']
        
        for niche in niches:
            niche_df = df[df['niche'] == niche]
            if not niche_df.empty:
                # Get top hashtags for this niche
                top_hashtags = niche_df['tag'].value_counts()
                filename = f"{niche}_hashtags.csv"
                top_hashtags.to_csv(filename)
                print(f"💾 {niche.replace('_', ' ').title()} hashtags saved to '{filename}'")
        
        # Save overall niche classification
        niche_summary = df['niche'].value_counts()
        niche_summary.to_csv('niche_breakdown.csv')
        print("💾 Overall niche breakdown saved to 'niche_breakdown.csv'")
        
        # Save complete dataset with niche classifications
        df[['tag', 'niche', 'datetime']].to_csv('hashtags_with_niches.csv', index=False)
        print("💾 Complete dataset with classifications saved to 'hashtags_with_niches.csv'")
        
    except Exception as e:
        print(f"Error saving results: {e}")

def show_detailed_analysis():
    """Show more detailed analysis"""
    try:
        conn = sqlite3.connect('trends.db')
        df = pd.read_sql_query("SELECT time, tag FROM hashtags", conn)
        
        if df.empty:
            return
            
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df['date'] = df['datetime'].dt.date
        
        # Show trending over time
        print(f"\n📈 OVERALL TRENDING OVER TIME:")
        trending_over_time = df.groupby('date').size()
        for date, count in trending_over_time.tail(7).items():  # Last 7 days
            print(f"  {date}: {count} mentions")
        
        conn.close()
        
    except Exception as e:
        print(f"Detailed analysis error: {e}")

if __name__ == "__main__":
    print("=" * 80)
    print("    MULTI-NICHE TIKTOK TRENDS ANALYSIS")
    print("    Power Tools | Appliances | Outdoor Power Equipment")
    print("=" * 80)
    
    analyze_multi_niche_trends()
    show_detailed_analysis()
    
    print("\n" + "=" * 80)
    print("✅ Multi-niche analysis complete! Generated files:")
    print("   📊 multi_niche_analysis.png - Comprehensive visual dashboard")
    print("   📋 power_tools_hashtags.csv - Power tools specific hashtags")  
    print("   📋 appliances_hashtags.csv - Appliances specific hashtags")
    print("   📋 ope_hashtags.csv - OPE specific hashtags")
    print("   📋 niche_breakdown.csv - Overall niche distribution")
    print("   📋 hashtags_with_niches.csv - Complete dataset with classifications")
    print("=" * 80)
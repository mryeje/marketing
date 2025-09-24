import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib as mpl
import os
import json
from typing import List, Dict, Tuple

# Set a font that supports English characters only to avoid warnings
mpl.rcParams['font.family'] = 'DejaVu Sans'

class MultiNicheFilter:
    def __init__(self):
        """Initialize with comprehensive niche definitions"""
        
        # Power Tools Niche - Expanded with more specific terms
        self.power_tools_keywords = [
            # Brands
            'dewalt', 'milwaukee', 'makita', 'ryobi', 'bosch', 'craftsman', 
            'skil', 'ridgid', 'hilti', 'festool', 'metabo', 'hitachi',
            'ingeroll', 'snapon', 'matco', 'kobalt', 'harborfreight',
            
            # Tool Types
            'drill', 'hammerdrill', 'impactdriver', 'circularsaw', 'tablesaw',
            'mitersaw', 'bandsaw', 'jigsaw', 'reciprocatingsaw', 'oscillatingtool',
            'sander', 'grinder', 'router', 'planer', 'nailer', 'stapler',
            'wrench', 'socket', 'ratchet', 'pliers', 'screwdriver', 'chisel',
            'mallet', 'vise', 'clamp', 'level', 'measuringtape', 'caliper',
            
            # Applications
            'woodworking', 'carpentry', 'metalworking', 'construction', 'renovation',
            'remodeling', 'diy', 'homeimprovement', 'workshop', 'garage',
            'fabrication', 'welding', 'machining', 'cnc', '3dprinting',
            
            # Features
            'cordless', 'brushless', 'lithium', 'batterypowered', 'heavyduty',
            'professional', 'industrial', 'precision', 'ergonomic', 'compact',
            'pneumatic', 'hydraulic', 'electric', 'gaspowered',
            
            # Specific terms
            'toolbox', 'toolchest', 'toolstorage', 'toolorganization', 'toolreview',
            'toolsetup', 'toolcollection', 'toolsofthetrade', 'toolmaintenance'
        ]
        
        # Appliances Niche - More specific terms
        self.appliances_keywords = [
            # Brands
            'whirlpool', 'kitchenaid', 'maytag', 'geappliances', 'samsungappliances',
            'lgappliances', 'boschappliances', 'frigidaire', 'electrolux', 'kenmore',
            'miele', 'subzero', 'wolf', 'cove', 'thermador', 'jennair', 'viking',
            
            # Appliance Types
            'refrigerator', 'fridge', 'freezer', 'icemaker', 'waterdispenser',
            'oven', 'stove', 'cooktop', 'range', 'microwave', 'dishwasher',
            'washer', 'dryer', 'laundry', 'washerdryer', 'venthood', 'hood',
            'disposal', 'garbagedisposal', 'trashcompactor', 'winecooler',
            
            # Small Appliances
            'blender', 'mixer', 'standmixer', 'toaster', 'toasteroven', 'coffeemaker',
            'espressomachine', 'airfryer', 'slowcooker', 'pressurecooker', 'instantpot',
            'foodprocessor', 'juicer', 'vacuum', 'vacuumcleaner', 'robovacuum',
            
            # Features
            'smartappliance', 'wifienabled', 'energyefficient', 'energystar',
            'stainlesssteel', 'fingerprintresistant', 'smartthinq', 'smartthings',
            'wificonnect', 'appcontrol', 'voicecontrol', 'smarthome',
            
            # Services
            'appliancerepair', 'applianceservice', 'appliancereplacement',
            'applianceinstallation', 'applianceparts', 'appliancerepairparts'
        ]
        
        # OPE (Outdoor Power Equipment) Niche - Enhanced
        self.ope_keywords = [
            # Brands
            'stihl', 'husqvarna', 'echo', 'egopower', 'greenworks', 'toro',
            'honda', 'craftsmanope', 'ryobiope', 'dewaltope', 'milwaukeeope',
            'cubcadet', 'johndeere', 'ariens', 'snapper', 'troybilt',
            
            # Equipment Types
            'lawnmower', 'ridingmower', 'zeroturn', 'tractor', 'lawntractor',
            'stringtrimmer', 'weedeater', 'edger', 'leafblower', 'blower',
            'chainsaw', 'hedgetrimmer', 'polesaw', 'snowblower', 'generator',
            'pressurewasher', 'tiller', 'cultivator', 'logsplitter', 'chipper',
            
            # Applications
            'lawncare', 'landscaping', 'yardwork', 'gardening', 'outdoor',
            'propertymaintenance', 'groundskeeping', 'treecare', 'arborist',
            'snowremoval', 'pressurewashing', 'powerwashing',
            
            # Features
            'gaspowered', 'electricope', 'batterypowered', 'cordlessope',
            'commercialgrade', 'residential', 'professionalgrade', 'heavydutyope'
        ]
        
        # Common exclusion patterns
        self.exclude_patterns = [
            # Entertainment
            'movie', 'music', 'dance', 'celebrity', 'actor', 'singer', 'artist',
            'gaming', 'videogame', 'streamer', 'gamer', 'esports',
            
            # Lifestyle
            'fashion', 'beauty', 'makeup', 'skincare', 'hair', 'outfit', 'style',
            'fitness', 'gym', 'workout', 'yoga', 'nutrition', 'diet',
            'travel', 'vacation', 'hotel', 'restaurant', 'food', 'recipe', 'cooking',
            
            # Relationships
            'dating', 'relationship', 'love', 'couple', 'marriage', 'family',
            
            # Inappropriate
            'nsfw', 'adult', 'dating', 'casino', 'gambling', 'betting',
            
            # Generic viral tags
            'fyp', 'foryou', 'foryoupage', 'viral', 'trending', 'popular',
            
            # Generic emotions
            'happy', 'sad', 'funny', 'comedy', 'lol', 'laugh'
        ]
        
        # Normalize all keywords to lowercase and remove spaces
        self.power_tools_keywords = [kw.lower().replace(' ', '') for kw in self.power_tools_keywords]
        self.appliances_keywords = [kw.lower().replace(' ', '') for kw in self.appliances_keywords]
        self.ope_keywords = [kw.lower().replace(' ', '') for kw in self.ope_keywords]
        self.exclude_patterns = [kw.lower() for kw in self.exclude_patterns]
        
        # Additional validation: minimum length requirement
        self.min_hashtag_length = 3
    
    def classify_hashtag(self, hashtag: str) -> str:
        """Classify a hashtag into one of the three niches or 'general'"""
        # Clean and prepare the hashtag
        clean_tag = hashtag.lower().replace('#', '').replace(' ', '').replace('_', '').replace('-', '')
        
        # Basic validation
        if len(clean_tag) < self.min_hashtag_length:
            return 'general'
        
        # Check for exclusion patterns first
        for exclude in self.exclude_patterns:
            if exclude in clean_tag:
                return 'general'
        
        # Check for exact matches first (more specific)
        if clean_tag in self.power_tools_keywords:
            return 'power_tools'
        if clean_tag in self.appliances_keywords:
            return 'appliances'
        if clean_tag in self.ope_keywords:
            return 'ope'
        
        # Then check for partial matches
        power_tools_match = any(keyword in clean_tag for keyword in self.power_tools_keywords)
        appliances_match = any(keyword in clean_tag for keyword in self.appliances_keywords)
        ope_match = any(keyword in clean_tag for keyword in self.ope_keywords)
        
        # Prioritize the strongest match
        matches = []
        if power_tools_match:
            matches.append(('power_tools', self._match_quality(clean_tag, self.power_tools_keywords)))
        if appliances_match:
            matches.append(('appliances', self._match_quality(clean_tag, self.appliances_keywords)))
        if ope_match:
            matches.append(('ope', self._match_quality(clean_tag, self.ope_keywords)))
        
        if matches:
            # Return the best match based on quality score
            matches.sort(key=lambda x: x[1], reverse=True)
            return matches[0][0]
        
        return 'general'
    
    def _match_quality(self, hashtag: str, keyword_list: list) -> float:
        """Calculate match quality score (0-1) based on exact or partial matches"""
        best_score = 0.0
        
        for keyword in keyword_list:
            if hashtag == keyword:
                return 1.0  # Exact match
            elif keyword in hashtag:
                # Longer keywords get higher scores
                score = 0.8 + (len(keyword) / len(hashtag)) * 0.2
                best_score = max(best_score, score)
        
        return best_score

class TikTokDashboard:
    def __init__(self, db_path='hashtags.db'):
        self.db_path = db_path
        self.niche_filter = MultiNicheFilter()
        
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database '{self.db_path}' not found. Please run data collection first.")
        
        self.conn = sqlite3.connect(self.db_path)
        self.df = self.load_data()
    
    def load_data(self):
        """Load and process data from the database"""
        try:
            # Use the correct column name - 'hashtag' instead of 'tag'
            query = "SELECT collected_at as time, hashtag as tag FROM hashtags ORDER BY collected_at DESC"
            df = pd.read_sql_query(query, self.conn)
            
            if df.empty:
                print("No data found in the database!")
                return pd.DataFrame()
            
            print(f"Loaded {len(df)} raw records from database")
            print(f"Sample timestamps: {df['time'].head(3).tolist()}")
            
            # Try multiple datetime parsing approaches
            df['datetime'] = None
            
            # First try: standard ISO format with UTC
            try:
                df['datetime'] = pd.to_datetime(df['time'], utc=True, errors='coerce')
                parsed_count = df['datetime'].notna().sum()
                print(f"ISO8601 UTC parsing: {parsed_count} successful")
            except:
                pass
            
            # Second try: mixed format
            if df['datetime'].isna().all():
                try:
                    df['datetime'] = pd.to_datetime(df['time'], errors='coerce', infer_datetime_format=True)
                    parsed_count = df['datetime'].notna().sum()
                    print(f"Mixed format parsing: {parsed_count} successful")
                except:
                    pass
            
            # Third try: common timestamp formats
            if df['datetime'].isna().all():
                formats_to_try = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S.%f',
                    '%Y-%m-%dT%H:%M:%SZ',
                    '%Y-%m-%dT%H:%M:%S.%fZ'
                ]
                
                for fmt in formats_to_try:
                    try:
                        df['datetime'] = pd.to_datetime(df['time'], format=fmt, errors='coerce')
                        parsed_count = df['datetime'].notna().sum()
                        if parsed_count > 0:
                            print(f"Format '{fmt}' parsing: {parsed_count} successful")
                            break
                    except:
                        continue
            
            # Drop rows where datetime parsing failed
            original_len = len(df)
            df = df.dropna(subset=['datetime'])
            
            if df.empty:
                print("No valid datetime data found after parsing!")
                print("Unable to create time-based analysis, but will proceed with hashtag analysis only")
                # Return basic dataframe without time columns for hashtag analysis
                df_basic = pd.read_sql_query(query, self.conn)
                df_basic['niche'] = df_basic['tag'].apply(self.niche_filter.classify_hashtag)
                return df_basic
            
            print(f"Successfully parsed {len(df)} of {original_len} datetime records")
            
            # Add time-based columns only if we have valid datetime data
            if 'datetime' in df.columns and df['datetime'].notna().any():
                df['date'] = df['datetime'].dt.date
                df['hour'] = df['datetime'].dt.hour
                df['day_of_week'] = df['datetime'].dt.day_name()
                print(f"Data range: {df['datetime'].min()} to {df['datetime'].max()}")
            
            # Classify hashtags by niche
            df['niche'] = df['tag'].apply(self.niche_filter.classify_hashtag)
            
            print(f"Final dataset: {len(df)} records ready for analysis")
            return df
            
        except Exception as e:
            print(f"Error loading data: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()
    
    def generate_visualizations(self):
        """Generate all visualization charts"""
        if self.df.empty:
            print("No data available for visualizations")
            return
        
        # Create output directory
        os.makedirs('dashboard_assets', exist_ok=True)
        
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D', '#5C7AEA', '#FF9A76']
        
        # 1. Multi-niche overview
        fig, axes = plt.subplots(2, 3, figsize=(18, 12))
        fig.suptitle('TikTok Multi-Niche Analysis Dashboard', fontsize=20, fontweight='bold')
        
        # Niche distribution pie chart
        niche_counts = self.df['niche'].value_counts()
        niche_data = niche_counts[niche_counts.index != 'general']  # Exclude general for cleaner view
        
        if not niche_data.empty:
            axes[0, 0].pie(niche_data.values, labels=[n.replace('_', ' ').title() for n in niche_data.index], 
                          autopct='%1.1f%%', colors=colors[:len(niche_data)])
            axes[0, 0].set_title('Niche Distribution\n(Excluding General)')
        
        # Top hashtags by niche
        niches = ['power_tools', 'appliances', 'ope']
        niche_titles = ['Power Tools', 'Appliances', 'OPE']
        positions = [(0, 1), (0, 2), (1, 0)]
        
        for i, (niche, title, pos) in enumerate(zip(niches, niche_titles, positions)):
            niche_df = self.df[self.df['niche'] == niche]
            if not niche_df.empty:
                top_hashtags = niche_df['tag'].value_counts().head(8)
                axes[pos].barh(range(len(top_hashtags)), top_hashtags.values, color=colors[i])
                axes[pos].set_yticks(range(len(top_hashtags)))
                axes[pos].set_yticklabels(top_hashtags.index, fontsize=8)
                axes[pos].set_title(f'Top {title} Hashtags')
        
        # Daily activity by niche
        if 'date' in self.df.columns:
            for i, (niche, color) in enumerate(zip(niches, colors[:3])):
                niche_daily = self.df[self.df['niche'] == niche].groupby('date').size()
                if not niche_daily.empty:
                    axes[1, 1].plot(niche_daily.index, niche_daily.values, 
                                   label=niche.replace('_', ' ').title(), 
                                   marker='o', color=color)
            axes[1, 1].set_title('Daily Activity by Niche')
            axes[1, 1].legend()
            axes[1, 1].tick_params(axis='x', rotation=45)
        
        # Hourly patterns combined
        if 'hour' in self.df.columns:
            for niche, color in zip(niches, colors[:3]):
                niche_hourly = self.df[self.df['niche'] == niche]['hour'].value_counts().sort_index()
                if not niche_hourly.empty:
                    axes[1, 2].plot(niche_hourly.index, niche_hourly.values, 
                                   label=niche.replace('_', ' ').title(), 
                                   marker='s', alpha=0.7, color=color)
            
            axes[1, 2].set_title('Hourly Activity Patterns')
            axes[1, 2].set_xlabel('Hour of Day')
            axes[1, 2].legend()
        
        plt.tight_layout()
        plt.savefig('dashboard_assets/multi_niche_analysis.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        # 2. Top hashtags overall
        plt.figure(figsize=(12, 8))
        top_10 = self.df['tag'].value_counts().head(10)
        plt.barh(range(len(top_10)), top_10.values, color=colors[:len(top_10)])
        plt.yticks(range(len(top_10)), top_10.index)
        plt.title('Top 10 Trending Hashtags Overall', fontweight='bold', fontsize=16)
        plt.xlabel('Mentions')
        plt.tight_layout()
        plt.savefig('dashboard_assets/top_hashtags.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        # 3. Daily trends
        if 'date' in self.df.columns and len(self.df['date'].unique()) > 1:
            plt.figure(figsize=(12, 6))
            daily = self.df['date'].value_counts().sort_index()
            plt.plot(daily.index, daily.values, marker='o', linewidth=2, color=colors[0])
            plt.title('Daily Hashtag Activity', fontweight='bold', fontsize=16)
            plt.xlabel('Date')
            plt.ylabel('Total Mentions')
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig('dashboard_assets/daily_activity.png', dpi=150, bbox_inches='tight')
            plt.close()
        
        print("Visualizations generated successfully!")
    
    def create_html_dashboard(self):
        """Create a comprehensive HTML dashboard"""
        
        # Generate visualizations first
        self.generate_visualizations()
        
        # Calculate statistics
        total_mentions = len(self.df)
        unique_hashtags = self.df['tag'].nunique()
        top_hashtag = self.df['tag'].value_counts().index[0] if not self.df.empty else "N/A"
        top_count = self.df['tag'].value_counts().iloc[0] if not self.df.empty else 0
        
        # Get niche breakdown
        niche_counts = self.df['niche'].value_counts()
        
        # Get top hashtags for each niche
        niches_data = {}
        for niche in ['power_tools', 'appliances', 'ope']:
            niche_df = self.df[self.df['niche'] == niche]
            if not niche_df.empty:
                niches_data[niche] = niche_df['tag'].value_counts().head(10).to_dict()
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TikTok Multi-Niche Dashboard</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    color: #333;
                }}
                
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .header {{
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    text-align: center;
                    margin-bottom: 30px;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                }}
                
                .header h1 {{
                    color: #2c3e50;
                    font-size: 3em;
                    margin-bottom: 10px;
                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                }}
                
                .header p {{
                    color: #7f8c8d;
                    font-size: 1.2em;
                    margin-bottom: 20px;
                }}
                
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .stat-card {{
                    background: white;
                    border-radius: 15px;
                    padding: 30px;
                    text-align: center;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease;
                }}
                
                .stat-card:hover {{
                    transform: translateY(-5px);
                }}
                
                .stat-number {{
                    font-size: 3em;
                    font-weight: bold;
                    color: #FF6B6B;
                    display: block;
                    margin-bottom: 10px;
                }}
                
                .stat-label {{
                    color: #7f8c8d;
                    font-size: 1.1em;
                    font-weight: 600;
                }}
                
                .charts-section {{
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    margin-bottom: 30px;
                    box-shadow: 0 15px 35px rgba(0,0,0,0.1);
                }}
                
                .chart-container {{
                    margin-bottom: 40px;
                }}
                
                .chart-container img {{
                    width: 100%;
                    height: auto;
                    border-radius: 10px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                }}
                
                .niche-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
                    gap: 25px;
                    margin-bottom: 30px;
                }}
                
                .niche-card {{
                    background: white;
                    border-radius: 15px;
                    padding: 30px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease;
                }}
                
                .niche-card:hover {{
                    transform: translateY(-5px);
                }}
                
                .power-tools {{ border-left: 5px solid #FF6B6B; }}
                .appliances {{ border-left: 5px solid #4ECDC4; }}
                .ope {{ border-left: 5px solid #45B7D1; }}
                
                .niche-card h2 {{
                    color: #2c3e50;
                    margin-bottom: 20px;
                    font-size: 1.5em;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #ecf0f1;
                }}
                
                .hashtag-list {{
                    list-style: none;
                }}
                
                .hashtag-item {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 0;
                    border-bottom: 1px solid #f8f9fa;
                }}
                
                .hashtag-item:last-child {{
                    border-bottom: none;
                }}
                
                .hashtag {{
                    font-weight: 600;
                    color: #2980b9;
                    font-size: 1.1em;
                }}
                
                .count {{
                    background: linear-gradient(45deg, #FF6B6B, #4ECDC4);
                    color: white;
                    padding: 6px 15px;
                    border-radius: 20px;
                    font-weight: bold;
                    font-size: 0.9em;
                }}
                
                .footer {{
                    text-align: center;
                    color: white;
                    margin-top: 40px;
                    padding: 20px;
                    opacity: 0.9;
                }}
                
                .section-title {{
                    color: #2c3e50;
                    font-size: 2em;
                    margin-bottom: 30px;
                    text-align: center;
                }}
                
                @media (max-width: 768px) {{
                    .header h1 {{
                        font-size: 2em;
                    }}
                    
                    .niche-grid {{
                        grid-template-columns: 1fr;
                    }}
                    
                    .stats-grid {{
                        grid-template-columns: repeat(2, 1fr);
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>TikTok Multi-Niche Dashboard</h1>
                    <p>Power Tools | Appliances | Outdoor Power Equipment</p>
                    <p>Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <span class="stat-number">{total_mentions:,}</span>
                        <div class="stat-label">Total Mentions</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{unique_hashtags:,}</span>
                        <div class="stat-label">Unique Hashtags</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{niche_counts.get('power_tools', 0):,}</span>
                        <div class="stat-label">Power Tools</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{niche_counts.get('appliances', 0):,}</span>
                        <div class="stat-label">Appliances</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{niche_counts.get('ope', 0):,}</span>
                        <div class="stat-label">OPE</div>
                    </div>
                    <div class="stat-card">
                        <span class="stat-number">{top_count:,}</span>
                        <div class="stat-label">Top: #{top_hashtag}</div>
                    </div>
                </div>
                
                <div class="charts-section">
                    <h2 class="section-title">Visual Analytics</h2>
                    
                    <div class="chart-container">
                        <img src="dashboard_assets/multi_niche_analysis.png" alt="Multi-Niche Analysis">
                    </div>
                    
                    <div class="chart-container">
                        <img src="dashboard_assets/top_hashtags.png" alt="Top Hashtags">
                    </div>
                    
                    <div class="chart-container">
                        <img src="dashboard_assets/daily_activity.png" alt="Daily Activity">
                    </div>
                </div>
                
                <div class="niche-grid">
        """
        
        # Add niche-specific sections
        niche_configs = {
            'power_tools': ('Power Tools', 'power-tools'),
            'appliances': ('Appliances', 'appliances'), 
            'ope': ('Outdoor Power Equipment', 'ope')
        }
        
        for niche_key, (title, css_class) in niche_configs.items():
            if niche_key in niches_data:
                html_content += f"""
                    <div class="niche-card {css_class}">
                        <h2>{title}</h2>
                        <ul class="hashtag-list">
                """
                
                for hashtag, count in list(niches_data[niche_key].items())[:10]:
                    html_content += f"""
                        <li class="hashtag-item">
                            <span class="hashtag">#{hashtag}</span>
                            <span class="count">{count}</span>
                        </li>
                    """
                
                html_content += """
                        </ul>
                    </div>
                """
        
        html_content += """
                </div>
                
                <div class="footer">
                    <p>Use this data to plan your TikTok content strategy and identify trending hashtags in your niches</p>
                    <p>Dashboard combines analysis of Power Tools, Appliances, and Outdoor Power Equipment trends</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Save the HTML dashboard
        try:
            with open('tiktok_dashboard.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print("Dashboard generated successfully!")
            print("Open 'tiktok_dashboard.html' in your web browser to view the complete dashboard")
            
        except Exception as e:
            print(f"Error saving dashboard: {e}")
    
    def run_complete_analysis(self):
        """Run the complete analysis and generate the dashboard"""
        print("=" * 80)
        print("    COMPREHENSIVE TIKTOK MULTI-NICHE ANALYSIS")
        print("    Power Tools | Appliances | Outdoor Power Equipment")
        print("=" * 80)
        
        if self.df.empty:
            print("No data available for analysis!")
            return
        
        # Print summary statistics
        total_hashtags = len(self.df)
        unique_hashtags = self.df['tag'].nunique()
        
        print(f"\nOVERALL STATISTICS:")
        print(f"Total hashtag mentions: {total_hashtags:,}")
        print(f"Unique hashtags: {unique_hashtags:,}")
        
        # Niche breakdown
        niche_counts = self.df['niche'].value_counts()
        print(f"\nNICHE BREAKDOWN:")
        for niche, count in niche_counts.items():
            percentage = (count / total_hashtags) * 100
            niche_name = niche.replace('_', ' ').title()
            print(f"{niche_name}: {count:,} mentions ({percentage:.1f}%)")
        
        # Top hashtags in each niche
        print(f"\nTOP HASHTAGS BY NICHE:")
        for niche in ['power_tools', 'appliances', 'ope']:
            niche_df = self.df[self.df['niche'] == niche]
            if not niche_df.empty:
                top_hashtags = niche_df['tag'].value_counts().head(5)
                print(f"\n{niche.replace('_', ' ').title()}:")
                for i, (hashtag, count) in enumerate(top_hashtags.items(), 1):
                    print(f"   {i}. #{hashtag}: {count:,} mentions")
        
        # Generate the HTML dashboard
        self.create_html_dashboard()
        
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE!")
        print("Generated files:")
        print("   📊 tiktok_dashboard.html - Interactive web dashboard")
        print("   📁 dashboard_assets/ - Visualization charts")
        print("=" * 80)
        print("Open 'tiktok_dashboard.html' in your web browser to view the complete dashboard!")

def main():
    """Main function to run the analysis"""
    try:
        dashboard = TikTokDashboard()
        dashboard.run_complete_analysis()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Make sure you have run the data collection script first to create the hashtags.db database.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

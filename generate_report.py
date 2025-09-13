import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os

# Set style for better looking charts
plt.style.use('default')

class TikTokReporter:
    def __init__(self):
        self.conn = sqlite3.connect('trends.db')
        self.df = self.load_data()
        self.report_date = datetime.now().strftime('%Y-%m-%d')
        
    def load_data(self):
        """Load data from SQLite database"""
        query = "SELECT time, tag FROM hashtags ORDER BY time DESC"
        df = pd.read_sql_query(query, self.conn)
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['time'], unit='s')
            df['date'] = df['datetime'].dt.date
            df['day_of_week'] = df['datetime'].dt.day_name()
            df['hour'] = df['datetime'].dt.hour
        return df
    
    def generate_daily_report(self):
        """Generate comprehensive daily report"""
        if self.df.empty:
            print("❌ No data available for reporting")
            return
        
        print("📊 Generating Daily TikTok Trends Report...")
        
        # Create report directory
        os.makedirs('reports', exist_ok=True)
        
        # Generate all report components
        self.generate_summary()
        self.generate_trending_hashtags()
        self.generate_time_analysis()
        self.generate_weekly_trends()
        self.generate_visualizations()
        
        # Create HTML report
        self.create_html_report()
        
        print("✅ Daily report generated successfully!")
        print(f"📁 Reports saved in 'reports/' directory")
    
    def generate_summary(self):
        """Generate summary statistics"""
        summary = {
            'total_mentions': len(self.df),
            'unique_hashtags': self.df['tag'].nunique(),
            'data_start_date': self.df['datetime'].min(),
            'data_end_date': self.df['datetime'].max(),
            'avg_daily_mentions': len(self.df) / self.df['date'].nunique() if not self.df.empty else 0
        }
        
        # Save summary to file
        with open('reports/summary.txt', 'w', encoding='utf-8') as f:
            f.write("TIKTOK TRENDS SUMMARY REPORT\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Report Date: {self.report_date}\n")
            f.write(f"Total Hashtag Mentions: {summary['total_mentions']:,}\n")
            f.write(f"Unique Hashtags: {summary['unique_hashtags']:,}\n")
            f.write(f"Data Collection Period: {summary['data_start_date']} to {summary['data_end_date']}\n")
            f.write(f"Average Daily Mentions: {summary['avg_daily_mentions']:.1f}\n")
        
        return summary
    
    def generate_trending_hashtags(self):
        """Generate trending hashtags analysis"""
        # Top 20 hashtags
        top_hashtags = self.df['tag'].value_counts().head(20)
        top_hashtags.to_csv('reports/top_hashtags.csv')
        
        # Trending today (last 24 hours)
        yesterday = datetime.now() - timedelta(hours=24)
        recent_hashtags = self.df[self.df['datetime'] > yesterday]['tag'].value_counts().head(10)
        recent_hashtags.to_csv('reports/recent_trends.csv')
        
        # Emerging trends (hashtags that appeared recently)
        emerging = self.df[self.df['datetime'] > datetime.now() - timedelta(days=3)]
        emerging_trends = emerging['tag'].value_counts().head(15)
        emerging_trends.to_csv('reports/emerging_trends.csv')
        
        if not self.df.empty:
            top_hashtag = self.df['tag'].value_counts().index[0]
            top_count = self.df['tag'].value_counts().iloc[0]
            print(f"📊 Top hashtag: {top_hashtag} ({top_count} mentions)")
        else:
            print("📊 No hashtags found in database")
    
    def generate_time_analysis(self):
        """Analyze temporal patterns"""
        # Daily activity
        daily_activity = self.df['date'].value_counts().sort_index()
        daily_activity.to_csv('reports/daily_activity.csv')
        
        # Hourly patterns
        hourly_activity = self.df['hour'].value_counts().sort_index()
        hourly_activity.to_csv('reports/hourly_activity.csv')
        
        # Day of week patterns
        dow_activity = self.df['day_of_week'].value_counts()
        dow_activity.to_csv('reports/day_of_week_activity.csv')
    
    def generate_weekly_trends(self):
        """Generate weekly trends comparison"""
        if len(self.df) < 14:  # Need at least 2 weeks of data
            return
            
        # Compare this week vs last week
        one_week_ago = datetime.now() - timedelta(days=7)
        two_weeks_ago = datetime.now() - timedelta(days=14)
        
        this_week = self.df[self.df['datetime'] > one_week_ago]
        last_week = self.df[(self.df['datetime'] > two_weeks_ago) & (self.df['datetime'] <= one_week_ago)]
        
        if not this_week.empty and not last_week.empty:
            this_week_trends = this_week['tag'].value_counts().head(10)
            last_week_trends = last_week['tag'].value_counts().head(10)
            
            weekly_comparison = pd.DataFrame({
                'This Week': this_week_trends,
                'Last Week': last_week_trends.reindex(this_week_trends.index, fill_value=0)
            }).fillna(0)
            
            weekly_comparison.to_csv('reports/weekly_comparison.csv')
    
    def generate_visualizations(self):
        """Generate visual charts without seaborn"""
        if self.df.empty:
            print("❌ No data available for visualizations")
            return
            
        # Create a color palette manually
        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D', '#5C7AEA', '#FF9A76', '#6A0572', '#AB83A1']
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # Top hashtags chart
        top_10 = self.df['tag'].value_counts().head(10)
        axes[0, 0].barh(range(len(top_10)), top_10.values, color=colors[:len(top_10)])
        axes[0, 0].set_yticks(range(len(top_10)))
        axes[0, 0].set_yticklabels(top_10.index)
        axes[0, 0].set_title('Top 10 Trending Hashtags', fontweight='bold')
        axes[0, 0].set_xlabel('Mentions')
        
        # Daily activity
        daily = self.df['date'].value_counts().sort_index()
        axes[0, 1].plot(daily.index, daily.values, marker='o', linewidth=2, color=colors[0])
        axes[0, 1].set_title('Daily Hashtag Mentions', fontweight='bold')
        axes[0, 1].set_xlabel('Date')
        axes[0, 1].set_ylabel('Mentions')
        axes[0, 1].tick_params(axis='x', rotation=45)
        
        # Hourly distribution
        hourly = self.df['hour'].value_counts().sort_index()
        axes[1, 0].bar(hourly.index, hourly.values, alpha=0.7, color=colors[1])
        axes[1, 0].set_title('Hourly Distribution of Mentions', fontweight='bold')
        axes[1, 0].set_xlabel('Hour of Day')
        axes[1, 0].set_ylabel('Mentions')
        axes[1, 0].set_xticks(range(0, 24, 2))
        
        # Day of week activity
        dow = self.df['day_of_week'].value_counts()
        axes[1, 1].bar(range(len(dow)), dow.values, color=colors[2:2+len(dow)])
        axes[1, 1].set_title('Activity by Day of Week', fontweight='bold')
        axes[1, 1].set_xlabel('Day of Week')
        axes[1, 1].set_ylabel('Mentions')
        axes[1, 1].set_xticks(range(len(dow)))
        axes[1, 1].set_xticklabels(dow.index, rotation=45)
        
        plt.tight_layout()
        plt.savefig('reports/trends_dashboard.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # Additional: Top hashtags growth chart
        plt.figure(figsize=(10, 6))
        color_cycle = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D', '#5C7AEA']
        
        for i, hashtag in enumerate(self.df['tag'].value_counts().head(5).index):
            hashtag_data = self.df[self.df['tag'] == hashtag]
            daily_count = hashtag_data.groupby('date').size()
            plt.plot(daily_count.index, daily_count.values, marker='o', 
                    label=hashtag, linewidth=2, color=color_cycle[i % len(color_cycle)])
        
        plt.title('Top 5 Hashtags Daily Trend', fontweight='bold')
        plt.xlabel('Date')
        plt.ylabel('Daily Mentions')
        plt.legend()
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig('reports/top_hashtags_trend.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("📈 Visualizations created successfully!")
    
    def create_html_report(self):
        """Create HTML version of the report with UTF-8 encoding"""
        # Get some stats for the HTML report
        total_mentions = len(self.df)
        unique_hashtags = self.df['tag'].nunique()
        top_hashtag = self.df['tag'].value_counts().index[0] if not self.df.empty else "N/A"
        top_count = self.df['tag'].value_counts().iloc[0] if not self.df.empty else 0
        
        # Replace emojis with HTML entities to avoid encoding issues
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>TikTok Trends Report - {self.report_date}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #ff0055, #ff6b6b); color: white; padding: 30px; border-radius: 10px; text-align: center; margin-bottom: 30px; }}
                .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 30px; }}
                .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 10px; text-align: center; border-left: 4px solid #ff0055; }}
                .stat-number {{ font-size: 2em; font-weight: bold; color: #ff0055; }}
                .section {{ margin: 30px 0; padding: 20px; border: 1px solid #e9ecef; border-radius: 10px; }}
                img {{ max-width: 100%; height: auto; border-radius: 10px; box-shadow: 0 3px 10px rgba(0,0,0,0.1); }}
                ul {{ line-height: 1.8; }}
                li {{ margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>&#128202; TikTok Trends Report</h1>
                    <p>Generated on: {self.report_date}</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{total_mentions:,}</div>
                        <h3>Total Mentions</h3>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{unique_hashtags:,}</div>
                        <h3>Unique Hashtags</h3>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{top_count}</div>
                        <h3>Top Hashtag: {top_hashtag}</h3>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{self.df['date'].nunique() if not self.df.empty else 0}</div>
                        <h3>Days of Data</h3>
                    </div>
                </div>
                
                <div class="section">
                    <h2>&#128247; Trending Dashboard</h2>
                    <img src="trends_dashboard.png" alt="Trends Dashboard">
                </div>
                
                <div class="section">
                    <h2>&#128293; Top Hashtags Trend</h2>
                    <img src="top_hashtags_trend.png" alt="Top Hashtags Trend">
                </div>
                
                <div class="section">
                    <h2>&#128203; Generated Report Files</h2>
                    <ul>
                        <li><strong>trends_dashboard.png</strong> - Comprehensive visual dashboard</li>
                        <li><strong>top_hashtags_trend.png</strong> - Top hashtags growth chart</li>
                        <li><strong>top_hashtags.csv</strong> - Top 20 trending hashtags</li>
                        <li><strong>recent_trends.csv</strong> - Trends from last 24 hours</li>
                        <li><strong>emerging_trends.csv</strong> - New trending hashtags</li>
                        <li><strong>daily_activity.csv</strong> - Daily mention counts</li>
                        <li><strong>hourly_activity.csv</strong> - Hourly distribution</li>
                        <li><strong>weekly_comparison.csv</strong> - Week-over-week comparison</li>
                        <li><strong>summary.txt</strong> - Executive summary report</li>
                    </ul>
                </div>
                
                <div class="section">
                    <h2>&#128161; How to Use This Data</h2>
                    <ul>
                        <li>Schedule content around top trending hashtags</li>
                        <li>Post during peak activity hours shown in hourly analysis</li>
                        <li>Monitor emerging trends for early adoption opportunities</li>
                        <li>Compare weekly performance to track growth</li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Write with UTF-8 encoding
        with open('reports/daily_report.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print("🌐 HTML report created!")
    
    def close(self):
        """Close database connection"""
        self.conn.close()

def main():
    print("🎬 Starting TikTok Automated Reporting...")
    print("=" * 60)
    
    reporter = TikTokReporter()
    
    try:
        # Generate complete report
        reporter.generate_daily_report()
        
    except Exception as e:
        print(f"❌ Error generating report: {e}")
        import traceback
        traceback.print_exc()
    finally:
        reporter.close()
    
    print("=" * 60)
    print("✅ Automated reporting completed!")
    print("📁 Check the 'reports/' directory for all generated files")
    print("🌐 Open 'reports/daily_report.html' in your browser to view the full report!")

if __name__ == "__main__":
    main()
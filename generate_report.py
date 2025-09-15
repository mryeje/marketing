import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
import os

# Set style for better looking charts
plt.style.use('default')

class TikTokReporter:
    def __init__(self):
        self.db_path = 'hashtags.db'  # Updated DB name

        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database '{self.db_path}' not found. Please run data collection first.")

        self.conn = sqlite3.connect(self.db_path)
        self.df = self.load_data()
        self.report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    def load_data(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"Available tables in database: {[table[0] for table in tables]}")

            query = "SELECT collected_at as time, hashtag as tag FROM hashtags ORDER BY collected_at DESC"
            df = pd.read_sql_query(query, self.conn)
            print("Successfully loaded data from database.")

            # Convert all timestamps to UTC
            df['datetime'] = pd.to_datetime(df['time'], utc=True, errors='coerce')
            df.dropna(subset=['datetime'], inplace=True)
            if not df.empty:
                df['date'] = df['datetime'].dt.date
                df['day_of_week'] = df['datetime'].dt.day_name()
                df['hour'] = df['datetime'].dt.hour

            return df
        except Exception as e:
            print(f"Error loading data: {e}")
            return pd.DataFrame()

    def generate_daily_report(self):
        if self.df.empty:
            print("No data available for reporting.")
            return

        print("Generating Daily TikTok Trends Report...")
        os.makedirs('reports', exist_ok=True)

        self.generate_summary()
        self.generate_trending_hashtags()
        self.generate_time_analysis()
        self.generate_weekly_trends()
        self.generate_visualizations()
        self.create_html_report()

        print("Daily report generated successfully! Reports saved in 'reports/' directory")

    def generate_summary(self):
        summary = {
            'total_mentions': len(self.df),
            'unique_hashtags': self.df['tag'].nunique(),
            'data_start_date': self.df['datetime'].min(),
            'data_end_date': self.df['datetime'].max(),
            'avg_daily_mentions': len(self.df) / self.df['date'].nunique()
        }

        with open('reports/summary.txt', 'w', encoding='utf-8') as f:
            f.write("TIKTOK TRENDS SUMMARY REPORT\n")
            f.write("="*50 + "\n\n")
            f.write(f"Report Date: {self.report_date}\n")
            f.write(f"Total Hashtag Mentions: {summary['total_mentions']:,}\n")
            f.write(f"Unique Hashtags: {summary['unique_hashtags']:,}\n")
            f.write(f"Data Collection Period: {summary['data_start_date']} to {summary['data_end_date']}\n")
            f.write(f"Average Daily Mentions: {summary['avg_daily_mentions']:.1f}\n")
        
        return summary

    def generate_trending_hashtags(self):
        top_hashtags = self.df['tag'].value_counts().head(20)
        top_hashtags.to_csv('reports/top_hashtags.csv')

        if 'datetime' in self.df.columns:
            yesterday = pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=1))
            recent_hashtags = self.df[self.df['datetime'] > yesterday]['tag'].value_counts().head(10)
            recent_hashtags.to_csv('reports/recent_trends.csv')

            emerging = self.df[self.df['datetime'] > pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=3))]
            emerging_trends = emerging['tag'].value_counts().head(15)
            emerging_trends.to_csv('reports/emerging_trends.csv')
        else:
            top_hashtags.head(10).to_csv('reports/recent_trends.csv')
            top_hashtags.head(15).to_csv('reports/emerging_trends.csv')

        if not self.df.empty:
            top_hashtag = self.df['tag'].value_counts().index[0]
            top_count = self.df['tag'].value_counts().iloc[0]
            print(f"Top hashtag: {top_hashtag} ({top_count} mentions)")
        else:
            print("No hashtags found in database")

    def generate_time_analysis(self):
        if 'date' in self.df.columns:
            daily_activity = self.df['date'].value_counts().sort_index()
            daily_activity.to_csv('reports/daily_activity.csv')
        if 'hour' in self.df.columns:
            hourly_activity = self.df['hour'].value_counts().sort_index()
            hourly_activity.to_csv('reports/hourly_activity.csv')
        if 'day_of_week' in self.df.columns:
            dow_activity = self.df['day_of_week'].value_counts()
            dow_activity.to_csv('reports/day_of_week_activity.csv')

    def generate_weekly_trends(self):
        if 'datetime' not in self.df.columns or len(self.df) < 14:
            return

        one_week_ago = pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=7))
        two_weeks_ago = pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=14))

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
        if self.df.empty:
            print("No data available for visualizations")
            return

        colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D', '#5C7AEA', '#FF9A76', '#6A0572', '#AB83A1']

        plot_count = 0
        plots = []

        if len(self.df['tag'].value_counts()) > 0:
            plots.append('top_hashtags')
            plot_count += 1
        if 'date' in self.df.columns and len(self.df['date'].value_counts()) > 1:
            plots.append('daily_activity')
            plot_count += 1
        if 'hour' in self.df.columns:
            plots.append('hourly_activity')
            plot_count += 1
        if 'day_of_week' in self.df.columns:
            plots.append('day_of_week')
            plot_count += 1

        if plot_count == 0:
            print("No sufficient data for visualizations")
            return

        if plot_count == 1:
            fig, axes = plt.subplots(1, 1, figsize=(10, 6))
            axes = [axes]
        elif plot_count == 2:
            fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        else:
            fig, axes = plt.subplots(2, 2, figsize=(15, 12))
            axes = axes.flatten()

        plot_idx = 0

        if 'top_hashtags' in plots:
            top_10 = self.df['tag'].value_counts().head(10)
            axes[plot_idx].barh(range(len(top_10)), top_10.values, color=colors[:len(top_10)])
            axes[plot_idx].set_yticks(range(len(top_10)))
            axes[plot_idx].set_yticklabels(top_10.index)
            axes[plot_idx].set_title('Top 10 Trending Hashtags', fontweight='bold')
            axes[plot_idx].set_xlabel('Mentions')
            plot_idx += 1

        if 'daily_activity' in plots:
            daily = self.df['date'].value_counts().sort_index()
            axes[plot_idx].plot(daily.index, daily.values, marker='o', linewidth=2, color=colors[0])
            axes[plot_idx].set_title('Daily Hashtag Mentions', fontweight='bold')
            axes[plot_idx].set_xlabel('Date')
            axes[plot_idx].set_ylabel('Mentions')
            axes[plot_idx].tick_params(axis='x', rotation=45)
            plot_idx += 1

        if 'hourly_activity' in plots:
            hourly = self.df['hour'].value_counts().sort_index()
            axes[plot_idx].bar(hourly.index, hourly.values, alpha=0.7, color=colors[1])
            axes[plot_idx].set_title('Hourly Distribution of Mentions', fontweight='bold')
            axes[plot_idx].set_xlabel('Hour of Day')
            axes[plot_idx].set_ylabel('Mentions')
            axes[plot_idx].set_xticks(range(0, 24, 2))
            plot_idx += 1

        if 'day_of_week' in plots:
            dow = self.df['day_of_week'].value_counts()
            axes[plot_idx].bar(range(len(dow)), dow.values, color=colors[2:2+len(dow)])
            axes[plot_idx].set_title('Activity by Day of Week', fontweight='bold')
            axes[plot_idx].set_xlabel('Day of Week')
            axes[plot_idx].set_ylabel('Mentions')
            axes[plot_idx].set_xticks(range(len(dow)))
            axes[plot_idx].set_xticklabels(dow.index, rotation=45)
            plot_idx += 1

        for i in range(plot_idx, len(axes)):
            axes[i].set_visible(False)

        plt.tight_layout()
        plt.savefig('reports/trends_dashboard.png', dpi=300, bbox_inches='tight')
        plt.close()

        if 'date' in self.df.columns and len(self.df['date'].unique()) > 1:
            plt.figure(figsize=(10, 6))
            color_cycle = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFE66D', '#5C7AEA']
            for i, hashtag in enumerate(self.df['tag'].value_counts().head(5).index):
                hashtag_data = self.df[self.df['tag'] == hashtag]
                daily_count = hashtag_data.groupby('date').size()
                plt.plot(daily_count.index, daily_count.values, marker='o', label=hashtag,
                         linewidth=2, color=color_cycle[i % len(color_cycle)])
            plt.title('Top 5 Hashtags Daily Trend', fontweight='bold')
            plt.xlabel('Date')
            plt.ylabel('Daily Mentions')
            plt.legend()
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig('reports/top_hashtags_trend.png', dpi=300, bbox_inches='tight')
            plt.close()

        print("Visualizations created successfully!")

    def create_html_report(self):
        total_mentions = len(self.df)
        unique_hashtags = self.df['tag'].nunique()
        top_hashtag = self.df['tag'].value_counts().index[0] if not self.df.empty else "N/A"
        top_count = self.df['tag'].value_counts().iloc[0] if not self.df.empty else 0

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
                img {{ max-width: 100%; height: auto; display: block; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>TikTok Trends Report</h1>
                    <p>Date: {self.report_date}</p>
                </div>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{total_mentions:,}</div>
                        <div>Total Mentions</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{unique_hashtags:,}</div>
                        <div>Unique Hashtags</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{top_count:,}</div>
                        <div>Top Hashtag: {top_hashtag}</div>
                    </div>
                </div>
                <div class="section">
                    <h2>Trend Visualizations</h2>
                    <img src="trends_dashboard.png" alt="Trends Dashboard">
                    <img src="top_hashtags_trend.png" alt="Top Hashtags Daily Trend">
                </div>
            </div>
        </body>
        </html>
        """

        with open('reports/daily_report.html', 'w', encoding='utf-8') as f:
            f.write(html_content)

        print("HTML report generated successfully! Open 'reports/daily_report.html' in your browser.")

if __name__ == "__main__":
    reporter = TikTokReporter()
    reporter.generate_daily_report()

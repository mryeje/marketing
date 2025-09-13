import pandas as pd
import os
from datetime import datetime
import json

def generate_html_dashboard():
    """Generate an interactive HTML dashboard from CSV files"""
    
    print("📊 Generating interactive HTML dashboard...")
    
    # Check which CSV files exist
    csv_files = {
        'power_tools': 'power_tools_hashtags.csv',
        'appliances': 'appliances_hashtags.csv', 
        'ope': 'ope_hashtags.csv',
        'niche_breakdown': 'niche_breakdown.csv',
        'general': 'top_hashtags.csv'  # fallback to general if niche files don't exist
    }
    
    # Load data from available CSV files
    data = {}
    for key, filename in csv_files.items():
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename)
                print(f"📋 Loading {filename} with columns: {list(df.columns)}")
                
                # Handle different CSV formats more robustly
                if key == 'niche_breakdown':
                    # Handle niche breakdown with flexible column names
                    if len(df.columns) >= 2:
                        # Use the first two columns, regardless of their names
                        df.columns = ['category', 'count'] + list(df.columns[2:])
                        data[key] = df.to_dict('records')
                elif df.shape[1] >= 2:  # hashtag, count format
                    # Use the first two columns for hashtag data
                    first_col, second_col = df.columns[0], df.columns[1]
                    df_subset = df[[first_col, second_col]].copy()
                    df_subset.columns = ['hashtag', 'count']
                    data[key] = df_subset.head(15).to_dict('records')
                else:
                    # Single column or unknown format
                    data[key] = df.head(15).to_dict('records')
                    
                print(f"✅ Loaded {filename} - {len(data[key])} records")
                
            except Exception as e:
                print(f"⚠️ Error loading {filename}: {e}")
                continue
    
    if not data:
        print("❌ No CSV files found! Run the analysis first.")
        return
    
    # Generate HTML dashboard
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TikTok Hashtag Analysis Dashboard</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
                line-height: 1.6;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 20px;
            }}
            
            .header {{
                background: white;
                border-radius: 15px;
                padding: 30px;
                text-align: center;
                margin-bottom: 30px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }}
            
            .header h1 {{
                color: #2c3e50;
                margin-bottom: 10px;
                font-size: 2.5em;
            }}
            
            .header p {{
                color: #7f8c8d;
                font-size: 1.1em;
            }}
            
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                gap: 25px;
                margin-bottom: 30px;
            }}
            
            .card {{
                background: white;
                border-radius: 15px;
                padding: 25px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
            }}
            
            .card:hover {{
                transform: translateY(-5px);
            }}
            
            .card h2 {{
                color: #2c3e50;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 3px solid #3498db;
                font-size: 1.4em;
            }}
            
            .hashtag-list {{
                list-style: none;
            }}
            
            .hashtag-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 0;
                border-bottom: 1px solid #ecf0f1;
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
                background: #3498db;
                color: white;
                padding: 5px 12px;
                border-radius: 20px;
                font-weight: bold;
                font-size: 0.9em;
            }}
            
            .power-tools {{ border-left: 5px solid #e74c3c; }}
            .appliances {{ border-left: 5px solid #2ecc71; }}
            .ope {{ border-left: 5px solid #f39c12; }}
            .general {{ border-left: 5px solid #9b59b6; }}
            
            .summary {{
                background: white;
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 30px;
                box-shadow: 0 8px 25px rgba(0,0,0,0.1);
            }}
            
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }}
            
            .summary-item {{
                text-align: center;
                padding: 20px;
                background: #f8f9fa;
                border-radius: 10px;
            }}
            
            .summary-number {{
                font-size: 2.5em;
                font-weight: bold;
                color: #2c3e50;
                display: block;
            }}
            
            .summary-label {{
                color: #7f8c8d;
                font-size: 1.1em;
                margin-top: 5px;
            }}
            
            .footer {{
                text-align: center;
                color: white;
                margin-top: 30px;
                opacity: 0.8;
            }}
            
            @media (max-width: 768px) {{
                .grid {{
                    grid-template-columns: 1fr;
                }}
                .header h1 {{
                    font-size: 2em;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 TikTok Hashtag Analysis Dashboard</h1>
                <p>Power Tools | Appliances | Outdoor Power Equipment</p>
                <p>Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
    """
    
    # Add summary section if we have niche breakdown
    if 'niche_breakdown' in data and data['niche_breakdown']:
        html_content += """
            <div class="summary">
                <h2>📊 Niche Overview</h2>
                <div class="summary-grid">
        """
        
        for item in data['niche_breakdown']:
            # Handle different possible key names
            category_key = None
            count_key = None
            
            # Find the category key
            for key in ['category', 'niche', 'type', 'name']:
                if key in item:
                    category_key = key
                    break
            
            # Find the count key
            for key in ['count', 'total', 'mentions', 'frequency']:
                if key in item:
                    count_key = key
                    break
            
            if category_key and count_key:
                category_name = str(item[category_key]).replace('_', ' ').title()
                count_value = item[count_key]
                html_content += f"""
                    <div class="summary-item">
                        <span class="summary-number">{count_value}</span>
                        <div class="summary-label">{category_name}</div>
                    </div>
                """
        
        html_content += """
                </div>
            </div>
        """
    
    html_content += '<div class="grid">'
    
    # Add cards for each niche
    niche_configs = {
        'power_tools': ('🔧 Power Tools', 'power-tools'),
        'appliances': ('🏠 Appliances', 'appliances'), 
        'ope': ('🌿 Outdoor Power Equipment', 'ope'),
        'general': ('📈 General Trends', 'general')
    }
    
    for key, (title, css_class) in niche_configs.items():
        if key in data and data[key]:
            html_content += f"""
                <div class="card {css_class}">
                    <h2>{title}</h2>
                    <ul class="hashtag-list">
            """
            
            for item in data[key]:
                # Handle different possible key names for hashtag and count
                hashtag_key = None
                count_key = None
                
                # Find hashtag key
                for key_name in ['hashtag', 'tag', 'name', 'keyword']:
                    if key_name in item:
                        hashtag_key = key_name
                        break
                
                # Find count key
                for key_name in ['count', 'mentions', 'frequency', 'total']:
                    if key_name in item:
                        count_key = key_name
                        break
                
                # Use first available keys if specific ones not found
                if not hashtag_key and item:
                    hashtag_key = list(item.keys())[0]
                if not count_key and len(item.keys()) > 1:
                    count_key = list(item.keys())[1]
                
                if hashtag_key and count_key:
                    hashtag = str(item[hashtag_key])
                    count = item[count_key]
                    
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
    
    # Close HTML
    html_content += """
            </div>
            <div class="footer">
                <p>💡 Tip: Use this data to plan your TikTok content strategy and identify trending hashtags in your niches</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Save HTML file
    try:
        with open('hashtag_dashboard.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print("✅ Dashboard generated successfully!")
        print("🌐 Open 'hashtag_dashboard.html' in your web browser to view the interactive dashboard")
        
    except Exception as e:
        print(f"❌ Error saving dashboard: {e}")

def create_simple_text_report():
    """Create a simple text report as backup"""
    
    csv_files = [
        'power_tools_hashtags.csv',
        'appliances_hashtags.csv', 
        'ope_hashtags.csv',
        'niche_breakdown.csv'
    ]
    
    report = []
    report.append("=" * 60)
    report.append("TIKTOK HASHTAG ANALYSIS REPORT")
    report.append(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    report.append("=" * 60)
    
    for filename in csv_files:
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename)
                niche_name = filename.replace('_hashtags.csv', '').replace('_', ' ').title()
                
                report.append(f"\n{niche_name.upper()}:")
                report.append("-" * 30)
                
                if df.shape[1] >= 2:
                    # Use first two columns regardless of names
                    for i, row in enumerate(df.head(10).iterrows(), 1):
                        first_val = row[1].iloc[0]
                        second_val = row[1].iloc[1]
                        report.append(f"{i:2d}. #{first_val}: {second_val} mentions")
                
            except Exception as e:
                report.append(f"Error loading {filename}: {e}")
    
    # Save text report
    try:
        with open('hashtag_report.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        
        print("📄 Text report saved as 'hashtag_report.txt'")
        
    except Exception as e:
        print(f"❌ Error saving text report: {e}")

if __name__ == "__main__":
    print("🔧 Creating dashboard from your CSV files...")
    generate_html_dashboard()
    create_simple_text_report()
    
    print("\n📂 View your results:")
    print("   🌐 hashtag_dashboard.html - Interactive web dashboard")
    print("   📄 hashtag_report.txt - Simple text summary")
    print("\nDouble-click the HTML file to open it in your web browser!")
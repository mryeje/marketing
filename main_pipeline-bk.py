#!/usr/bin/env python3
"""
Main Pipeline for TikTok Hashtag Intelligence
Orchestrates the complete workflow from data collection to visualization
"""

import asyncio
import logging
import subprocess
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pipeline.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class TikTokHashtagPipeline:
    def __init__(self):
        self.execution_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        logger.info(f"🚀 Starting TikTok Hashtag Pipeline - Execution: {self.execution_time}")
    
    async def run_complete_pipeline(self):
        """Execute the complete pipeline end-to-end"""
        try:
            # Stage 1: Data Collection
            logger.info("📥 STAGE 1: Data Collection")
            await self.collect_data()
            
            # Stage 2: Analysis & Classification
            logger.info("🔍 STAGE 2: Analysis & Classification")
            self.analyze_trends()
            
            # Stage 3: Visualization & Reporting
            logger.info("📊 STAGE 3: Visualization & Reporting")
            self.generate_reports()
            
            logger.info("✅ Pipeline completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def collect_data(self):
        """Run data collection from multiple sources"""
        try:
            logger.info("Running TikTok data collection...")
            
            # Run the data collection script
            process = await asyncio.create_subprocess_exec(
                sys.executable, "TT-dataCollection.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Data collection completed successfully")
                if stdout:
                    logger.info(f"Data collection output: {stdout.decode().strip()}")
            else:
                logger.error(f"❌ Data collection failed: {stderr.decode().strip()}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error during data collection: {e}")
            return False
    
    def analyze_trends(self):
        """Run trend analysis and classification"""
        try:
            logger.info("Running multi-niche trend analysis...")
            
            # Import and run the analysis
            from analyze_trends import analyze_multi_niche_trends
            analyze_multi_niche_trends()
            
            logger.info("✅ Trend analysis completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during trend analysis: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def generate_reports(self):
        """Generate visualizations and dashboards"""
        try:
            logger.info("Generating reports and dashboards...")
            
            # Run dashboard generation
            from dashboard_generator import generate_html_dashboard, create_simple_text_report
            generate_html_dashboard()
            create_simple_text_report()
            
            logger.info("✅ Reports generated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during report generation: {e}")
            return False
    
    def show_database_status(self):
        """Show current database status"""
        try:
            import sqlite3
            conn = sqlite3.connect('hashtags.db')
            cursor = conn.cursor()
            
            # Get total hashtags count
            cursor.execute("SELECT COUNT(*) FROM hashtags")
            total_count = cursor.fetchone()[0]
            
            # Get unique sources
            cursor.execute("SELECT DISTINCT source, COUNT(*) FROM hashtags GROUP BY source")
            sources = cursor.fetchall()
            
            # Get latest entries
            cursor.execute("SELECT hashtag, collected_at FROM hashtags ORDER BY collected_at DESC LIMIT 5")
            latest = cursor.fetchall()
            
            conn.close()
            
            logger.info(f"📊 Database Status:")
            logger.info(f"   Total hashtags: {total_count}")
            logger.info(f"   Sources: {dict(sources)}")
            logger.info(f"   Latest entries: {latest}")
            
        except Exception as e:
            logger.error(f"Error checking database status: {e}")

async def main():
    """Main execution function"""
    pipeline = TikTokHashtagPipeline()
    
    # Show current status
    pipeline.show_database_status()
    
    # Run complete pipeline
    success = await pipeline.run_complete_pipeline()
    
    # Show final status
    pipeline.show_database_status()
    
    if success:
        logger.info("🎉 Pipeline execution completed! Check the generated files:")
        logger.info("   📊 hashtag_dashboard.html - Interactive dashboard")
        logger.info("   📄 hashtag_report.txt - Text summary")
        logger.info("   📈 multi_niche_analysis.png - Visual charts")
        logger.info("   📋 *_hashtags.csv - Niche-specific data")
    else:
        logger.error("💥 Pipeline execution failed!")
    
    return success

if __name__ == "__main__":
    print("=" * 80)
    print("    TIKTOK HASHTAG INTELLIGENCE PIPELINE")
    print("    Complete Automation Workflow")
    print("=" * 80)
    
    # Run the pipeline
    success = asyncio.run(main())
    
    print("=" * 80)
    if success:
        print("✅ Pipeline completed successfully!")
    else:
        print("❌ Pipeline failed - check pipeline.log for details")
    print("=" * 80)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
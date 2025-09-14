#!/usr/bin/env python3
"""
Main Pipeline for TikTok Hashtag Intelligence
With Real AI Content Filtering Integration
"""

import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import Callable, Any

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

# Import AI Filter (with graceful fallback)
try:
    from ai_filter import get_content_filter
    HAS_AI_FILTER = True
    logger.info("🤖 AI content filter available")
except ImportError:
    HAS_AI_FILTER = False
    logger.warning("⚠️ AI filtering not available - install transformers package")
except Exception as e:
    HAS_AI_FILTER = False
    logger.error(f"⚠️ AI filter import failed: {e}")

class PipelineError(Exception):
    """Custom exception for pipeline errors"""
    pass

class TikTokHashtagPipeline:
    def __init__(self):
        self.execution_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.errors = []
        logger.info(f"🚀 Starting TikTok Hashtag Pipeline - Execution: {self.execution_time}")
    
    async def run_with_retry(self, func: Callable, task_name: str, max_retries: int = 3, delay: int = 2) -> Any:
        """
        Execute a function with retry logic and exponential backoff
        """
        for attempt in range(max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func()
                else:
                    result = func()
                logger.info(f"✅ {task_name} completed successfully")
                return result
                
            except Exception as e:
                if attempt < max_retries:
                    wait_time = delay * (2 ** attempt)
                    logger.warning(
                        f"⚠️ {task_name} failed on attempt {attempt + 1}/{max_retries + 1}. "
                        f"Retrying in {wait_time}s. Error: {e}"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"❌ {task_name} failed after {max_retries + 1} attempts. Final error: {e}"
                    logger.error(error_msg)
                    self.errors.append(error_msg)
                    raise PipelineError(error_msg) from e
    
    def safe_function_execution(self, func: Callable, task_name: str) -> Any:
        """
        Execute a function with basic error handling
        """
        try:
            result = func()
            logger.info(f"✅ {task_name} completed successfully")
            return result
        except Exception as e:
            error_msg = f"❌ {task_name} failed: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            raise PipelineError(error_msg) from e
    
    async def collect_data(self) -> bool:
        """Run data collection from multiple sources with error handling"""
        try:
            logger.info("📥 Starting data collection...")
            
            # Import here to avoid circular imports
            import subprocess
            import sys
            
            # Run the data collection script as a subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, "TT-dataCollection.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Data collection completed successfully")
                if stdout:
                    logger.debug(f"Data collection output: {stdout.decode().strip()}")
                return True
            else:
                error_output = stderr.decode().strip()
                logger.error(f"❌ Data collection failed with return code {process.returncode}: {error_output}")
                self.errors.append(f"Data collection: {error_output}")
                return False
                
        except FileNotFoundError:
            error_msg = "❌ Data collection script 'TT-dataCollection.py' not found"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
        except Exception as e:
            error_msg = f"❌ Unexpected error during data collection: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def apply_ai_filtering(self, df):
        """
        Apply AI content filtering to identify relevant content
        """
        if not HAS_AI_FILTER or df.empty:
            logger.info("⚠️ Skipping AI filtering (not available or empty data)")
            return df
            
        try:
            logger.info("🤖 Applying AI content filtering...")
            
            # Get the AI filter instance
            content_filter = get_content_filter()
            
            # Prepare text for analysis - use description if available, otherwise use hashtags
            if 'description' in df.columns:
                texts = df['description'].fillna('').astype(str).tolist()
                logger.info(f"Analyzing {len(texts)} descriptions for relevance")
            else:
                texts = df['tag'].fillna('').astype(str).tolist()
                logger.info(f"Analyzing {len(texts)} hashtags for relevance")
            
            # Apply AI filtering
            df['is_relevant'] = content_filter.filter_irrelevant(texts, threshold=0.6)
            
            # Calculate statistics
            relevant_count = df['is_relevant'].sum()
            total_count = len(df)
            relevance_percentage = (relevant_count / total_count) * 100 if total_count > 0 else 0
            
            logger.info(f"✅ AI filtering complete: {relevant_count}/{total_count} items ({relevance_percentage:.1f}%) marked relevant")
            
            return df
            
        except Exception as e:
            error_msg = f"❌ AI filtering failed: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            # Continue without AI filtering
            df['is_relevant'] = True
            return df
    
    def analyze_trends(self) -> bool:
        """Run trend analysis and classification with error handling"""
        try:
            logger.info("🔍 Starting trend analysis...")
            
            # Import inside function to handle module not found errors
            try:
                from analyze_trends import analyze_multi_niche_trends
            except ImportError as e:
                error_msg = f"❌ Could not import analyze_trends module: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
            
            # First, load the data to apply AI filtering
            import sqlite3
            import pandas as pd
            
            conn = sqlite3.connect('hashtags.db')
            df = pd.read_sql_query("SELECT * FROM hashtags ORDER BY collected_at DESC", conn)
            conn.close()
            
            if df.empty:
                logger.warning("⚠️ No data found for AI filtering")
                analyze_multi_niche_trends()
                return True
            
            # Apply AI filtering before analysis
            df = self.apply_ai_filtering(df)
            
            # Save the filtered data for analysis
            df[['tag', 'collected_at', 'source', 'is_relevant']].to_csv('hashtags_with_relevance.csv', index=False)
            logger.info("💾 Saved hashtags with relevance scores to 'hashtags_with_relevance.csv'")
            
            # Run the analysis
            analyze_multi_niche_trends()
            
            logger.info("✅ Trend analysis completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"❌ Error during trend analysis: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def generate_reports(self) -> bool:
        """Generate visualizations and dashboards with error handling"""
        try:
            logger.info("📊 Generating reports and dashboards...")
            
            # Import inside function to handle module not found errors
            try:
                from dashboard_generator import generate_html_dashboard, create_simple_text_report
            except ImportError as e:
                error_msg = f"❌ Could not import dashboard_generator module: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
            
            generate_html_dashboard()
            create_simple_text_report()
            
            logger.info("✅ Reports generated successfully")
            return True
            
        except Exception as e:
            error_msg = f"❌ Error during report generation: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def show_database_status(self) -> bool:
        """Show current database status with error handling"""
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
            
            conn.close()
            
            logger.info(f"📊 Database Status:")
            logger.info(f"   Total hashtags: {total_count}")
            logger.info(f"   Sources: {dict(sources)}")
            return True
            
        except sqlite3.OperationalError as e:
            if "no such table" in str(e):
                logger.warning("⚠️ Database table doesn't exist yet (first run?)")
                return True
            else:
                error_msg = f"❌ Database error: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
        except Exception as e:
            error_msg = f"❌ Error checking database status: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    async def run_complete_pipeline(self) -> bool:
        """Execute the complete pipeline end-to-end with comprehensive error handling"""
        pipeline_stages = [
            ("Database status check", lambda: self.show_database_status()),
            ("Data collection", self.collect_data),
            ("AI content filtering", lambda: True),  # Placeholder, filtering happens in analysis
            ("Trend analysis", self.analyze_trends),
            ("Report generation", self.generate_reports),
            ("Final database check", lambda: self.show_database_status())
        ]
        
        successful = True
        
        for stage_name, stage_func in pipeline_stages:
            try:
                if asyncio.iscoroutinefunction(stage_func):
                    stage_success = await self.run_with_retry(stage_func, stage_name)
                else:
                    stage_success = self.safe_function_execution(stage_func, stage_name)
                
                if not stage_success:
                    successful = False
                    # Continue with next stages even if one fails
                    
            except PipelineError:
                successful = False
                # Continue with next stages
            except Exception as e:
                error_msg = f"❌ Unexpected error in {stage_name}: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                successful = False
                # Continue with next stages
        
        return successful
    
    def generate_error_report(self) -> str:
        """Generate a summary of errors encountered"""
        if not self.errors:
            return "No errors encountered"
        
        report = ["❌ ERROR REPORT:"]
        report.append("=" * 50)
        for i, error in enumerate(self.errors, 1):
            report.append(f"{i}. {error}")
        report.append("=" * 50)
        report.append(f"Total errors: {len(self.errors)}")
        
        return "\n".join(report)

async def main():
    """Main execution function with comprehensive error handling"""
    pipeline = TikTokHashtagPipeline()
    
    try:
        # Run complete pipeline
        success = await pipeline.run_complete_pipeline()
        
        # Generate final report
        error_report = pipeline.generate_error_report()
        logger.info(f"\n{error_report}")
        
        if success:
            logger.info("🎉 Pipeline execution completed successfully!")
            logger.info("📁 Generated files:")
            logger.info("   📊 hashtag_dashboard.html - Interactive dashboard")
            logger.info("   📄 hashtag_report.txt - Text summary")
            logger.info("   📈 multi_niche_analysis.png - Visual charts")
            logger.info("   📋 *_hashtags.csv - Niche-specific data")
            logger.info("   🤖 hashtags_with_relevance.csv - AI-filtered data")
        else:
            logger.error("💥 Pipeline execution completed with errors!")
        
        return success
        
    except Exception as e:
        logger.error(f"💥 Critical pipeline failure: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("    TIKTOK HASHTAG INTELLIGENCE PIPELINE")
    print("    With Real AI Content Filtering")
    print("=" * 80)
    
    # Run the pipeline
    success = asyncio.run(main())
    
    print("=" * 80)
    if success:
        print("✅ Pipeline completed successfully!")
    else:
        print("❌ Pipeline completed with errors - check pipeline.log for details")
    print("=" * 80)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
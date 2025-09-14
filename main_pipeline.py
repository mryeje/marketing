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
from typing import Callable, Any, List, Dict

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
        """Execute a function with retry logic and exponential backoff"""
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
                    logger.warning(f"⚠️ {task_name} failed on attempt {attempt + 1}/{max_retries + 1}. Retrying in {wait_time}s. Error: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"❌ {task_name} failed after {max_retries + 1} attempts. Final error: {e}"
                    logger.error(error_msg)
                    self.errors.append(error_msg)
                    raise PipelineError(error_msg) from e
    
    def safe_function_execution(self, func: Callable, task_name: str) -> Any:
        """Execute a function with basic error handling"""
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
            
            import subprocess
            import sys
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "TT-dataCollection.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Data collection completed successfully")
                return True
            else:
                error_output = stderr.decode().strip()
                logger.error(f"❌ Data collection failed: {error_output}")
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
        """Apply AI content filtering to identify relevant content"""
        if not HAS_AI_FILTER or df.empty:
            logger.info("⚠️ Skipping AI filtering")
            return df
            
        try:
            logger.info("🤖 Applying AI content filtering...")
            content_filter = get_content_filter()
            
            if 'description' in df.columns:
                texts = df['description'].fillna('').astype(str).tolist()
            else:
                texts = df['tag'].fillna('').astype(str).tolist()
            
            df['is_relevant'] = content_filter.filter_irrelevant(texts, threshold=0.6)
            relevant_count = df['is_relevant'].sum()
            
            logger.info(f"✅ AI filtering complete: {relevant_count}/{len(df)} items marked relevant")
            return df
            
        except Exception as e:
            error_msg = f"❌ AI filtering failed: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            df['is_relevant'] = True
            return df
    
    def analyze_trends(self) -> bool:
        """Run trend analysis and classification with error handling"""
        try:
            logger.info("🔍 Starting trend analysis...")
            
            try:
                from analyze_trends import analyze_multi_niche_trends
            except ImportError as e:
                error_msg = f"❌ Could not import analyze_trends: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
            
            import sqlite3
            import pandas as pd
            
            conn = sqlite3.connect('hashtags.db')
            df = pd.read_sql_query("SELECT * FROM hashtags", conn)
            conn.close()
            
            if not df.empty:
                df = self.apply_ai_filtering(df)
                df.to_csv('hashtags_with_relevance.csv', index=False)
                logger.info("💾 Saved filtered data")
            
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
            
            try:
                from dashboard_generator import generate_html_dashboard, create_simple_text_report
            except ImportError as e:
                error_msg = f"❌ Could not import dashboard_generator: {e}"
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
            cursor.execute("SELECT COUNT(*) FROM hashtags")
            total_count = cursor.fetchone()[0]
            conn.close()
            
            logger.info(f"📊 Database Status: {total_count} hashtags")
            return True
            
        except sqlite3.OperationalError:
            logger.warning("⚠️ Database table doesn't exist yet")
            return True
        except Exception as e:
            error_msg = f"❌ Error checking database: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    async def run_complete_pipeline(self) -> bool:
        """Execute the complete pipeline end-to-end"""
        pipeline_stages = [
            ("Database status check", lambda: self.show_database_status()),
            ("Data collection", self.collect_data),
            ("Trend analysis", self.analyze_trends),
            ("Report generation", self.generate_reports),
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
                    
            except Exception as e:
                error_msg = f"❌ Error in {stage_name}: {e}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                successful = False
        
        return successful
    
    def generate_error_report(self) -> str:
        """Generate a summary of errors encountered"""
        if not self.errors:
            return "No errors encountered"
        
        report = ["❌ ERROR REPORT:", "=" * 50]
        for i, error in enumerate(self.errors, 1):
            report.append(f"{i}. {error}")
        report.extend(["=" * 50, f"Total errors: {len(self.errors)}"])
        return "\n".join(report)

async def main():
    """Main execution function"""
    pipeline = TikTokHashtagPipeline()
    
    try:
        success = await pipeline.run_complete_pipeline()
        error_report = pipeline.generate_error_report()
        logger.info(f"\n{error_report}")
        
        if success:
            logger.info("🎉 Pipeline execution completed successfully!")
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
    print("=" * 80)
    
    success = asyncio.run(main())
    
    print("=" * 80)
    if success:
        print("✅ Pipeline completed successfully!")
    else:
        print("❌ Pipeline completed with errors!")
    print("=" * 80)
    
    sys.exit(0 if success else 1)
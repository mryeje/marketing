#!/usr/bin/env python3
"""
Main Pipeline for TikTok Hashtag Intelligence
With Real AI Content Filtering Integration
"""

import asyncio
import logging
import sys
import time
import os
import sqlite3
import pandas as pd
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
    
    def ensure_database_schema(self):
        """Ensure the database exists with proper schema"""
        try:
            conn = sqlite3.connect('hashtags.db')
            cursor = conn.cursor()
            
            # Create hashtags table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hashtags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    niche TEXT,
                    description TEXT,
                    is_relevant BOOLEAN DEFAULT 1
                )
            ''')
            
            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_tag ON hashtags(tag)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON hashtags(timestamp)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_niche ON hashtags(niche)
            ''')
            
            conn.commit()
            conn.close()
            logger.info("📊 Database schema ensured")
            
        except Exception as e:
            logger.error(f"❌ Database schema creation failed: {e}")
            raise
    
    def import_csv_to_database(self):
        """Import data from CSV files to database if CSV exists but database is empty"""
        try:
            conn = sqlite3.connect('hashtags.db')
            cursor = conn.cursor()
            
            # Check if database has data
            cursor.execute("SELECT COUNT(*) FROM hashtags")
            db_count = cursor.fetchone()[0]
            
            if db_count > 0:
                logger.info(f"📊 Database already has {db_count} records")
                conn.close()
                return
            
            # Look for CSV files to import
            csv_files = [
                ('power_tools_hashtags.csv', 'power_tools'),
                ('appliances_hashtags.csv', 'appliances'), 
                ('ope_hashtags.csv', 'ope'),
                ('top_hashtags.csv', 'general')
            ]
            
            total_imported = 0
            
            for csv_file, niche in csv_files:
                if os.path.exists(csv_file):
                    try:
                        df = pd.read_csv(csv_file)
                        logger.info(f"📥 Found {csv_file} with {len(df)} records")
                        
                        # Prepare data for insertion
                        for _, row in df.iterrows():
                            cursor.execute('''
                                INSERT INTO hashtags (tag, count, niche, timestamp)
                                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            ''', (row['tag'], row.get('count', 1), niche))
                        
                        total_imported += len(df)
                        logger.info(f"✅ Imported {len(df)} records from {csv_file}")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Could not import {csv_file}: {e}")
            
            if total_imported > 0:
                conn.commit()
                logger.info(f"💾 Successfully imported {total_imported} total records to database")
            else:
                logger.info("ℹ️ No CSV files found to import")
            
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ CSV import failed: {e}")
            raise
    
    async def collect_data(self) -> bool:
        """Run data collection from multiple sources with error handling"""
        try:
            logger.info("📥 Starting data collection...")
            
            # Ensure database schema exists first
            self.ensure_database_schema()
            
            import subprocess
            import sys
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, "TT-dataCollection.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Data collection script completed")
                
                # Check if database was populated, if not try to import from CSV
                self.import_csv_to_database()
                
                # Verify we have data
                conn = sqlite3.connect('hashtags.db')
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM hashtags")
                count = cursor.fetchone()[0]
                conn.close()
                
                if count > 0:
                    logger.info(f"✅ Data collection completed successfully - {count} records in database")
                    return True
                else:
                    logger.warning("⚠️ Data collection completed but no data in database")
                    return False
                    
            else:
                error_output = stderr.decode().strip()
                logger.error(f"❌ Data collection failed: {error_output}")
                self.errors.append(f"Data collection: {error_output}")
                
                # Still try to import from existing CSV files as fallback
                logger.info("🔄 Attempting fallback CSV import...")
                self.import_csv_to_database()
                
                return False
                
        except FileNotFoundError:
            error_msg = "❌ Data collection script 'TT-dataCollection.py' not found"
            logger.error(error_msg)
            self.errors.append(error_msg)
            
            # Try fallback CSV import
            try:
                logger.info("🔄 Attempting fallback CSV import...")
                self.ensure_database_schema()
                self.import_csv_to_database()
                return True
            except Exception as fallback_error:
                logger.error(f"❌ Fallback also failed: {fallback_error}")
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
            logger.info(f"📊 DataFrame shape: {df.shape}")
            logger.info(f"📊 DataFrame columns: {df.columns.tolist()}")
            
            # If no suitable columns, skip filtering
            if 'tag' not in df.columns and 'description' not in df.columns:
                logger.warning("⚠️ No 'tag' or 'description' column found for AI filtering")
                df['is_relevant'] = True
                return df
                
            content_filter = get_content_filter()
            
            # Use tag column if available, otherwise description
            if 'tag' in df.columns:
                texts = df['tag'].fillna('').astype(str).tolist()
            else:
                texts = df['description'].fillna('').astype(str).tolist()
            
            # Debug: show sample texts
            logger.info(f"📝 Sample texts for AI filtering: {texts[:3] if texts else 'No texts'}")
            
            df['is_relevant'] = content_filter.filter_irrelevant(texts, threshold=0.6)
            relevant_count = df['is_relevant'].sum()
            
            logger.info(f"✅ AI filtering complete: {relevant_count}/{len(df)} items marked relevant")
            return df
            
        except Exception as e:
            error_msg = f"❌ AI filtering failed: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(f"🔍 Full traceback: {traceback.format_exc()}")
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
            
            # Check if database has data
            conn = sqlite3.connect('hashtags.db')
            try:
                df = pd.read_sql_query("SELECT * FROM hashtags", conn)
            except pd.errors.DatabaseError:
                logger.warning("⚠️ Could not read from hashtags table, creating empty DataFrame")
                df = pd.DataFrame()
            conn.close()
            
            if not df.empty:
                df = self.apply_ai_filtering(df)
                df.to_csv('hashtags_with_relevance.csv', index=False)
                logger.info(f"💾 Saved filtered data - {len(df)} records")
            else:
                logger.warning("⚠️ No data found in database for trend analysis")
            
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
            conn = sqlite3.connect('hashtags.db')
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hashtags'")
            table_exists = cursor.fetchone() is not None
            
            if table_exists:
                cursor.execute("SELECT COUNT(*) FROM hashtags")
                total_count = cursor.fetchone()[0]
                
                # Get counts by niche if possible
                try:
                    cursor.execute("SELECT niche, COUNT(*) FROM hashtags GROUP BY niche")
                    niche_counts = cursor.fetchall()
                    niche_info = ", ".join([f"{niche}: {count}" for niche, count in niche_counts])
                    logger.info(f"📊 Database Status: {total_count} hashtags ({niche_info})")
                except:
                    logger.info(f"📊 Database Status: {total_count} hashtags")
            else:
                logger.warning("⚠️ Database table doesn't exist yet")
            
            conn.close()
            return True
            
        except Exception as e:
            error_msg = f"❌ Error checking database: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
    
    def optimize_database(self):
        """Remove old data to keep database size reasonable"""
        try:
            conn = sqlite3.connect('hashtags.db')
            cursor = conn.cursor()
            
            # Keep only data from last 90 days
            cursor.execute("DELETE FROM hashtags WHERE timestamp < datetime('now', '-90 days')")
            deleted_count = cursor.rowcount
            
            # Vacuum to reclaim space
            conn.execute("VACUUM")
            conn.commit()
            conn.close()
            
            if deleted_count > 0:
                logger.info(f"🗑️ Removed {deleted_count} old records from database")
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Database optimization failed: {e}")
            return False
    
    async def run_complete_pipeline(self) -> bool:
        """Execute the complete pipeline end-to-end"""
        pipeline_stages = [
            ("Database status check", lambda: self.show_database_status()),
            ("Data collection", self.collect_data),
            ("Trend analysis", self.analyze_trends),
            ("Report generation", self.generate_reports),
            ("Database optimization", lambda: self.optimize_database()),
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

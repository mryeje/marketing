# Run this one-liner to get all the info you need:

import sqlite3, os
from datetime import datetime

def get_db_info():
    if not os.path.exists('hashtags.db'):
        return '❌ Database file does not exist'
    
    try:
        conn = sqlite3.connect('hashtags.db')
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute('SELECT name FROM sqlite_master WHERE type=''table'' AND name=''hashtags'';')
        if not cursor.fetchone():
            return '❌ hashtags table does not exist'
        
        # Get stats
        cursor.execute('SELECT MAX(collected_at), COUNT(*) FROM hashtags;')
        latest, total = cursor.fetchone()
        
        cursor.execute('SELECT COUNT(*) FROM hashtags WHERE datetime(collected_at) > datetime(''now'', ''-1 day'');')
        recent = cursor.fetchone()[0]
        
        cursor.execute('SELECT source, COUNT(*) FROM hashtags GROUP BY source;')
        sources = dict(cursor.fetchall())
        
        conn.close()
        
        return f''' DATABASE STATUS:
 Latest collection: {latest or 'No data'}
 Total hashtags: {total}
 Last 24 hours: {recent}
 Sources: {sources}'''
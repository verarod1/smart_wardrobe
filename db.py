import sqlite3
import os

# Automatically use /data if it exists (for Amvera), else fallback to .
DATA_DIR = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else '.')
DB_PATH = os.path.join(DATA_DIR, 'wardrobe.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            brand TEXT,
            color TEXT,
            photo_url TEXT,
            weight_grams INTEGER,
            season TEXT,
            style_note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # History table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            date_worn DATE,
            social_media_posted BOOLEAN,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Automatically initialize database tables if they do not exist
init_db()

import sqlite3
import os

# Automatically use /data if it exists (for Amvera), else fallback to .
DATA_DIR = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else '.')
DB_PATH = os.path.join(DATA_DIR, 'wardrobe.db')

def seed_data_to_cloud():
    """Copy local db and photos to the persistent cloud storage if it is empty."""
    if DATA_DIR != '.':
        project_root = os.path.dirname(__file__)
        local_db = os.path.join(project_root, 'wardrobe.db')
        
        should_copy = False
        if not os.path.exists(DB_PATH):
            should_copy = True
        else:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM items")
                count = c.fetchone()[0]
                conn.close()
                if count == 0:
                    should_copy = True
            except Exception:
                should_copy = True
                
        if should_copy and os.path.exists(local_db) and DB_PATH != local_db:
            import shutil
            try:
                shutil.copy2(local_db, DB_PATH)
            except Exception:
                pass
                
        local_photos = os.path.join(project_root, 'photos')
        target_photos = os.path.join(DATA_DIR, 'photos')
        if os.path.exists(local_photos) and local_photos != target_photos:
            os.makedirs(target_photos, exist_ok=True)
            for f in os.listdir(local_photos):
                src = os.path.join(local_photos, f)
                dst = os.path.join(target_photos, f)
                if os.path.isfile(src) and not os.path.exists(dst):
                    import shutil
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass

seed_data_to_cloud()

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
    
    # Auto-fix absolute paths in photo_url on startup
    cursor.execute("SELECT id, photo_url FROM items WHERE photo_url IS NOT NULL")
    for row in cursor.fetchall():
        if row[1] and ('\\' in row[1] or '/' in row[1]):
            filename = row[1].replace('\\', '/').split('/')[-1]
            new_path = os.path.join(DATA_DIR, 'photos', filename)
            if row[1] != new_path:
                cursor.execute("UPDATE items SET photo_url = ? WHERE id = ?", (new_path, row[0]))
                
    conn.commit()
    conn.close()

# Automatically initialize database tables if they do not exist
init_db()

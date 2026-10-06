import os
from db import get_connection
from logic import calculate_packing

def test_packing():
    conn = get_connection()
    c = conn.cursor()
    # Get items
    columns = [desc[0] for desc in c.execute('SELECT * FROM items').description]
    all_items = [dict(zip(columns, row)) for row in c.fetchall()]
    
    # Get history
    c.execute("SELECT item_id, COUNT(item_id) as c FROM history WHERE date_worn >= date('now', '-45 days') AND social_media_posted = 1 GROUP BY item_id")
    history_freq = {row[0]: row[1] for row in c.fetchall()}
    
    conn.close()

    temp = 28.0
    limit_kg = 9.0
    
    packed, total_weight, recs = calculate_packing(all_items, history_freq, temp, limit_kg)
    
    print(f"Total Packed: {len(packed)}")
    print(f"Total Weight: {total_weight / 1000} kg")
    print("Recommendations:")
    print(recs)
    
    underwear = [i for i in packed if i.get('category') == 'underwear' or i.get('type') == 'underwear']
    evening_dress = [i for i in packed if i.get('type') == 'evening_dress']

    print(f"Underwear packed: {len(underwear)}")
    for u in underwear:
        print(f"ID {u['id']}: color={u['color']}, note={u.get('style_note','')}")
        
    print(f"Evening dress packed: {len(evening_dress)}")
    for e in evening_dress:
        print(f"ID {e['id']}: {e['color']}")
        
if __name__ == '__main__':
    test_packing()

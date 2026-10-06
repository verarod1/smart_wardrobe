from weather import get_season_strategy
import random

def calculate_packing(all_items: list, history_freq: dict, temp: float, max_weight_kg: float) -> tuple:
    """
    all_items is a list of dicts from the db.
    history_freq is a dictionary mapping item_id -> int (number of times worn recently).
    max_weight_kg is user input (e.g., 17).
    Returns (packed_items (list of dicts), total_weight_grams, message).
    """
    max_grams = int(max_weight_kg * 1000)
    valid_season = get_season_strategy(temp)
    
    # Filter items that fit the season, with strict rules for shoes
    season_items = []
    for i in all_items:
        if i['season'] not in valid_season:
            continue
        
        c = (i.get('category') or '').lower()
        t = (i.get('type') or '').lower()
        if c == 'shoes' or 'shoe' in t:
            if temp <= 5 and i['season'] not in ('winter', 'demi'):
                continue
            if temp >= 20 and i['season'] not in ('summer', 'all'):
                continue
                
        season_items.append(i)
    
    # Shuffle for randomness, but then sort by usage frequency (favoring items with lower history count)
    random.shuffle(season_items) 
    season_items.sort(key=lambda x: history_freq.get(x['id'], 0))
    
    main_items = [i for i in season_items if i.get('category') != 'underwear' and i.get('type') != 'underwear']
    underwear_items = [i for i in season_items if i.get('category') == 'underwear' or i.get('type') == 'underwear']
    
    available_sport_tops = sum(1 for i in season_items if i.get('type') == 'sport_top')
    available_sport_bottoms = sum(1 for i in season_items if i.get('type') == 'sport_bottom')
    # Force strictly matched sets
    sport_limit = min(4, available_sport_tops, available_sport_bottoms)
    
    casual_bottoms = sum(1 for i in season_items if i.get('type') in ('casual_bottom',))
    cb_limit = min(5, max(1, casual_bottoms))
    ct_limit = cb_limit * 3

    categories = {
        'sport_top': sport_limit,
        'sport_bottom': sport_limit,
        'bag': 4,
        'shoes': 4,
        'evening_dress': 2,
        'business_suit': 2,
        'casual_top': ct_limit,
        'casual_bottom': cb_limit,
        'outer': 2
    }
    
    packed = []
    total_weight = 0
    counts = {k: 0 for k in categories.keys()}
    counts['underwear'] = 0
    main_colors = set()
    
    for item in main_items:
        t = item.get('type', '')
        
        # Normalize types
        if t == 'casual_tshirt':
            t = 'casual_top'
        if t == 'outerwear':
            t = 'outer'
            
        # If we already packed max for this specific type (if explicitly constrained), skip
        if t in categories and counts.get(t, 0) >= categories[t]:
            continue
        elif t not in categories:
            # Prevent unknown types from flooding (limit to 1 item per unknown type)
            if counts.get(t, 0) >= 1:
                continue
            
        w = item['weight_grams']
        if total_weight + w <= max_grams:
            packed.append(item)
            total_weight += w
            if t in counts:
                counts[t] += 1
            if item.get('color') and t not in ('bag', 'shoes', 'accessory', 'jewelry'):
                main_colors.add(item['color'].lower())
                
    # Sort underwear to match colors
    neutrals = {'black', 'white', 'бежевый', 'nude', 'черный', 'белый', 'серый', 'gray', 'grey'}
    
    def uw_score(item):
        c = (item.get('color') or '').lower()
        if c in main_colors:
            return 0  # Matches outfit color
        if c in neutrals:
            return 1  # Matches neutral
        return 2  # Other
        
    underwear_items.sort(key=lambda x: (uw_score(x), history_freq.get(x['id'], 0)))
    
    for item in underwear_items:
        if counts['underwear'] >= 10:
            break
            
        if uw_score(item) == 2:
            continue # Skip non-matching non-neutral underwear!
            
        w = item['weight_grams']
        if total_weight + w <= max_grams:
            packed.append(item)
            total_weight += w
            counts['underwear'] += 1
                
    # Check if we at least met minimums where possible
    recs = []
    
    if counts.get('sport_top', 0) < 4:
        missing_sport = 4 - counts.get('sport_top', 0)
        recs.append(f" - Спортивной одежды: докупить {missing_sport} комплекта (верх+низ).")
        
    if counts.get('underwear', 0) < 10:
        missing_uw = 10 - counts.get('underwear', 0)
        cname = "базового"
        if main_colors:
            # find the most common color or just pick one
            cname = list(main_colors)[0]
        recs.append(f" - Нижнего белья: докупить еще {missing_uw} штук (рекомендуемый цвет, подходящий к вещам: {cname}).")
        
    if counts.get('evening_dress', 0) == 0:
        recs.append(" - Вечерней одежды: докупить вечерний наряд.")
        
    if counts.get('business_suit', 0) == 0:
        recs.append(" - Деловой одежды: докупить строгий деловой костюм.")
        
    msg = "\n".join(recs)
        
    return packed, total_weight, msg

from weather import get_season_strategy_range
import random

def calculate_packing(all_items: list, history_freq: dict, temp_min: float, temp_max: float, max_weight_kg: float) -> tuple:
    """
    all_items is a list of dicts from the db.
    history_freq is a dictionary mapping item_id -> int (number of times worn recently).
    max_weight_kg is user input (e.g., 17).
    Returns (packed_items (list of dicts), total_weight_grams, message).
    """
    max_grams = int(max_weight_kg * 1000)
    valid_season = get_season_strategy_range(temp_min, temp_max)
    
    # Filter items that fit the season, with strict rules for shoes
    season_items = []
    for i in all_items:
        if i['season'] not in valid_season:
            continue
        
        c = (i.get('category') or '').lower()
        t = (i.get('type') or '').lower()
        if c == 'shoes' or 'shoe' in t:
            if temp_max <= 5 and i['season'] not in ('winter', 'demi', 'all'):
                continue
            if temp_min >= 20 and i['season'] not in ('summer', 'all'):
                continue
                
        season_items.append(i)
    
    # Shuffle for randomness, but then sort by usage frequency (favoring items with lower history count)
    random.shuffle(season_items) 
    
    main_items = [i for i in season_items if i.get('category') != 'underwear' and i.get('type') != 'underwear']
    underwear_items = [i for i in season_items if i.get('category') == 'underwear' or i.get('type') == 'underwear']
    
    # Sort main_items by priority so essentials are packed first, then by history frequency
    priority_map = {
        'evening_dress': 1,
        'business_suit': 1,
        'sport_top': 2,
        'sport_bottom': 2,
        'shoes': 3,
        'bag': 3,
        'outer': 3,
        'casual_top': 4,
        'casual_bottom': 4
    }
    
    main_items.sort(key=lambda x: (
        priority_map.get(x.get('type') or '', 5),
        history_freq.get(x['id'], 0)
    ))

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
    
    # Reserve weight for underwear (up to 10 pairs ~ 500g total if available)
    reserved_weight = min(10, len(underwear_items)) * 50 if len(underwear_items) > 0 else 0
    
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
        # Pack if fits within max_grams MINUS reserved_weight
        if total_weight + w <= (max_grams - reserved_weight):
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
        
    # Sort so best matching are first, then by frequency
    underwear_items.sort(key=lambda x: (uw_score(x), history_freq.get(x['id'], 0)))
    
    for item in underwear_items:
        if counts['underwear'] >= 10:
            break
            
        is_bad_match = (uw_score(item) == 2)
        
        # We enforce matching constraint in general, BUT user requested:
        # "в любом чемодане должно быть минимум 2 пары белья (если они не подходят по цвету то так и написать, что взяты из необходимости или базовые)"
        if is_bad_match and counts['underwear'] >= 2:
            continue
            
        w = item['weight_grams']
        # Since we reserved weight earlier, we now can use up to max_grams
        if total_weight + w <= max_grams:
            item_to_add = item.copy()
            if is_bad_match:
                item_to_add['style_note'] = item_to_add.get('style_note', '') + " (взято из необходимости)"
                
            packed.append(item_to_add)
            total_weight += w
            counts['underwear'] += 1
                
    # Count totals in wardrobe to not ask to buy items they already own
    in_wardrobe = {}
    for i in all_items:
        t = i.get('type', '')
        if t == 'casual_tshirt': t = 'casual_top'
        if t == 'outerwear': t = 'outer'
        in_wardrobe[t] = in_wardrobe.get(t, 0) + 1
        if i.get('category') == 'underwear' or i.get('type') == 'underwear':
            in_wardrobe['underwear'] = in_wardrobe.get('underwear', 0) + 1

    recs = []
    
    if counts.get('sport_top', 0) < 4:
        missing_wardrobe = max(0, 4 - in_wardrobe.get('sport_top', 0))
        if missing_wardrobe > 0:
            recs.append(f" - Спортивной одежды: докупить {missing_wardrobe} комплекта.")
        elif in_wardrobe.get('sport_top', 0) >= 4:
            recs.append(" - Спортивной одежды: есть в гардеробе, но не поместилось по весу/лимиту.")
            
    if counts.get('underwear', 0) < 10:
        missing_w = max(0, 10 - in_wardrobe.get('underwear', 0))
        cname = "базового/нейтрального"
        if main_colors:
            cname = list(main_colors)[0]
        if missing_w > 0:
            recs.append(f" - Нижнего белья: докупить еще {missing_w} штук (рекомендуемый цвет: {cname}).")
        else:
            recs.append(" - Нижнего белья: есть в гардеробе, но не поместилось по весу или не подошло по цвету.")
        
    if counts.get('evening_dress', 0) == 0:
        if in_wardrobe.get('evening_dress', 0) == 0:
            recs.append(" - Вечерней одежды: докупить вечерний наряд.")
        else:
            recs.append(" - Вечерней одежды: есть в гардеробе, но не подошло по сезону или весу.")
        
    if counts.get('business_suit', 0) == 0:
        if in_wardrobe.get('business_suit', 0) == 0:
            recs.append(" - Деловой одежды: докупить строгий деловой костюм.")
        else:
            recs.append(" - Деловой одежды: есть в гардеробе, но не подошло по сезону или весу.")
        
    msg = "\n".join(recs)
        
    return packed, total_weight, msg

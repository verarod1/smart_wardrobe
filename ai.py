import os
import json
import logging
import asyncio
import aiohttp
import time
import io
import base64
import uuid
from PIL import Image
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GIGACHAT_AUTH_KEY = os.getenv('GIGACHAT_AUTH_KEY')
# Use GigaChat-3-Pro for optimal logic
GIGACHAT_MODEL = "GigaChat-3-Pro"

class GigaChatAuth:
    def __init__(self):
        self.auth_key = GIGACHAT_AUTH_KEY
        self.access_token = None
        self.token_expires_at = 0

    async def get_token(self):
        if not self.auth_key:
            raise ValueError("GIGACHAT_AUTH_KEY not found in .env")
            
        current_time = time.time()
        if self.access_token and (self.token_expires_at - current_time) > 60:
            return self.access_token

        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.auth_key}"
        }
        data = {"scope": "GIGACHAT_API_PERS"}
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.post(url, headers=headers, data=data) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    self.access_token = resp_data['access_token']
                    self.token_expires_at = resp_data['expires_at'] / 1000
                    return self.access_token
                else:
                    text = await resp.text()
                    logger.error(f"Failed to get GigaChat token: {resp.status} {text}")
                    raise Exception("GigaChat auth failed")

auth_manager = GigaChatAuth()

async def call_gigachat_api(prompt: str, image_bytes: bytes = None) -> str:
    """Calls GigaChat API with automatic retry on 503 errors."""
    if not GIGACHAT_AUTH_KEY:
        raise ValueError("Missing API key")
        
    try:
        token = await auth_manager.get_token()
    except Exception as auth_e:
        raise Exception(f"GigaChat Auth Error: {auth_e}")
        
    messages = []
    
    if image_bytes:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((800, 800))
        buffer = io.BytesIO()
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(buffer, format="JPEG")
        
        form = aiohttp.FormData()
        form.add_field('file', buffer.getvalue(), filename='image.jpg', content_type='image/jpeg')
        form.add_field('purpose', 'general')
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            h = {"Authorization": f"Bearer {token}"}
            async with session.post("https://api.giga.chat/v1/files", headers=h, data=form) as f_resp:
                if f_resp.status == 200:
                    f_data = await f_resp.json()
                    file_id = f_data.get('id')
                    messages.append({
                        "role": "user",
                        "content": f'{prompt}<img src="{file_id}">',
                        "attachments": [file_id]
                    })
                else:
                    raise Exception(f"Image upload failed with status {f_resp.status}: {await f_resp.text()}")
    else:
        messages.append({
            "role": "user",
            "content": prompt
        })

    payload = {
        "model": GIGACHAT_MODEL,
        "messages": messages,
        "temperature": 0.5
    }
    
    url = "https://api.giga.chat/v1/chat/completions"
    
    headers_text = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    max_retries = 8
    for attempt in range(max_retries):
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.post(url, headers=headers_text, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    try:
                        return data['choices'][0]['message']['content']
                    except (KeyError, IndexError):
                        logger.error(f"Unexpected response structure: {data}")
                        raise Exception("Unexpected API response")
                elif resp.status in (503, 429):
                    wait_time = (attempt + 1) * 5
                    reason = "high demand" if resp.status == 503 else "rate limit"
                    logger.info(f"GigaChat {resp.status} ({reason}), retry {attempt+1}/{max_retries} in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    data = await resp.text()
                    logger.error(f"GigaChat API error {resp.status}: {data}")
                    raise Exception(f"API Error {resp.status}: {data}")
                    
    raise Exception("GigaChat API unavailable after retries (503/429)")

async def get_outfits(user_prompt: str, available_items: list) -> str:
    """Uses GigaChat to create 3 outfits based on the user_prompt and available items."""
    if not GIGACHAT_AUTH_KEY:
        return "Пожалуйста, добавьте ключ авторизации GigaChat (GIGACHAT_AUTH_KEY) в файл .env."

    items_str = "\n".join([
        f"ID: {i['id']} | Type: {i['type']} | Color: {i['color']} | Season: {i['season']} | Style: {i.get('style_note', '')}" 
        for i in available_items
    ])
    
    full_prompt = (
        "You are an AI stylist. The user will ask for outfits containing a specific item. "
        "You MUST choose items ONLY from the provided wardrobe database below. "
        "If the user mentions a specific ID (e.g. '70' or 'ID 70'), you MUST use that exact item ID in EVERY SINGLE outfit you generate. Do not generate any outfit that does not contain this specific item. If you cannot make another distinct outfit with it, then return fewer outfits. "
        "CRITICAL RULE: Outfits MUST be stylistically logical and strictly match in formality. Do NOT mix incompatible styles. "
        "For example, NEVER pair an 'evening_dress' with casual, sport, or beach items (e.g., do not use 'пляжные сланцы'/flip-flops, straw bags, chunky sneakers, or backpacks with elegant dresses). "
        "Evening wear must ONLY be paired with appropriate formal accessories (e.g. elegant shoes, clutches). If you don't have matching formal items, do not generate the outfit. "
        "Try to return 3 distinct outfits. HOWEVER, if there are not enough compatible items in the wardrobe to create 3 sensible outfits, return fewer outfits (1 or 2). "
        "If you cannot even make 1 good outfit, gracefully explain in Russian that the wardrobe lacks suitable items to pair with this piece. "
        "If you generate exactly 3 outfits, DO NOT output any warnings about missing items. ONLY if you return fewer than 3 outfits (1 or 2), you must add a note at the end saying exactly: 'В гардеробе больше нет подходящих вещей для других комбинаций.' "
        "Out of the generated outfits, select ONE as the 'Recommended Outfit'. "
        "For the Recommended Outfit ONLY, you MUST include a line exactly like this at the very end of your response: "
        "`RECOMMENDED_IDS: ID1, ID2, ID3` (replace with actual numbers). "
        "Format the output text beautifully for Telegram (Markdown). When listing the items in an outfit, ALWAYS include a short descriptive name in parentheses next to the item category, based on its color, type, and style. For example: *Юбка (зеленая юбка миди): ID 72 | Топ (белая футболка): ID 64 | Обувь (сандалии на каблуке): ID 88*. "
        "IMPORTANT: Your response (the descriptions, titles, tips, etc.) MUST be entirely in conversational Russian. "
        "HOWEVER, do NOT translate the names of clothing types, categories, or colors (e.g. keep 'casual_top', 'white', 'bottom' exactly as they are in the database).\n\n"
        f"WARDROBE ITEMS:\n{items_str}\n\nUser Request: {user_prompt}"
    )

    try:
        text = await call_gigachat_api(full_prompt)
        return text
    except Exception as e:
        logger.error(f"GigaChat styling error: {e}")
        return (
            "❌ Серверы нейросети сейчас перегружены и не смогли обработать запрос.\n"
            "Пожалуйста, попробуйте снова через пару минут командой /style"
        )

async def auto_tag_image_bytes(image_bytes: bytes) -> dict:
    """Uses GigaChat Vision to extract clothing info from raw image bytes."""
    
    if not GIGACHAT_AUTH_KEY:
         raise Exception("GIGACHAT_AUTH_KEY is not set.")
         
    prompt = (
        "Look carefully at this clothing item photo. Return a JSON object with the following keys:\n"
        "- type (string, e.g. sport_top, sport_bottom, casual_top, casual_bottom, shoes, bag, evening_dress, business_suit, underwear, bra, outerwear)\n"
        "- category (string, must be one of: top, bottom, outer, full-body, shoes, bag, underwear)\n"
        "- brand (string, guess if visible, or 'Unknown')\n"
        "- color (string, the main color of the item)\n"
        "- weight_grams (integer, estimate the physical weight in grams)\n"
        "- season (string, one of: summer, winter, demi, all)\n"
        "- style_note (string, describe stylistic specifics in Russian: material, length, fit, heel type, pattern, etc)\n"
        "IMPORTANT: Identify the item correctly. Pants/trousers are 'casual_bottom' category 'bottom'. "
        "Shirts/blouses are 'casual_top' category 'top'. Dresses are 'evening_dress' category 'full-body'.\n"
        "Return ONLY the strict JSON object with NO markdown wrapping."
    )
    
    text = await call_gigachat_api(prompt, image_bytes)
    text = text.strip()
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    # Parse it nicely
    return json.loads(text.strip())

async def check_city_dress_code(city: str) -> str:
    """Uses GigaChat to determine if a city has strict dress-code rules."""
    if not GIGACHAT_AUTH_KEY:
        return "standard"

    full_prompt = (
        f"You are a travel advisor. The user is traveling to: {city}. "
        "Determine if this location has a strictly conservative or religious public dress code (e.g. Muslim countries like UAE, Iran, Saudi Arabia, or highly traditional areas) where tourists are expected to avoid mini-skirts, short shorts, crop tops, and revealing clothes in public. "
        "Return ONLY the word 'conservative' if they should avoid revealing clothes, or 'standard' if normal Western casual wear is acceptable. "
        "Do not output anything else."
    )
    try:
        text = await call_gigachat_api(full_prompt)
        text = text.strip().lower()
        if "conservative" in text:
            return "conservative"
        return "standard"
    except Exception as e:
        logger.error(f"GigaChat dress-code error: {e}")
        return "standard"

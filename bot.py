import os
import re
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

from db import get_connection
from weather import get_weather_forecast
from logic import calculate_packing
from ai import get_outfits, auto_tag_image_bytes, check_city_dress_code, parse_user_intent
from visuals import create_moodboard

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- FSM STATES ---
class DialogState(StatesGroup):
    clarifying_pack = State()
    clarifying_style = State()

def get_missing_pack_prompt(data: dict) -> str:
    missing = []
    if not data.get("city"):
        missing.append("• Город назначения")
    if not data.get("days"):
        missing.append("• Длительность поездки (в днях)")
    if not data.get("weight_limit_kg"):
        missing.append("• Лимит веса багажа (в кг)")
    if not data.get("date"):
        missing.append("• Дату вылета (ДД.ММ.ГГГГ, например: 15.10.2026)")
        
    known_info = []
    if data.get("city"):
        known_info.append(f"Город: {data['city']}")
    if data.get("days"):
        known_info.append(f"Дней: {data['days']}")
    if data.get("weight_limit_kg"):
        known_info.append(f"Вес: {data['weight_limit_kg']} кг")
    if data.get("date"):
        known_info.append(f"Дата: {data['date']}")
        
    text = "🧳 **С удовольствием помогу собрать чемодан!**\n\n"
    if known_info:
        text += f"Уже записал: {', '.join(known_info)}\n\n"
    text += "Уточните, пожалуйста:\n" + "\n".join(missing) + "\n\n"
    text += "💡 _Вы можете написать всё одним сообщением (например: «Дубай, 14 дней, 15.10.2026, 17 кг»)_"
    return text

# --- HANDLERS ---

@dp.message(Command("start", "help"))
async def send_welcome(message: types.Message):
    await message.reply(
        "Добро пожаловать в твой AI Гардероб!\n"
        "Команды:\n"
        "/wardrobe - Посмотреть вещи\n"
        "/pack <город> <дни> <дата(ДД.ММ.ГГГГ)> <лимит_веса_кг> - Напр. /pack Dubai 7 15.10.2026 17\n"
        "/style <описание_или_ID> - Напр. /style green skirt или /style 60\n"
        "/delete <ID> - Удалить вещь\n"
        "/edit <ID> <поле> <значение> - Напр. /edit 60 brand Prada\n"
        "/photo <ID> - Получить фото вещи\n"
        "/cancel - Отменить текущий диалог\n"
        "Отправь мне фото одежды, чтобы автоматически добавить её в базу!\n\n"
        "Либо просто напиши мне человеческим языком, например: «Собери чемодан в Дубай на 14 дней» или «Подбери образ»!"
    )

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.reply("Нет активного диалога для отмены.")
        return
    await state.clear()
    await message.reply("❌ Диалог отменен.")

@dp.message(Command("wardrobe"))
async def cmd_wardrobe(message: types.Message):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, color, brand, weight_grams, season, style_note FROM items ORDER BY id DESC")
    items = c.fetchall()
    conn.close()
    
    if not items:
        await message.reply("Гардероб пуст!")
        return
    
    text = f"👗 Гардероб ({len(items)} вещей, новые сверху):\n\n"
    for i in items[:30]:  # Show up to 30
        desc = f" | {i[6]}" if i[6] else ""
        text += f"{i[0]}) {i[2]} {i[1]} ({i[3]}) — {i[4]}г, {i[5]}{desc}\n"
    if len(items) > 30:
        text += f"\n...и ещё {len(items) - 30} вещей."
    await message.reply(text)

@dp.message(Command("pack"))
async def cmd_pack(message: types.Message):
    parts = message.text.split()
    if len(parts) < 5:
        return await message.reply("Использование: /pack <город> <дни> <дата_отправления(ДД.ММ.ГГГГ)> <лимит_веса_кг>")
        
    try:
        limit_kg = float(parts[-1])
        date_str = parts[-2]
        days = int(parts[-3])
        city = " ".join(parts[1:-3])
    except ValueError:
        return await message.reply("Ошибка: проверьте правильность ввода чисел (дни и вес).")
    
    from weather import get_weather_forecast
    weather_info = await get_weather_forecast(city, date_str, days)
    if 'error' in weather_info:
        return await message.reply(f"❌ Ошибка получения погоды: {weather_info['error']}")
        
    t_min = weather_info['temp_min']
    t_max = weather_info['temp_max']
    
    await message.reply("🌎 Анализирую культурные особенности и дресс-код страны...")
    dress_code = await check_city_dress_code(city)
    dc_msg = "‼️Строгий/консервативный (исключаю мини и открытые наряды)" if dress_code == 'conservative' else "Стандартный (свободный)"
    
    await message.reply(f"Погода в {city} ({date_str}, {days} дн.): от {t_min}°C до {t_max}°C, {weather_info['condition']}.\nДресс-код: {dc_msg}.\nСобираю чемодан...")
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM items")
    cols = [desc[0] for desc in c.description]
    all_items = [dict(zip(cols, row)) for row in c.fetchall()]
    
    c.execute("SELECT item_id, COUNT(item_id) as c FROM history WHERE date_worn >= date('now', '-45 days') AND social_media_posted = 1 GROUP BY item_id")
    history_freq = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    packed, total_weight, recommendations = calculate_packing(all_items, history_freq, t_min, t_max, limit_kg, dress_code)
    
    response = f"🧳 Собрано {len(packed)} вещей. Общий вес: {total_weight / 1000} кг.\n\n"
    
    if recommendations:
        response += f"💡 **Рекомендации стилиста (чего не хватает):**\n{recommendations}\n\n"
        
    categorized = {}
    for p in packed:
        t = (p.get('type') or '').lower()
        if 'sport' in t:
            cat = 'Спорт'
        elif 'shoe' in t:
            cat = 'Обувь'
        elif 'bag' in t:
            cat = 'Сумка'
        elif 'underwear' in t:
            cat = 'Бельё'
        elif 'accessory' in t or 'jewelry' in t:
            cat = 'Аксессуар/Украшение'
        else:
            cat = 'Одежда'
        categorized.setdefault(cat, []).append(p)
        
    for cat, items in categorized.items():
        response += f"📌 {cat}:\n"
        for p in items:
            p_id = p.get('id', '?')
            p_desc = p.get('style_note', '')
            desc_text = f" - {p_desc}" if p_desc else ""
            response += f"{p_id}) {p.get('color', 'unknown')} {p.get('type', 'unknown')} ({p.get('weight_grams', 0)}г){desc_text}\n"
        response += "\n"
        
    # Split by chunks safely
    while len(response) > 4000:
        split_idx = response.rfind('\n', 0, 4000)
        if split_idx == -1:
            split_idx = 4000
        await message.reply(response[:split_idx])
        response = response[split_idx:].strip()

    keyboard = None
    if packed:
        packed_ids = [p['id'] for p in packed if p.get('id')]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []
        for pid in packed_ids:
            row.append(InlineKeyboardButton(text=f"📷 #{pid}", callback_data=f"show_photo_{pid}"))
            if len(row) >= 4:
                keyboard.inline_keyboard.append(row)
                row = []
        if row:
            keyboard.inline_keyboard.append(row)

    if response:
        if keyboard and keyboard.inline_keyboard:
            await message.reply(response, reply_markup=keyboard)
        else:
            await message.reply(response)
            
    if packed:
        checklist_lines = [f"🧳 ЧЕК-ЛИСТ ДЛЯ СБОРОВ: {city.upper()} ({days} дн.)\n"]
        for cat, items_in_cat in categorized.items():
            checklist_lines.append(f"\n{cat.upper()}:")
            for p in items_in_cat:
                p_desc = p.get('style_note', '')
                desc_text = f" - {p_desc}" if p_desc else ""
                checklist_lines.append(f" [ ] {p.get('color', 'unknown')} {p.get('type', 'unknown')}{desc_text} (ID: {p.get('id')})")
        
        checklist_path = os.path.join(os.getenv('DATA_DIR', '.'), f"checklist.txt")
        with open(checklist_path, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(checklist_lines))
            
        try:
            await message.reply_document(FSInputFile(checklist_path), caption="📝 Ваш чеклист (удобно распечатать/отметить)!")
        except Exception as e:
            logger.error(f"Error sending checklist: {e}")

@dp.message(Command("style"))
async def cmd_style(message: types.Message):
    prompt = message.text.replace("/style", "").strip()
    if not prompt:
        return await message.reply("Укажите вещь, например: /style серая толстовка")
        
    await message.reply("🎨 Консультируюсь с AI-стилистом...")
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, type, color, season, photo_url, style_note FROM items WHERE photo_url != '' AND photo_url IS NOT NULL")
    cols = [desc[0] for desc in c.description]
    available_items = [dict(zip(cols, row)) for row in c.fetchall()]
    conn.close()
    
    outfits_text = await get_outfits(prompt, available_items)
    
    # Save full text for ID extraction before chunked sending consumes it
    outfits_text_full = outfits_text
    
    mentioned_ids = set()
    rec_match = re.search(r'RECOMMENDED_IDS[^\d]*([\d\s,]+)', outfits_text_full)
    if rec_match:
        # Extract all numbers from the matched line
        mentioned_ids = set(map(int, re.findall(r'\d+', rec_match.group(1))))
        
    if not mentioned_ids:
        # Fallback if AI didn't follow the format: grab all IDs it mentioned
        mentioned_ids = set(map(int, re.findall(r'`(\d+)`', outfits_text_full)))
        if not mentioned_ids:
            mentioned_ids = set(map(int, re.findall(r'ID[:\s]*(\d+)', outfits_text_full)))

    valid_ids = {i['id'] for i in available_items}
    all_numbers_ai = set(map(int, re.findall(r'\b\d+\b', outfits_text_full)))
    all_numbers_user = set(map(int, re.findall(r'\b\d+\b', prompt)))
    all_mentioned_ids = (all_numbers_ai | all_numbers_user) & valid_ids

    keyboard = None
    if all_mentioned_ids:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        row = []
        for pid in sorted(list(all_mentioned_ids)):
            row.append(InlineKeyboardButton(text=f"📷 #{pid}", callback_data=f"show_photo_{pid}"))
            if len(row) >= 4:
                keyboard.inline_keyboard.append(row)
                row = []
        if row:
            keyboard.inline_keyboard.append(row)

    # Send text first (split into chunks if over 4096 chars)
    while outfits_text:
        chunk = outfits_text[:4096]
        outfits_text = outfits_text[4096:]
        if not outfits_text and keyboard and keyboard.inline_keyboard:
            await message.reply(chunk, reply_markup=keyboard)
        else:
            await message.reply(chunk)

    items_by_id = {i['id']: i for i in available_items}
    image_sources = []
    data_dir = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else os.path.dirname(__file__))
    for item_id in mentioned_ids:
        item = items_by_id.get(item_id)
        if item and item.get('photo_url'):
            filename = item['photo_url'].replace('\\', '/').split('/')[-1]
            actual_path = os.path.join(data_dir, 'photos', filename)
            if os.path.exists(actual_path):
                image_sources.append(actual_path)
        if len(image_sources) >= 4:
            break
    if image_sources:
        try:
            collage_path = await create_moodboard(image_sources)
            if collage_path and os.path.exists(collage_path):
                photo = FSInputFile(collage_path)
                await message.reply_photo(photo)
        except Exception as e:
            logger.error(f"Error sending collage: {e}")
    
@dp.message(Command("delete"))
async def cmd_delete(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.reply("Использование: /delete <ID>")
    
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM items WHERE id = ?", (int(parts[1]),))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    
    if deleted > 0:
        await message.reply(f"✅ Вещь с ID {parts[1]} успешно удалена.")
    else:
        await message.reply(f"❌ Вещь с ID {parts[1]} не найдена.")

@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        return await message.reply("Использование: /edit <ID> <поле> <новое_значение>\nПоля: type, category, brand, color, weight_grams, season")
    
    item_id = parts[1]
    field = parts[2].lower()
    value = parts[3]
    
    if not item_id.isdigit():
        return await message.reply("ID должен быть числом.")
        
    allowed_fields = ['type', 'category', 'brand', 'color', 'weight_grams', 'season', 'style_note']
    if field not in allowed_fields:
        return await message.reply(f"Неизвестное поле. Способы: {', '.join(allowed_fields)}")
        
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM items WHERE id = ?", (int(item_id),))
    if not c.fetchone():
        conn.close()
        return await message.reply(f"❌ Вещь с ID {item_id} не найдена.")
        
    c.execute(f"UPDATE items SET {field} = ? WHERE id = ?", (value, int(item_id)))
    conn.commit()
    conn.close()
    
    await message.reply(f"✅ Для вещи ID {item_id} обновлено поле {field} = {value}")

@dp.message(Command("photo"))
async def cmd_photo(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.reply("Использование: /photo <ID>")
    
    item_id = int(parts[1])
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT photo_url FROM items WHERE id = ?", (item_id,))
    res = c.fetchone()
    conn.close()
    
    if res and res[0]:
        photo_val = res[0]
        filename = photo_val.replace('\\', '/').split('/')[-1]
        data_dir = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else os.path.dirname(__file__))
        actual_path = os.path.join(data_dir, 'photos', filename)
        
        if os.path.exists(actual_path):
            try:
                await message.reply_photo(FSInputFile(actual_path), caption=f"Вещь #{item_id}")
                return
            except Exception as e:
                logger.error(f"Failed to send photo for item {item_id}: {e}")
                await message.reply("фото отсутствует")
                return
        else:
            await message.reply("фото отсутствует")
            return

    await message.reply("фото отсутствует")

@dp.callback_query(F.data.startswith('show_photo_'))
async def process_show_photo(callback: CallbackQuery):
    item_id_str = callback.data.replace('show_photo_', '')
    if not item_id_str.isdigit():
        return await callback.answer("Неверный ID")
    
    item_id = int(item_id_str)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT photo_url FROM items WHERE id = ?", (item_id,))
    res = c.fetchone()
    conn.close()
    
    if res and res[0]:
        photo_val = res[0]
        # Robust path resolution: grab the filename only
        filename = photo_val.replace('\\', '/').split('/')[-1]
        data_dir = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else os.path.dirname(__file__))
        actual_path = os.path.join(data_dir, 'photos', filename)
        
        if os.path.exists(actual_path):
            try:
                await callback.message.answer_photo(FSInputFile(actual_path), caption=f"Вещь #{item_id}")
                await callback.answer()
                return
            except Exception as e:
                logger.error(f"Failed to send photo for item {item_id}: {e}")
                await callback.answer("Ошибка при отправке фото", show_alert=True)
                return
        else:
            files = os.listdir(os.path.join(data_dir, 'photos')) if os.path.exists(os.path.join(data_dir, 'photos')) else []
            debug_info = f"Нет фото! Искал: {actual_path}. Папка существует: {os.path.exists(os.path.join(data_dir, 'photos'))}. Файлов в ней: {len(files)}"
            await callback.answer(debug_info, show_alert=True)
            return

    await callback.answer("Фотографии для этой вещи нет в базе", show_alert=True)

@dp.message(DialogState.clarifying_pack, F.text & ~F.text.startswith('/'))
async def handle_pack_clarification(message: types.Message, state: FSMContext):
    data = await state.get_data()
    status_msg = await message.reply("🤔 Обрабатываю...")
    try:
        new_info = await parse_user_intent(message.text, existing_context=data)
    except Exception as e:
        logger.error(f"Error in clarification: {e}")
        new_info = {}

    for k in ["city", "days", "date", "weight_limit_kg"]:
        v = new_info.get(k)
        if v is not None:
            data[k] = v

    if data.get("city") and data.get("days") and data.get("date") and data.get("weight_limit_kg"):
        await state.clear()
        await status_msg.delete()
        mocked_message = message.model_copy(update={"text": f"/pack {data['city']} {data['days']} {data['date']} {data['weight_limit_kg']}"})
        await cmd_pack(mocked_message)
    else:
        await state.update_data(data)
        await status_msg.edit_text(get_missing_pack_prompt(data))

@dp.message(DialogState.clarifying_style, F.text & ~F.text.startswith('/'))
async def handle_style_clarification(message: types.Message, state: FSMContext):
    item = message.text.strip()
    await state.clear()
    mocked_message = message.model_copy(update={"text": f"/style {item}"})
    await cmd_style(mocked_message)

@dp.message(F.text & ~F.text.startswith('/'))
async def handle_text_intent(message: types.Message, state: FSMContext):
    status_msg = await message.reply("🤔 Анализирую ваш запрос...")
    try:
        intent_data = await parse_user_intent(message.text)
    except Exception as e:
        return await status_msg.edit_text("❌ Ошибка при анализе запроса.")
        
    intent = intent_data.get("intent", "unknown")
    
    if intent == "pack":
        city = intent_data.get("city")
        days = intent_data.get("days")
        date_str = intent_data.get("date")
        weight = intent_data.get("weight_limit_kg")

        if not (city and days and date_str and weight):
            await state.set_state(DialogState.clarifying_pack)
            data = {"city": city, "days": days, "date": date_str, "weight_limit_kg": weight}
            await state.set_data(data)
            return await status_msg.edit_text(get_missing_pack_prompt(data))
            
        await status_msg.delete()
        # Mock message text to reuse cmd_pack via model_copy
        mocked_message = message.model_copy(update={"text": f"/pack {city} {days} {date_str} {weight}"})
        await cmd_pack(mocked_message)
        
    elif intent == "style":
        item = intent_data.get("item")
        if not item:
            await state.set_state(DialogState.clarifying_style)
            return await status_msg.edit_text(
                "👗 **С удовольствием подберу образ!**\n\n"
                "С какой вещью из вашего гардероба составить лук? Укажите название вещи (например: *белая футболка*, *синяя юбка*) или её ID:"
            )
            
        await status_msg.delete()
        mocked_message = message.model_copy(update={"text": f"/style {item}"})
        await cmd_style(mocked_message)
        
    elif intent == "wardrobe":
        await status_msg.delete()
        await cmd_wardrobe(message)
        
    else:
        await status_msg.edit_text("Извините, но я пока не умею выполнять такие запросы. Я могу помочь собрать чемодан, подобрать образ или показать гардероб.")

@dp.message(lambda msg: msg.photo is not None)
async def handle_photo(message: types.Message):
    # Send a quick holding message
    status_msg = await message.reply("⏳ Загрузка фото...")
    
    # Download the actual photo from Telegram
    photo = message.photo[-1]  # highest resolution
    file = await bot.get_file(photo.file_id)
    
    from io import BytesIO
    photo_bytes_io = BytesIO()
    await bot.download_file(file.file_path, photo_bytes_io)
    photo_bytes = photo_bytes_io.getvalue()
    
    # Save photo locally
    import time
    data_dir = os.getenv('DATA_DIR', '/data' if os.path.isdir('/data') else os.path.dirname(__file__))
    photos_dir = os.path.join(data_dir, 'photos')
    os.makedirs(photos_dir, exist_ok=True)
    photo_filename = f"item_{int(time.time())}_{photo.file_id[:8]}.jpg"
    photo_path = os.path.join(photos_dir, photo_filename)
    with open(photo_path, 'wb') as f:
        f.write(photo_bytes)
    
    # Check if user provided manual tags in the caption to save AI limits
    item_metadata = None
    is_manual = False
    if message.caption:
        parts = [p.strip() for p in message.caption.split(',')]
        if len(parts) >= 2:
            is_manual = True
            
            item_metadata = {
                'type': parts[0],
                'color': parts[1],
                'category': parts[2] if len(parts) > 2 else ('bottom' if 'bottom' in parts[0] else 'top'),
                'brand': parts[3] if len(parts) > 3 else 'Unknown',
                'weight_grams': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 250,
                'season': parts[5] if len(parts) > 5 else 'all',
                'style_note': parts[6] if len(parts) > 6 else ''
            }
            await status_msg.edit_text("📝 Обрабатываю по ручным тегам (без траты API)...")
            
    if not item_metadata:
        await status_msg.edit_text("🔍 Анализирую фото через AI Vision...")
        try:
            item_metadata = await auto_tag_image_bytes(photo_bytes)
        except Exception as e:
            await status_msg.edit_text(f"❌ Ошибка распознавания: {e}\n\nПожалуйста, добавьте вещь с указанием тегов в подписи к фото, например:\n`casual_top, black, nike`")
            return
            
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO items (type, category, brand, color, photo_url, weight_grams, season, style_note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item_metadata.get('type', 'casual_top'),
        item_metadata.get('category', 'top'),
        item_metadata.get('brand', 'Unknown'),
        item_metadata.get('color', 'unknown'),
        photo_path,
        item_metadata.get('weight_grams', 250),
        item_metadata.get('season', 'all'),
        item_metadata.get('style_note', '')
    ))
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Check if fallback data was used (all fields match defaults)
    is_fallback = (
        item_metadata.get('type') == 'casual_top' and
        item_metadata.get('color') == 'black' and
        item_metadata.get('brand') == 'Unknown' and
        item_metadata.get('weight_grams') == 200
    )
    
    status = "⚠️ Вещь добавлена (AI Vision недоступен, данные приблизительные!):" if is_fallback else "✅ Вещь добавлена в гардероб!"
    
    await message.reply(
        f"{status}\n"
        f"ID вещи: {item_id}\n"
        f"Тип: {item_metadata.get('type')}\n"
        f"Категория: {item_metadata.get('category')}\n"
        f"Цвет: {item_metadata.get('color')}\n"
        f"Бренд: {item_metadata.get('brand')}\n"
        f"Вес: {item_metadata.get('weight_grams')}г\n"
        f"Сезон: {item_metadata.get('season')}\n"
        f"Описание: {item_metadata.get('style_note', '')}"
    )

async def main():
    if not BOT_TOKEN or "your_telegram_bot_token" in BOT_TOKEN:
        logger.error("PLEASE GET A TELEGRAM BOT TOKEN AND ENTER IT IN .env")
        return
        
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Запуск бота"),
        types.BotCommand(command="wardrobe", description="Посмотреть ваши вещи"),
        types.BotCommand(command="pack", description="Собрать чемодан"),
        types.BotCommand(command="style", description="Собрать лук с вещью"),
        types.BotCommand(command="delete", description="Удалить вещь по ID"),
        types.BotCommand(command="edit", description="Изменить данные вещи"),
        types.BotCommand(command="photo", description="Получить фото вещи"),
        types.BotCommand(command="cancel", description="Отменить текущий диалог")
    ])

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
import os
import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

logger = logging.getLogger(__name__)

async def get_weather_forecast(city: str, date_str: str, days: int) -> dict:
    """
    Fetches the 5-day forecast for a city using OpenWeatherMap API and extracts the min/max temperature for the specified date range.
    """
    if not WEATHER_API_KEY:
        logger.warning("No WEATHER_API_KEY provided.")
        return {'error': 'Ключ API погоды не настроен'}
        
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    import datetime
                    start_date = None
                    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
                        try:
                            start_date = datetime.datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            pass
                            
                    if not start_date:
                        return {'error': 'Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 15.10.2026)'}
                        
                    end_date = start_date + datetime.timedelta(days=days-1)
                    temps = []
                    today = datetime.datetime.now().date()
                    
                    for item in data['list']:
                        dt = datetime.datetime.fromtimestamp(item['dt']).date()
                        if start_date <= dt <= end_date:
                            temps.append(item['main']['temp'])
                            
                    if not temps:
                        if start_date < today:
                            return {'error': 'Дата отправления в прошлом.'}
                            
                        logger.warning("Requested dates are outside the 5-day forecast range. Using overall forecast.")
                        temps = [item['main']['temp'] for item in data['list']]
                        
                    return {
                        'temp_min': round(min(temps)),
                        'temp_max': round(max(temps)),
                        'condition': data['list'][0]['weather'][0]['main']
                    }
                else:
                    logger.error(f"Weather API error: {response.status}")
                    return {'error': f'Не удалось получить прогноз (ошибка {response.status})'}
        except Exception as e:
            logger.error(f"Exception fetching weather: {e}")
            return {'error': 'Ошибка сети при запросе погоды'}

def get_season_strategy_range(temp_min: float, temp_max: float) -> list:
    seasons = set(['all'])
    if temp_max >= 22:
        seasons.add('summer')
    if temp_min < 22 and temp_max >= 10:
        seasons.add('demi')
    if temp_min < 10:
        seasons.add('winter')
    return list(seasons)

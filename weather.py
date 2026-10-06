import os
import aiohttp
import logging
from dotenv import load_dotenv

load_dotenv()
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

logger = logging.getLogger(__name__)

async def get_weather(city: str) -> dict:
    """
    Fetches the current weather for a city using OpenWeatherMap API to decide on clothing strategy.
    Returns a dict with 'temp' (in celsius) and 'condition' (main weather condition).
    """
    if not WEATHER_API_KEY:
        logger.warning("No WEATHER_API_KEY provided.")
        return {'error': 'Ключ API погоды не настроен'}
        
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'temp': data['main']['temp'],
                        'condition': data['weather'][0]['main']
                    }
                else:
                    logger.error(f"Weather API error: {response.status}")
                    return {'error': f'Не удалось получить погоду (ошибка {response.status})'}
        except Exception as e:
            logger.error(f"Exception fetching weather: {e}")
            return {'error': 'Ошибка сети при запросе погоды'}

def get_season_strategy(temp: float) -> list:
    """Returns valid seasons for the given temperature."""
    if temp >= 22:
        return ['summer', 'all']
    elif temp >= 10:
        return ['demi', 'all']
    else:
        return ['winter', 'demi', 'all']

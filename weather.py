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
    For dates beyond 5 days, uses Open-Meteo Historical API for a proxy based on data from exactly 2 years ago.
    """
    if not WEATHER_API_KEY:
        logger.warning("No WEATHER_API_KEY provided.")
        return {'error': 'Ключ API погоды не настроен'}
        
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
    today = datetime.datetime.now().date()
    
    if start_date < today:
        return {'error': 'Дата отправления в прошлом.'}

    async with aiohttp.ClientSession() as session:
        # Check if dates are within the next 5 days
        if (start_date - today).days <= 5:
            url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={WEATHER_API_KEY}&units=metric"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        temps = []
                        for item in data['list']:
                            dt = datetime.datetime.fromtimestamp(item['dt']).date()
                            if start_date <= dt <= end_date:
                                temps.append(item['main']['temp'])
                                
                        if temps:
                            return {
                                'temp_min': round(min(temps)),
                                'temp_max': round(max(temps)),
                                'condition': data['list'][0]['weather'][0]['main']
                            }
            except Exception as e:
                logger.error(f"Exception fetching 5-day weather: {e}")

        # If date > 5 days or 5-day forecast didn't yield results, calculate a historical proxy
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={WEATHER_API_KEY}"
        try:
            async with session.get(geo_url) as geo_resp:
                if geo_resp.status == 200:
                    geo_data = await geo_resp.json()
                    if geo_data:
                        lat, lon = geo_data[0]['lat'], geo_data[0]['lon']
                        
                        # Adjust dates: approximately 2 years ago to ensure we have historical data
                        h_start = start_date - datetime.timedelta(days=730)
                        h_end = end_date - datetime.timedelta(days=730)
                        
                        # Open-Meteo historically requires dates to be perfectly formatted YYYY-MM-DD
                        om_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={h_start.strftime('%Y-%m-%d')}&end_date={h_end.strftime('%Y-%m-%d')}&daily=temperature_2m_max,temperature_2m_min"
                        
                        async with session.get(om_url) as om_resp:
                            if om_resp.status == 200:
                                om_data = await om_resp.json()
                                if 'daily' in om_data:
                                    t_max_list = [x for x in om_data['daily'].get('temperature_2m_max', []) if x is not None]
                                    t_min_list = [x for x in om_data['daily'].get('temperature_2m_min', []) if x is not None]
                                    if t_max_list and t_min_list:
                                        return {
                                            'temp_min': round(min(t_min_list)),
                                            'temp_max': round(max(t_max_list)),
                                            'condition': 'Исторический прогноз'
                                        }
                    else:
                        return {'error': 'Город не найден для долгосрочного прогноза.'}
        except Exception as e:
            logger.error(f"Exception fetching historical weather: {e}")
            
        return {'error': 'Не удалось получить достоверный прогноз для указанных дат.'}

def get_season_strategy_range(temp_min: float, temp_max: float) -> list:
    seasons = set(['all'])
    if temp_max >= 22:
        seasons.add('summer')
    if temp_min < 22 and temp_max >= 10:
        seasons.add('demi')
    if temp_min < 10:
        seasons.add('winter')
    return list(seasons)

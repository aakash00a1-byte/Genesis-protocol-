"""Genesis Protocol - Live Info Service

Provides real-time information:
- Current date/time
- Weather
- News
- Location
"""

import requests
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger("integrations.live_info")

# IST timezone (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class WeatherInfo:
    """Weather data."""
    temp: float
    condition: str
    humidity: int
    wind_speed: float
    city: str
    country: str
    icon: str

@dataclass
class LocationInfo:
    """Location data."""
    city: str
    region: str
    country: str
    timezone: str
    ip: str
    lat: float
    lon: float

@dataclass
class LiveInfo:
    """Combined live info."""
    timestamp: str
    date: str
    time: str
    weather: Optional[WeatherInfo] = None
    location: Optional[LocationInfo] = None
    news: list = None
    error: str = None


class LiveInfoService:
    """
    Live information service for Genesis Protocol.
    
    Automatically fetches:
    - Current date/time
    - Weather (using free APIs)
    - News headlines
    - Location (IP-based)
    """
    
    def __init__(self, weather_api_key: str = None, news_api_key: str = None):
        self.weather_api_key = weather_api_key
        self.news_api_key = news_api_key
        self._location_cache: Optional[LocationInfo] = None
        self._weather_cache: Optional[WeatherInfo] = None
        self._news_cache: list = []
        self._cache_time: datetime = None
        self._cache_ttl_seconds = 300  # 5 minutes
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl_seconds
    
    def get_location(self) -> Optional[LocationInfo]:
        """Get location from IP address (free, no API key needed)."""
        if self._location_cache:
            return self._location_cache
        
        try:
            # Using ip-api.com (free, no key required)
            response = requests.get("http://ip-api.com/json/", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    self._location_cache = LocationInfo(
                        city=data.get("city", "Unknown"),
                        region=data.get("regionName", "Unknown"),
                        country=data.get("country", "Unknown"),
                        timezone=data.get("timezone", "Unknown"),
                        ip=data.get("query", "Unknown"),
                        lat=data.get("lat", 0),
                        lon=data.get("lon", 0)
                    )
                    return self._location_cache
        except Exception as e:
            logger.error(f"Error fetching location: {e}")
        
        return None
    
    def get_weather(self, city: str = None) -> Optional[WeatherInfo]:
        """Get weather info using Open-Meteo (free, no API key)."""
        if self._weather_cache and city is None:
            return self._weather_cache
        
        try:
            location = self.get_location() if not city else None
            
            # Use coordinates or default to New Delhi
            lat = location.lat if location else 28.6139
            lon = location.lon if location else 77.2090
            
            # Open-Meteo free API (no key needed)
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                current = data.get("current", {})
                
                weather_codes = {
                    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
                    55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
                    71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
                    81: "Heavy showers", 82: "Violent showers", 95: "Thunderstorm"
                }
                
                code = current.get("weather_code", 0)
                condition = weather_codes.get(code, "Unknown")
                
                # Weather icons based on condition
                if code == 0:
                    icon = "☀️"
                elif code <= 3:
                    icon = "⛅"
                elif code <= 48:
                    icon = "🌫️"
                elif code <= 55:
                    icon = "🌧️"
                elif code <= 65:
                    icon = "🌧️"
                elif code <= 75:
                    icon = "❄️"
                elif code <= 82:
                    icon = "🌦️"
                else:
                    icon = "⛈️"
                
                weather = WeatherInfo(
                    temp=current.get("temperature_2m", 0),
                    condition=condition,
                    humidity=int(current.get("relative_humidity_2m", 0)),
                    wind_speed=current.get("wind_speed_10m", 0),
                    city=location.city if location else city or "Unknown",
                    country=location.country if location else "Unknown",
                    icon=icon
                )
                
                if city is None:
                    self._weather_cache = weather
                return weather
                
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
        
        return None
    
    def get_news(self, category: str = "general") -> list:
        """Get latest news using GNews (free tier available)."""
        if self._news_cache and self._is_cache_valid():
            return self._news_cache
        
        news_items = []
        
        try:
            # Using GNews API (free tier: 100 requests/day)
            # For demo, using public RSS feeds as fallback
            url = "https://gnews.io/api/v4/top-headlines"
            params = {
                "lang": "en",
                "max": 5,
                "token": self.news_api_key or "demo"
            }
            
            if self.news_api_key:
                response = requests.get(url, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    for article in data.get("articles", [])[:5]:
                        news_items.append({
                            "title": article.get("title", "")[:80],
                            "url": article.get("url", ""),
                            "source": article.get("source", {}).get("name", "Unknown")
                        })
            else:
                # Fallback: Use public news RSS
                news_items = self._get_news_from_rss()
                
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            news_items = self._get_news_from_rss()
        
        self._news_cache = news_items
        return news_items
    
    def _get_news_from_rss(self) -> list:
        """Get news from public RSS feeds."""
        try:
            response = requests.get(
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                timeout=5
            )
            if response.status_code == 200:
                # Simple RSS parsing
                import re
                items = re.findall(r'<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>', 
                                   response.text, re.DOTALL)
                return [
                    {"title": title[:80], "url": link, "source": "BBC News"}
                    for title, link in items[:5]
                ]
        except Exception:
            pass
        
        return [
            {"title": "News unavailable - API key required", "url": "", "source": "System"},
            {"title": "Get free API keys for live news", "url": "https://gnews.io", "source": "GNews"}
        ]
    
    def get_all_info(self) -> LiveInfo:
        """Get all live information at once."""
        # Use IST timezone (India Standard Time)
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(IST)
        
        location = self.get_location()
        weather = self.get_weather()
        news = self.get_news()
        
        return LiveInfo(
            timestamp=now_ist.isoformat(),
            date=now_ist.strftime("%d %B %Y"),
            time=now_ist.strftime("%I:%M:%S %p IST"),
            weather=weather,
            location=location,
            news=news
        )
    
    def format_for_display(self) -> str:
        """Format live info for display."""
        info = self.get_all_info()
        
        lines = [
            "═══════════════════════════════════",
            "📍 LIVE INFO",
            "═══════════════════════════════════",
            f"🕐 {info.time} | 📅 {info.date}",
        ]
        
        if info.weather:
            lines.append(f"🌤️  {info.weather.icon} {info.weather.temp}°C - {info.weather.condition}")
            lines.append(f"   📍 {info.weather.city}, {info.weather.country}")
            lines.append(f"   💨 Wind: {info.weather.wind_speed} km/h | 💧 Humidity: {info.weather.humidity}%")
        
        if info.location:
            lines.append(f"🌐 IP: {info.location.ip}")
            lines.append(f"   📌 {info.location.city}, {info.location.region}")
        
        if info.news:
            lines.append("")
            lines.append("📰 TOP NEWS:")
            for i, item in enumerate(info.news[:3], 1):
                lines.append(f"  {i}. {item['title']}")
        
        lines.append("═══════════════════════════════════")
        
        return "\n".join(lines)
    
    def clear_cache(self):
        """Clear all cached data."""
        self._location_cache = None
        self._weather_cache = None
        self._news_cache = []
        self._cache_time = None


# Singleton instance
_live_info_service: Optional[LiveInfoService] = None

def get_live_info_service() -> LiveInfoService:
    """Get singleton instance."""
    global _live_info_service
    if _live_info_service is None:
        _live_info_service = LiveInfoService()
    return _live_info_service

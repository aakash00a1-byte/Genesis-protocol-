"""Key-free exact live facts: weather and currency exchange rates.

Search snippets rarely carry an exact temperature or rate, so the agent either
guessed or refused. These providers return the number directly, so the answer
can be exact and still honest about its source and time.

- Weather: wttr.in (JSON). Open-Meteo is tried first but is unreachable from
  some hosts; wttr.in has been reliable from the deployment.
- FX: Frankfurter (ECB reference rates). Rates are daily, not tick-by-tick, so
  the response says so.
"""

from typing import Any, Dict

import httpx

from genesis_protocol.utils.logger import get_logger

logger = get_logger("integrations.live_facts")

_TIMEOUT = 15.0
_UA = {"User-Agent": "Mozilla/5.0 (compatible; GenesisProtocol/1.0)"}

# wttr.in "weather code" -> plain description. Only the codes we are likely to
# see are mapped; anything else falls back to the raw code.
_WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog", 51: "light drizzle",
    53: "moderate drizzle", 55: "dense drizzle", 61: "slight rain",
    63: "moderate rain", 65: "heavy rain", 71: "slight snow",
    73: "moderate snow", 75: "heavy snow", 80: "rain showers",
    81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
    99: "thunderstorm with heavy hail",
}


async def get_weather(location: str) -> Dict[str, Any]:
    """Exact current weather for a place, or an error. Never a guess."""
    if not location or not location.strip():
        return {"error": "no location given"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                     follow_redirects=True) as client:
            response = await client.get(
                f"https://wttr.in/{location.strip()}", params={"format": "j1"}
            )
        if response.status_code != 200:
            return {"error": f"weather provider HTTP {response.status_code}"}

        data = response.json()
        current = (data.get("current_condition") or [{}])[0]
        area = (data.get("nearest_area") or [{}])[0]
        city = (area.get("areaName") or [{}])[0].get("value") if area else None

        return {
            "location": city or location.strip(),
            "temperature_c": current.get("temp_C"),
            "feels_like_c": current.get("FeelsLikeC"),
            "condition": (current.get("weatherDesc") or [{}])[0].get("value"),
            "humidity": current.get("humidity"),
            "observed_at": current.get("observation_time"),
            "source": "wttr.in",
        }
    except Exception as e:
        logger.warning(f"weather lookup failed: {e}")
        return {"error": f"weather lookup failed: {e}"}


async def get_exchange_rate(base: str, quote: str) -> Dict[str, Any]:
    """Exact reference exchange rate, or an error. Never a guess."""
    base = (base or "").strip().upper()
    quote = (quote or "").strip().upper()
    if not base or not quote:
        return {"error": "need both a base and a quote currency"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                     follow_redirects=True) as client:
            response = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": base, "to": quote},
            )
        if response.status_code != 200:
            return {"error": f"fx provider HTTP {response.status_code}"}

        data = response.json()
        rate = (data.get("rates") or {}).get(quote)
        if rate is None:
            return {"error": f"no rate for {base}->{quote}"}

        return {
            "base": base,
            "quote": quote,
            "rate": rate,
            "rate_date": data.get("date"),
            "source": "frankfurter.app (ECB reference rates, daily)",
        }
    except Exception as e:
        logger.warning(f"fx lookup failed: {e}")
        return {"error": f"fx lookup failed: {e}"}

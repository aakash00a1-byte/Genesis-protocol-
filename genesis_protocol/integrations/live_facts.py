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


# CoinGecko id for the coins the chat is most likely to ask about.
_CRYPTO_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "solana": "solana", "sol": "solana",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "ripple": "ripple", "xrp": "ripple",
    "cardano": "cardano", "ada": "cardano",
    "polkadot": "polkadot", "dot": "polkadot",
    "polygon": "matic-network", "matic": "matic-network",
    "avalanche": "avalanche-2", "avax": "avalanche-2",
    "bnb": "binancecoin", "binancecoin": "binancecoin",
    "litecoin": "litecoin", "ltc": "litecoin",
    "tron": "tron", "trx": "tron",
    "shiba": "shiba-inu", "shib": "shiba-inu",
}


# Coinbase spot-pair symbols for the coins the chat is most likely to ask about.
_CRYPTO_TICKERS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "dogecoin": "DOGE",
    "ripple": "XRP", "cardano": "ADA", "polkadot": "DOT",
    "matic-network": "MATIC", "avalanche-2": "AVAX", "binancecoin": "BNB",
    "litecoin": "LTC", "tron": "TRX", "shiba-inu": "SHIB",
}


async def _coingecko_price(client: "httpx.AsyncClient", coin_id: str) -> Dict[str, Any]:
    """CoinGecko spot price. Flat keys per currency, not a nested dict."""
    response = await client.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": coin_id,
            "vs_currencies": "inr,usd",
            "include_24hr_change": "true",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
        },
    )
    if response.status_code != 200:
        return {"error": f"coingecko HTTP {response.status_code}"}

    data = response.json().get(coin_id)
    if not data or data.get("inr") is None:
        return {"error": f"coingecko has no price for {coin_id}"}

    return {
        "coin": coin_id,
        "price_inr": data.get("inr"),
        "price_usd": data.get("usd"),
        "change_24h_pct": data.get("inr_24h_change"),
        "market_cap_inr": data.get("inr_market_cap"),
        "volume_24h_inr": data.get("inr_24h_vol"),
        "source": "coingecko.com (spot price, live)",
    }


async def _coinbase_price(client: "httpx.AsyncClient", coin_id: str) -> Dict[str, Any]:
    """Coinbase spot price in USD, converted to INR via the ECB reference rate.

    The fallback for CoinGecko's free tier, which rate-limits (HTTP 429).
    """
    ticker = _CRYPTO_TICKERS.get(coin_id)
    if not ticker:
        return {"error": f"no fallback ticker for {coin_id}"}

    response = await client.get(
        f"https://api.coinbase.com/v2/prices/{ticker}-USD/spot"
    )
    if response.status_code != 200:
        return {"error": f"coinbase HTTP {response.status_code}"}
    usd = (response.json().get("data") or {}).get("amount")
    if usd is None:
        return {"error": f"coinbase has no price for {ticker}"}
    usd = float(usd)

    fx = await client.get(
        "https://api.frankfurter.app/latest", params={"from": "USD", "to": "INR"}
    )
    rate = ((fx.json().get("rates") or {}) if fx.status_code == 200 else {}).get("INR")

    return {
        "coin": coin_id,
        "price_inr": round(usd * rate) if rate else None,
        "price_usd": usd,
        "change_24h_pct": None,
        "market_cap_inr": None,
        "volume_24h_inr": None,
        "source": "coinbase.com spot (USD) + frankfurter.app FX",
    }


async def get_crypto_price(coin: str = "bitcoin") -> Dict[str, Any]:
    """Exact crypto price in INR and USD, or an error. Never a guess.

    Tries CoinGecko first (INR + USD + 24h change) and falls back to Coinbase
    plus an FX rate when CoinGecko rate-limits. Both providers are key-free.

    CoinGecko's ``/simple/price`` returns flat keys per currency (``inr`` is
    the price, ``inr_24h_change`` the change), not a nested ``{"inr": {...}}``
    object. Reading it as nested crashed the older service, which is why a
    crypto question always ended in "price unavailable".
    """
    key = (coin or "").strip().lower()
    coin_id = _CRYPTO_IDS.get(key, key)
    if not coin_id:
        return {"error": "no coin given"}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA,
                                     follow_redirects=True) as client:
            result = await _coingecko_price(client, coin_id)
            if result.get("error"):
                fallback = await _coinbase_price(client, coin_id)
                if not fallback.get("error"):
                    return fallback
                result["error"] += f"; {fallback['error']}"
            return result
    except Exception as e:
        logger.warning(f"crypto lookup failed: {e}")
        return {"error": f"crypto lookup failed: {e}"}

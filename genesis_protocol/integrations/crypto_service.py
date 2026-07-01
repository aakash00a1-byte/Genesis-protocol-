"""Genesis Protocol - Crypto Price Service

Free crypto prices using CoinGecko API (no API key required!)
Provides: BTC, ETH, and major crypto prices
"""

import requests
import logging
from datetime import datetime
from typing import Dict, Optional, List

logger = logging.getLogger("integrations.crypto")

# CoinGecko free API (no key needed)
COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class CryptoPrice:
    """Crypto price data."""
    def __init__(self, name: str, symbol: str, price: float, change_24h: float, 
                 market_cap: float = 0, volume: float = 0, icon: str = "🪙"):
        self.name = name
        self.symbol = symbol.upper()
        self.price = price
        self.change_24h = change_24h
        self.market_cap = market_cap
        self.volume = volume
        self.icon = icon
    
    def format_price(self) -> str:
        """Format price for display."""
        if self.price >= 1000:
            return f"₹{self.price:,.0f}"
        elif self.price >= 1:
            return f"₹{self.price:,.2f}"
        else:
            return f"₹{self.price:,.6f}"
    
    def format_change(self) -> str:
        """Format 24h change."""
        emoji = "📈" if self.change_24h >= 0 else "📉"
        sign = "+" if self.change_24h >= 0 else ""
        return f"{emoji} {sign}{self.change_24h:.2f}%"


class CryptoService:
    """
    Crypto price service using CoinGecko free API.
    
    Features:
    - No API key required!
    - Bitcoin, Ethereum, and major cryptos
    - INR (Indian Rupee) prices
    - 24h price change
    - Market cap and volume
    """
    
    def __init__(self):
        self._cache: Dict[str, CryptoPrice] = {}
        self._cache_time: datetime = None
        self._cache_ttl = 60  # 1 minute cache (CoinGecko rate limit)
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cache_time is None:
            return False
        elapsed = (datetime.now() - self._cache_time).total_seconds()
        return elapsed < self._cache_ttl
    
    def get_price(self, symbol: str = "bitcoin") -> Optional[CryptoPrice]:
        """Get price for a specific crypto symbol."""
        symbol_lower = symbol.lower()
        
        # Map common names to CoinGecko IDs
        symbol_map = {
            "bitcoin": "bitcoin", "btc": "bitcoin",
            "ethereum": "ethereum", "eth": "ethereum",
            "solana": "solana", "sol": "solana",
            "dogecoin": "dogecoin", "doge": "dogecoin",
            "ripple": "ripple", "xrp": "ripple",
            "cardano": "cardano", "ada": "cardano",
            "polkadot": "polkadot", "dot": "polkadot",
            "matic": "matic-network", "polygon": "matic-network",
            "avalanche": "avalanche-2", "avax": "avalanche-2",
        }
        
        coin_id = symbol_map.get(symbol_lower, symbol_lower)
        
        try:
            url = f"{COINGECKO_BASE}/simple/price"
            params = {
                "ids": coin_id,
                "vs_currencies": "inr",
                "include_24hr_change": "true",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if coin_id in data:
                    coin_data = data[coin_id]
                    inr_data = coin_data.get("inr", {})
                    
                    return CryptoPrice(
                        name=coin_id.replace("-", " ").title(),
                        symbol=coin_id,
                        price=inr_data.get("inr", 0),
                        change_24h=inr_data.get("inr_24h_change", 0),
                        market_cap=inr_data.get("inr_market_cap", 0),
                        volume=inr_data.get("inr_24h_vol", 0),
                    )
                    
        except Exception as e:
            logger.error(f"Error fetching crypto price: {e}")
        
        return None
    
    def get_top_cryptos(self, limit: int = 10) -> List[CryptoPrice]:
        """Get top cryptocurrencies by market cap."""
        if self._cache and self._is_cache_valid():
            return list(self._cache.values())[:limit]
        
        try:
            # Get top coins from CoinGecko
            url = f"{COINGECKO_BASE}/coins/markets"
            params = {
                "vs_currency": "inr",
                "order": "market_cap_desc",
                "per_page": limit,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h",
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                cryptos = []
                
                for coin in data:
                    cryptos.append(CryptoPrice(
                        name=coin.get("name", ""),
                        symbol=coin.get("symbol", ""),
                        price=coin.get("current_price", 0),
                        change_24h=coin.get("price_change_percentage_24h", 0),
                        market_cap=coin.get("market_cap", 0),
                        volume=coin.get("total_volume", 0),
                    ))
                
                self._cache = {c.symbol: c for c in cryptos}
                self._cache_time = datetime.now()
                return cryptos
                
        except Exception as e:
            logger.error(f"Error fetching top cryptos: {e}")
        
        return []
    
    def get_bitcoin_price(self) -> Optional[CryptoPrice]:
        """Get Bitcoin price specifically."""
        return self.get_price("bitcoin")
    
    def format_crypto_display(self, symbol: str = "bitcoin") -> str:
        """Get formatted crypto display string."""
        crypto = self.get_price(symbol)
        
        if not crypto:
            return "❌ Crypto price unavailable"
        
        return f"""
{crypto.icon} **{crypto.name}** ({crypto.symbol})
💰 Price: {crypto.format_price()}
{crypto.format_change()}
"""

    def format_top_cryptos(self, limit: int = 5) -> str:
        """Get formatted top cryptos display."""
        cryptos = self.get_top_cryptos(limit)
        
        if not cryptos:
            return "❌ Crypto prices unavailable"
        
        lines = ["📊 **Top Cryptocurrencies (INR)**", ""]
        
        for i, crypto in enumerate(cryptos, 1):
            lines.append(f"{i}. {crypto.icon} **{crypto.symbol}**")
            lines.append(f"   💰 {crypto.format_price()}")
            lines.append(f"   {crypto.format_change()}")
            lines.append("")
        
        return "\n".join(lines)


# Singleton instance
_crypto_service: Optional[CryptoService] = None

def get_crypto_service() -> CryptoService:
    """Get singleton instance."""
    global _crypto_service
    if _crypto_service is None:
        _crypto_service = CryptoService()
    return _crypto_service

"""
⚡ Genesis Crypto Exchange Agent ⚡
Manages crypto wallets, trading, and exchange operations
"""

import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class Exchange(Enum):
    BINANCE = "binance"
    KUCOIN = "kucoin"
    BYBIT = "bybit"
    OKX = "okx"
    GATE_IO = "gate_io"


@dataclass
class ExchangeAccount:
    exchange: Exchange
    api_key: str
    api_secret: str
    wallet_address: str
    connected: bool = False
    last_sync: Optional[str] = None


@dataclass
class TradeOrder:
    order_id: str
    exchange: Exchange
    pair: str  # e.g., "BTC/USDT"
    type: str  # "buy" or "sell"
    amount: float
    price: float
    status: str  # pending, filled, cancelled
    timestamp: str


@dataclass
class Portfolio:
    btc: float = 0.0
    usdt: float = 0.0
    eth: float = 0.0
    other: Dict[str, float] = None
    
    def __post_init__(self):
        if self.other is None:
            self.other = {}


class CryptoExchangeAgent:
    """
    Genesis Crypto Exchange Agent.
    Manages wallets across exchanges.
    """
    
    VERSION = "1.0.0"
    
    def __init__(self, storage_path: str = "./data/exchange"):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        
        self.exchanges: Dict[str, ExchangeAccount] = {}
        self.orders: List[TradeOrder] = []
        self.portfolio = Portfolio()
        
        self._load_data()
    
    def _load_data(self):
        try:
            with open(f"{self.storage_path}/exchanges.json", 'r') as f:
                data = json.load(f)
                for item in data:
                    item['exchange'] = Exchange(item['exchange'])
                    self.exchanges[item['exchange'].value] = ExchangeAccount(**item)
        except Exception:
            pass
        
        try:
            with open(f"{self.storage_path}/orders.json", 'r') as f:
                data = json.load(f)
                for item in data:
                    item['exchange'] = Exchange(item['exchange'])
                    self.orders.append(TradeOrder(**item))
        except Exception:
            pass
        
        try:
            with open(f"{self.storage_path}/portfolio.json", 'r') as f:
                self.portfolio = Portfolio(**json.load(f))
        except Exception:
            pass
    
    def _save_data(self):
        with open(f"{self.storage_path}/exchanges.json", 'w') as f:
            data = []
            for ex in self.exchanges.values():
                d = asdict(ex)
                d['exchange'] = d['exchange'].value
                data.append(d)
            json.dump(data, f, indent=2)
        
        with open(f"{self.storage_path}/orders.json", 'w') as f:
            data = []
            for o in self.orders:
                d = asdict(o)
                d['exchange'] = d['exchange'].value
                data.append(d)
            json.dump(data, f, indent=2)
        
        with open(f"{self.storage_path}/portfolio.json", 'w') as f:
            json.dump(asdict(self.portfolio), f, indent=2)
    
    def connect_exchange(
        self,
        exchange: Exchange,
        api_key: str,
        api_secret: str
    ) -> str:
        """Connect to an exchange."""
        acc = ExchangeAccount(
            exchange=exchange,
            api_key=api_key,
            api_secret=api_secret,
            wallet_address=self._generate_wallet_address(exchange),
            connected=True,
            last_sync=datetime.now().isoformat()
        )
        
        self.exchanges[exchange.value] = acc
        self._save_data()
        
        return acc.wallet_address
    
    def disconnect_exchange(self, exchange: Exchange) -> bool:
        """Disconnect from an exchange."""
        if exchange.value in self.exchanges:
            del self.exchanges[exchange.value]
            self._save_data()
            return True
        return False
    
    def _generate_wallet_address(self, exchange: Exchange) -> str:
        """Generate a wallet address (in production, fetch from exchange)."""
        return f"0x{hashlib.md5(exchange.value.encode()).hexdigest()[:40]}"
    
    def sync_portfolio(self) -> Portfolio:
        """Sync portfolio from all connected exchanges."""
        # In production, call exchange APIs
        # For now, use stored data
        
        total_btc = self.portfolio.btc
        total_usdt = self.portfolio.usdt
        total_eth = self.portfolio.eth
        
        for ex in self.exchanges.values():
            if ex.connected:
                # Simulate sync
                ex.last_sync = datetime.now().isoformat()
        
        self._save_data()
        return self.portfolio
    
    def get_portfolio_value(self) -> float:
        """Get total portfolio value in USDT."""
        # Approximate prices
        btc_price = 65000
        eth_price = 3500
        
        return (
            self.portfolio.usdt +
            (self.portfolio.btc * btc_price) +
            (self.portfolio.eth * eth_price) +
            sum(self.portfolio.other.values())
        )
    
    def place_order(
        self,
        exchange: Exchange,
        pair: str,
        order_type: str,
        amount: float,
        price: float
    ) -> Optional[str]:
        """Place a trade order."""
        if exchange.value not in self.exchanges:
            return None
        
        order_id = hashlib.md5(f"{exchange.value}{pair}{amount}{datetime.now().isoformat()}".encode()).hexdigest()[:16]
        
        order = TradeOrder(
            order_id=order_id,
            exchange=exchange,
            pair=pair,
            type=order_type,
            amount=amount,
            price=price,
            status="pending",
            timestamp=datetime.now().isoformat()
        )
        
        self.orders.append(order)
        self._save_data()
        
        return order_id
    
    def get_open_orders(self) -> List[TradeOrder]:
        """Get all open orders."""
        return [o for o in self.orders if o.status == "pending"]
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        for order in self.orders:
            if order.order_id == order_id and order.status == "pending":
                order.status = "cancelled"
                self._save_data()
                return True
        return False
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get trade history."""
        filled = [o for o in self.orders if o.status == "filled"][:limit]
        return [
            {
                "order_id": o.order_id,
                "exchange": o.exchange.value,
                "pair": o.pair,
                "type": o.type,
                "amount": o.amount,
                "price": o.price,
                "total": o.amount * o.price,
                "timestamp": o.timestamp
            }
            for o in filled
        ]
    
    def get_exchange_balances(self) -> Dict:
        """Get balances from all connected exchanges."""
        balances = {}
        for ex_id, ex in self.exchanges.items():
            if ex.connected:
                balances[ex_id] = {
                    "wallet_address": ex.wallet_address[:20] + "...",
                    "last_sync": ex.last_sync,
                    "connected": True
                }
        return balances
    
    def get_status(self) -> Dict:
        """Get exchange agent status."""
        return {
            "version": self.VERSION,
            "connected_exchanges": [ex.value for ex in self.exchanges.values() if ex.connected],
            "total_exchanges": len(self.exchanges),
            "open_orders": len(self.get_open_orders()),
            "total_orders": len(self.orders),
            "portfolio_value_usdt": self.get_portfolio_value(),
            "balances": self.get_exchange_balances()
        }


# Global singleton
_exchange_agent: Optional[CryptoExchangeAgent] = None

def get_exchange_agent() -> CryptoExchangeAgent:
    global _exchange_agent
    if _exchange_agent is None:
        _exchange_agent = CryptoExchangeAgent()
    return _exchange_agent


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║  ⚡ GENESIS CRYPTO EXCHANGE AGENT v1.0.0 ⚡    ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    agent = CryptoExchangeAgent()
    status = agent.get_status()
    
    print(f"\n🔗 Connected Exchanges: {len(status['connected_exchanges'])}")
    print(f"📋 Open Orders: {status['open_orders']}")
    print(f"💰 Portfolio Value: ${status['portfolio_value_usdt']:.2f}")

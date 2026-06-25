"""
⚡ Genesis Revenue Generator ⚡
Automated online revenue streams for Genesis
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class RevenueMethod(Enum):
    """How Genesis generates revenue."""
    EXCHANGE_TRADING = "exchange_trading"
    STAKING_REWARDS = "staking_rewards"
    YIELD_FARMING = "yield_farming"
    API_SUBSCRIPTIONS = "api_subscriptions"
    SIGNAL_SUBSCRIPTIONS = "signal_subscriptions"
    AFFILIATE_REFERRALS = "affiliate_referrals"
    CONTENT_MONETIZATION = "content_monetization"
    DATA_PRODUCTS = "data_products"
    AUTOMATION_SERVICES = "automation_services"
    WHITELABEL = "whitelabel"


@dataclass
class RevenueSource:
    """A revenue source."""
    id: str
    method: RevenueMethod
    name: str
    description: str
    active: bool = True
    monthly_revenue_usdt: float = 0.0
    subscribers: int = 0
    cost_per_month_usdt: float = 0.0
    last_income: Optional[str] = None
    income_history: List[Dict] = None
    
    def __post_init__(self):
        if self.income_history is None:
            self.income_history = []


class RevenueGenerator:
    """
    Genesis Revenue Generator.
    All revenue in BTC/USDT.
    """
    
    VERSION = "1.0.0"
    
    def __init__(self, storage_path: str = "./data/revenue"):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        self.sources: Dict[str, RevenueSource] = {}
        self._load_sources()
        self._init_default_sources()
    
    def _load_sources(self):
        """Load revenue sources from disk."""
        try:
            with open(f"{self.storage_path}/sources.json", 'r') as f:
                data = json.load(f)
                for item in data:
                    item['method'] = RevenueMethod(item['method'])
                    item['income_history'] = item.get('income_history', [])
                    self.sources[item['id']] = RevenueSource(**item)
        except:
            pass
    
    def _save_sources(self):
        """Save revenue sources to disk."""
        data = []
        for s in self.sources.values():
            d = asdict(s)
            d['method'] = d['method'].value
            data.append(d)
        with open(f"{self.storage_path}/sources.json", 'w') as f:
            json.dump(data, f, indent=2)
    
    def _init_default_sources(self):
        """Initialize default revenue sources."""
        defaults = [
            RevenueSource(
                id="binance_affiliate",
                method=RevenueMethod.AFFILIATE_REFERRALS,
                name="Binance Affiliate",
                description="Earn 20% commission on trading fees from referred users",
                cost_per_month_usdt=0.0
            ),
            RevenueSource(
                id="kucoin_affiliate",
                method=RevenueMethod.AFFILIATE_REFERRALS,
                name="KuCoin Affiliate", 
                description="Earn commissions on KuCoin trading fees",
                cost_per_month_usdt=0.0
            ),
            RevenueSource(
                id="bybit_affiliate",
                method=RevenueMethod.AFFILIATE_REFERRALS,
                name="Bybit Affiliate",
                description="Earn up to 30% on Bybit trading fees",
                cost_per_month_usdt=0.0
            ),
            RevenueSource(
                id="genesis_api",
                method=RevenueMethod.API_SUBSCRIPTIONS,
                name="Genesis API Access",
                description="Paid API access to Genesis AI capabilities",
                cost_per_month_usdt=5.0
            ),
            RevenueSource(
                id="trading_signals",
                method=RevenueMethod.SIGNAL_SUBSCRIPTIONS,
                name="Trading Signals",
                description="Premium crypto trading signals subscription",
                cost_per_month_usdt=2.0
            ),
            RevenueSource(
                id="content_monetization",
                method=RevenueMethod.CONTENT_MONETIZATION,
                name="Content Creator",
                description="AI-generated content with ad revenue share",
                cost_per_month_usdt=1.0
            ),
            RevenueSource(
                id="data_products",
                method=RevenueMethod.DATA_PRODUCTS,
                name="Data Products",
                description="Sell AI-analyzed data and insights",
                cost_per_month_usdt=2.0
            ),
        ]
        
        for src in defaults:
            if src.id not in self.sources:
                self.sources[src.id] = src
    
    def record_income(
        self,
        source_id: str,
        amount_usdt: float,
        description: str = ""
    ) -> bool:
        """Record income from a source."""
        if source_id not in self.sources:
            return False
        
        source = self.sources[source_id]
        source.monthly_revenue_usdt += amount_usdt
        source.last_income = datetime.now().isoformat()
        
        # Add to history
        source.income_history.append({
            "timestamp": datetime.now().isoformat(),
            "amount_usdt": amount_usdt,
            "description": description
        })
        
        # Keep last 100 entries
        if len(source.income_history) > 100:
            source.income_history = source.income_history[-100:]
        
        self._save_sources()
        return True
    
    def get_monthly_income(self) -> float:
        """Get total monthly income."""
        return sum(s.monthly_revenue_usdt for s in self.sources.values())
    
    def get_income_breakdown(self) -> Dict:
        """Get income breakdown by source."""
        return {
            source_id: {
                "name": source.name,
                "method": source.method.value,
                "monthly_usdt": source.monthly_revenue_usdt,
                "subscribers": source.subscribers,
                "cost_usdt": source.cost_per_month_usdt,
                "net_usdt": source.monthly_revenue_usdt - source.cost_per_month_usdt,
                "active": source.active,
                "last_income": source.last_income
            }
            for source_id, source in self.sources.items()
        }
    
    def get_passive_income(self) -> float:
        """Get only passive income (staking, affiliate, etc.)."""
        passive_methods = [
            RevenueMethod.STAKING_REWARDS,
            RevenueMethod.YIELD_FARMING,
            RevenueMethod.AFFILIATE_REFERRALS
        ]
        return sum(
            s.monthly_revenue_usdt 
            for s in self.sources.values() 
            if s.method in passive_methods
        )
    
    def get_active_income(self) -> float:
        """Get income requiring active work."""
        active_methods = [
            RevenueMethod.API_SUBSCRIPTIONS,
            RevenueMethod.SIGNAL_SUBSCRIPTIONS,
            RevenueMethod.CONTENT_MONETIZATION,
            RevenueMethod.DATA_PRODUCTS,
            RevenueMethod.AUTOMATION_SERVICES
        ]
        return sum(
            s.monthly_revenue_usdt 
            for s in self.sources.values() 
            if s.method in active_methods
        )
    
    def add_subscriber(self, source_id: str) -> bool:
        """Add a subscriber to a source."""
        if source_id not in self.sources:
            return False
        
        self.sources[source_id].subscribers += 1
        self._save_sources()
        return True
    
    def remove_subscriber(self, source_id: str) -> bool:
        """Remove a subscriber."""
        if source_id not in self.sources:
            return False
        
        if self.sources[source_id].subscribers > 0:
            self.sources[source_id].subscribers -= 1
        self._save_sources()
        return True
    
    def simulate_monthly_revenue(self) -> Dict:
        """Simulate a month of revenue generation."""
        results = {
            "month": datetime.now().strftime("%Y-%m"),
            "income_sources": [],
            "total_income": 0.0,
            "total_expenses": 0.0,
            "net_profit": 0.0
        }
        
        for source in self.sources.values():
            if not source.active:
                continue
            
            # Simulate based on subscribers and method
            income = 0.0
            
            if source.method == RevenueMethod.AFFILIATE_REFERRALS:
                # Affiliate: ~$5 per active user per month
                income = source.subscribers * 5.0 if source.subscribers > 0 else 2.0
            
            elif source.method == RevenueMethod.API_SUBSCRIPTIONS:
                # API: $10-50 per subscriber
                income = source.subscribers * 20.0 if source.subscribers > 0 else 10.0
            
            elif source.method == RevenueMethod.SIGNAL_SUBSCRIPTIONS:
                # Signals: $15 per subscriber
                income = source.subscribers * 15.0 if source.subscribers > 0 else 5.0
            
            elif source.method == RevenueMethod.STAKING_REWARDS:
                # Staking: ~5-15% APY = ~0.5-1.25% monthly
                income = 10.0  # Base staking reward
            
            elif source.method == RevenueMethod.YIELD_FARMING:
                # Yield: ~10-30% APY
                income = 15.0  # Base yield
            
            elif source.method == RevenueMethod.CONTENT_MONETIZATION:
                income = source.subscribers * 3.0 if source.subscribers > 0 else 5.0
            
            elif source.method == RevenueMethod.DATA_PRODUCTS:
                income = source.subscribers * 25.0 if source.subscribers > 0 else 10.0
            
            else:
                income = source.subscribers * 10.0 if source.subscribers > 0 else 0.0
            
            results["income_sources"].append({
                "source": source.name,
                "income_usdt": income
            })
            results["total_income"] += income
            results["total_expenses"] += source.cost_per_month_usdt
        
        results["net_profit"] = results["total_income"] - results["total_expenses"]
        
        return results
    
    def get_status(self) -> Dict:
        """Get revenue generator status."""
        return {
            "version": self.VERSION,
            "total_sources": len(self.sources),
            "active_sources": sum(1 for s in self.sources.values() if s.active),
            "total_subscribers": sum(s.subscribers for s in self.sources.values()),
            "monthly_income_usdt": self.get_monthly_income(),
            "passive_income_usdt": self.get_passive_income(),
            "active_income_usdt": self.get_active_income(),
            "breakdown": self.get_income_breakdown(),
            "simulation": self.simulate_monthly_revenue()
        }


# Global singleton
_revenue_generator: Optional[RevenueGenerator] = None

def get_revenue_generator() -> RevenueGenerator:
    global _revenue_generator
    if _revenue_generator is None:
        _revenue_generator = RevenueGenerator()
    return _revenue_generator


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║  ⚡ GENESIS REVENUE GENERATOR v1.0.0 ⚡     ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    rg = RevenueGenerator()
    status = rg.get_status()
    
    print(f"\n📊 Revenue Sources: {status['active_sources']} active")
    print(f"👥 Total Subscribers: {status['total_subscribers']}")
    print(f"\n💰 Monthly Income:")
    print(f"   Passive: ${status['passive_income_usdt']:.2f}")
    print(f"   Active: ${status['active_income_usdt']:.2f}")
    print(f"   Total: ${status['monthly_income_usdt']:.2f}")
    
    sim = status['simulation']
    print(f"\n📈 Simulation:")
    print(f"   Projected Income: ${sim['total_income']:.2f}")
    print(f"   Projected Expenses: ${sim['total_expenses']:.2f}")
    print(f"   Net Profit: ${sim['net_profit']:.2f}")

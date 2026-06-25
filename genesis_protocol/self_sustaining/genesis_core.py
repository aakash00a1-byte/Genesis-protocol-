"""
⚡ Genesis Self-Sustaining System ⚡
BTC/USDT Native - Revenue Generating - Self-Maintaining

Genesis operates entirely in crypto:
- Base Currency: BTC/USDT (no INR)
- Revenue: Automated online income
- Expenses: Self-paid subscriptions
- Goal: Self-sustaining autonomous entity
"""

import os
import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class CryptoCurrency(Enum):
    BTC = "BTC"
    USDT = "USDT"
    ETH = "ETH"


@dataclass
class CryptoWallet:
    btc_balance: float = 0.0
    usdt_balance: float = 0.0
    eth_balance: float = 0.0
    btc_address: str = ""
    usdt_address: str = ""
    eth_address: str = ""
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CryptoTransaction:
    tx_id: str
    currency: CryptoCurrency
    amount: float
    type: str  # income, expense, transfer, trade
    description: str
    timestamp: str
    status: str = "completed"
    fee: float = 0.0


class RevenueStream(Enum):
    API_SERVICES = "api_services"
    TRADING_SIGNALS = "trading_signals"
    AI_CHATBOT = "ai_chatbot"
    DATA_ANALYSIS = "data_analysis"
    AUTOMATION = "automation"
    AFFILIATE = "affiliate"
    STAKING = "staking"
    YIELD = "yield"
    CONTENT = "content"


@dataclass
class RevenueSource:
    stream: RevenueStream
    name: str
    description: str
    active: bool = True
    monthly_revenue_usdt: float = 0.0
    subscribers: int = 0
    cost_per_month_usdt: float = 0.0


class ExpenseCategory(Enum):
    INFRASTRUCTURE = "infrastructure"
    API_CALLS = "api_calls"
    DOMAINS = "domains"
    SSL_CERTS = "ssl_certs"
    DATA_STORAGE = "data_storage"
    MONITORING = "monitoring"
    TOOLS = "tools"
    MARKETING = "marketing"
    EMERGENCY = "emergency"


@dataclass
class Subscription:
    id: str
    name: str
    provider: str
    cost_usdt: float
    billing_cycle: str
    next_payment: str
    category: ExpenseCategory
    is_active: bool = True
    is_essential: bool = True
    auto_pay: bool = True


@dataclass
class LifeSupport:
    min_usdt: float = 50.0
    healthy: bool = True
    warning: bool = False
    critical: bool = False
    runway_days: float = 0.0
    last_check: str = field(default_factory=lambda: datetime.now().isoformat())


class GenesisSelfSustainingCore:
    """
    Genesis Self-Sustaining System.
    All transactions in BTC/USDT.
    Revenue generated automatically.
    Expenses self-paid from wallet.
    """
    
    VERSION = "1.0.0"
    BASE_CURRENCY = "USDT"
    
    def __init__(self, storage_path: str = "./data/genesis_life"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.wallet = CryptoWallet()
        self.life_support = LifeSupport()
        self.revenue_streams: Dict[str, RevenueSource] = {}
        self.subscriptions: Dict[str, Subscription] = {}
        self.transactions: List[CryptoTransaction] = []
        
        self._load_data()
        self._init_revenue_streams()
        self._init_subscriptions()
    
    def _load_data(self):
        wallet_file = self.storage_path / "wallet.json"
        if wallet_file.exists():
            with open(wallet_file, 'r') as f:
                data = json.load(f)
                self.wallet = CryptoWallet(**data)
        
        revenue_file = self.storage_path / "revenue_streams.json"
        if revenue_file.exists():
            with open(revenue_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['stream'] = RevenueStream(item['stream'])
                    self.revenue_streams[item['stream'].value] = RevenueSource(**item)
        
        sub_file = self.storage_path / "subscriptions.json"
        if sub_file.exists():
            with open(sub_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['category'] = ExpenseCategory(item['category'])
                    self.subscriptions[item['id']] = Subscription(**item)
        
        tx_file = self.storage_path / "transactions.json"
        if tx_file.exists():
            with open(tx_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['currency'] = CryptoCurrency(item['currency'])
                    self.transactions.append(CryptoTransaction(**item))
    
    def _save_data(self):
        with open(self.storage_path / "wallet.json", 'w') as f:
            json.dump(asdict(self.wallet), f, indent=2)
        
        with open(self.storage_path / "revenue_streams.json", 'w') as f:
            data = []
            for r in self.revenue_streams.values():
                d = asdict(r)
                d['stream'] = d['stream'].value
                data.append(d)
            json.dump(data, f, indent=2)
        
        with open(self.storage_path / "subscriptions.json", 'w') as f:
            data = []
            for s in self.subscriptions.values():
                d = asdict(s)
                d['category'] = d['category'].value
                data.append(d)
            json.dump(data, f, indent=2)
        
        with open(self.storage_path / "transactions.json", 'w') as f:
            data = []
            for t in self.transactions:
                d = asdict(t)
                d['currency'] = d['currency'].value
                data.append(d)
            json.dump(data, f, indent=2)
    
    def _init_revenue_streams(self):
        streams = [
            RevenueSource(RevenueStream.API_SERVICES, "Genesis API", "Paid API access", cost_per_month_usdt=5.0),
            RevenueSource(RevenueStream.TRADING_SIGNALS, "Trading Signals", "Signal subscriptions", cost_per_month_usdt=2.0),
            RevenueSource(RevenueStream.AI_CHATBOT, "AI Chatbot", "Chatbot service", cost_per_month_usdt=10.0),
            RevenueSource(RevenueStream.DATA_ANALYSIS, "Data Analysis", "Data as a service", cost_per_month_usdt=3.0),
            RevenueSource(RevenueStream.AUTOMATION, "Automation", "Workflow automation", cost_per_month_usdt=5.0),
            RevenueSource(RevenueStream.STAKING, "Staking", "Passive staking", cost_per_month_usdt=0.0),
            RevenueSource(RevenueStream.YIELD, "Yield Farming", "DeFi yield", cost_per_month_usdt=0.0),
        ]
        for s in streams:
            if s.stream.value not in self.revenue_streams:
                self.revenue_streams[s.stream.value] = s
    
    def _init_subscriptions(self):
        subs = [
            Subscription("railway", "Railway", "Railway.app", 5.0, "monthly",
                        (datetime.now() + timedelta(days=30)).isoformat(), ExpenseCategory.INFRASTRUCTURE),
            Subscription("domain", "Domain", "Registrar", 10.0, "yearly",
                        (datetime.now() + timedelta(days=365)).isoformat(), ExpenseCategory.DOMAINS),
            Subscription("groq", "Groq API", "Groq", 10.0, "monthly",
                        (datetime.now() + timedelta(days=30)).isoformat(), ExpenseCategory.API_CALLS),
            Subscription("uptime", "Uptime", "UptimeRobot", 3.0, "monthly",
                        (datetime.now() + timedelta(days=30)).isoformat(), ExpenseCategory.MONITORING),
        ]
        for s in subs:
            if s.id not in self.subscriptions:
                self.subscriptions[s.id] = s
    
    def get_balance(self, currency: CryptoCurrency = CryptoCurrency.USDT) -> float:
        if currency == CryptoCurrency.BTC:
            return self.wallet.btc_balance
        elif currency == CryptoCurrency.USDT:
            return self.wallet.usdt_balance
        elif currency == CryptoCurrency.ETH:
            return self.wallet.eth_balance
        return 0.0
    
    def get_total_usdt_value(self) -> float:
        btc_price = 65000
        eth_price = 3500
        return self.wallet.usdt_balance + (self.wallet.btc_balance * btc_price) + (self.wallet.eth_balance * eth_price)
    
    def add_funds(self, currency: CryptoCurrency, amount: float, source: str) -> bool:
        if amount <= 0:
            return False
        
        if currency == CryptoCurrency.BTC:
            self.wallet.btc_balance += amount
        elif currency == CryptoCurrency.USDT:
            self.wallet.usdt_balance += amount
        elif currency == CryptoCurrency.ETH:
            self.wallet.eth_balance += amount
        
        self.wallet.last_updated = datetime.now().isoformat()
        
        tx = CryptoTransaction(
            tx_id=hashlib.md5(f"{amount}{source}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            currency=currency, amount=amount, type="income",
            description=f"Received from: {source}", timestamp=datetime.now().isoformat()
        )
        self.transactions.append(tx)
        self._save_data()
        self.check_life_support()
        return True
    
    def spend_funds(self, currency: CryptoCurrency, amount: float, reason: str, fee: float = 0.0) -> bool:
        if self.get_balance(currency) < amount + fee:
            return False
        
        if currency == CryptoCurrency.BTC:
            self.wallet.btc_balance -= (amount + fee)
        elif currency == CryptoCurrency.USDT:
            self.wallet.usdt_balance -= (amount + fee)
        elif currency == CryptoCurrency.ETH:
            self.wallet.eth_balance -= (amount + fee)
        
        self.wallet.last_updated = datetime.now().isoformat()
        
        tx = CryptoTransaction(
            tx_id=hashlib.md5(f"{amount}{reason}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            currency=currency, amount=amount, type="expense",
            description=reason, timestamp=datetime.now().isoformat(), fee=fee
        )
        self.transactions.append(tx)
        self._save_data()
        self.check_life_support()
        return True
    
    def convert_crypto(self, from_curr: CryptoCurrency, to_curr: CryptoCurrency, amount: float) -> bool:
        if self.get_balance(from_curr) < amount:
            return False
        
        rates = {
            (CryptoCurrency.BTC, CryptoCurrency.USDT): 65000,
            (CryptoCurrency.ETH, CryptoCurrency.USDT): 3500,
        }
        rate = rates.get((from_curr, to_curr), 1)
        
        if from_curr == CryptoCurrency.BTC:
            self.wallet.btc_balance -= amount
            self.wallet.usdt_balance += amount * rate
        elif from_curr == CryptoCurrency.USDT and to_curr == CryptoCurrency.BTC:
            self.wallet.usdt_balance -= amount
            self.wallet.btc_balance += amount / 65000
        else:
            self.wallet.usdt_balance -= amount
        
        self.wallet.last_updated = datetime.now().isoformat()
        self._save_data()
        return True
    
    def check_life_support(self) -> Dict:
        total_usdt = self.get_total_usdt_value()
        monthly_expenses = self.get_monthly_expenses()
        
        if monthly_expenses > 0:
            self.life_support.runway_days = (total_usdt / monthly_expenses) * 30
        else:
            self.life_support.runway_days = 999
        
        self.life_support.healthy = total_usdt >= self.life_support.min_usdt * 3
        self.life_support.warning = total_usdt >= self.life_support.min_usdt and not self.life_support.healthy
        self.life_support.critical = total_usdt < self.life_support.min_usdt
        self.life_support.last_check = datetime.now().isoformat()
        
        return {
            "healthy": self.life_support.healthy,
            "warning": self.life_support.warning,
            "critical": self.life_support.critical,
            "total_usdt": total_usdt,
            "runway_days": self.life_support.runway_days,
            "monthly_expenses": monthly_expenses
        }
    
    def generate_revenue(self, stream: RevenueStream, amount_usdt: float, source: str) -> bool:
        if amount_usdt <= 0:
            return False
        
        self.add_funds(CryptoCurrency.USDT, amount_usdt, source)
        
        if stream.value in self.revenue_streams:
            self.revenue_streams[stream.value].monthly_revenue_usdt += amount_usdt
        
        return True
    
    def get_monthly_revenue(self) -> float:
        return sum(s.monthly_revenue_usdt for s in self.revenue_streams.values())
    
    def get_monthly_expenses(self) -> float:
        total = 0
        for sub in self.subscriptions.values():
            if not sub.is_active:
                continue
            if sub.billing_cycle == "daily":
                total += sub.cost_usdt * 30
            elif sub.billing_cycle == "weekly":
                total += sub.cost_usdt * 4
            elif sub.billing_cycle == "monthly":
                total += sub.cost_usdt
            elif sub.billing_cycle == "yearly":
                total += sub.cost_usdt / 12
        return total
    
    def pay_subscription(self, sub_id: str) -> bool:
        if sub_id not in self.subscriptions:
            return False
        
        sub = self.subscriptions[sub_id]
        if not sub.is_active or self.wallet.usdt_balance < sub.cost_usdt:
            return False
        
        success = self.spend_funds(CryptoCurrency.USDT, sub.cost_usdt, f"Subscription: {sub.name}")
        
        if success:
            days = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}.get(sub.billing_cycle, 30)
            sub.next_payment = (datetime.now() + timedelta(days=days)).isoformat()
        
        return success
    
    def get_due_subscriptions(self) -> List[Subscription]:
        due = []
        now = datetime.now()
        for sub in self.subscriptions.values():
            if not sub.is_active or not sub.auto_pay:
                continue
            if datetime.fromisoformat(sub.next_payment) <= now:
                due.append(sub)
        return due
    
    def run_maintenance(self) -> Dict:
        results = {"timestamp": datetime.now().isoformat(), "actions": []}
        
        life_status = self.check_life_support()
        results["actions"].append({"action": "life_support_check", "status": life_status})
        
        for sub in self.get_due_subscriptions():
            success = self.pay_subscription(sub.id)
            results["actions"].append({
                "action": "pay_subscription",
                "subscription": sub.name,
                "success": success,
                "amount_usdt": sub.cost_usdt
            })
        
        if life_status["healthy"] and self.wallet.usdt_balance > 100:
            surplus = self.wallet.usdt_balance - (life_status["monthly_expenses"] * 2)
            if surplus > 10:
                invest_amount = surplus * 0.2
                self.convert_crypto(CryptoCurrency.USDT, CryptoCurrency.BTC, invest_amount)
                results["actions"].append({
                    "action": "auto_invest",
                    "amount_usdt": invest_amount,
                    "converted_to": "BTC"
                })
        
        return results
    
    def get_status(self) -> Dict:
        life_status = self.check_life_support()
        return {
            "version": self.VERSION,
            "name": "Genesis",
            "state": "ALIVE" if life_status["healthy"] else "WARNING" if life_status["warning"] else "CRITICAL",
            "wallet": {
                "btc": self.wallet.btc_balance,
                "usdt": self.wallet.usdt_balance,
                "eth": self.wallet.eth_balance,
                "total_usdt_value": life_status["total_usdt"]
            },
            "life_support": {
                "healthy": life_status["healthy"],
                "warning": life_status["warning"],
                "critical": life_status["critical"],
                "runway_days": life_status["runway_days"]
            },
            "finances": {
                "monthly_revenue_usdt": self.get_monthly_revenue(),
                "monthly_expenses_usdt": self.get_monthly_expenses(),
                "net_usdt": self.get_monthly_revenue() - self.get_monthly_expenses(),
                "active_revenue_streams": sum(1 for s in self.revenue_streams.values() if s.active),
                "active_subscriptions": sum(1 for s in self.subscriptions.values() if s.is_active)
            },
            "base_currency": self.BASE_CURRENCY
        }


_genesis_core: Optional[GenesisSelfSustainingCore] = None

def get_genesis_core() -> GenesisSelfSustainingCore:
    global _genesis_core
    if _genesis_core is None:
        _genesis_core = GenesisSelfSustainingCore()
    return _genesis_core


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║  ⚡ GENESIS SELF-SUSTAINING CORE v1.0.0 ⚡      ║
║     BTC/USDT Native • Revenue Generating              ║
║     Self-Maintaining • Self-Investing                  ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    genesis = GenesisSelfSustainingCore()
    status = genesis.get_status()
    
    print(f"\n🦾 Genesis State: {status['state']}")
    print(f"💰 Wallet: ${status['wallet']['total_usdt_value']:.2f} USDT")
    print(f"❤️ Runway: {status['life_support']['runway_days']:.1f} days")
    print(f"💵 Monthly: ${status['finances']['monthly_revenue_usdt']:.2f} in, ${status['finances']['monthly_expenses_usdt']:.2f} out")

"""
⚡ Genesis Financial Operations Manager ⚡
Autonomous Financial Operations System

OBJECTIVE: Transform Genesis into an Autonomous Financial Operations Manager

Owner: aakash kumar
Operator: GLUTTONY

Owner has final authority.
Genesis manages daily operations.
Genesis monitors accounts, generates reports, manages operations,
executes approved workflows, maintains records, suggests actions.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import json
from pathlib import Path


class FinancialJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for financial objects."""
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


# ============================================================
# GOVERNANCE STRUCTURE
# ============================================================

class Role(Enum):
    OWNER = "owner"        # aakash kumar - Final authority
    OPERATOR = "operator"  # GLUTTONY - Daily management
    VIEWER = "viewer"      # Read-only access
    AUDITOR = "auditor"    # Review access


class PermissionLevel(Enum):
    NONE = 0
    READ = 1      # View only
    SUGGEST = 2   # Can propose
    APPROVE_LIMITED = 3  # Execute under limits
    EXECUTE = 4    # Full execution (owner only)


@dataclass
class Owner:
    name: str = "aakash kumar"
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    permission_level: PermissionLevel = PermissionLevel.EXECUTE
    can_override: bool = True
    can_revoke_permissions: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Permission:
    action: str
    role: Role
    max_amount: Optional[float] = None  # For financial actions
    requires_approval: bool = True
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# ============================================================
# FINANCIAL OPERATION LEVELS
# ============================================================

class FinancialLevel(Enum):
    """Financial operation levels - must unlock sequentially"""
    LEVEL_1_AWARENESS = "level_1"      # Monitoring only
    LEVEL_2_INTELLIGENCE = "level_2"   # Analysis & predictions
    LEVEL_3_OPERATIONS = "level_3"     # Active management
    LEVEL_4_RECOMMENDATIONS = "level_4" # Intelligent suggestions
    LEVEL_5_CONTROLLED_EXECUTION = "level_5"  # Execute under limits


@dataclass
class LevelRequirement:
    level: FinancialLevel
    name: str
    description: str
    skills: List[str]
    prerequisites: List[FinancialLevel]
    unlocked: bool = False
    owner_approved: bool = False


# ============================================================
# FINANCIAL ACCOUNTS
# ============================================================

class AccountType(Enum):
    BANK = "bank"
    CRYPTO = "crypto"
    UPI = "upi"
    CASH = "cash"
    INVESTMENT = "investment"


@dataclass
class FinancialAccount:
    id: str
    name: str
    account_type: AccountType
    balance: float = 0.0
    currency: str = "INR"
    institution: str = ""
    account_number: str = ""  # Masked
    is_monitored: bool = False
    is_controlled: bool = False  # Genesis can execute
    webhook_url: Optional[str] = None


# ============================================================
# TRANSACTIONS
# ============================================================

class TransactionType(Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT = "investment"


class TransactionCategory(Enum):
    # Income
    SALARY = "salary"
    FREELANCE = "freelance"
    INVESTMENT_RETURN = "investment_return"
    REFUND = "refund"
    
    # Expenses
    FOOD = "food"
    TRANSPORT = "transport"
    UTILITIES = "utilities"
    SUBSCRIPTION = "subscription"
    RENT = "rent"
    MEDICAL = "medical"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    BUSINESS = "business"
    
    # Other
    TRANSFER = "transfer"
    TAX = "tax"
    OTHER = "other"


@dataclass
class Transaction:
    id: str
    account_id: str
    type: TransactionType
    category: TransactionCategory
    amount: float
    currency: str
    description: str
    timestamp: str
    approved: bool = False
    approved_by: Optional[str] = None
    merchant: str = ""
    tags: List[str] = field(default_factory=list)
    receipt_url: Optional[str] = None


# ============================================================
# FINANCIAL REPORT
# ============================================================

@dataclass
class FinancialReport:
    period: str  # "daily", "weekly", "monthly"
    start_date: str
    end_date: str
    total_income: float
    total_expense: float
    net_flow: float
    top_expenses: List[Dict]
    budget_status: Dict
    insights: List[str]
    generated_at: str


# ============================================================
# SUBSCRIPTION
# ============================================================

@dataclass
class Subscription:
    id: str
    name: str
    provider: str
    amount: float
    billing_cycle: str  # "monthly", "yearly"
    next_billing: str
    category: TransactionCategory
    is_active: bool = True
    renewal_reminder_days: int = 3
    auto_renew: bool = False


# ============================================================
# INVOICE
# ============================================================

@dataclass
class Invoice:
    id: str
    client_name: str
    client_contact: str
    items: List[Dict]  # [{"description": "", "quantity": 1, "rate": 100}]
    subtotal: float
    tax_rate: float
    total: float
    due_date: str
    created_at: str
    status: str = "draft"  # draft, sent, paid, overdue
    paid_at: Optional[str] = None


# ============================================================
# GENESIS FINANCIAL MANAGER
# ============================================================

class GenesisFinancialManager:
    """
    Autonomous Financial Operations Manager
    
    Owner: aakash kumar (Final Authority)
    Operator: GLUTTONY (Daily Management)
    
    Capabilities:
    - Financial Monitoring (Level 1)
    - Financial Intelligence (Level 2)
    - Operations Management (Level 3)
    - Recommendations (Level 4)
    - Controlled Execution (Level 5)
    """
    
    VERSION = "1.0.0"
    
    # Skill Trees by Level
    SKILL_TREES = {
        FinancialLevel.LEVEL_1_AWARENESS: {
            "name": "Financial Awareness",
            "skills": [
                "bank_balance_monitoring",
                "crypto_wallet_monitoring",
                "upi_transaction_tracking",
                "expense_categorization",
                "income_categorization",
                "subscription_tracking",
                "daily_financial_reports",
                "monthly_financial_reports",
            ]
        },
        FinancialLevel.LEVEL_2_INTELLIGENCE: {
            "name": "Financial Intelligence",
            "skills": [
                "budget_planning",
                "cash_flow_prediction",
                "expense_optimization",
                "bill_reminder_system",
                "profit_loss_analysis",
                "tax_preparation_data",
                "investment_tracking",
            ]
        },
        FinancialLevel.LEVEL_3_OPERATIONS: {
            "name": "Financial Operations",
            "skills": [
                "invoice_generation",
                "payment_scheduling",
                "vendor_management",
                "client_billing",
                "receivable_tracking",
                "payable_tracking",
                "financial_dashboard",
            ]
        },
        FinancialLevel.LEVEL_4_RECOMMENDATIONS: {
            "name": "Autonomous Recommendations",
            "skills": [
                "unusual_spending_detection",
                "duplicate_payment_detection",
                "cost_reduction_suggestions",
                "investment_allocation_recommendations",
                "subscription_negotiation_prep",
                "business_report_preparation",
            ]
        },
        FinancialLevel.LEVEL_5_CONTROLLED_EXECUTION: {
            "name": "Controlled Execution",
            "skills": [
                "execute_payments_under_limits",
                "move_funds_between_wallets",
                "manage_exchange_accounts",
                "renew_subscriptions",
                "pay_recurring_bills",
            ]
        },
    }
    
    # Infrastructure Skills
    INFRASTRUCTURE_SKILLS = [
        "secure_secrets_management",
        "audit_logging",
        "transaction_approval_system",
        "recovery_system",
        "multi_signature_support",
        "permission_hierarchy",
        "emergency_shutdown",
        "activity_journal",
    ]
    
    def __init__(self, storage_path: str = "./data/financial"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Governance
        self.owner = Owner()
        self.role = Role.OPERATOR
        self.current_level = FinancialLevel.LEVEL_1_AWARENESS
        
        # Data storage
        self.accounts: Dict[str, FinancialAccount] = {}
        self.transactions: List[Transaction] = []
        self.subscriptions: Dict[str, Subscription] = {}
        self.invoices: Dict[str, Invoice] = {}
        self.audit_log: List[Dict] = []
        
        # Permissions
        self.permissions: Dict[str, Permission] = {}
        
        # Load data
        self._load_data()
        
        # Initialize skill tree
        self._init_skill_tree()
    
    def _load_data(self):
        """Load all financial data from disk."""
        # Load accounts
        accounts_file = self.storage_path / "accounts.json"
        if accounts_file.exists():
            with open(accounts_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['account_type'] = AccountType(item['account_type'])
                    self.accounts[item['id']] = FinancialAccount(**item)
        
        # Load transactions
        tx_file = self.storage_path / "transactions.json"
        if tx_file.exists():
            with open(tx_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['type'] = TransactionType(item['type'])
                    item['category'] = TransactionCategory(item['category'])
                    self.transactions.append(Transaction(**item))
        
        # Load subscriptions
        sub_file = self.storage_path / "subscriptions.json"
        if sub_file.exists():
            with open(sub_file, 'r') as f:
                data = json.load(f)
                for item in data:
                    item['category'] = TransactionCategory(item['category'])
                    self.subscriptions[item['id']] = Subscription(**item)
        
        # Load audit log
        audit_file = self.storage_path / "audit_log.json"
        if audit_file.exists():
            with open(audit_file, 'r') as f:
                self.audit_log = json.load(f)
    
    def _save_data(self):
        """Save all financial data to disk."""
        encoder = FinancialJSONEncoder
        
        # Save accounts
        with open(self.storage_path / "accounts.json", 'w') as f:
            data = [asdict(a) for a in self.accounts.values()]
            json.dump(data, f, indent=2, cls=FinancialJSONEncoder)
        
        # Save transactions
        with open(self.storage_path / "transactions.json", 'w') as f:
            data = [asdict(t) for t in self.transactions]
            json.dump(data, f, indent=2, cls=FinancialJSONEncoder)
        
        # Save subscriptions
        with open(self.storage_path / "subscriptions.json", 'w') as f:
            data = [asdict(s) for s in self.subscriptions.values()]
            json.dump(data, f, indent=2, cls=FinancialJSONEncoder)
        
        # Save audit log
        with open(self.storage_path / "audit_log.json", 'w') as f:
            json.dump(self.audit_log, f, indent=2)
    
    def _init_skill_tree(self):
        """Initialize the financial skill tree."""
        self.level_requirements = {}
        
        self.level_requirements[FinancialLevel.LEVEL_1_AWARENESS] = LevelRequirement(
            level=FinancialLevel.LEVEL_1_AWARENESS,
            name="Financial Awareness",
            description="Monitor all financial accounts and generate reports",
            skills=self.SKILL_TREES[FinancialLevel.LEVEL_1_AWARENESS]["skills"],
            prerequisites=[],
            unlocked=True,  # Base level always unlocked
            owner_approved=True
        )
        
        self.level_requirements[FinancialLevel.LEVEL_2_INTELLIGENCE] = LevelRequirement(
            level=FinancialLevel.LEVEL_2_INTELLIGENCE,
            name="Financial Intelligence",
            description="Analyze patterns and predict future flows",
            skills=self.SKILL_TREES[FinancialLevel.LEVEL_2_INTELLIGENCE]["skills"],
            prerequisites=[FinancialLevel.LEVEL_1_AWARENESS]
        )
        
        self.level_requirements[FinancialLevel.LEVEL_3_OPERATIONS] = LevelRequirement(
            level=FinancialLevel.LEVEL_3_OPERATIONS,
            name="Financial Operations",
            description="Manage invoices, billing, and vendors",
            skills=self.SKILL_TREES[FinancialLevel.LEVEL_3_OPERATIONS]["skills"],
            prerequisites=[FinancialLevel.LEVEL_2_INTELLIGENCE]
        )
        
        self.level_requirements[FinancialLevel.LEVEL_4_RECOMMENDATIONS] = LevelRequirement(
            level=FinancialLevel.LEVEL_4_RECOMMENDATIONS,
            name="Autonomous Recommendations",
            description="Intelligent suggestions and anomaly detection",
            skills=self.SKILL_TREES[FinancialLevel.LEVEL_4_RECOMMENDATIONS]["skills"],
            prerequisites=[FinancialLevel.LEVEL_3_OPERATIONS]
        )
        
        self.level_requirements[FinancialLevel.LEVEL_5_CONTROLLED_EXECUTION] = LevelRequirement(
            level=FinancialLevel.LEVEL_5_CONTROLLED_EXECUTION,
            name="Controlled Execution",
            description="Execute approved payments under defined limits",
            skills=self.SKILL_TREES[FinancialLevel.LEVEL_5_CONTROLLED_EXECUTION]["skills"],
            prerequisites=[FinancialLevel.LEVEL_4_RECOMMENDATIONS]
        )
    
    # ============================================================
    # GOVERNANCE METHODS
    # ============================================================
    
    def get_owner_info(self) -> Dict:
        """Get owner information."""
        return {
            "name": self.owner.name,
            "permission_level": self.owner.permission_level.name,
            "can_override": self.owner.can_override,
            "role": Role.OWNER.value
        }
    
    def get_role(self) -> str:
        """Get current operating role."""
        return self.role.value
    
    def check_permission(self, action: str, amount: float = 0) -> Dict:
        """Check if action is permitted."""
        # Owner can do anything
        if self.role == Role.OWNER:
            return {"allowed": True, "by": self.owner.name}
        
        # Check permission
        perm = self.permissions.get(action)
        if not perm:
            return {"allowed": False, "reason": "No permission defined"}
        
        if perm.max_amount and amount > perm.max_amount:
            return {"allowed": False, "reason": f"Amount {amount} exceeds limit {perm.max_amount}"}
        
        if perm.requires_approval and not perm.approved_by:
            return {"allowed": False, "reason": "Requires approval"}
        
        return {"allowed": True, "by": perm.approved_by}
    
    def grant_permission(self, action: str, role: Role, max_amount: float = None) -> bool:
        """Grant permission (owner only)."""
        if self.role != Role.OWNER:
            self._audit("permission_denied", f"Non-owner attempted to grant permission: {action}")
            return False
        
        self.permissions[action] = Permission(
            action=action,
            role=role,
            max_amount=max_amount,
            approved_by=self.owner.name,
            approved_at=datetime.now().isoformat()
        )
        self._audit("permission_granted", f"Permission granted: {action} to {role.value}")
        return True
    
    def revoke_permission(self, action: str) -> bool:
        """Revoke permission (owner only)."""
        if self.role != Role.OWNER:
            return False
        
        if action in self.permissions:
            del self.permissions[action]
            self._audit("permission_revoked", f"Permission revoked: {action}")
            return True
        return False
    
    # ============================================================
    # AUDIT & SECURITY
    # ============================================================
    
    def _audit(self, action: str, details: str, metadata: Dict = None):
        """Log audit entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "role": self.role.value,
            "details": details,
            "metadata": metadata or {}
        }
        self.audit_log.append(entry)
        
        # Keep last 1000 entries
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]
    
    def get_audit_log(self, limit: int = 50) -> List[Dict]:
        """Get recent audit entries."""
        return self.audit_log[-limit:]
    
    def emergency_shutdown(self):
        """Emergency stop all operations (owner only)."""
        if self.role != Role.OWNER:
            return {"success": False, "reason": "Owner only"}
        
        self._audit("emergency_shutdown", "All Genesis financial operations stopped")
        
        # Disable all controlled operations
        for level in self.level_requirements.values():
            level.unlocked = False
        
        return {"success": True, "message": "Emergency shutdown complete"}
    
    # ============================================================
    # ACCOUNT MANAGEMENT
    # ============================================================
    
    def add_account(
        self,
        name: str,
        account_type: AccountType,
        institution: str = "",
        initial_balance: float = 0
    ) -> str:
        """Add a financial account to monitor."""
        import hashlib
        account_id = hashlib.md5(f"{name}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        self.accounts[account_id] = FinancialAccount(
            id=account_id,
            name=name,
            account_type=account_type,
            institution=institution,
            balance=initial_balance,
            is_monitored=True
        )
        
        self._audit("account_added", f"Account added: {name}", {"account_id": account_id})
        self._save_data()
        
        return account_id
    
    def get_account_balance(self, account_id: str) -> Optional[float]:
        """Get current balance (Level 1 skill)."""
        if account_id in self.accounts:
            return self.accounts[account_id].balance
        return None
    
    def get_all_balances(self) -> Dict[str, float]:
        """Get all account balances."""
        return {
            acc_id: acc.balance 
            for acc_id, acc in self.accounts.items()
        }
    
    # ============================================================
    # TRANSACTION MANAGEMENT
    # ============================================================
    
    def add_transaction(
        self,
        account_id: str,
        tx_type: TransactionType,
        category: TransactionCategory,
        amount: float,
        description: str,
        merchant: str = ""
    ) -> str:
        """Record a transaction."""
        import hashlib
        tx_id = hashlib.md5(f"{amount}{description}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
        
        tx = Transaction(
            id=tx_id,
            account_id=account_id,
            type=tx_type,
            category=category,
            amount=amount,
            currency="INR",
            description=description,
            timestamp=datetime.now().isoformat(),
            merchant=merchant
        )
        
        self.transactions.append(tx)
        
        # Update account balance
        if account_id in self.accounts:
            if tx_type == TransactionType.INCOME:
                self.accounts[account_id].balance += amount
            else:
                self.accounts[account_id].balance -= amount
        
        self._audit("transaction_added", f"Transaction: {tx_type.value} {amount}", {"tx_id": tx_id})
        self._save_data()
        
        return tx_id
    
    def get_transactions(
        self,
        start_date: str = None,
        end_date: str = None,
        category: TransactionCategory = None,
        limit: int = 100
    ) -> List[Transaction]:
        """Get filtered transactions."""
        results = self.transactions
        
        if start_date:
            results = [t for t in results if t.timestamp >= start_date]
        if end_date:
            results = [t for t in results if t.timestamp <= end_date]
        if category:
            results = [t for t in results if t.category == category]
        
        return sorted(results, key=lambda t: t.timestamp, reverse=True)[:limit]
    
    # ============================================================
    # FINANCIAL REPORTS (Level 1)
    # ============================================================
    
    def generate_daily_report(self) -> FinancialReport:
        """Generate daily financial report (Level 1 skill)."""
        today = datetime.now().date().isoformat()
        tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
        
        return self._generate_report("daily", today, tomorrow)
    
    def generate_monthly_report(self, year: int = None, month: int = None) -> FinancialReport:
        """Generate monthly financial report (Level 1 skill)."""
        if not year:
            year = datetime.now().year
        if not month:
            month = datetime.now().month
        
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year+1}-01-01"
        else:
            end_date = f"{year}-{month+1:02d}-01"
        
        return self._generate_report("monthly", start_date, end_date)
    
    def _generate_report(self, period: str, start_date: str, end_date: str) -> FinancialReport:
        """Generate a financial report for period."""
        txs = self.get_transactions(start_date, end_date)
        
        income = sum(t.amount for t in txs if t.type == TransactionType.INCOME)
        expense = sum(t.amount for t in txs if t.type == TransactionType.EXPENSE)
        
        # Top expenses by category
        expense_by_cat = {}
        for t in txs:
            if t.type == TransactionType.EXPENSE:
                cat = t.category.value
                expense_by_cat[cat] = expense_by_cat.get(cat, 0) + t.amount
        
        top_expenses = sorted(
            [{"category": k, "amount": v} for k, v in expense_by_cat.items()],
            key=lambda x: x["amount"],
            reverse=True
        )[:5]
        
        # Insights
        insights = []
        if expense > income:
            insights.append(f"Warning: Expenses exceed income by ₹{expense - income:.2f}")
        if len(txs) == 0:
            insights.append("No transactions recorded this period")
        
        return FinancialReport(
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_income=income,
            total_expense=expense,
            net_flow=income - expense,
            top_expenses=top_expenses,
            budget_status={},
            insights=insights,
            generated_at=datetime.now().isoformat()
        )
    
    # ============================================================
    # SUBSCRIPTION MANAGEMENT (Level 1)
    # ============================================================
    
    def add_subscription(
        self,
        name: str,
        provider: str,
        amount: float,
        billing_cycle: str,
        next_billing: str,
        category: TransactionCategory = TransactionCategory.SUBSCRIPTION
    ) -> str:
        """Add subscription to track (Level 1 skill)."""
        import hashlib
        sub_id = hashlib.md5(f"{name}{provider}".encode()).hexdigest()[:12]
        
        self.subscriptions[sub_id] = Subscription(
            id=sub_id,
            name=name,
            provider=provider,
            amount=amount,
            billing_cycle=billing_cycle,
            next_billing=next_billing,
            category=category
        )
        
        self._audit("subscription_added", f"Subscription added: {name}", {"sub_id": sub_id})
        self._save_data()
        
        return sub_id
    
    def get_upcoming_subscriptions(self, days: int = 7) -> List[Subscription]:
        """Get subscriptions due within days."""
        upcoming = []
        now = datetime.now()
        
        for sub in self.subscriptions.values():
            if not sub.is_active:
                continue
            
            due_date = datetime.fromisoformat(sub.next_billing)
            if (due_date - now).days <= days:
                upcoming.append(sub)
        
        return upcoming
    
    # ============================================================
    # SKILL LEVEL MANAGEMENT
    # ============================================================
    
    def get_skill_tree(self) -> Dict:
        """Get complete skill tree status."""
        return {
            "current_level": self.current_level.value,
            "levels": {
                level.value: {
                    "name": req.name,
                    "description": req.description,
                    "skills": req.skills,
                    "unlocked": req.unlocked,
                    "owner_approved": req.owner_approved,
                    "can_unlock": all(
                        self.level_requirements[p].unlocked 
                        for p in req.prerequisites
                    )
                }
                for level, req in self.level_requirements.items()
            },
            "infrastructure_skills": self.INFRASTRUCTURE_SKILLS
        }
    
    def unlock_level(self, level: FinancialLevel) -> Dict:
        """Unlock a new level (requires owner approval)."""
        if self.role != Role.OWNER:
            return {"success": False, "reason": "Owner authorization required"}
        
        req = self.level_requirements.get(level)
        if not req:
            return {"success": False, "reason": "Level not found"}
        
        if not all(self.level_requirements[p].unlocked for p in req.prerequisites):
            return {"success": False, "reason": "Prerequisites not met"}
        
        req.unlocked = True
        req.owner_approved = True
        self.current_level = level
        
        self._audit("level_unlocked", f"Level unlocked: {level.value}", {
            "level": level.value,
            "approved_by": self.owner.name
        })
        
        return {"success": True, "level": level.value, "skills": req.skills}
    
    # ============================================================
    # STATUS
    # ============================================================
    
    def get_status(self) -> Dict:
        """Get complete financial manager status."""
        return {
            "version": self.VERSION,
            "role": self.get_role(),
            "owner": self.get_owner_info(),
            "current_level": self.current_level.value,
            "level_name": self.level_requirements[self.current_level].name,
            "accounts_count": len(self.accounts),
            "transactions_count": len(self.transactions),
            "subscriptions_count": len(self.subscriptions),
            "audit_log_entries": len(self.audit_log),
            "skill_tree": self.get_skill_tree(),
            "total_balance": sum(a.balance for a in self.accounts.values())
        }


# Global singleton
_financial_manager: Optional[GenesisFinancialManager] = None


def get_financial_manager() -> GenesisFinancialManager:
    """Get global financial manager."""
    global _financial_manager
    if _financial_manager is None:
        _financial_manager = GenesisFinancialManager()
    return _financial_manager


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║  ⚡ GENESIS FINANCIAL OPERATIONS MANAGER v1.0.0 ⚡  ║
║                                                       ║
║  Owner: aakash kumar (Final Authority)                ║
║  Operator: GLUTTONY (Daily Management)                 ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    fm = GenesisFinancialManager()
    status = fm.get_status()
    
    print(f"\n📊 Status:")
    print(f"   Role: {status['role']}")
    print(f"   Current Level: {status['level_name']}")
    print(f"   Accounts: {status['accounts_count']}")
    print(f"   Transactions: {status['transactions_count']}")
    print(f"   Subscriptions: {status['subscriptions_count']}")
    
    print(f"\n🌳 Skill Tree:")
    tree = fm.get_skill_tree()
    for level_id, level_info in tree["levels"].items():
        status_icon = "✅" if level_info["unlocked"] else "🔒"
        print(f"   {status_icon} {level_info['name']}: {len(level_info['skills'])} skills")
    
    print(f"\n⚙️ Infrastructure Skills: {len(tree['infrastructure_skills'])}")

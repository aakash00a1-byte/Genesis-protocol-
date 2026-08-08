"""
Genesis Financial Bot - Telegram Handler
Financial operations via Telegram
"""

from typing import Dict, List, Optional
from datetime import datetime

from genesis_protocol.financial import (
    get_financial_manager,
    AccountType,
    TransactionType,
    TransactionCategory,
    FinancialLevel,
)


class FinancialBotHandler:
    """
    Telegram handler for Genesis Financial Manager.
    
    Commands:
    /financial - Main menu
    /balances - Show all account balances
    /report daily - Daily financial report
    /report monthly - Monthly report
    /tx add [amount] [category] [desc] - Add transaction
    /subscriptions - List subscriptions
    /skills - Show skill tree
    /audit - Recent audit log
    """
    
    VERSION = "1.0.0"
    
    def __init__(self, bot):
        self.bot = bot
        self.financial = get_financial_manager()
    
    async def handle_financial(self, update, context) -> str:
        """Main financial menu."""
        status = self.financial.get_status()
        
        menu = f"""💰 *Genesis Financial Manager*

👤 Role: {status['role']}
📊 Level: {status['level_name']}
💵 Total Balance: ₹{status['total_balance']:.2f}

*Accounts:* {status['accounts_count']}
*Transactions:* {status['transactions_count']}
*Subscriptions:* {status['subscriptions_count']}

━━━━━━━━━━━━━━━
📋 *Quick Commands:*
/balances - View all accounts
/report daily - Daily report
/report monthly - Monthly report
/tx add [amount] [category] [desc] - Add transaction
/subscriptions - Manage subs
/skills - View skill tree
/audit - View audit log
"""
        return menu
    
    async def handle_balances(self, update, context) -> str:
        """Show all account balances."""
        balances = self.financial.get_all_balances()
        
        if not balances:
            return "❌ No accounts added yet.\n\nUse /financial add to add an account."
        
        lines = ["💰 *Account Balances*\n"]
        
        total = 0
        for acc_id, balance in balances.items():
            acc = self.financial.accounts.get(acc_id)
            if acc:
                emoji = self._get_account_emoji(acc.account_type.value)
                lines.append(f"{emoji} {acc.name}: ₹{balance:.2f}")
                total += balance
        
        lines.append(f"\n━━━━━━━━━━━━━━━")
        lines.append(f"💵 *Total: ₹{total:.2f}*")
        
        return "\n".join(lines)
    
    async def handle_report(self, update, context, period: str) -> str:
        """Generate financial report."""
        if period == "daily":
            report = self.financial.generate_daily_report()
            title = "📅 Daily Report"
        else:
            report = self.financial.generate_monthly_report()
            title = "📆 Monthly Report"
        
        lines = [
            f"*{title}*",
            f"━━━━━━━━━━━━━━━",
            f"📥 Income: ₹{report.total_income:.2f}",
            f"📤 Expenses: ₹{report.total_expense:.2f}",
            f"💹 Net Flow: ₹{report.net_flow:.2f}",
        ]
        
        if report.top_expenses:
            lines.append(f"\n📊 *Top Expenses:*")
            for i, exp in enumerate(report.top_expenses[:3], 1):
                lines.append(f"  {i}. {exp['category']}: ₹{exp['amount']:.2f}")
        
        if report.insights:
            lines.append(f"\n💡 *Insights:*")
            for insight in report.insights:
                lines.append(f"  • {insight}")
        
        return "\n".join(lines)
    
    async def handle_add_transaction(self, update, context, args: List[str]) -> str:
        """Add a transaction."""
        if len(args) < 3:
            return "❌ Usage: /tx add [amount] [category] [description]\n\nExample: /tx add 500 food Lunch"
        
        try:
            amount = float(args[0])
            category_str = args[1].lower()
            description = " ".join(args[2:])
        except ValueError:
            return "❌ Invalid amount. Use numbers only."
        
        # Map category string to enum
        category_map = {
            "food": TransactionCategory.FOOD,
            "transport": TransactionCategory.TRANSPORT,
            "utilities": TransactionCategory.UTILITIES,
            "subscription": TransactionCategory.SUBSCRIPTION,
            "entertainment": TransactionCategory.ENTERTAINMENT,
            "business": TransactionCategory.BUSINESS,
            "salary": TransactionCategory.SALARY,
            "freelance": TransactionCategory.FREELANCE,
        }
        
        category = category_map.get(category_str, TransactionCategory.OTHER)
        tx_type = TransactionType.EXPENSE if amount > 0 else TransactionType.INCOME
        
        # Use first account or create one
        account_id = list(self.financial.accounts.keys())[0] if self.financial.accounts else None
        
        if not account_id:
            return "❌ No account found. Add an account first."
        
        tx_id = self.financial.add_transaction(
            account_id=account_id,
            tx_type=tx_type,
            category=category,
            amount=abs(amount),
            description=description
        )
        
        return f"✅ Transaction added!\n\n📝 ID: {tx_id}\n💰 Amount: ₹{abs(amount):.2f}\n📂 Category: {category.value}\n📌 {description}"
    
    async def handle_subscriptions(self, update, context) -> str:
        """Show subscriptions."""
        upcoming = self.financial.get_upcoming_subscriptions(7)
        all_subs = list(self.financial.subscriptions.values())
        
        if not all_subs:
            return "❌ No subscriptions tracked.\n\nUse /sub add [name] [amount] to add."
        
        lines = ["📺 *Subscriptions*\n━━━━━━━━━━━━━━━"]
        
        total_monthly = 0
        for sub in all_subs:
            status_icon = "✅" if sub.is_active else "❌"
            lines.append(f"{status_icon} {sub.name}: ₹{sub.amount:.2f}/{sub.billing_cycle}")
            
            if sub.is_active:
                if sub.billing_cycle == "monthly":
                    total_monthly += sub.amount
                else:
                    total_monthly += sub.amount / 12
        
        lines.append(f"\n━━━━━━━━━━━━━━━")
        lines.append(f"💰 Monthly Cost: ₹{total_monthly:.2f}")
        
        if upcoming:
            lines.append(f"\n⚠️ *Due Soon:*")
            for sub in upcoming[:3]:
                lines.append(f"  • {sub.name} (₹{sub.amount})")
        
        return "\n".join(lines)
    
    async def handle_skills(self, update, context) -> str:
        """Show skill tree."""
        tree = self.financial.get_skill_tree()
        
        lines = ["🌳 *Financial Skill Tree*\n━━━━━━━━━━━━━━━"]
        
        for level_id, info in tree["levels"].items():
            icon = "✅" if info["unlocked"] else "🔒"
            approved = "👑" if info["owner_approved"] else ""
            
            lines.append(f"\n{icon} *{info['name']}* {approved}")
            lines.append(f"   {info['description']}")
            
            for skill in info["skills"][:3]:
                lines.append(f"   • {skill}")
            
            if len(info["skills"]) > 3:
                lines.append(f"   • ... +{len(info['skills']) - 3} more")
        
        return "\n".join(lines)
    
    async def handle_audit(self, update, context) -> str:
        """Show recent audit log."""
        entries = self.financial.get_audit_log(10)
        
        if not entries:
            return "📋 *Audit Log Empty*"
        
        lines = ["📋 *Recent Activity*\n━━━━━━━━━━━━━━━"]
        
        for entry in reversed(entries[-10:]):
            timestamp = datetime.fromisoformat(entry["timestamp"]).strftime("%m/%d %H:%M")
            lines.append(f"\n[{timestamp}] {entry['action']}")
            lines.append(f"  📝 {entry['details'][:50]}")
        
        return "\n".join(lines)
    
    async def handle_add_account(self, update, context, args: List[str]) -> str:
        """Add a new account."""
        if len(args) < 2:
            return "❌ Usage: /account add [name] [type]\n\nTypes: bank, crypto, upi, cash, investment"
        
        name = args[0]
        type_str = args[1].lower()
        
        type_map = {
            "bank": AccountType.BANK,
            "crypto": AccountType.CRYPTO,
            "upi": AccountType.UPI,
            "cash": AccountType.CASH,
            "investment": AccountType.INVESTMENT,
        }
        
        acc_type = type_map.get(type_str)
        if not acc_type:
            return "❌ Invalid type. Use: bank, crypto, upi, cash, investment"
        
        account_id = self.financial.add_account(
            name=name,
            account_type=acc_type
        )
        
        return f"✅ Account added!\n\n📝 ID: {account_id}\n🏦 Name: {name}\n📂 Type: {type_str}"
    
    def _get_account_emoji(self, account_type: str) -> str:
        """Get emoji for account type."""
        emojis = {
            "bank": "🏦",
            "crypto": "🪙",
            "upi": "📱",
            "cash": "💵",
            "investment": "📈",
        }
        return emojis.get(account_type, "💰")


# Quick access function
def get_financial_handler(bot) -> FinancialBotHandler:
    """Get financial handler instance."""
    return FinancialBotHandler(bot)


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     💰 Genesis Financial Bot Handler v1.0.0 💰      ║
╚═══════════════════════════════════════════════════════════╝
    """)
    print("Commands:")
    print("  /financial - Main menu")
    print("  /balances - Show balances")
    print("  /report daily - Daily report")
    print("  /subscriptions - Manage subs")
    print("  /skills - View skill tree")

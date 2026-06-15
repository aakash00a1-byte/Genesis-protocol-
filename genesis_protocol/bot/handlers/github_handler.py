"""Genesis Protocol - GitHub Handler

Telegram bot handler for GitHub operations.
"""

from telegram import Update
from telegram.ext import ContextTypes

from genesis_protocol.powers.github_manager import get_github_manager
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.handlers.github")


async def handle_github(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /github command - GitHub operations."""
    
    github = get_github_manager()
    chat_id = update.effective_chat.id
    args = context.args
    
    if not args:
        if not github.is_configured():
            await update.message.reply_text("❌ GitHub Not Configured\n\nSet GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO in .env")
            return
        
        repo_result = github.get_repo_info()
        if not repo_result.success:
            await update.message.reply_text(f"❌ Error: {repo_result.error}")
            return
        
        r = repo_result.data
        response = f"🔗 *GitHub Connected*\n\n"
        response += f"📁 *{r.get('full_name')}*\n"
        response += f"Branch: `{r.get('default_branch')}`\n"
        response += f"Language: {r.get('language') or 'N/A'}\n"
        response += f"Stars: ⭐ {r.get('stargazers_count', 0)}\n\n"
        
        response += "*Commands:*\n"
        response += "`/github info` - Repo details\n"
        response += "`/github branches` - List branches\n"
        response += "`/github prs` - List PRs\n"
        response += "`/github issues` - List issues\n"
        response += "`/github create-branch <name>`\n"
        response += "`/github create-issue <title>`\n"
        response += "`/github deploys` - Deployments\n"
        response += "`/github actions` - Workflow runs\n"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        return
    
    action = args[0].lower()
    
    try:
        if action == "info":
            result = github.get_repo_info()
            if result.success:
                r = result.data
                response = f"📊 *Repo Details*\n\n"
                response += f"Name: {r.get('full_name')}\n"
                response += f"Branch: `{r.get('default_branch')}`\n"
                response += f"Language: {r.get('language') or 'N/A'}\n"
                response += f"Stars: ⭐ {r.get('stargazers_count', 0)}\n"
                response += f"Forks: 🍴 {r.get('forks_count', 0)}\n"
                response += f"Issues: 📋 {r.get('open_issues_count', 0)}\n"
                response += f"\n🔗 {r.get('html_url')}"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "branches":
            result = github.list_branches()
            if result.success:
                branches = result.data if isinstance(result.data, list) else []
                response = "🌿 *Branches*\n\n"
                for b in branches[:10]:
                    name = b.get('name', '')
                    is_default = b.get('default', False)
                    response += f"• `{name}` {'(default)' if is_default else ''}\n"
                if len(branches) > 10:
                    response += f"\n...and {len(branches) - 10} more"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "prs":
            result = github.list_prs()
            if result.success:
                prs = result.data if isinstance(result.data, list) else []
                response = "🔀 *Pull Requests*\n\n"
                for pr in prs[:5]:
                    response += f"• #{pr.get('number')}: {pr.get('title')}\n"
                    response += f"  State: {pr.get('state')} | By: {pr.get('user', {}).get('login')}\n\n"
                if len(prs) == 0:
                    response = "🔀 *Pull Requests*\n\nNo open PRs! ✅"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "issues":
            result = github.list_issues()
            if result.success:
                issues = result.data if isinstance(result.data, list) else []
                response = "📋 *Issues*\n\n"
                for i in issues[:5]:
                    response += f"• #{i.get('number')}: {i.get('title')}\n\n"
                if len(issues) == 0:
                    response = "📋 *Issues*\n\nNo open issues! ✅"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "deploys":
            result = github.list_deployments()
            if result.success:
                deploys = result.data if isinstance(result.data, list) else []
                response = "🚀 *Deployments*\n\n"
                for d in deploys[:5]:
                    response += f"• ID: `{d.get('id')}`\n"
                    response += f"  Env: {d.get('environment')} | Ref: {d.get('ref')}\n"
                    response += f"  Created: {d.get('created_at', 'N/A')}\n\n"
                if len(deploys) == 0:
                    response = "🚀 *Deployments*\n\nNo deployments yet!"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "actions":
            result = github.get_workflow_runs()
            if result.success:
                runs = result.data.get('workflow_runs', []) if isinstance(result.data, dict) else []
                response = "⚙️ *Actions*\n\n"
                for r in runs[:5]:
                    response += f"• {r.get('name')}\n"
                    response += f"  Status: {r.get('status')} | Conclusion: {r.get('conclusion')}\n"
                    response += f"  Triggered: {r.get('run_started_at', 'N/A')}\n\n"
                if len(runs) == 0:
                    response = "⚙️ *Actions*\n\nNo workflow runs!"
            else:
                response = f"❌ Error: {result.error}"
            await update.message.reply_text(response, parse_mode="Markdown")
        
        elif action == "create-branch" and len(args) >= 2:
            branch_name = args[1]
            await update.message.reply_text(f"🌿 Creating branch: `{branch_name}`...")
            result = github.create_branch(branch_name)
            if result.success:
                await update.message.reply_text(
                    f"✅ *Branch Created!*\n\nBranch: `{branch_name}`\nNow you can commit files!",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ Error: {result.error}", parse_mode="Markdown")
        
        elif action == "create-issue" and len(args) >= 2:
            issue_title = " ".join(args[1:])
            await update.message.reply_text(f"📋 Creating issue: {issue_title}...")
            result = github.create_issue(issue_title)
            if result.success:
                issue_url = result.data.get('html_url', '')
                await update.message.reply_text(
                    f"✅ *Issue Created!*\n\n🔗 {issue_url}",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"❌ Error: {result.error}", parse_mode="Markdown")
        
        else:
            await update.message.reply_text(
                "❌ Unknown command.\n\nTry:\n/github info\n/github branches\n/github prs\n/github issues\n/github create-branch <name>\n/github create-issue <title>",
                parse_mode="Markdown"
            )
    
    except Exception as e:
        logger.error(f"GitHub command error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

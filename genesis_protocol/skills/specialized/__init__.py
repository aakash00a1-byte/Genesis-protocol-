"""
Specialized Tools Integration
===============================
Linear, Notion, Slack, GitHub/GitLab PR management, data analysis.
"""

import subprocess
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
from genesis_protocol.skills import Skill, SkillCategory

# Skill definitions
SKILLS = [
    Skill(
        name="linear_integration",
        category=SkillCategory.SPECIALIZED,
        description="Manage Linear issues and workflows",
        tools=["graphql", "http"],
        dependencies=["api_integration"]
    ),
    Skill(
        name="notion_integration",
        category=SkillCategory.SPECIALIZED,
        description="Create and manage Notion pages and databases",
        tools=["http", "json"],
        dependencies=["api_integration"]
    ),
    Skill(
        name="slack_integration",
        category=SkillCategory.SPECIALIZED,
        description="Send messages and manage Slack channels",
        tools=["http", "api"],
        dependencies=["api_integration"]
    ),
    Skill(
        name="github_pr_management",
        category=SkillCategory.SPECIALIZED,
        description="Create, review, and manage GitHub pull requests",
        tools=["gh", "git"],
        dependencies=["git_operations"]
    ),
    Skill(
        name="data_analysis",
        category=SkillCategory.SPECIALIZED,
        description="Analyze data and generate insights",
        tools=["python", "pandas"],
        version="1.0.0"
    ),
]


class LinearIntegration:
    """Integrate with Linear API."""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://api.linear.app/graphql"
    
    def set_api_key(self, api_key: str):
        """Set the API key."""
        self.api_key = api_key
    
    def _graphql_request(self, query: str, variables: Dict = None) -> Dict[str, Any]:
        """Make a GraphQL request to Linear."""
        try:
            import aiohttp
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.base_url,
                        json={"query": query, "variables": variables or {}},
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": self.api_key
                        },
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        return await response.json()
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return {"error": str(e)}
    
    def get_issues(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get issues assigned to the viewer."""
        query = """
        query {
            viewer {
                assignedIssues(first: %d) {
                    nodes {
                        id
                        identifier
                        title
                        description
                        priority
                        priorityLabel
                        state { name }
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """ % limit
        
        result = self._graphql_request(query)
        
        if "data" in result:
            return result["data"]["viewer"]["assignedIssues"]["nodes"]
        return []
    
    def create_issue(
        self,
        team_id: str,
        title: str,
        description: str = "",
        priority: int = 3
    ) -> Dict[str, Any]:
        """Create a new issue."""
        mutation = """
        mutation {
            issueCreate(input: {
                teamId: "%s",
                title: "%s",
                description: "%s",
                priority: %d
            }) {
                success
                issue {
                    id
                    identifier
                    title
                }
            }
        }
        """ % (team_id, title, description, priority)
        
        result = self._graphql_request(mutation)
        return result.get("data", {}).get("issueCreate", {})
    
    def update_issue_state(self, issue_id: str, state_id: str) -> Dict[str, Any]:
        """Update issue state."""
        mutation = """
        mutation {
            issueUpdate(id: "%s", input: { stateId: "%s" }) {
                success
                issue {
                    identifier
                    state { name }
                }
            }
        }
        """ % (issue_id, state_id)
        
        result = self._graphql_request(mutation)
        return result.get("data", {}).get("issueUpdate", {})
    
    def add_comment(self, issue_id: str, body: str) -> Dict[str, Any]:
        """Add a comment to an issue."""
        mutation = """
        mutation {
            commentCreate(input: {
                issueId: "%s",
                body: "%s"
            }) {
                success
                comment { id body }
            }
        }
        """ % (issue_id, body.replace('"', '\\"'))
        
        result = self._graphql_request(mutation)
        return result.get("data", {}).get("commentCreate", {})


class NotionIntegration:
    """Integrate with Notion API."""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
    
    def set_api_key(self, api_key: str):
        """Set the API key."""
        self.api_key = api_key
        self.headers["Authorization"] = f"Bearer {api_key}"
    
    def search_pages(self, query: str = "") -> List[Dict[str, Any]]:
        """Search for pages."""
        try:
            import aiohttp
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/search",
                        json={"query": query, "page_size": 50},
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        data = await response.json()
                        return data.get("results", [])
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return []
    
    def create_page(
        self,
        parent_id: str,
        title: str,
        properties: Dict = None,
        children: List[Dict] = None
    ) -> Dict[str, Any]:
        """Create a new page."""
        try:
            import aiohttp
            
            page_data = {
                "parent": {"page_id": parent_id},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": title}}]
                    }
                }
            }
            
            if properties:
                page_data["properties"].update(properties)
            
            if children:
                page_data["children"] = children
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/pages",
                        json=page_data,
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        return await response.json()
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return {"error": str(e)}
    
    def append_blocks(self, block_id: str, children: List[Dict]) -> Dict[str, Any]:
        """Append blocks to a page."""
        try:
            import aiohttp
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.patch(
                        f"{self.base_url}/blocks/{block_id}/children",
                        json={"children": children},
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        return await response.json()
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return {"error": str(e)}


class SlackIntegration:
    """Integrate with Slack API."""
    
    def __init__(self, bot_token: str = ""):
        self.bot_token = bot_token
        self.base_url = "https://slack.com/api"
    
    def set_token(self, token: str):
        """Set the bot token."""
        self.bot_token = token
    
    def send_message(self, channel: str, text: str) -> Dict[str, Any]:
        """Send a message to a channel."""
        try:
            import aiohttp
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/chat.postMessage",
                        data={
                            "channel": channel,
                            "text": text
                        },
                        headers={
                            "Authorization": f"Bearer {self.bot_token}",
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        return await response.json()
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    def get_channel_info(self, channel: str) -> Dict[str, Any]:
        """Get information about a channel."""
        try:
            import aiohttp
            
            async def make_request():
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/conversations.info",
                        data={"channel": channel},
                        headers={
                            "Authorization": f"Bearer {self.bot_token}",
                            "Content-Type": "application/x-www-form-urlencoded"
                        },
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        return await response.json()
            
            import asyncio
            return asyncio.run(make_request())
        except Exception as e:
            return {"ok": False, "error": str(e)}


class GitHubPRManager:
    """Manage GitHub pull requests."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
    
    def run_gh(self, *args) -> Dict[str, Any]:
        """Run a gh command."""
        try:
            result = subprocess.run(
                ["gh"] + list(args),
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_prs(self, state: str = "open") -> List[Dict[str, Any]]:
        """List pull requests."""
        result = self.run_gh("pr", "list", "--state", state, "--json", "number,title,state,url,author")
        
        if result.get("success"):
            try:
                return json.loads(result["stdout"])
            except:
                pass
        
        return []
    
    def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: str = None
    ) -> Dict[str, Any]:
        """Create a pull request."""
        args = ["pr", "create", "--title", title, "--body", body, "--base", base]
        
        if head:
            args.extend(["--head", head])
        
        result = self.run_gh(*args)
        
        if result.get("success"):
            # Extract PR URL from output
            for line in result["stdout"].split("\n"):
                if "https://github.com" in line:
                    return {"success": True, "url": line.strip()}
        
        return {"success": False, "error": result.get("stderr", "Unknown error")}
    
    def get_pr_details(self, pr_number: int) -> Dict[str, Any]:
        """Get PR details."""
        result = self.run_gh(
            "pr", "view", str(pr_number),
            "--json", "number,title,body,state,url,author,labels,reviews"
        )
        
        if result.get("success"):
            try:
                return json.loads(result["stdout"])
            except:
                pass
        
        return {}
    
    def add_review(self, pr_number: int, body: str = "", event: str = "COMMENT") -> Dict[str, Any]:
        """Add a review to a PR."""
        return self.run_gh("pr", "review", str(pr_number), "--body", body, "--event", event)
    
    def merge_pr(self, pr_number: int, method: str = "merge") -> Dict[str, Any]:
        """Merge a pull request."""
        return self.run_gh("pr", "merge", str(pr_number), "--admin", "--auto")


class DataAnalyzer:
    """Data analysis capabilities."""
    
    def __init__(self):
        self.pandas_available = self._check_pandas()
    
    def _check_pandas(self) -> bool:
        """Check if pandas is available."""
        try:
            import pandas
            return True
        except:
            return False
    
    def analyze_csv(self, file_path: str) -> Dict[str, Any]:
        """Analyze a CSV file."""
        if not self.pandas_available:
            return {"success": False, "error": "pandas not installed"}
        
        try:
            import pandas as pd
            
            df = pd.read_csv(file_path)
            
            return {
                "success": True,
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
                "dtypes": df.dtypes.to_dict(),
                "summary": df.describe().to_dict(),
                "missing": df.isnull().sum().to_dict()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def generate_report(self, data: List[Dict], format: str = "markdown") -> str:
        """Generate a report from data."""
        if format == "markdown":
            return self._generate_markdown_report(data)
        elif format == "json":
            return json.dumps(data, indent=2)
        return str(data)
    
    def _generate_markdown_report(self, data: List[Dict]) -> str:
        """Generate a markdown report."""
        if not data:
            return "No data available"
        
        headers = list(data[0].keys())
        report = "| " + " | ".join(headers) + " |\n"
        report += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        
        for row in data:
            values = [str(row.get(h, "")) for h in headers]
            report += "| " + " | ".join(values) + " |\n"
        
        return report


# Export skill executors
async def execute_linear_create_issue(team_id: str, title: str, **kwargs) -> Dict[str, Any]:
    """Execute Linear issue creation."""
    integration = LinearIntegration()
    return integration.create_issue(team_id, title, **kwargs)


async def execute_notion_create_page(parent_id: str, title: str, **kwargs) -> Dict[str, Any]:
    """Execute Notion page creation."""
    integration = NotionIntegration()
    return integration.create_page(parent_id, title, **kwargs)


async def execute_slack_send_message(channel: str, text: str) -> Dict[str, Any]:
    """Execute Slack message sending."""
    integration = SlackIntegration()
    return integration.send_message(channel, text)


async def execute_github_create_pr(title: str, body: str, **kwargs) -> Dict[str, Any]:
    """Execute GitHub PR creation."""
    manager = GitHubPRManager()
    return manager.create_pr(title, body, **kwargs)


async def execute_data_analysis(file_path: str) -> Dict[str, Any]:
    """Execute data analysis."""
    analyzer = DataAnalyzer()
    
    if file_path.endswith('.csv'):
        return analyzer.analyze_csv(file_path)
    
    return {"success": False, "error": "Unsupported file type"}


# Export skill executors
SKILL_EXECUTORS = {
    "linear_integration": execute_linear_create_issue,
    "notion_integration": execute_notion_create_page,
    "slack_integration": execute_slack_send_message,
    "github_pr_management": execute_github_create_pr,
    "data_analysis": execute_data_analysis,
}
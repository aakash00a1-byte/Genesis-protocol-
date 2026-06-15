"""Genesis Protocol - GitHub Manager

Real GitHub integration using GitHub API.
"""

import os
import base64
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.github")


@dataclass
class GitHubResult:
    """Result of GitHub operation."""
    success: bool
    output: str
    error: Optional[str] = None
    data: Optional[Dict] = None


class GitHubManager:
    """GitHub integration manager."""

    def __init__(self, token: str = None, owner: str = None, repo: str = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.owner = owner or os.environ.get("GITHUB_OWNER", "")
        self.repo = repo or os.environ.get("GITHUB_REPO", "")
        
        if self.token:
            os.environ["GITHUB_TOKEN"] = self.token
        
        logger.info(f"GitHub Manager initialized for {self.owner}/{self.repo}")

    def is_configured(self) -> bool:
        """Check if GitHub is configured."""
        return bool(self.token and self.owner and self.repo)

    def _api_request(self, endpoint: str, method: str = "GET", data: dict = None) -> GitHubResult:
        """Make GitHub API request."""
        try:
            import requests
            
            headers = {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            url = f"https://api.github.com{endpoint}"
            
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == "PATCH":
                response = requests.patch(url, headers=headers, json=data, timeout=30)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                return GitHubResult(success=False, output="", error=f"Unknown method: {method}")
            
            if response.status_code in [200, 201, 204]:
                return GitHubResult(
                    success=True,
                    output=response.text,
                    data=response.json() if response.text else {}
                )
            else:
                return GitHubResult(
                    success=False,
                    output=response.text,
                    error=f"API error: {response.status_code}"
                )
        except Exception as e:
            return GitHubResult(success=False, output="", error=str(e))

    # ========== REPO OPERATIONS ==========

    def get_repo_info(self) -> GitHubResult:
        """Get repository information."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}")

    def create_branch(self, branch_name: str, from_branch: str = "main") -> GitHubResult:
        """Create a new branch."""
        sha_result = self._api_request(f"/repos/{self.owner}/{self.repo}/git/ref/heads/{from_branch}")
        if not sha_result.success:
            return sha_result
        
        sha = sha_result.data.get("object", {}).get("sha", "")
        
        return self._api_request(
            f"/repos/{self.owner}/{self.repo}/git/refs",
            method="POST",
            data={
                "ref": f"refs/heads/{branch_name}",
                "sha": sha
            }
        )

    def delete_branch(self, branch_name: str) -> GitHubResult:
        """Delete a branch."""
        return self._api_request(
            f"/repos/{self.owner}/{self.repo}/git/refs/heads/{branch_name}",
            method="DELETE"
        )

    def list_branches(self) -> GitHubResult:
        """List all branches."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}/branches")

    # ========== FILE OPERATIONS ==========

    def create_file(self, path: str, content: str, message: str, branch: str = None) -> GitHubResult:
        """Create or update a file."""
        branch = branch or "main"
        
        existing = self._api_request(f"/repos/{self.owner}/{self.repo}/contents/{path}?ref={branch}")
        sha = existing.data.get("sha", "") if existing.success else ""
        
        content_b64 = base64.b64encode(content.encode()).decode()
        
        return self._api_request(
            f"/repos/{self.owner}/{self.repo}/contents/{path}",
            method="PUT",
            data={
                "message": message,
                "content": content_b64,
                "branch": branch,
                "sha": sha if sha else None
            }
        )

    def get_file(self, path: str, branch: str = "main") -> GitHubResult:
        """Get file content."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}/contents/{path}?ref={branch}")

    # ========== PULL REQUESTS ==========

    def create_pr(self, title: str, body: str, head: str, base: str = "main") -> GitHubResult:
        """Create a pull request."""
        return self._api_request(
            f"/repos/{self.owner}/{self.repo}/pulls",
            method="POST",
            data={
                "title": title,
                "body": body,
                "head": head,
                "base": base
            }
        )

    def list_prs(self, state: str = "open") -> GitHubResult:
        """List pull requests."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}/pulls?state={state}")

    # ========== ISSUES ==========

    def create_issue(self, title: str, body: str = "", labels: List[str] = None) -> GitHubResult:
        """Create an issue."""
        return self._api_request(
            f"/repos/{self.owner}/{self.repo}/issues",
            method="POST",
            data={
                "title": title,
                "body": body,
                "labels": labels or []
            }
        )

    def list_issues(self, state: str = "open") -> GitHubResult:
        """List issues."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}/issues?state={state}")

    # ========== DEPLOYMENTS ==========

    def list_deployments(self, environment: str = None) -> GitHubResult:
        """List deployments."""
        url = f"/repos/{self.owner}/{self.repo}/deployments"
        if environment:
            url += f"?environment={environment}"
        return self._api_request(url)

    def get_workflow_runs(self) -> GitHubResult:
        """Get workflow runs."""
        return self._api_request(f"/repos/{self.owner}/{self.repo}/actions/runs")


# Singleton
_github_manager: Optional[GitHubManager] = None


def get_github_manager() -> GitHubManager:
    """Get or create GitHubManager singleton."""
    global _github_manager
    if _github_manager is None:
        _github_manager = GitHubManager()
    return _github_manager

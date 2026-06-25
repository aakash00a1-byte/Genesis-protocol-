"""
⚡ Genesis GitHub Agent ⚡
Autonomous GitHub operations for Genesis Protocol
"""

import os
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class GitHubOperationResult:
    success: bool
    operation: str
    message: str
    commit_sha: Optional[str] = None
    url: Optional[str] = None


class GitHubAgent:
    """Autonomous GitHub operations agent."""
    
    VERSION = "1.0.0"
    REPO_OWNER = "aakash00a1-byte"
    REPO_NAME = "Genesis-protocol-"
    
    def __init__(self, github_token: Optional[str] = None):
        self.token = github_token or os.getenv("GITHUB_TOKEN", "")
        self.repo_url = f"https://github.com/{self.REPO_OWNER}/{self.REPO_NAME}.git"
        self.branch = "main"
        self.log = []
    
    def _log(self, message: str, level: str = "INFO"):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}"
        self.log.append(entry)
        print(entry)
    
    def setup_remote(self, local_path: str) -> bool:
        """Setup authenticated remote."""
        try:
            if self.token:
                remote_url = f"https://{self.token}@github.com/{self.REPO_OWNER}/{self.REPO_NAME}.git"
                subprocess.run(
                    ["git", "remote", "set-url", "origin", remote_url],
                    cwd=local_path,
                    capture_output=True
                )
                self._log("Remote configured with authentication")
            return True
        except Exception as e:
            self._log(f"Remote setup failed: {e}", "ERROR")
            return False
    
    def commit_and_push(
        self,
        local_path: str,
        files: List[str],
        message: str,
        author_name: str = "Genesis-AI",
        author_email: str = "genesis@autonomous.ai"
    ) -> GitHubOperationResult:
        """Commit and push changes to GitHub."""
        self._log(f"🚀 Committing {len(files)} file(s)...")
        
        try:
            # Configure git
            subprocess.run(
                ["git", "config", "user.name", author_name],
                cwd=local_path, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", author_email],
                cwd=local_path, capture_output=True
            )
            
            # Add files
            for file in files:
                subprocess.run(["git", "add", file], cwd=local_path, capture_output=True)
            
            # Commit
            timestamp = datetime.now().isoformat()
            full_message = f"""🤖 {message}

[Genesis-AI Autonomous Commit]
Timestamp: {timestamp}
Files: {', '.join(files)}
"""
            result = subprocess.run(
                ["git", "commit", "-m", full_message],
                cwd=local_path, capture_output=True, text=True
            )
            
            if result.returncode != 0:
                if "nothing to commit" in result.stdout:
                    return GitHubOperationResult(
                        success=True,
                        operation="commit",
                        message="No changes to commit"
                    )
                return GitHubOperationResult(
                    success=False,
                    operation="commit",
                    message=f"Commit failed: {result.stderr}"
                )
            
            commit_sha = result.stdout.split()[1][:7] if "commit" in result.stdout else None
            self._log(f"✅ Committed: {commit_sha}")
            
            # Push
            if self.token:
                remote_url = f"https://{self.token}@github.com/{self.REPO_OWNER}/{self.REPO_NAME}.git"
                subprocess.run(
                    ["git", "remote", "set-url", "origin", remote_url],
                    cwd=local_path, capture_output=True
                )
            
            result = subprocess.run(
                ["git", "push", "origin", self.branch],
                cwd=local_path, capture_output=True, text=True
            )
            
            if result.returncode == 0:
                url = f"https://github.com/{self.REPO_OWNER}/{self.REPO_NAME}/commits/{self.branch}"
                self._log("✅ Pushed to GitHub!")
                return GitHubOperationResult(
                    success=True,
                    operation="push",
                    message="Successfully pushed to GitHub",
                    commit_sha=commit_sha,
                    url=url
                )
            else:
                return GitHubOperationResult(
                    success=False,
                    operation="push",
                    message=f"Push failed: {result.stderr}"
                )
                
        except Exception as e:
            return GitHubOperationResult(
                success=False,
                operation="commit_push",
                message=f"Error: {str(e)}"
            )
    
    def create_branch(self, local_path: str, branch_name: str) -> bool:
        """Create a new branch."""
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=local_path, capture_output=True
            )
            self._log(f"✅ Branch created: {branch_name}")
            return True
        except Exception as e:
            self._log(f"Branch creation failed: {e}", "ERROR")
            return False
    
    def get_status(self, local_path: str) -> Dict:
        """Get git status."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=local_path, capture_output=True, text=True
            )
            return {
                "has_changes": bool(result.stdout.strip()),
                "changes": result.stdout.strip().split("\n") if result.stdout.strip() else []
            }
        except Exception as e:
            return {"error": str(e)}


def autonomous_github_update(
    local_path: str,
    files: List[str],
    message: str,
    github_token: Optional[str] = None
) -> GitHubOperationResult:
    """One-command autonomous GitHub update."""
    agent = GitHubAgent(github_token)
    return agent.commit_and_push(local_path, files, message)


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS GITHUB AGENT v1.0.0 ⚡                ║
╚═══════════════════════════════════════════════════════════╝
    """)
    print("Usage: from genesis_protocol.autonomy.github_agent import autonomous_github_update")

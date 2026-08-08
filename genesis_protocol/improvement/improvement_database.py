"""Improvement Database - Genesis Protocol v1.7"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path


class ImprovementDatabase:
    """Stores improvement issues and proposals."""
    
    def __init__(self, storage_path: str = "./data/improvements"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._issues = []
        self._load_issues()
    
    def _load_issues(self):
        issues_file = self.storage_path / "issues.json"
        if issues_file.exists():
            try:
                with open(issues_file, 'r') as f:
                    self._issues = json.load(f)
            except Exception:
                pass
    
    def _save_issues(self):
        issues_file = self.storage_path / "issues.json"
        try:
            with open(issues_file, 'w') as f:
                json.dump(self._issues[-50:], f, indent=2)
        except Exception:
            pass
    
    def add_issue(self, issue_type: str, description: str, severity: float, evidence: List[str] = None) -> Dict:
        """Add an issue."""
        issue = {
            "id": f"issue_{len(self._issues) + 1}",
            "type": issue_type,
            "description": description,
            "severity": severity,
            "evidence": evidence or [],
            "timestamp": datetime.now().isoformat(),
            "status": "open"
        }
        self._issues.append(issue)
        self._save_issues()
        return issue
    
    def get_issues(self, status: str = None) -> List[Dict]:
        if status:
            return [i for i in self._issues if i.get("status") == status]
        return self._issues
    
    def close_issue(self, issue_id: str):
        for issue in self._issues:
            if issue["id"] == issue_id:
                issue["status"] = "resolved"
                break
        self._save_issues()


_db = None


def get_improvement_database() -> ImprovementDatabase:
    global _db
    if _db is None:
        _db = ImprovementDatabase()
    return _db

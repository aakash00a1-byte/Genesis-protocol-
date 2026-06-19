"""Capabilities Module - GLUTTONY Ω+2

Documents and exposes all system capabilities."""

from typing import Dict, List, Any
from datetime import datetime


class Capabilities:
    """GLUTTONY capabilities enumeration."""
    
    # 1. Coding & Development
    CODING = {
        "category": "Coding & Development",
        "capabilities": [
            "Code writing (Python, JavaScript, Java, C++, Go, Rust, etc.)",
            "Code editing and modification",
            "Debugging and error resolution",
            "Code review and analysis",
            "Refactoring and optimization",
            "Testing (unit, integration, e2e)",
            "Bug fixing and patch creation"
        ]
    }
    
    # 2. File & Project Management
    FILE_MANAGEMENT = {
        "category": "File & Project Management",
        "capabilities": [
            "Create files and directories",
            "Edit existing files",
            "Delete files safely",
            "Project structure exploration",
            "Git operations (commit, push, pull, merge)",
            "Branch management",
            "Merge conflict resolution"
        ]
    }
    
    # 3. Web & Browser
    WEB_BROWSER = {
        "category": "Web & Browser",
        "capabilities": [
            "Navigate to websites",
            "Fill web forms",
            "Click buttons and interact",
            "Extract web content",
            "Screenshot capture",
            "API calls (REST, GraphQL)",
            "Web scraping"
        ]
    }
    
    # 4. Automation
    AUTOMATION = {
        "category": "Automation",
        "capabilities": [
            "Cron jobs and scheduled tasks",
            "GitHub Actions workflow creation",
            "Webhook integrations",
            "API automation",
            "CI/CD pipeline setup",
            "Background job management"
        ]
    }
    
    # 5. Cloud & DevOps
    CLOUD_DEVOPS = {
        "category": "Cloud & DevOps",
        "capabilities": [
            "Docker container management",
            "Kubernetes cluster operations",
            "Cloud service integrations",
            "AWS/GCP/Azure operations",
            "Infrastructure as Code",
            "Deployment automation"
        ]
    }
    
    # 6. Specialized Tools
    SPECIALIZED = {
        "category": "Specialized Tools",
        "capabilities": [
            "Linear (project management)",
            "Notion (documentation)",
            "Slack (communication)",
            "GitHub PR/Issue management",
            "GitLab merge requests",
            "Datadog monitoring",
            "Data analysis and research"
        ]
    }
    
    # 7. Document Creation
    DOCUMENTS = {
        "category": "Document Creation",
        "capabilities": [
            "LaTeX document generation",
            "Markdown documentation",
            "Skill file creation",
            "Report generation",
            "Technical writing",
            "API documentation"
        ]
    }
    
    def __init__(self):
        self.all_categories = [
            self.CODING,
            self.FILE_MANAGEMENT,
            self.WEB_BROWSER,
            self.AUTOMATION,
            self.CLOUD_DEVOPS,
            self.SPECIALIZED,
            self.DOCUMENTS
        ]
        self.last_updated = datetime.now().isoformat()
    
    def get_all_capabilities(self) -> Dict[str, Any]:
        """Get all capabilities."""
        return {
            "entity": "GLUTTONY",
            "version": "OMEGA Ω+2",
            "total_categories": len(self.all_categories),
            "total_capabilities": self.get_total_capability_count(),
            "categories": self.all_categories,
            "last_updated": self.last_updated
        }
    
    def get_category(self, category_name: str) -> Dict:
        """Get specific category."""
        for cat in self.all_categories:
            if cat["category"].lower().replace(" ", "_") == category_name.lower().replace(" ", "_"):
                return cat
        return None
    
    def get_capability_summary(self) -> List[str]:
        """Get simple capability list."""
        summary = []
        for cat in self.all_categories:
            summary.append(f"**{cat['category']}**: {len(cat['capabilities'])} capabilities")
        return summary
    
    def get_total_capability_count(self) -> int:
        """Get total count of all capabilities."""
        return sum(len(cat["capabilities"]) for cat in self.all_categories)


_capabilities: Capabilities = None


def get_capabilities() -> Capabilities:
    """Get capabilities singleton."""
    global _capabilities
    if _capabilities is None:
        _capabilities = Capabilities()
    return _capabilities

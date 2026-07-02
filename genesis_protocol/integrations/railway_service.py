"""Gluttony OS - Railway Integration Service

Provides real-time access to Railway deployment logs, status, and management using GraphQL API.
"""

import requests
import logging
from typing import Dict, Optional, List, Any

logger = logging.getLogger("integrations.railway")

# Railway GraphQL API
RAILWAY_API = "https://backboard.railway.app/graphql/v2"


class RailwayService:
    """
    Railway deployment service for Gluttony OS using GraphQL API.
    
    Features:
    - Get deployment status
    - Fetch real-time logs
    - Trigger redeploy
    - View project information
    """
    
    def __init__(self, token: str = None):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}" if token else "",
            "Content-Type": "application/json"
        }
    
    def is_configured(self) -> bool:
        """Check if Railway token is configured."""
        return bool(self.token)
    
    def _graphql(self, query: str, variables: Dict = None) -> Dict:
        """Execute GraphQL query."""
        if not self.token:
            return {"error": "Token not configured"}
        
        try:
            response = requests.post(
                RAILWAY_API,
                headers=self.headers,
                json={"query": query, "variables": variables} if variables else {"query": query},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    return {"error": data["errors"][0]["message"]}
                return data.get("data", {})
            else:
                return {"error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"GraphQL error: {e}")
            return {"error": str(e)}
    
    def get_projects(self) -> List[Dict]:
        """Get all Railway projects."""
        query = """
        query {
            projects {
                edges {
                    node {
                        id
                        name
                        description
                        createdAt
                    }
                }
            }
        }
        """
        data = self._graphql(query)
        
        if "error" in data:
            logger.error(f"Error: {data['error']}")
            return []
        
        return [e["node"] for e in data.get("projects", {}).get("edges", [])]
    
    def get_project_by_name(self, name: str = None) -> Optional[Dict]:
        """Get project by name. If no name given, return first project."""
        projects = self.get_projects()
        
        if not name:
            return projects[0] if projects else None
        
        for project in projects:
            if name.lower() in project.get('name', '').lower():
                return project
        
        return projects[0] if projects else None
    
    def get_services(self, project_id: str) -> List[Dict]:
        """Get services in a project."""
        query = """
        query GetServices($projectId: String!) {
            project(id: $projectId) {
                services {
                    edges {
                        node {
                            id
                            name
                            status
                        }
                    }
                }
            }
        }
        """
        data = self._graphql(query, {"projectId": project_id})
        
        if "error" in data:
            return []
        
        project = data.get("project", {})
        return [e["node"] for e in project.get("services", {}).get("edges", [])]
    
    def get_deployment_status(self, project_id: str) -> Dict:
        """Get current deployment status for a project."""
        query = """
        query GetDeployments($projectId: String!) {
            project(id: $projectId) {
                deployments(first: 1) {
                    edges {
                        node {
                            id
                            status
                            createdAt
                            updatedAt
                            buildLog
                        }
                    }
                }
            }
        }
        """
        data = self._graphql(query, {"projectId": project_id})
        
        if "error" in data:
            return {"status": "error", "message": data["error"]}
        
        project = data.get("project", {})
        deployments = project.get("deployments", {}).get("edges", [])
        
        if not deployments:
            return {"status": "unknown", "message": "No deployments found"}
        
        deployment = deployments[0]["node"]
        
        status_emoji = {
            "SUCCESS": "✅",
            "FAILED": "❌",
            "BUILDING": "🔨",
            "DEPLOYING": "🚀",
            "INITIALIZING": "⚡",
            "REMOVED": "🗑️"
        }.get(deployment.get("status", "").upper(), "❓")
        
        return {
            "status": deployment.get("status", "unknown"),
            "status_emoji": status_emoji,
            "message": f"{status_emoji} {deployment.get('status', 'Unknown')}",
            "deployment_id": deployment.get("id"),
            "created_at": deployment.get("createdAt"),
            "updated_at": deployment.get("updatedAt")
        }
    
    def get_logs(self, project_id: str, service_id: str = None) -> List[str]:
        """Get deployment logs."""
        query = """
        query GetLogs($projectId: String!, $serviceId: String) {
            project(id: $projectId) {
                deployments(first: 1) {
                    edges {
                        node {
                            id
                            status
                            buildLog
                        }
                    }
                }
            }
        }
        """
        data = self._graphql(query, {"projectId": project_id})
        
        if "error" in data:
            return [f"Error: {data['error']}"]
        
        project = data.get("project", {})
        deployments = project.get("deployments", {}).get("edges", [])
        
        if not deployments:
            return ["No deployments found"]
        
        build_log = deployments[0]["node"].get("buildLog", "")
        
        if build_log:
            return build_log.split("\n")[-50:]  # Last 50 lines
        else:
            return ["No build logs available"]
    
    def trigger_redeploy(self, project_id: str) -> Dict:
        """Trigger a new deployment via Railway Connect."""
        if not self.token:
            return {"success": False, "message": "Token not configured"}
        
        # Note: Redeploy requires Railway Connect which needs CLI setup
        # For now, return instructions
        return {
            "success": True,
            "message": "Redeploy via Railway Dashboard or Railway CLI",
            "project_id": project_id,
            "dashboard_url": f"https://railway.app/project/{project_id}"
        }
    
    def get_service_status(self, project_id: str = None) -> Dict:
        """Get overall service status. If no project_id, find first project."""
        if not project_id:
            project = self.get_project_by_name()
            if project:
                project_id = project.get("id")
            else:
                return {"status": "unknown", "message": "No projects found"}
        
        # Get deployment status
        deploy_status = self.get_deployment_status(project_id)
        
        # Get project info
        projects = self.get_projects()
        project_name = "Unknown"
        for p in projects:
            if p.get("id") == project_id:
                project_name = p.get("name", "Unknown")
                break
        
        return {
            "project_id": project_id,
            "project_name": project_name,
            "status": deploy_status.get("status", "unknown"),
            "message": deploy_status.get("message", ""),
            "deployment_id": deploy_status.get("deployment_id"),
            "last_deploy": deploy_status.get("created_at"),
            "dashboard_url": f"https://railway.app/project/{project_id}"
        }
    
    def format_status(self) -> str:
        """Format Railway status for display."""
        if not self.token:
            return "❌ Railway API not configured\n\nTo enable:\n1. Railway Dashboard → Settings → API Tokens\n2. Create new token\n3. Add RAILWAY_TOKEN to environment"
        
        status = self.get_service_status()
        
        if status.get("status") == "unknown" and "No projects" in status.get("message", ""):
            return "⚠️ No Railway projects found with this token"
        
        lines = [
            "🚂 **Railway Status**\n",
            f"📦 **Project:** {status.get('project_name', 'Unknown')}",
            f"📊 **Status:** {status.get('message', 'Unknown')}",
            f"🔗 **Dashboard:** {status.get('dashboard_url', 'N/A')}",
            f"🕐 **Last Deploy:** {status.get('last_deploy', 'Unknown')[:10] if status.get('last_deploy') else 'Unknown'}",
        ]
        
        return "\n".join(lines)


# Singleton instance
_railway_service = None

def get_railway_service() -> RailwayService:
    """Get singleton instance."""
    global _railway_service
    if _railway_service is None:
        import os
        token = os.getenv("RAILWAY_TOKEN")
        _railway_service = RailwayService(token)
    return _railway_service

"""Gluttony OS - Railway Integration Service

Provides real-time access to Railway deployment logs, status, and management.
"""

import requests
import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger("integrations.railway")

# Railway API Base
RAILWAY_API = "https://backboard.railway.app/api/v2"


class RailwayService:
    """
    Railway deployment service for Gluttony OS.
    
    Features:
    - Get deployment status
    - Fetch real-time logs
    - Check environment variables
    - Trigger redeploy
    - View resource usage
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
    
    def get_projects(self) -> List[Dict]:
        """Get all Railway projects."""
        if not self.token:
            return []
        
        try:
            response = requests.get(
                f"{RAILWAY_API}/projects",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('projects', [])
            else:
                logger.error(f"Railway API error: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching projects: {e}")
            return []
    
    def get_project_by_name(self, name: str = "genesis-protocol-00a1") -> Optional[Dict]:
        """Get project by name."""
        projects = self.get_projects()
        
        for project in projects:
            if name.lower() in project.get('name', '').lower():
                return project
        
        # Return first project if exact match not found
        return projects[0] if projects else None
    
    def get_deployments(self, project_id: str) -> List[Dict]:
        """Get recent deployments for a project."""
        if not self.token or not project_id:
            return []
        
        try:
            response = requests.get(
                f"{RAILWAY_API}/projects/{project_id}/deployments",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('deployments', [])
            return []
            
        except Exception as e:
            logger.error(f"Error fetching deployments: {e}")
            return []
    
    def get_logs(self, project_id: str, deployment_id: str = None, limit: int = 100) -> List[str]:
        """Get deployment logs."""
        if not self.token or not project_id:
            return ["Railway token not configured"]
        
        try:
            endpoint = f"{RAILWAY_API}/projects/{project_id}/logs"
            if deployment_id:
                endpoint += f"?deploymentId={deployment_id}"
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                return logs[-limit:] if logs else ["No logs available"]
            else:
                return [f"Error: {response.status_code} - {response.text}"]
                
        except Exception as e:
            logger.error(f"Error fetching logs: {e}")
            return [f"Error: {str(e)}"]
    
    def get_service_status(self, project_id: str) -> Dict:
        """Get current service status."""
        deployments = self.get_deployments(project_id)
        
        if not deployments:
            return {
                "status": "unknown",
                "message": "No deployments found",
                "last_deploy": None
            }
        
        latest = deployments[0]
        status = latest.get('status', 'unknown')
        
        return {
            "status": status,
            "message": f"Deployment #{latest.get('number', '?')}",
            "last_deploy": latest.get('createdAt', ''),
            "url": latest.get('url', ''),
            "region": latest.get('region', 'unknown')
        }
    
    def trigger_redeploy(self, project_id: str) -> Dict:
        """Trigger a new deployment."""
        if not self.token or not project_id:
            return {"success": False, "message": "Railway token not configured"}
        
        try:
            response = requests.post(
                f"{RAILWAY_API}/projects/{project_id}/deployments",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                return {
                    "success": True,
                    "message": "Deployment triggered successfully",
                    "data": response.json()
                }
            else:
                return {
                    "success": False,
                    "message": f"Error: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error triggering deploy: {e}")
            return {"success": False, "message": str(e)}
    
    def format_status(self) -> str:
        """Format Railway status for display."""
        if not self.token:
            return "❌ Railway API not configured\n\nTo enable:\n1. Railway Dashboard → Settings → API Tokens\n2. Create new token\n3. Add RAILWAY_TOKEN to environment"
        
        projects = self.get_projects()
        
        if not projects:
            return "⚠️ No Railway projects found"
        
        lines = ["🚂 **Railway Status**\n"]
        
        for project in projects[:3]:  # Show max 3 projects
            project_id = project.get('id', '')
            name = project.get('name', 'Unknown')
            
            lines.append(f"📦 **{name}**")
            
            status = self.get_service_status(project_id)
            lines.append(f"   Status: {status['status']}")
            lines.append(f"   Message: {status['message']}")
            lines.append("")
        
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

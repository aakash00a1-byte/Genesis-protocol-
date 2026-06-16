"""
Automation Skills
==================
Cron jobs, scheduled tasks, GitHub Actions, and API integrations.
"""

import os
import re
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from genesis_protocol.skills import Skill, SkillCategory

# Skill definitions
SKILLS = [
    Skill(
        name="cron_jobs",
        category=SkillCategory.AUTOMATION,
        description="Create and manage cron jobs for scheduled tasks",
        tools=["subprocess", "crontab"],
        version="1.0.0"
    ),
    Skill(
        name="github_actions",
        category=SkillCategory.AUTOMATION,
        description="Create and manage GitHub Actions workflows",
        tools=["file_write", "git"],
        version="1.0.0"
    ),
    Skill(
        name="api_integration",
        category=SkillCategory.AUTOMATION,
        description="Integrate with external APIs",
        tools=["http", "json"],
        version="1.0.0"
    ),
    Skill(
        name="webhook_handler",
        category=SkillCategory.AUTOMATION,
        description="Handle webhooks and events",
        tools=["http", "json"],
        version="1.0.0"
    ),
]


class CronManager:
    """Manage cron jobs."""
    
    def __init__(self):
        self.crontab_file = Path.home() / ".genesis_crontab"
    
    def list_jobs(self) -> List[Dict[str, str]]:
        """List all current cron jobs."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            jobs = []
            for line in result.stdout.split("\n"):
                if line and not line.startswith("#") and "*" in line:
                    parts = line.split(None, 5)
                    if len(parts) >= 6:
                        jobs.append({
                            "schedule": " ".join(parts[:5]),
                            "command": parts[5]
                        })
            
            return jobs
        except Exception:
            return []
    
    def create_job(self, schedule: str, command: str, description: str = "") -> Dict[str, Any]:
        """Create a new cron job."""
        try:
            # Validate schedule
            if not self._validate_schedule(schedule):
                return {"success": False, "error": "Invalid cron schedule"}
            
            # Add to crontab
            job_entry = f"# {description}\n{schedule} {command}\n"
            
            # Read existing crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )
            
            existing = result.stdout if result.returncode == 0 else ""
            
            # Append new job
            new_crontab = existing + "\n" + job_entry
            
            # Write new crontab
            with open(self.crontab_file, "w") as f:
                f.write(new_crontab)
            
            subprocess.run(["crontab", str(self.crontab_file)], check=True)
            
            return {
                "success": True,
                "schedule": schedule,
                "command": command,
                "message": "Cron job created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_job(self, schedule: str, command: str) -> Dict[str, Any]:
        """Delete a cron job."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return {"success": False, "error": "No crontab found"}
            
            lines = result.stdout.split("\n")
            new_lines = []
            skip = False
            
            for line in lines:
                if skip:
                    skip = False
                    continue
                
                # Check if this line matches the job to delete
                parts = line.split(None, 5)
                if len(parts) >= 6:
                    job_schedule = " ".join(parts[:5])
                    job_command = parts[5]
                    
                    if job_schedule == schedule and job_command == command:
                        # Skip this job (and its comment)
                        if new_lines and new_lines[-1].startswith("# "):
                            new_lines.pop()
                        continue
                
                new_lines.append(line)
            
            # Write new crontab
            new_crontab = "\n".join(new_lines) + "\n"
            with open(self.crontab_file, "w") as f:
                f.write(new_crontab)
            
            subprocess.run(["crontab", str(self.crontab_file)], check=True)
            
            return {"success": True, "message": "Cron job deleted"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _validate_schedule(self, schedule: str) -> bool:
        """Validate cron schedule format."""
        pattern = r'^(\*|[0-9,\-]+)\s+(\*|[0-9,\-]+)\s+(\*|[0-9,\-]+)\s+(\*|[0-9,\-]+)\s+(\*|[0-9,\-]+)$'
        return bool(re.match(pattern, schedule))


class GitHubActionsManager:
    """Manage GitHub Actions workflows."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path)
        self.workflows_dir = self.repo_path / ".github" / "workflows"
    
    def create_workflow(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new GitHub Actions workflow."""
        try:
            self.workflows_dir.mkdir(parents=True, exist_ok=True)
            
            workflow_file = self.workflows_dir / f"{name}.yml"
            
            # Generate workflow content
            content = self._generate_workflow(name, config)
            
            workflow_file.write_text(content)
            
            return {
                "success": True,
                "path": str(workflow_file),
                "name": name
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _generate_workflow(self, name: str, config: Dict[str, Any]) -> str:
        """Generate workflow YAML content."""
        triggers = config.get("on", ["push", "pull_request"])
        if isinstance(triggers, str):
            triggers = [triggers]
        
        jobs = config.get("jobs", {})
        
        workflow = f"""name: {name}

on:
"""
        
        for trigger in triggers:
            workflow += f"  {trigger}:\n"
        
        if "branches" in config:
            workflow += "    branches:\n"
            for branch in config["branches"]:
                workflow += f"      - {branch}\n"
        
        workflow += "\njobs:\n"
        
        for job_name, job_config in jobs.items():
            workflow += f"  {job_name}:\n"
            workflow += f"    runs-on: {job_config.get('runs-on', 'ubuntu-latest')}\n"
            workflow += "    steps:\n"
            
            for step in job_config.get("steps", []):
                if isinstance(step, str):
                    workflow += f"      - run: {step}\n"
                elif isinstance(step, dict):
                    if "uses" in step:
                        workflow += f"      - uses: {step['uses']}\n"
                    if "run" in step:
                        workflow += f"      - run: {step['run']}\n"
                    if "name" in step:
                        workflow += f"      - name: {step['name']}\n"
                    if "with" in step:
                        for key, value in step["with"].items():
                            workflow += f"        {key}: {value}\n"
        
        return workflow
    
    def create_ci_workflow(self) -> Dict[str, Any]:
        """Create a standard CI workflow."""
        return self.create_workflow("ci", {
            "on": ["push", "pull_request"],
            "branches": ["main", "develop"],
            "jobs": {
                "test": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        "uses: actions/checkout@v4",
                        "name: Set up Python",
                        "uses: actions/setup-python@v5",
                        {"with": {"python-version": "3.11"}},
                        "run: pip install -r requirements.txt",
                        "run: pytest tests/",
                    ]
                }
            }
        })
    
    def create_docker_workflow(self) -> Dict[str, Any]:
        """Create a Docker build/push workflow."""
        return self.create_workflow("docker", {
            "on": {"push": {"tags": ["v*"]}},
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "steps": [
                        "uses: actions/checkout@v4",
                        "name: Set up Docker Buildx",
                        "uses: docker/setup-buildx-action@v3",
                        "name: Login to Container Registry",
                        "uses: docker/login-action@v3",
                        {"with": {"registry": "ghcr.io", "username": "${{ github.actor }}", "password": "${{ secrets.GITHUB_TOKEN }}"}},
                        "name: Build and Push",
                        "uses: docker/build-push-action@v5",
                        {"with": {"push": "true", "tags": "ghcr.io/${{ github.repository }}:latest"}},
                    ]
                }
            }
        })


class APIIntegration:
    """Handle API integrations."""
    
    def __init__(self):
        self.session = None
    
    async def call_api(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an API call."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    content = await response.text()
                    
                    try:
                        json_data = await response.json()
                    except:
                        json_data = None
                    
                    return {
                        "success": 200 <= response.status < 300,
                        "status": response.status,
                        "data": json_data,
                        "text": content,
                        "headers": dict(response.headers)
                    }
        except ImportError:
            return {"success": False, "error": "aiohttp not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_webhook_handler(
        self,
        event_type: str,
        handler_code: str
    ) -> Dict[str, Any]:
        """Create a webhook handler script."""
        return {
            "success": True,
            "event_type": event_type,
            "handler": handler_code,
            "note": "Webhook handler template created"
        }


# Export skill execution functions
async def execute_cron_create(schedule: str, command: str, description: str = "") -> Dict[str, Any]:
    """Execute cron job creation."""
    manager = CronManager()
    return manager.create_job(schedule, command, description)


async def execute_github_actions_create(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute GitHub Actions workflow creation."""
    manager = GitHubActionsManager()
    return manager.create_workflow(name, config)


async def execute_api_call(url: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
    """Execute API call."""
    integrator = APIIntegration()
    return await integrator.call_api(url, method, **kwargs)


# Export skill executors
SKILL_EXECUTORS = {
    "cron_jobs": execute_cron_create,
    "github_actions": execute_github_actions_create,
    "api_integration": execute_api_call,
}
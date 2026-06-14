"""Genesis Protocol - Deployer

Deployment automation for multiple platforms:
- Railway
- Render
- Vercel
- Docker
- Custom VPS
"""

import os
import subprocess
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from genesis_protocol.utils.logger import get_logger

logger = get_logger("powers.deployer")


@dataclass
class DeploymentResult:
    """Result of deployment."""
    success: bool
    platform: str
    url: Optional[str]
    logs: str
    error: Optional[str] = None


class Deployer:
    """
    Multi-platform deployment system.
    
    Supported platforms:
    - Railway (railway.app)
    - Render (render.com)
    - Vercel (vercel.com)
    - Docker (containerized)
    - Custom SSH
    """

    def __init__(self):
        """Initialize deployer."""
        self.platforms = {
            "railway": self._deploy_railway,
            "render": self._deploy_render,
            "vercel": self._deploy_vercel,
            "docker": self._deploy_docker,
            "dockerhub": self._deploy_dockerhub,
        }
        logger.info("Deployer initialized")

    async def deploy(
        self,
        project_path: str,
        platform: str,
        options: Dict = None
    ) -> DeploymentResult:
        """
        Deploy project to specified platform.
        
        Args:
            project_path: Path to project to deploy
            platform: Target platform (railway, render, vercel, docker)
            options: Platform-specific options
            
        Returns:
            DeploymentResult with deployment status
        """
        options = options or {}
        
        if platform not in self.platforms:
            return DeploymentResult(
                success=False,
                platform=platform,
                url=None,
                logs="",
                error=f"Unknown platform: {platform}"
            )
        
        try:
            return await self.platforms[platform](project_path, options)
        except Exception as e:
            logger.error(f"Deployment to {platform} failed: {e}")
            return DeploymentResult(
                success=False,
                platform=platform,
                url=None,
                logs="",
                error=str(e)
            )

    async def _deploy_railway(self, project_path: str, options: Dict) -> DeploymentResult:
        """Deploy to Railway."""
        try:
            # Check if Railway CLI is installed
            try:
                subprocess.run(["railway", "--version"], check=True, capture_output=True)
            except:
                return DeploymentResult(
                    success=False,
                    platform="railway",
                    url=None,
                    logs="",
                    error="Railway CLI not installed. Run: npm install -g @railway/cli"
                )
            
            # Check for railway.json
            railway_config = os.path.join(project_path, "railway.json")
            if not os.path.exists(railway_config):
                # Create default config
                self._create_railway_config(project_path)
            
            # Run railway deploy
            result = subprocess.run(
                ["railway", "up"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return DeploymentResult(
                    success=True,
                    platform="railway",
                    url="https://railway.app/project",
                    logs=result.stdout
                )
            else:
                return DeploymentResult(
                    success=False,
                    platform="railway",
                    url=None,
                    logs=result.stdout,
                    error=result.stderr
                )
                
        except subprocess.TimeoutExpired:
            return DeploymentResult(
                success=False,
                platform="railway",
                url=None,
                logs="",
                error="Deployment timed out"
            )
        except Exception as e:
            return DeploymentResult(
                success=False,
                platform="railway",
                url=None,
                logs="",
                error=str(e)
            )

    async def _deploy_render(self, project_path: str, options: Dict) -> DeploymentResult:
        """Deploy to Render."""
        try:
            # Check for render.yaml
            render_config = os.path.join(project_path, "render.yaml")
            if not os.path.exists(render_config):
                self._create_render_config(project_path, options)
            
            return DeploymentResult(
                success=True,
                platform="render",
                url="https://render.com",
                logs="Render configuration created. Connect your GitHub repo at render.com to deploy."
            )
                
        except Exception as e:
            return DeploymentResult(
                success=False,
                platform="render",
                url=None,
                logs="",
                error=str(e)
            )

    async def _deploy_vercel(self, project_path: str, options: Dict) -> DeploymentResult:
        """Deploy to Vercel."""
        try:
            try:
                subprocess.run(["vercel", "--version"], check=True, capture_output=True)
            except:
                return DeploymentResult(
                    success=False,
                    platform="vercel",
                    url=None,
                    logs="",
                    error="Vercel CLI not installed. Run: npm install -g vercel"
                )
            
            result = subprocess.run(
                ["vercel", "--prod"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                # Extract URL from output
                url_match = [line for line in result.stdout.split('\n') if 'vercel.app' in line]
                url = url_match[0].strip() if url_match else "Deployed successfully"
                
                return DeploymentResult(
                    success=True,
                    platform="vercel",
                    url=url,
                    logs=result.stdout
                )
            else:
                return DeploymentResult(
                    success=False,
                    platform="vercel",
                    url=None,
                    logs=result.stdout,
                    error=result.stderr
                )
                
        except Exception as e:
            return DeploymentResult(
                success=False,
                platform="vercel",
                url=None,
                logs="",
                error=str(e)
            )

    async def _deploy_docker(self, project_path: str, options: Dict) -> DeploymentResult:
        """Build and run Docker container."""
        try:
            dockerfile = os.path.join(project_path, "Dockerfile")
            if not os.path.exists(dockerfile):
                return DeploymentResult(
                    success=False,
                    platform="docker",
                    url=None,
                    logs="",
                    error="No Dockerfile found in project"
                )
            
            image_name = options.get("image_name", "genesis-app")
            port = options.get("port", 8000)
            
            # Build image
            build_result = subprocess.run(
                ["docker", "build", "-t", image_name, "."],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if build_result.returncode != 0:
                return DeploymentResult(
                    success=False,
                    platform="docker",
                    url=None,
                    logs=build_result.stdout,
                    error=build_result.stderr
                )
            
            # Run container
            run_result = subprocess.run(
                ["docker", "run", "-d", "-p", f"{port}:{port}", "--name", image_name, image_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if run_result.returncode == 0:
                return DeploymentResult(
                    success=True,
                    platform="docker",
                    url=f"http://localhost:{port}",
                    logs=f"Container '{image_name}' running on port {port}"
                )
            else:
                return DeploymentResult(
                    success=False,
                    platform="docker",
                    url=None,
                    logs=build_result.stdout,
                    error=run_result.stderr
                )
                
        except Exception as e:
            return DeploymentResult(
                success=False,
                platform="docker",
                url=None,
                logs="",
                error=str(e)
            )

    async def _deploy_dockerhub(self, project_path: str, options: Dict) -> DeploymentResult:
        """Build and push to Docker Hub."""
        try:
            dockerfile = os.path.join(project_path, "Dockerfile")
            if not os.path.exists(dockerfile):
                return DeploymentResult(
                    success=False,
                    platform="dockerhub",
                    url=None,
                    logs="",
                    error="No Dockerfile found"
                )
            
            image_name = options.get("image_name", "genesis-app")
            dockerhub_user = options.get("dockerhub_user", "")
            
            if not dockerhub_user:
                return DeploymentResult(
                    success=False,
                    platform="dockerhub",
                    url=None,
                    logs="",
                    error="Docker Hub username required (set dockerhub_user in options)"
                )
            
            full_image = f"{dockerhub_user}/{image_name}"
            
            # Build
            build_result = subprocess.run(
                ["docker", "build", "-t", full_image, "."],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if build_result.returncode != 0:
                return DeploymentResult(
                    success=False,
                    platform="dockerhub",
                    url=None,
                    logs=build_result.stdout,
                    error=build_result.stderr
                )
            
            # Tag
            subprocess.run(["docker", "tag", full_image, f"{full_image}:latest"], check=True)
            
            # Push
            push_result = subprocess.run(
                ["docker", "push", full_image],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if push_result.returncode == 0:
                return DeploymentResult(
                    success=True,
                    platform="dockerhub",
                    url=f"https://hub.docker.com/r/{full_image}",
                    logs=f"Image pushed to Docker Hub: {full_image}"
                )
            else:
                return DeploymentResult(
                    success=False,
                    platform="dockerhub",
                    url=None,
                    logs="",
                    error="Push failed. Run 'docker login' first."
                )
                
        except Exception as e:
            return DeploymentResult(
                success=False,
                platform="dockerhub",
                url=None,
                logs="",
                error=str(e)
            )

    def _create_railway_config(self, project_path: str):
        """Create Railway configuration."""
        config = {
            "build": {
                "builder": "NIXPACKS",
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "python genesis_protocol/main.py"
            },
            "deploy": {
                "numReplicas": 1,
                "restartPolicyType": "ON_FAILURE",
                "restartPolicyMaxRetries": 10
            }
        }
        
        import json
        with open(os.path.join(project_path, "railway.json"), "w") as f:
            json.dump(config, f, indent=2)

    def _create_render_config(self, project_path: str, options: Dict):
        """Create Render configuration."""
        config = {
            "services": [{
                "type": "web",
                "name": "genesis-protocol",
                "env": "python",
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "python genesis_protocol/main.py",
                "healthCheckPath": "/health",
                "envVars": [
                    {"key": "TELEGRAM_BOT_TOKEN", "sync": False},
                    {"key": "GROQ_API_KEY", "sync": False},
                    {"key": "OPENAI_API_KEY", "sync": False}
                ]
            }]
        }
        
        import json
        with open(os.path.join(project_path, "render.yaml"), "w") as f:
            json.dump(config, f, indent=2)

    def get_platforms(self) -> List[str]:
        """Get list of supported platforms."""
        return list(self.platforms.keys())

    def check_platform_cli(self, platform: str) -> bool:
        """Check if platform CLI is installed."""
        cli_map = {
            "railway": "railway",
            "vercel": "vercel",
            "docker": "docker"
        }
        
        if platform not in cli_map:
            return True  # No CLI needed
        
        try:
            result = subprocess.run(
                [cli_map[platform], "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False


# Singleton
_deployer: Optional[Deployer] = None


def get_deployer() -> Deployer:
    """Get or create Deployer singleton."""
    global _deployer
    if _deployer is None:
        _deployer = Deployer()
    return _deployer
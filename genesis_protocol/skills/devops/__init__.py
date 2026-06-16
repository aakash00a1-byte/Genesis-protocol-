"""
DevOps Skills
==============
Docker, Kubernetes, and cloud services management.
"""

import subprocess
import json
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from genesis_protocol.skills import Skill, SkillCategory

# Skill definitions
SKILLS = [
    Skill(
        name="docker_management",
        category=SkillCategory.DEVOPS,
        description="Manage Docker containers, images, and compose",
        tools=["docker", "subprocess"],
        version="1.0.0"
    ),
    Skill(
        name="kubernetes_management",
        category=SkillCategory.DEVOPS,
        description="Manage Kubernetes clusters and deployments",
        tools=["kubectl", "docker"],
        version="1.0.0"
    ),
    Skill(
        name="cloud_services",
        category=SkillCategory.DEVOPS,
        description="Interact with cloud platforms (AWS, GCP, Azure)",
        tools=["aws", "gcloud", "az"],
        version="1.0.0"
    ),
    Skill(
        name="infrastructure_as_code",
        category=SkillCategory.DEVOPS,
        description="Create and manage infrastructure configurations",
        tools=["file_write", "terraform"],
        version="1.0.0"
    ),
]


class DockerManager:
    """Manage Docker containers and images."""
    
    def __init__(self):
        self.docker_available = self._check_docker()
    
    def _check_docker(self) -> bool:
        """Check if Docker is available."""
        try:
            subprocess.run(["docker", "--version"], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def run_command(self, *args) -> Dict[str, Any]:
        """Run a Docker command."""
        if not self.docker_available:
            return {"success": False, "error": "Docker not available"}
        
        try:
            result = subprocess.run(
                ["docker"] + list(args),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_containers(self, all: bool = True) -> List[Dict[str, str]]:
        """List Docker containers."""
        result = self.run_command("ps", "--format", "{{json .}}")
        
        if result.get("success"):
            containers = []
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        containers.append(json.loads(line))
                    except:
                        pass
            return containers
        
        return []
    
    def list_images(self) -> List[Dict[str, str]]:
        """List Docker images."""
        result = self.run_command("images", "--format", "{{json .}}")
        
        if result.get("success"):
            images = []
            for line in result["stdout"].strip().split("\n"):
                if line:
                    try:
                        images.append(json.loads(line))
                    except:
                        pass
            return images
        
        return []
    
    def build_image(
        self,
        path: str = ".",
        tag: str = "latest",
        dockerfile: str = "Dockerfile"
    ) -> Dict[str, Any]:
        """Build a Docker image."""
        return self.run_command(
            "build",
            "-f", dockerfile,
            "-t", tag,
            path
        )
    
    def run_container(
        self,
        image: str,
        name: Optional[str] = None,
        ports: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
        detach: bool = True
    ) -> Dict[str, Any]:
        """Run a Docker container."""
        args = ["run"]
        
        if detach:
            args.append("-d")
        
        if name:
            args.extend(["--name", name])
        
        if ports:
            for host, container in ports.items():
                args.extend(["-p", f"{host}:{container}"])
        
        if env:
            for key, value in env.items():
                args.extend(["-e", f"{key}={value}"])
        
        args.append(image)
        
        return self.run_command(*args)
    
    def stop_container(self, name_or_id: str) -> Dict[str, Any]:
        """Stop a container."""
        return self.run_command("stop", name_or_id)
    
    def remove_container(self, name_or_id: str, force: bool = False) -> Dict[str, Any]:
        """Remove a container."""
        args = ["rm"]
        if force:
            args.append("-f")
        args.append(name_or_id)
        return self.run_command(*args)
    
    def compose_up(
        self,
        path: str = "docker-compose.yml",
        detach: bool = True
    ) -> Dict[str, Any]:
        """Run docker-compose up."""
        args = ["compose", "-f", path]
        if detach:
            args.append("-d")
        args.append("up")
        
        return self.run_command(*args)
    
    def compose_down(self, path: str = "docker-compose.yml") -> Dict[str, Any]:
        """Run docker-compose down."""
        return self.run_command("compose", "-f", path, "down")


class KubernetesManager:
    """Manage Kubernetes resources."""
    
    def __init__(self):
        self.kubectl_available = self._check_kubectl()
    
    def _check_kubectl(self) -> bool:
        """Check if kubectl is available."""
        try:
            subprocess.run(["kubectl", "version", "--client"], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def run_command(self, *args) -> Dict[str, Any]:
        """Run a kubectl command."""
        if not self.kubectl_available:
            return {"success": False, "error": "kubectl not available"}
        
        try:
            result = subprocess.run(
                ["kubectl"] + list(args),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_pods(self, namespace: str = "default") -> List[Dict[str, str]]:
        """Get pods in a namespace."""
        result = self.run_command(
            "get", "pods",
            "-n", namespace,
            "-o", "json"
        )
        
        if result.get("success"):
            try:
                data = json.loads(result["stdout"])
                return [
                    {
                        "name": p["metadata"]["name"],
                        "status": p["status"]["phase"],
                        "ready": f"{sum(1 for c in p['status'].get('conditions', []) if c['type'] == 'Ready' and c['status'] == 'True')}/{len(p['status'].get('containerStatuses', []))}"
                    }
                    for p in data.get("items", [])
                ]
            except:
                pass
        
        return []
    
    def get_services(self, namespace: str = "default") -> List[Dict[str, str]]:
        """Get services in a namespace."""
        result = self.run_command(
            "get", "services",
            "-n", namespace,
            "-o", "wide"
        )
        
        return result.get("stdout", "").split("\n")
    
    def apply_manifest(self, manifest_path: str) -> Dict[str, Any]:
        """Apply a Kubernetes manifest."""
        return self.run_command("apply", "-f", manifest_path)
    
    def delete_manifest(self, manifest_path: str) -> Dict[str, Any]:
        """Delete resources from a manifest."""
        return self.run_command("delete", "-f", manifest_path)
    
    def scale_deployment(
        self,
        name: str,
        replicas: int,
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """Scale a deployment."""
        return self.run_command(
            "scale", "deployment", name,
            f"--replicas={replicas}",
            "-n", namespace
        )
    
    def get_logs(
        self,
        name: str,
        namespace: str = "default",
        tail: int = 100
    ) -> Dict[str, Any]:
        """Get pod logs."""
        return self.run_command(
            "logs", name,
            "-n", namespace,
            f"--tail={tail}"
        )


class CloudManager:
    """Manage cloud services."""
    
    def __init__(self):
        self.providers = {
            "aws": self._check_aws(),
            "gcp": self._check_gcp(),
            "azure": self._check_azure()
        }
    
    def _check_aws(self) -> bool:
        try:
            subprocess.run(["aws", "--version"], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def _check_gcp(self) -> bool:
        try:
            subprocess.run(["gcloud", "--version"], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def _check_azure(self) -> bool:
        try:
            subprocess.run(["az", "--version"], capture_output=True, timeout=5)
            return True
        except:
            return False
    
    def run_aws_command(self, *args) -> Dict[str, Any]:
        """Run AWS CLI command."""
        if not self.providers["aws"]:
            return {"success": False, "error": "AWS CLI not available"}
        
        try:
            result = subprocess.run(
                ["aws"] + list(args),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def run_gcloud_command(self, *args) -> Dict[str, Any]:
        """Run Google Cloud CLI command."""
        if not self.providers["gcp"]:
            return {"success": False, "error": "gcloud not available"}
        
        try:
            result = subprocess.run(
                ["gcloud"] + list(args),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class IaCManager:
    """Infrastructure as Code management."""
    
    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace)
    
    def create_docker_compose(
        self,
        services: Dict[str, Dict],
        output_path: str = "docker-compose.yml"
    ) -> Dict[str, Any]:
        """Create a docker-compose.yml file."""
        try:
            config = {
                "version": "3.8",
                "services": services
            }
            
            output_file = self.workspace / output_path
            output_file.write_text(yaml.dump(config, default_flow_style=False))
            
            return {"success": True, "path": str(output_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_dockerfile(
        self,
        base_image: str,
        working_dir: str = "/app",
        run_commands: List[str] = None,
        output_path: str = "Dockerfile"
    ) -> Dict[str, Any]:
        """Create a Dockerfile."""
        try:
            content = f"""FROM {base_image}

WORKDIR {working_dir}
"""
            if run_commands:
                content += "\n".join([f"RUN {cmd}" for cmd in run_commands])
                content += "\n"
            
            content += """
COPY . .
"""
            
            output_file = self.workspace / output_path
            output_file.write_text(content)
            
            return {"success": True, "path": str(output_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def create_k8s_manifest(
        self,
        kind: str,
        name: str,
        spec: Dict[str, Any],
        output_path: str
    ) -> Dict[str, Any]:
        """Create a Kubernetes manifest."""
        try:
            manifest = {
                "apiVersion": self._get_api_version(kind),
                "kind": kind,
                "metadata": {"name": name},
                "spec": spec
            }
            
            output_file = self.workspace / output_path
            output_file.write_text(yaml.dump(manifest, default_flow_style=False))
            
            return {"success": True, "path": str(output_file)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _get_api_version(self, kind: str) -> str:
        """Get Kubernetes API version for resource kind."""
        api_versions = {
            "Deployment": "apps/v1",
            "Service": "v1",
            "ConfigMap": "v1",
            "Secret": "v1",
            "Pod": "v1",
            "Ingress": "networking.k8s.io/v1",
            "PersistentVolumeClaim": "v1"
        }
        return api_versions.get(kind, "v1")


# Export skill executors
async def execute_docker_list() -> Dict[str, Any]:
    """Execute Docker container listing."""
    manager = DockerManager()
    return {"success": True, "containers": manager.list_containers()}


async def execute_k8s_get_pods(namespace: str = "default") -> Dict[str, Any]:
    """Execute Kubernetes pod listing."""
    manager = KubernetesManager()
    return {"success": True, "pods": manager.get_pods(namespace)}


SKILL_EXECUTORS = {
    "docker_management": execute_docker_list,
    "kubernetes_management": execute_k8s_get_pods,
}
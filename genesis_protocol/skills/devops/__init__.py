"""
DevOps Skills
==============
Docker, Kubernetes, and cloud services management.
"""

import json
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from genesis_protocol.skills import Skill, SkillCategory
from genesis_protocol.tools.cli_guard import probe as _probe
from genesis_protocol.tools.cli_guard import run_guarded_command

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

    def __init__(self, *, user_id: Optional[int] = None,
                 approval_id: Optional[str] = None):
        self._user_id = user_id
        self._approval_id = approval_id
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        """Check if Docker is available (fixed probe, no user input)."""
        return _probe("docker", ["--version"])

    def run_command(self, *args, user_id: Optional[int] = None,
                    approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run a Docker command through the owner + consent gate."""
        if not self.docker_available:
            return {"success": False, "error": "Docker not available"}
        return run_guarded_command(
            "docker", list(args),
            user_id=self._user_id if user_id is None else user_id,
            approval_id=self._approval_id if approval_id is None else approval_id,
        )
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

    def __init__(self, *, user_id: Optional[int] = None,
                 approval_id: Optional[str] = None):
        self._user_id = user_id
        self._approval_id = approval_id
        self.kubectl_available = self._check_kubectl()

    def _check_kubectl(self) -> bool:
        """Check if kubectl is available (fixed probe, no user input)."""
        return _probe("kubectl", ["version", "--client"])

    def run_command(self, *args, user_id: Optional[int] = None,
                    approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run a kubectl command through the owner + consent gate."""
        if not self.kubectl_available:
            return {"success": False, "error": "kubectl not available"}
        return run_guarded_command(
            "kubectl", list(args),
            user_id=self._user_id if user_id is None else user_id,
            approval_id=self._approval_id if approval_id is None else approval_id,
        )
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

    def __init__(self, *, user_id: Optional[int] = None,
                 approval_id: Optional[str] = None):
        self._user_id = user_id
        self._approval_id = approval_id
        self.providers = {
            "aws": self._check_aws(),
            "gcp": self._check_gcp(),
            "azure": self._check_azure()
        }

    def _check_aws(self) -> bool:
        return _probe("aws", ["--version"])

    def _check_gcp(self) -> bool:
        return _probe("gcloud", ["--version"])

    def _check_azure(self) -> bool:
        return _probe("az", ["--version"])

    def _run(self, binary: str, args: tuple, user_id: Optional[int],
             approval_id: Optional[str], available: bool,
             label: str) -> Dict[str, Any]:
        if not available:
            return {"success": False, "error": f"{label} not available"}
        return run_guarded_command(
            binary, list(args),
            user_id=self._user_id if user_id is None else user_id,
            approval_id=self._approval_id if approval_id is None else approval_id,
        )

    def run_aws_command(self, *args, user_id: Optional[int] = None,
                        approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run an AWS CLI command through the owner + consent gate."""
        return self._run("aws", args, user_id, approval_id,
                         self.providers["aws"], "AWS CLI")

    def run_gcloud_command(self, *args, user_id: Optional[int] = None,
                           approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run a gcloud command through the owner + consent gate."""
        return self._run("gcloud", args, user_id, approval_id,
                         self.providers["gcp"], "gcloud")

    def run_az_command(self, *args, user_id: Optional[int] = None,
                       approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run an az command through the owner + consent gate."""
        return self._run("az", args, user_id, approval_id,
                         self.providers["azure"], "az")
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
async def execute_docker_list(user_id: Optional[int] = None,
                              approval_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute Docker container listing (owner only)."""
    manager = DockerManager(user_id=user_id, approval_id=approval_id)
    result = manager.run_command("ps", "--format", "{{json .}}")
    if not result.get("success"):
        return result
    return {"success": True, "containers": manager.list_containers()}


async def execute_k8s_get_pods(namespace: str = "default",
                               user_id: Optional[int] = None,
                               approval_id: Optional[str] = None) -> Dict[str, Any]:
    """Execute Kubernetes pod listing (owner only)."""
    manager = KubernetesManager(user_id=user_id, approval_id=approval_id)
    result = manager.run_command("get", "pods", "-n", namespace, "-o", "json")
    if not result.get("success"):
        return result
    return {"success": True, "pods": manager.get_pods(namespace)}


SKILL_EXECUTORS = {
    "docker_management": execute_docker_list,
    "kubernetes_management": execute_k8s_get_pods,
}

"""
File & Project Management Skills
=================================
File operations, project structure exploration, and git operations.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from genesis_protocol.skills import Skill, SkillCategory
from genesis_protocol.tools.cli_guard import run_guarded_command

# Skill definitions
SKILLS = [
    Skill(
        name="file_create",
        category=SkillCategory.FILE_MANAGEMENT,
        description="Create new files with content",
        tools=["file_write"],
        version="1.0.0"
    ),
    Skill(
        name="file_edit",
        category=SkillCategory.FILE_MANAGEMENT,
        description="Edit existing files",
        tools=["file_read", "file_write"],
        version="1.0.0"
    ),
    Skill(
        name="file_delete",
        category=SkillCategory.FILE_MANAGEMENT,
        description="Delete files and directories",
        tools=["subprocess"],
        version="1.0.0"
    ),
    Skill(
        name="project_explore",
        category=SkillCategory.FILE_MANAGEMENT,
        description="Explore project structure and find files",
        tools=["subprocess"],
        version="1.0.0"
    ),
    Skill(
        name="git_operations",
        category=SkillCategory.FILE_MANAGEMENT,
        description="Git operations - commit, push, pull, merge, branches",
        tools=["subprocess", "git"],
        version="1.0.0"
    ),
]


class FileManager:
    """Handle file operations with safety checks."""
    
    def __init__(self, workspace_root: str = "."):
        self.workspace_root = Path(workspace_root).resolve()
    
    def _validate_path(self, path: str) -> Path:
        """Validate and resolve path within workspace."""
        full_path = (self.workspace_root / path).resolve()
        if not str(full_path).startswith(str(self.workspace_root)):
            raise ValueError("Path outside workspace not allowed")
        return full_path
    
    def create_file(self, path: str, content: str) -> Dict[str, Any]:
        """Create a new file."""
        try:
            full_path = self._validate_path(path)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
            return {
                "success": True,
                "path": str(full_path),
                "size": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def read_file(self, path: str, lines: Optional[int] = None) -> Dict[str, Any]:
        """Read file contents."""
        try:
            full_path = self._validate_path(path)
            if not full_path.exists():
                return {"success": False, "error": "File not found"}
            
            content = full_path.read_text()
            if lines:
                content = "\n".join(content.splitlines()[:lines])
            
            return {
                "success": True,
                "path": str(full_path),
                "content": content,
                "size": len(content),
                "lines": len(content.splitlines())
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def edit_file(self, path: str, old_str: str, new_str: str) -> Dict[str, Any]:
        """Edit file content (find and replace)."""
        try:
            full_path = self._validate_path(path)
            if not full_path.exists():
                return {"success": False, "error": "File not found"}
            
            content = full_path.read_text()
            if old_str not in content:
                return {"success": False, "error": "Text not found in file"}
            
            new_content = content.replace(old_str, new_str, 1)
            full_path.write_text(new_content)
            
            return {
                "success": True,
                "path": str(full_path),
                "replacements": 1
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_file(self, path: str, recursive: bool = False) -> Dict[str, Any]:
        """Delete file or directory."""
        try:
            full_path = self._validate_path(path)
            if not full_path.exists():
                return {"success": False, "error": "Path not found"}
            
            if full_path.is_dir():
                if recursive:
                    shutil.rmtree(full_path)
                else:
                    full_path.rmdir()
            else:
                full_path.unlink()
            
            return {"success": True, "path": str(full_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def copy_file(self, src: str, dst: str) -> Dict[str, Any]:
        """Copy file or directory."""
        try:
            src_path = self._validate_path(src)
            dst_path = self._validate_path(dst)
            
            if not src_path.exists():
                return {"success": False, "error": "Source not found"}
            
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dst_path)
            
            return {"success": True, "src": str(src_path), "dst": str(dst_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def move_file(self, src: str, dst: str) -> Dict[str, Any]:
        """Move file or directory."""
        try:
            src_path = self._validate_path(src)
            dst_path = self._validate_path(dst)
            
            if not src_path.exists():
                return {"success": False, "error": "Source not found"}
            
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_path), str(dst_path))
            
            return {"success": True, "src": str(src_path), "dst": str(dst_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ProjectExplorer:
    """Explore and analyze project structures."""
    
    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()
    
    def get_structure(self, max_depth: int = 3, exclude: List[str] = None) -> Dict[str, Any]:
        """Get project structure as a tree."""
        exclude = exclude or [".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".pytest_cache"]
        
        def walk_tree(path: Path, depth: int = 0) -> Dict[str, Any]:
            if depth >= max_depth:
                return {"type": "truncated", "path": str(path)}
            
            items = {}
            try:
                for item in sorted(path.iterdir()):
                    if any(ex in item.name for ex in exclude):
                        continue
                    
                    if item.is_dir():
                        items[item.name] = walk_tree(item, depth + 1)
                    else:
                        size = item.stat().st_size
                        items[item.name] = {
                            "type": "file",
                            "size": size,
                            "ext": item.suffix
                        }
            except PermissionError:
                return {"type": "permission_denied"}
            
            return items
        
        return {
            "root": str(self.root),
            "tree": walk_tree(self.root),
            "timestamp": datetime.now().isoformat()
        }
    
    def find_files(self, pattern: str, search_path: Optional[str] = None) -> List[str]:
        """Find files matching a pattern."""
        search_path = Path(search_path) if search_path else self.root
        pattern_parts = pattern.split("*")
        
        matches = []
        for path in search_path.rglob("*"):
            if path.is_file():
                name = path.name
                matches_all = True
                last_pos = 0
                for part in pattern_parts:
                    if part:
                        pos = name.find(part, last_pos)
                        if pos == -1:
                            matches_all = False
                            break
                        last_pos = pos + len(part)
                
                if matches_all:
                    matches.append(str(path.relative_to(self.root)))
        
        return matches[:100]  # Limit results
    
    def get_file_info(self, path: str) -> Dict[str, Any]:
        """Get detailed file information."""
        try:
            full_path = self.root / path
            if not full_path.exists():
                return {"success": False, "error": "File not found"}
            
            stat = full_path.stat()
            return {
                "success": True,
                "path": str(full_path),
                "name": full_path.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_dir": full_path.is_dir(),
                "extension": full_path.suffix
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class GitOperations:
    """Handle Git operations through the CLI gate.

    ``run_git`` used to build its own argv, so ``run_git("push", "origin",
    "main")`` pushed with no owner check. Read verbs (status/log/diff/show) are
    allowed for the owner; destructive git verbs (push/reset/commit/checkout)
    are refused by ``cli_policy``.
    """

    def __init__(self, repo_path: str = ".", *, user_id: Optional[int] = None,
                 approval_id: Optional[str] = None):
        self.repo_path = repo_path
        self._user_id = user_id
        self._approval_id = approval_id

    def run_git(self, *args, check: bool = True, user_id: Optional[int] = None,
                approval_id: Optional[str] = None) -> Dict[str, Any]:
        """Run a git command, or refuse it."""
        result = run_guarded_command(
            "git", ["-C", self.repo_path, *[str(a) for a in args]],
            user_id=self._user_id if user_id is None else user_id,
            approval_id=self._approval_id if approval_id is None else approval_id,
            timeout=60,
        )
        if result.get("denied"):
            return result
        result["success"] = check is False or bool(result.get("success"))
        result["stdout"] = (result.get("stdout") or "").strip()
        result["stderr"] = (result.get("stderr") or "").strip()
        return result

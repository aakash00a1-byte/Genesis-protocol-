"""
Genesis Protocol - Autonomous Agent Core
=========================================
A fully autonomous AI agent with skills execution capabilities.
Inspired by OpenHands architecture.

Components:
- agent.py: Main GenesisAgent class
- brain.py: LLM-powered decision making
- __init__.py: Core utilities and ToolExecutor
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import traceback

from genesis_protocol.skills import get_skill_registry, Skill, SkillCategory
from genesis_protocol.config import get_config

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent execution states."""
    IDLE = "idle"
    THINKING = "thinking"
    PLANNING = "planning"
    EXECUTING = "executing"
    OBSERVING = "observing"
    DONE = "done"
    ERROR = "error"


class ActionType(Enum):
    """Types of actions the agent can take."""
    USE_SKILL = "use_skill"
    CALL_FUNCTION = "call_function"
    RESPOND = "respond"
    ASK_CLARIFICATION = "ask_clarification"
    SEARCH = "search"
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RUN_COMMAND = "run_command"
    THINK = "think"


@dataclass
class Message:
    """A message in the conversation."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Action:
    """An action to be executed by the agent."""
    type: ActionType
    skill_name: Optional[str] = None
    function_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    thought: str = ""
    result: Any = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class Task:
    """A task for the agent to complete."""
    id: str
    description: str
    context: Dict[str, Any] = field(default_factory=dict)
    history: List[Action] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    result: Optional[Any] = None
    created_at: datetime = field(default_factory=datetime.now)


class ToolExecutor:
    """Execute tools and skills."""
    
    def __init__(self):
        self.skill_registry = get_skill_registry()
        self._function_registry: Dict[str, Callable] = {}
        self._register_builtin_functions()
    
    def _register_builtin_functions(self):
        """Register built-in functions."""
        # File operations
        self._function_registry["read_file"] = self._read_file
        self._function_registry["write_file"] = self._write_file
        self._function_registry["list_files"] = self._list_files
        self._function_registry["search_files"] = self._search_files
        
        # Command execution
        self._function_registry["run_bash"] = self._run_bash
        self._function_registry["run_python"] = self._run_python
        
        # Web operations
        self._function_registry["web_search"] = self._web_search
        self._function_registry["fetch_url"] = self._fetch_url
        
        # Git operations
        self._function_registry["git_status"] = self._git_status
        self._function_registry["git_commit"] = self._git_commit
        self._function_registry["git_push"] = self._git_push
        
        # Utility
        self._function_registry["get_time"] = self._get_time
        self._function_registry["calculate"] = self._calculate
    
    async def execute_action(self, action: Action) -> Action:
        """Execute an action and return the result."""
        try:
            if action.type == ActionType.USE_SKILL:
                return await self._execute_skill(action)
            elif action.type == ActionType.CALL_FUNCTION:
                return await self._execute_function(action)
            elif action.type == ActionType.RESPOND:
                return action  # Response doesn't need execution
            else:
                return action
        except Exception as e:
            action.success = False
            action.error = str(e)
            logger.error(f"Action execution error: {e}")
            return action
    
    async def _execute_skill(self, action: Action) -> Action:
        """Execute a skill."""
        if not action.skill_name:
            action.error = "No skill name provided"
            action.success = False
            return action
        
        skill = self.skill_registry.get_skill(action.skill_name)
        if not skill:
            action.error = f"Skill not found: {action.skill_name}"
            action.success = False
            return action
        
        if not skill.enabled:
            action.error = f"Skill disabled: {action.skill_name}"
            action.success = False
            return action
        
        try:
            # Execute skill based on category
            action.result = await self._execute_skill_class(skill, action.parameters)
            action.success = True
            return action
            
        except Exception as e:
            action.error = f"Skill execution failed: {str(e)}"
            action.success = False
            return action
    
    async def _execute_skill_class(self, skill: Skill, params: Dict) -> Any:
        """Execute skill using its class directly."""
        # Generic skill execution based on skill name
        if skill.name == "git_operations":
            from genesis_protocol.skills.file_management import GitOperations
            git = GitOperations()
            op = params.get("operation", "status")
            return await self._execute_git_operation(git, op, params)
        
        elif skill.name == "data_analysis":
            from genesis_protocol.skills.specialized import DataAnalyzer
            analyzer = DataAnalyzer()
            return analyzer.analyze_csv(params.get("file_path", ""))
        
        elif skill.name == "web_search":
            from genesis_protocol.skills.web_browser import WebSearch
            config = get_config()
            search = WebSearch(config.tavily.api_key if config else None)
            return await search.search(params.get("query", ""), params.get("max_results", 10))
        
        elif skill.name == "code_review":
            from genesis_protocol.skills.coding import CodeAnalyzer, Refactorer
            analyzer = CodeAnalyzer()
            refactorer = Refactorer()
            file_path = params.get("file_path", "")
            if file_path.endswith('.py'):
                analysis = analyzer.analyze_python_file(file_path)
                if analysis.get("valid"):
                    with open(file_path, 'r') as f:
                        code = f.read()
                    suggestions = refactorer.suggest_refactors(code, "python")
                    return {"success": True, "analysis": analysis, "suggestions": suggestions}
            return {"success": False, "error": "Unsupported file or analysis failed"}
        
        elif skill.name == "debugging":
            from genesis_protocol.skills.coding import Debugger
            debugger = Debugger()
            file_path = params.get("file_path", "")
            return {"lint": debugger.lint_code(file_path), "issues": debugger.run_tests()}
        
        elif skill.name == "project_explore":
            from genesis_protocol.skills.file_management import ProjectExplorer
            explorer = ProjectExplorer()
            return explorer.get_structure(params.get("max_depth", 3))
        
        elif skill.name == "file_create":
            from genesis_protocol.skills.file_management import FileManager
            manager = FileManager()
            return manager.create_file(params.get("path", ""), params.get("content", ""))
        
        elif skill.name == "file_edit":
            from genesis_protocol.skills.file_management import FileManager
            manager = FileManager()
            return manager.edit_file(params.get("path", ""), params.get("old_str", ""), params.get("new_str", ""))
        
        elif skill.name == "docker_management":
            from genesis_protocol.skills.devops import DockerManager
            manager = DockerManager()
            return {"success": True, "containers": manager.list_containers()}
        
        elif skill.name == "github_pr_management":
            from genesis_protocol.skills.specialized import GitHubPRManager
            manager = GitHubPRManager()
            operation = params.get("operation", "list_prs")
            if operation == "list_prs":
                return {"success": True, "prs": manager.list_prs()}
            elif operation == "create_pr":
                return manager.create_pr(params.get("title", ""), params.get("body", ""))
        
        return {"message": f"Skill {skill.name} executed", "params": params}
    
    async def _execute_function(self, action: Action) -> Action:
        """Execute a registered function."""
        if not action.function_name:
            action.error = "No function name provided"
            action.success = False
            return action
        
        if action.function_name not in self._function_registry:
            action.error = f"Function not found: {action.function_name}"
            action.success = False
            return action
        
        try:
            func = self._function_registry[action.function_name]
            if asyncio.iscoroutinefunction(func):
                action.result = await func(**action.parameters)
            else:
                action.result = func(**action.parameters)
            action.success = True
            return action
        except Exception as e:
            action.error = str(e)
            action.success = False
            return action
    
    # Built-in function implementations
    async def _read_file(self, path: str, lines: int = 100, **kwargs) -> Dict:
        from pathlib import Path
        try:
            p = Path(path)
            if not p.exists():
                return {"success": False, "error": "File not found"}
            content = p.read_text()
            if lines:
                content = "\n".join(content.splitlines()[:lines])
            return {"success": True, "path": path, "content": content, "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _write_file(self, path: str, content: str, **kwargs) -> Dict:
        from pathlib import Path
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return {"success": True, "path": path, "size": len(content)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _list_files(self, path: str = ".", pattern: str = "*", **kwargs) -> Dict:
        from pathlib import Path
        try:
            p = Path(path)
            files = [str(f.relative_to(p)) for f in p.rglob(pattern) if f.is_file()][:100]
            return {"success": True, "path": path, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _search_files(self, pattern: str, path: str = ".", **kwargs) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                ["grep", "-r", "-l", pattern, path],
                capture_output=True,
                text=True,
                timeout=30
            )
            files = result.stdout.strip().split("\n") if result.stdout else []
            return {"success": True, "pattern": pattern, "files": [f for f in files if f]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _run_bash(self, command: str, timeout: int = 60, **kwargs) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _run_python(self, code: str, **kwargs) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _web_search(self, query: str, max_results: int = 5, **kwargs) -> Dict:
        from genesis_protocol.skills.web_browser import WebSearch
        config = get_config()
        search = WebSearch(config.tavily.api_key if config else None)
        return await search.search(query, max_results)
    
    async def _fetch_url(self, url: str, **kwargs) -> Dict:
        import subprocess
        try:
            result = subprocess.run(
                ["curl", "-s", url],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {"success": True, "url": url, "content": result.stdout[:5000]}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _git_status(self, **kwargs) -> Dict:
        from genesis_protocol.skills.file_management import GitOperations
        git = GitOperations()
        return git.get_status()
    
    async def _git_commit(self, message: str, **kwargs) -> Dict:
        from genesis_protocol.skills.file_management import GitOperations
        git = GitOperations()
        return git.commit(message)
    
    async def _git_push(self, remote: str = "origin", **kwargs) -> Dict:
        from genesis_protocol.skills.file_management import GitOperations
        git = GitOperations()
        return git.push(remote)
    
    async def _get_time(self, **kwargs) -> Dict:
        return {"success": True, "datetime": datetime.now().isoformat()}
    
    async def _calculate(self, expression: str, **kwargs) -> Dict:
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return {"success": True, "expression": expression, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _execute_git_operation(self, git, operation: str, params: Dict) -> Dict:
        """Execute a git operation."""
        operations = {
            "status": git.get_status,
            "branch": lambda: {"current": git.get_current_branch(), "all": git.get_branches()},
            "commit": lambda: git.commit(params.get("message", "Auto commit")),
            "push": lambda: git.push(params.get("remote", "origin")),
            "pull": lambda: git.pull(params.get("remote", "origin")),
            "diff": lambda: git.get_diff(params.get("target", "HEAD")),
            "log": lambda: git.get_log(params.get("limit", 10)),
        }
        
        func = operations.get(operation)
        if func:
            return func()
        return {"error": f"Unknown operation: {operation}"}
    
    def get_available_functions(self) -> List[str]:
        """Get list of available functions."""
        return list(self._function_registry.keys())


# Export all classes for easy importing
__all__ = [
    "AgentState",
    "ActionType", 
    "Message",
    "Action",
    "Task",
    "ToolExecutor",
    "GenesisAgent",
    "AgentConfig",
    "AgentBrain",
    "quick_agent"
]

# Import main classes
from genesis_protocol.agent.agent import GenesisAgent, AgentConfig, quick_agent
from genesis_protocol.agent.brain import AgentBrain
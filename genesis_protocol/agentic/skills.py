"""Run a skill through the tools it declares.

A skill is a capability bundle: it names the tools it needs (``web_search``
declares ``["tavily", "http"]``). This runner ties the two halves together -
resolve the skill, resolve each declared tool to a real implementation, run the
ones the caller supplied parameters for, and report honest evidence for every
one of them.

Guarantees, matching the rest of the agentic layer:

* Every tool call passes the same fail-closed policy check as the loop. A tool
  the caller may not use is denied, not skipped silently.
* A tool that has no implementation fails with a reason; it is never reported
  as having run.
* Nothing here plans or invents work. The caller supplies the skill and the
  parameters; the runner executes exactly that.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.audit import AuditLog, get_audit_log
from genesis_protocol.agentic.policy import AgentPolicy, get_agent_policy
from genesis_protocol.tools.tool_registry import ToolRegistry, get_tool_registry


class SkillRunner:
    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        policy: Optional[AgentPolicy] = None,
        audit: Optional[AuditLog] = None,
    ):
        self._registry = registry
        self.policy = policy or get_agent_policy()
        self.audit = audit or get_audit_log()

    @property
    def registry(self) -> ToolRegistry:
        if self._registry is None:
            self._registry = get_tool_registry()
        return self._registry

    def resolve(self, skill_name: str) -> Dict[str, Any]:
        """Describe a skill: its declared tools and which of them are runnable."""
        from genesis_protocol.skills import get_skill_registry

        skill = get_skill_registry().get_skill(skill_name)
        if skill is None:
            return {
                "skill": skill_name,
                "found": False,
                "declared_tools": [],
                "runnable_tools": [],
                "unavailable_tools": [],
            }

        declared = list(skill.tools or [])
        runnable: List[str] = []
        unavailable: List[Dict[str, str]] = []
        for name in declared:
            tool = self.registry.get_tool(name)
            if tool is None:
                unavailable.append({"name": name, "reason": "not registered"})
                continue
            perm = getattr(getattr(tool, "permission", None), "value", None)
            if perm is None:
                unavailable.append({"name": name, "reason": "unknown permission"})
                continue
            if not tool.is_available():
                unavailable.append({"name": name, "reason": "not available in this deployment"})
                continue
            runnable.append(name)

        return {
            "skill": skill.name,
            "found": True,
            "category": skill.category.value,
            "description": skill.description,
            "declared_tools": declared,
            "runnable_tools": runnable,
            "unavailable_tools": unavailable,
        }

    def run(
        self,
        user_id: int,
        skill_name: str,
        tool_params: Optional[Dict[str, Dict[str, Any]]] = None,
        owner_approved: bool = False,
    ) -> Dict[str, Any]:
        """Run the tools of ``skill_name`` the caller gave parameters for.

        ``tool_params`` maps a declared tool name to its kwargs, e.g.
        ``{"tavily": {"query": "genesis protocol"}}``. Tools without parameters
        are reported as skipped, so the result never implies more ran than did.
        """
        tool_params = tool_params or {}
        info = self.resolve(skill_name)
        if not info["found"]:
            return {
                "skill": skill_name,
                "success": False,
                "error": f"unknown skill '{skill_name}'",
                "steps": [],
            }

        steps: List[Dict[str, Any]] = []
        for name in info["declared_tools"]:
            if name not in tool_params:
                steps.append({"tool": name, "ran": False, "reason": "no parameters supplied"})
                continue

            params = dict(tool_params[name] or {})
            tool = self.registry.get_tool(name)
            if tool is None:
                steps.append({"tool": name, "ran": False, "reason": "tool not available"})
                continue

            perm = getattr(getattr(tool, "permission", None), "value", None)
            decision = self.policy.authorize_tool(
                user_id, name, permission=perm, owner_approved=owner_approved
            )
            self.audit.record(
                "skill_tool_request", user_id, name, decision.allowed, decision.reason, detail=params
            )
            if not decision.allowed:
                steps.append(
                    {
                        "tool": name,
                        "ran": False,
                        "denied": True,
                        "error": decision.reason,
                        "policy": decision.to_dict(),
                    }
                )
                continue

            result = self.registry.execute(name, params)
            ran = isinstance(result, dict) and bool(result.get("success"))
            self.audit.record(
                "skill_tool_result", user_id, name, ran, "ok" if ran else "failed"
            )
            steps.append({"tool": name, "ran": ran, "result": result})

        any_ran = any(s.get("ran") for s in steps)
        any_denied = any(s.get("denied") for s in steps)
        all_ran = bool(steps) and all(s.get("ran") for s in steps)
        return {
            "skill": info["skill"],
            "category": info.get("category"),
            "success": all_ran,
            "executed": any_ran,
            "denied": any_denied,
            "steps": steps,
        }

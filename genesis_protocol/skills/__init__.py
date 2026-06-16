"""
Genesis Protocol Skills System
==============================
Autonomous agent capabilities organized as modular skills.
Each skill can be enabled/disabled independently.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Skill categories for organization."""
    CODING = "coding"
    FILE_MANAGEMENT = "file_management"
    WEB_BROWSER = "web_browser"
    AUTOMATION = "automation"
    DEVOPS = "devops"
    SPECIALIZED = "specialized"
    DOCUMENT = "document"


@dataclass
class Skill:
    """Represents a skill with its metadata and capabilities."""
    name: str
    category: SkillCategory
    description: str
    enabled: bool = True
    version: str = "1.0.0"
    tools: List[str] = None  # Tools this skill uses
    dependencies: List[str] = None  # Other skills it depends on
    
    def __post_init__(self):
        if self.tools is None:
            self.tools = []
        if self.dependencies is None:
            self.dependencies = []


class SkillRegistry:
    """
    Central registry for all skills.
    Manages skill loading, enabling/disabling, and execution.
    """
    
    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._enabled_skills: Dict[str, Skill] = {}
        self._skill_modules: Dict[str, Any] = {}
    
    def register(self, skill: Skill) -> None:
        """Register a new skill."""
        self._skills[skill.name] = skill
        if skill.enabled:
            self._enabled_skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name} ({skill.category.value})")
    
    def enable(self, skill_name: str) -> bool:
        """Enable a skill."""
        if skill_name in self._skills:
            self._skills[skill_name].enabled = True
            self._enabled_skills[skill_name] = self._skills[skill_name]
            logger.info(f"Enabled skill: {skill_name}")
            return True
        return False
    
    def disable(self, skill_name: str) -> bool:
        """Disable a skill."""
        if skill_name in self._skills:
            self._skills[skill_name].enabled = False
            self._enabled_skills.pop(skill_name, None)
            logger.info(f"Disabled skill: {skill_name}")
            return True
        return False
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)
    
    def get_enabled_skills(self) -> List[Skill]:
        """Get all enabled skills."""
        return list(self._enabled_skills.values())
    
    def get_skills_by_category(self, category: SkillCategory) -> List[Skill]:
        """Get all skills in a category."""
        return [s for s in self._skills.values() if s.category == category]
    
    def get_available_tools(self) -> List[str]:
        """Get all tools from enabled skills."""
        tools = set()
        for skill in self._enabled_skills.values():
            tools.update(skill.tools)
        return list(tools)
    
    def list_all_skills(self) -> List[Skill]:
        """List all registered skills."""
        return list(self._skills.values())


# Global skill registry instance
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get the global skill registry instance."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        _load_default_skills(_skill_registry)
    return _skill_registry


def _load_default_skills(registry: SkillRegistry) -> None:
    """Load all default skills into the registry."""
    from genesis_protocol.skills.coding import SKILLS as coding_skills
    from genesis_protocol.skills.file_management import SKILLS as file_skills
    from genesis_protocol.skills.web_browser import SKILLS as web_skills
    from genesis_protocol.skills.automation import SKILLS as automation_skills
    from genesis_protocol.skills.devops import SKILLS as devops_skills
    from genesis_protocol.skills.specialized import SKILLS as specialized_skills
    from genesis_protocol.skills.document import SKILLS as document_skills
    
    all_skills = (
        coding_skills + 
        file_skills + 
        web_skills + 
        automation_skills + 
        devops_skills + 
        specialized_skills + 
        document_skills
    )
    
    for skill in all_skills:
        registry.register(skill)
"""Proposal Templates - Genesis Protocol v1.8"""

from typing import Dict
from enum import Enum


class ProposalTemplate(Enum):
    PERFORMANCE = "performance_improvement"
    MEMORY = "memory_enhancement"
    TOOL = "tool_optimization"
    PROVIDER = "provider_optimization"
    BUG = "bug_fix"
    CAPABILITY = "new_capability"
    
    def get_template(self) -> Dict:
        templates = {
            "performance_improvement": {
                "title_prefix": "Performance Improvement:",
                "questions": ["What is the current metric?", "What is the target?"],
                "evidence_needed": ["metrics", "benchmarks"]
            },
            "memory_enhancement": {
                "title_prefix": "Memory Enhancement:",
                "questions": ["What needs improvement?", "What is the current recall?"],
                "evidence_needed": ["recall_tests"]
            },
            "tool_optimization": {
                "title_prefix": "Tool Optimization:",
                "questions": ["Which tool?", "What is the issue?"],
                "evidence_needed": ["tool_stats"]
            }
        }
        return templates.get(self.value, {})


def get_template(template_name: str) -> Dict:
    return ProposalTemplate[template_name.upper()].get_template() if template_name.upper() in [t.name for t in ProposalTemplate] else {}

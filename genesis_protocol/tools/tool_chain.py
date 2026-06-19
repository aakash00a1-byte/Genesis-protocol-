"""Tool Chains - Genesis Protocol v1.6
Allow tools to call other tools."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

logger = logging.getLogger("tools.chain")


class ChainStep:
    """A step in a tool chain."""
    
    def __init__(self, tool_name: str, input_mapping: Dict[str, str], description: str = ""):
        self.tool_name = tool_name
        self.input_mapping = input_mapping  # {"param": "previous_step.output_field"}
        self.description = description


@dataclass
class ChainResult:
    """Result of a chain execution."""
    chain_name: str
    success: bool
    steps_executed: int
    outputs: List[Dict[str, Any]]
    final_output: Any
    error: Optional[str] = None


class ToolChain:
    """A chain of tools to execute in sequence."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.steps: List[ChainStep] = []
        self.created_at = datetime.now()
    
    def add_step(self, tool_name: str, input_mapping: Dict[str, str], description: str = "") -> 'ToolChain':
        """Add a step to the chain."""
        self.steps.append(ChainStep(tool_name, input_mapping, description))
        return self
    
    def execute(self, context: Dict[str, Any]) -> ChainResult:
        """Execute the chain with given context."""
        from .tool_registry import get_tool_registry
        registry = get_tool_registry()
        
        outputs = []
        current_context = context.copy()
        error = None
        
        for i, step in enumerate(self.steps):
            try:
                # Build input parameters from mapping
                params = {}
                for param, source in step.input_mapping.items():
                    if '.' in source:
                        # Reference to previous step output: "step_0.result"
                        parts = source.split('.')
                        step_idx = int(parts[0].replace('step_', ''))
                        if step_idx < len(outputs):
                            output = outputs[step_idx]
                            for key in parts[1:]:
                                output = output.get(key, {})
                            params[param] = output
                    else:
                        # Direct context reference
                        params[param] = current_context.get(source, source)
                
                # Execute tool
                result = registry.execute(step.tool_name, params)
                outputs.append(result)
                
                if not result.get('success', False):
                    error = f"Step {i} failed: {result.get('error', 'Unknown error')}"
                    break
                
                # Update context with output for next step
                current_context[f'step_{i}'] = result
                
            except Exception as e:
                error = f"Step {i} exception: {str(e)}"
                break
        
        return ChainResult(
            chain_name=self.name,
            success=error is None,
            steps_executed=len(outputs),
            outputs=outputs,
            final_output=outputs[-1] if outputs else None,
            error=error
        )


class ToolChainExecutor:
    """Manages and executes tool chains."""
    
    def __init__(self):
        self._chains: Dict[str, ToolChain] = {}
        self._register_default_chains()
    
    def _register_default_chains(self):
        """Register built-in chains."""
        # search -> summarize -> save memory
        search_summarize_save = ToolChain("search_summarize_save", "Search, summarize, and save to memory")
        search_summarize_save.add_step("web_search", {"query": "input.query"}, "Search web")
        search_summarize_save.add_step("notes", {"action": "save", "key": "input.query", "content": "step_0.results"}, "Save results")
        self.register(search_summarize_save)
        
        # history -> reflection -> response
        history_reflect = ToolChain("history_reflect", "Search history and generate reflection")
        history_reflect.add_step("memory_search", {"query": "input.query"}, "Search memories")
        self.register(history_reflect)
        
        # task -> reminder -> memory
        task_reminder_memory = ToolChain("task_reminder_memory", "Create task, set reminder, save memory")
        task_reminder_memory.add_step("task_manager", {"action": "create", "name": "input.task_name"}, "Create task")
        task_reminder_memory.add_step("notes", {"action": "save", "key": "reminder", "content": "step_0.message"}, "Save reminder")
        self.register(task_reminder_memory)
    
    def register(self, chain: ToolChain):
        """Register a chain."""
        self._chains[chain.name] = chain
        logger.info(f"Registered chain: {chain.name}")
    
    def unregister(self, name: str):
        """Unregister a chain."""
        if name in self._chains:
            del self._chains[name]
    
    def get_chain(self, name: str) -> Optional[ToolChain]:
        """Get a chain by name."""
        return self._chains.get(name)
    
    def execute_chain(self, name: str, context: Dict[str, Any]) -> ChainResult:
        """Execute a chain by name."""
        chain = self.get_chain(name)
        if not chain:
            return ChainResult(
                chain_name=name,
                success=False,
                steps_executed=0,
                outputs=[],
                final_output=None,
                error=f"Chain '{name}' not found"
            )
        
        logger.info(f"Executing chain: {name}")
        return chain.execute(context)
    
    def get_all_chains(self) -> List[Dict[str, str]]:
        """Get all registered chains."""
        return [
            {"name": c.name, "description": c.description, "steps": len(c.steps)}
            for c in self._chains.values()
        ]
    
    def get_available_chains(self, context: Dict[str, Any]) -> List[str]:
        """Get chains that can be used with current context."""
        available = []
        for chain in self._chains.values():
            # Check if required inputs are in context
            has_input = any('input.' in step.input_mapping.values() 
                           for step in chain.steps)
            if not has_input or context:
                available.append(chain.name)
        return available


# Global singleton
_chain_executor: Optional[ToolChainExecutor] = None


def get_chain_executor() -> ToolChainExecutor:
    """Get global chain executor."""
    global _chain_executor
    if _chain_executor is None:
        _chain_executor = ToolChainExecutor()
    return _chain_executor

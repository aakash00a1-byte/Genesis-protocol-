"""
Genesis Protocol - Agent Brain
===============================
LLM-powered decision making and action planning.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from genesis_protocol.config import get_config
from genesis_protocol.agent import Action, ActionType, ToolExecutor, AgentState

logger = logging.getLogger(__name__)


class AgentBrain:
    """
    The "brain" of the autonomous agent.
    Uses LLM to decide actions based on user input and context.
    """
    
    def __init__(self):
        self.config = get_config()
        self.tool_executor = ToolExecutor()
        self.max_iterations = 10
        self.conversation_history: List[Dict] = []
    
    async def think(self, task: str, context: Dict[str, Any] = None) -> str:
        """
        Use LLM to think about the task and generate a response.
        """
        try:
            # Get available tools and skills
            available_tools = self.tool_executor.get_available_functions()
            skill_registry = self.tool_executor.skill_registry
            skills = skill_registry.list_all_skills()
            
            # Build context for LLM
            context_str = json.dumps(context, indent=2) if context else "No additional context"
            
            # Create system prompt
            system_prompt = f"""You are an autonomous AI assistant with the following capabilities:

AVAILABLE FUNCTIONS (use these to perform actions):
{json.dumps(available_tools, indent=2)}

AVAILABLE SKILLS:
{chr(10).join([f"- {s.name}: {s.description}" for s in skills[:10]])}

INSTRUCTIONS:
1. Analyze the user's request carefully
2. If the task requires an action (file operations, git, code execution, etc.), use the appropriate function
3. If the task is a question, provide a helpful answer
4. If more information is needed, ask clarifying questions
5. Be concise and direct in your responses

CONTEXT:
{context_str}

Respond in the following JSON format:
{{
    "thought": "Your reasoning about what to do",
    "action_type": "function_call" or "respond" or "ask_clarification",
    "function": "function_name if action_type is function_call",
    "parameters": {{"param_name": "value"}} if action_type is function_call,
    "response": "Your response text if action_type is respond"
}}
"""
            
            # Call LLM
            response = await self._call_llm(system_prompt, task)
            return response
            
        except Exception as e:
            logger.error(f"Thinking error: {e}")
            return json.dumps({
                "thought": f"Error: {str(e)}",
                "action_type": "respond",
                "response": f"I encountered an error: {str(e)}"
            })
    
    async def plan(self, task: str) -> List[Action]:
        """
        Create a plan of actions to complete the task.
        """
        try:
            # Get available functions
            available_tools = self.tool_executor.get_available_functions()
            skills = self.tool_executor.skill_registry.list_all_skills()
            
            # Create planning prompt
            planning_prompt = f"""Analyze this task and create a step-by-step plan:

TASK: {task}

AVAILABLE TOOLS:
{json.dumps(available_tools, indent=2)}

SKILLS:
{chr(10).join([f"- {s.name}" for s in skills])}

Break down the task into atomic steps. For each step, specify:
- What action to take
- What function to call (if any)
- What parameters to pass

Respond in JSON format:
{{
    "plan": [
        {{
            "step": 1,
            "description": "What to do in this step",
            "action_type": "function_call" or "respond",
            "function": "function_name or null",
            "parameters": {{}}
        }}
    ]
}}
"""
            
            response = await self._call_llm(planning_prompt, task)
            
            try:
                data = json.loads(response)
                plan = data.get("plan", [])
                
                actions = []
                for step_data in plan:
                    action = Action(
                        type=ActionType.CALL_FUNCTION if step_data.get("action_type") == "function_call" else ActionType.RESPOND,
                        function_name=step_data.get("function"),
                        parameters=step_data.get("parameters", {}),
                        thought=step_data.get("description", "")
                    )
                    actions.append(action)
                
                return actions
                
            except json.JSONDecodeError:
                logger.error(f"Failed to parse plan: {response}")
                return []
                
        except Exception as e:
            logger.error(f"Planning error: {e}")
            return []
    
    async def execute(self, task: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute a task autonomously using the think-act-observe loop.
        """
        history = []
        current_task = task
        iterations = 0
        
        while iterations < self.max_iterations:
            iterations += 1
            
            # THINK: Get LLM response
            thought_response = await self.think(current_task, context)
            
            try:
                thought_data = json.loads(thought_response)
            except:
                thought_data = {
                    "thought": "Failed to parse response",
                    "action_type": "respond",
                    "response": "I had trouble understanding that. Could you rephrase?"
                }
            
            history.append({
                "iteration": iterations,
                "thought": thought_data.get("thought", ""),
                "action_type": thought_data.get("action_type", ""),
            })
            
            # ACT: Execute if needed
            if thought_data.get("action_type") == "function_call":
                function_name = thought_data.get("function")
                parameters = thought_data.get("parameters", {})
                
                action = Action(
                    type=ActionType.CALL_FUNCTION,
                    function_name=function_name,
                    parameters=parameters,
                    thought=thought_data.get("thought", "")
                )
                
                action = await self.tool_executor.execute_action(action)
                history[-1]["result"] = action.result
                history[-1]["success"] = action.success
                
                # OBSERVE: Get result and continue if needed
                if action.success and action.result:
                    result_str = json.dumps(action.result, indent=2)[:500]
                    current_task = f"Based on the previous result:\n{result_str}\n\nShould I continue or is the task complete?"
                else:
                    current_task = f"The previous action failed: {action.error}. How should I proceed?"
            
            elif thought_data.get("action_type") == "respond":
                # Task is complete
                return {
                    "success": True,
                    "response": thought_data.get("response", "Task completed"),
                    "iterations": iterations,
                    "history": history
                }
            
            elif thought_data.get("action_type") == "ask_clarification":
                return {
                    "success": False,
                    "needs_clarification": True,
                    "question": thought_data.get("question", "Could you provide more details?"),
                    "history": history
                }
        
        return {
            "success": False,
            "error": f"Max iterations ({self.max_iterations}) reached",
            "history": history
        }
    
    async def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        Call the LLM with the configured provider.
        """
        # Try Groq first (fastest, free tier available)
        if self.config.groq.is_configured():
            return await self._call_groq(system_prompt, user_message)
        
        # Fallback to OpenAI
        elif self.config.openai.is_configured():
            return await self._call_openai(system_prompt, user_message)
        
        # Fallback to Gemini
        elif self.config.gemini.is_configured():
            return await self._call_gemini(system_prompt, user_message)
        
        else:
            # No LLM configured - return a basic response
            return json.dumps({
                "thought": "No LLM configured",
                "action_type": "respond",
                "response": "I don't have an AI model configured. Please set up at least one AI provider (Groq, OpenAI, or Gemini) in your .env file."
            })
    
    async def _call_groq(self, system_prompt: str, user_message: str) -> str:
        """Call Groq API."""
        try:
            from groq import Groq
            
            client = Groq(api_key=self.config.groq.api_key)
            
            response = client.chat.completions.create(
                model=self.config.groq.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1024
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise
    
    async def _call_openai(self, system_prompt: str, user_message: str) -> str:
        """Call OpenAI API."""
        try:
            import openai
            
            client = openai.OpenAI(api_key=self.config.openai.api_key)
            
            response = client.chat.completions.create(
                model=self.config.openai.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=1024
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    async def _call_gemini(self, system_prompt: str, user_message: str) -> str:
        """Call Google Gemini API."""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.config.gemini.api_key)
            model = genai.GenerativeModel(self.config.gemini.default_model)
            
            response = model.generate_content(
                f"{system_prompt}\n\nUser: {user_message}"
            )
            
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get agent capabilities."""
        return {
            "functions": self.tool_executor.get_available_functions(),
            "skills": [
                {
                    "name": s.name,
                    "category": s.category.value,
                    "description": s.description,
                    "enabled": s.enabled
                }
                for s in self.tool_executor.skill_registry.list_all_skills()
            ],
            "llm_providers": {
                "groq": self.config.groq.is_configured(),
                "openai": self.config.openai.is_configured(),
                "gemini": self.config.gemini.is_configured(),
                "huggingface": self.config.huggingface.is_configured()
            }
        }
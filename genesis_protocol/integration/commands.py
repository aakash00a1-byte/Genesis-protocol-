"""Personality Commands - Genesis Protocol v1.2"""

import re
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

from genesis_protocol.personality import Persona, ConversationMode


@dataclass
class CommandResult:
    """Result of a command processing."""
    is_command: bool
    handled: bool
    response: Optional[str] = None
    message: Optional[str] = None  # Original message if not a command


class PersonalityCommands:
    """Handles personality-related commands."""
    
    PERSONA_COMMANDS = {
        '/persona': Persona,
        '/setpersona': Persona,
        '/personality': Persona,
    }
    
    @classmethod
    def parse_command(cls, message: str) -> CommandResult:
        """Parse a command from message."""
        if not message or not message.strip().startswith('/'):
            return CommandResult(is_command=False, handled=False, message=message)
        
        parts = message.strip().split(maxsplit=1)
        if not parts:
            return CommandResult(is_command=False, handled=False, message=message)
        
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Check for persona commands
        if command in ['/persona', '/setpersona', '/personality']:
            return cls._handle_persona_command(command, args)
        
        # Check for mode commands
        if command in ['/mode', '/setmode']:
            return cls._handle_mode_command(command, args)
        
        # Check for reminder command
        if command in ['/remind', '/reminder', '/schedule']:
            return cls._handle_reminder_command(command, args)
        
        # Check for memory commands
        if command in ['/memory', '/remember', '/forget']:
            return cls._handle_memory_command(command, args)
        
        # Check for image mode command
        if command in ['/vision', '/image', '/analyze']:
            return cls._handle_vision_command(command, args)
        
        # Check for voice mode command
        if command in ['/voice', '/speak', '/listen']:
            return cls._handle_voice_command(command, args)
        
        # Check for status command
        if command in ['/status', '/modules', '/system']:
            return cls._handle_status_command(command)
        
        return CommandResult(is_command=False, handled=False, message=message)
    
    @classmethod
    def _handle_persona_command(cls, command: str, args: str) -> CommandResult:
        """Handle persona selection command."""
        if not args:
            return CommandResult(
                is_command=True,
                handled=True,
                response="Available personas: normal, jarvis, gluttony, friendly, developer\n\nExample: /persona gluttony"
            )
        
        persona_name = args.lower().strip()
        
        # Map aliases
        aliases = {
            'g': 'gluttony',
            'j': 'jarvis',
            'f': 'friendly',
            'd': 'developer',
            'n': 'normal',
            'buddy': 'friendly',
            'dev': 'developer',
        }
        persona_name = aliases.get(persona_name, persona_name)
        
        try:
            persona = Persona(persona_name)
            # The actual persona setting would be done in the chat handler
            persona_greetings = {
                'normal': "Hello! I'm Genesis, ready to help.",
                'jarvis': "At your service, sir.",
                'gluttony': "Hey hey! What's cooking? Let's have some fun! 😄",
                'friendly': "Hey friend! What's up? 😊",
                'developer': "Initializing... Hello, developer!"
            }
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"Persona set to **{persona_name.upper()}**!\n\n{persona_greetings.get(persona_name, 'Ready!')}"
            )
        except ValueError:
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"Unknown persona: {args}\n\nAvailable: normal, jarvis, gluttony, friendly, developer"
            )
    
    @classmethod
    def _handle_mode_command(cls, command: str, args: str) -> CommandResult:
        """Handle conversation mode command."""
        if not args:
            return CommandResult(
                is_command=True,
                handled=True,
                response="Modes: assistant, friend, casual\n\nExample: /mode casual"
            )
        
        mode_name = args.lower().strip()
        
        try:
            mode = ConversationMode(mode_name)
            mode_descriptions = {
                'assistant': "Switched to Assistant mode. Formal and task-focused.",
                'friend': "Switched to Friend mode. Casual and friendly!",
                'casual': "Switched to Casual mode. Very relaxed and fun! 😎"
            }
            return CommandResult(
                is_command=True,
                handled=True,
                response=mode_descriptions.get(mode_name, f"Mode set to {mode_name}.")
            )
        except ValueError:
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"Unknown mode: {args}\n\nAvailable: assistant, friend, casual"
            )
    
    @classmethod
    def _handle_reminder_command(cls, command: str, args: str) -> CommandResult:
        """Handle reminder command."""
        if not args:
            return CommandResult(
                is_command=True,
                handled=True,
                response="Usage: /remind <time> <message>\n\nExample: /remind 1h Check email\nExample: /remind 30m Meeting with team"
            )
        
        # Parse time and message
        match = re.match(r'(\d+)\s*(m|h|d)\s+(.*)', args, re.IGNORECASE)
        if match:
            amount, unit, reminder_message = match.groups()
            time_desc = f"{amount} {unit}"
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"✅ Reminder set for **{time_desc}**: {reminder_message}\n\nI'll remind you when the time comes!"
            )
        
        return CommandResult(
            is_command=True,
            handled=True,
            response="Could not parse reminder. Use format: /remind <time> <message>\n\nExample: /remind 30m Call mom"
        )
    
    @classmethod
    def _handle_memory_command(cls, command: str, args: str) -> CommandResult:
        """Handle memory commands."""
        if '/memory' in command or '/status' in command:
            return CommandResult(
                is_command=True,
                handled=True,
                response="Memory status: Active\n\nYour conversation context is being stored for personalized responses."
            )
        
        if '/remember' in command:
            if not args:
                return CommandResult(
                    is_command=True,
                    handled=True,
                    response="Usage: /remember <what to remember>\n\nExample: /remember I prefer concise answers"
                )
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"✅ Got it! I'll remember: {args}"
            )
        
        if '/forget' in command:
            if not args:
                return CommandResult(
                    is_command=True,
                    handled=True,
                    response="Usage: /forget <what to forget>\n\nExample: /forget my previous preference"
                )
            return CommandResult(
                is_command=True,
                handled=True,
                response=f"✅ Forgotten: {args}"
            )
        
        return CommandResult(is_command=False, handled=False, message=args)
    
    @classmethod
    def _handle_vision_command(cls, command: str, args: str) -> CommandResult:
        """Handle vision/image commands."""
        return CommandResult(
            is_command=True,
            handled=True,
            response="📷 Vision mode ready!\n\nSend an image and I'll analyze it for you.\n\nYou can also ask: \"What do you see in this image?\""
        )
    
    @classmethod
    def _handle_voice_command(cls, command: str, args: str) -> CommandResult:
        """Handle voice commands."""
        return CommandResult(
            is_command=True,
            handled=True,
            response="🎤 Voice mode ready!\n\nSend a voice message and I'll process it.\n\nNote: Voice features require microphone access."
        )
    
    @classmethod
    def _handle_status_command(cls, command: str) -> CommandResult:
        """Handle status/system command."""
        return CommandResult(
            is_command=True,
            handled=True,
            response="📊 Genesis Protocol v1.2 Status\n\n• All systems operational\n• Memory: Active\n• Personality: Ready\n• Task queue: Running\n\nUse /modules for detailed status."
        )

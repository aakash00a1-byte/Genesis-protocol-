"""Genesis Protocol - Conversation Prompt Formatting"""

from typing import List, Dict, Optional

from genesis_protocol.models.conversation import Conversation
from genesis_protocol.models.message import Message


def format_conversation(conversation: Conversation, 
                        max_messages: int = 20) -> List[Dict[str, str]]:
    """
    Format conversation for AI processing.
    
    Args:
        conversation: Conversation object
        max_messages: Maximum messages to include
        
    Returns:
        List of message dictionaries
    """
    messages = conversation.get_recent_messages(max_messages)
    
    result = []
    for msg in messages:
        role = "user" if msg.direction.value == "incoming" else "assistant"
        content = msg.text or ""
        
        if msg.message_type.value == "voice" and not content:
            content = "[Voice message]"
        elif msg.message_type.value == "image" and not content:
            content = "[Image]"
        
        result.append({
            "role": role,
            "content": content,
        })
    
    return result


def build_context(messages: List[Message], 
                  system_prompt: str = None,
                  max_tokens: int = 8000) -> List[Dict[str, str]]:
    """
    Build context from messages for AI.
    
    Args:
        messages: List of messages
        system_prompt: System prompt to prepend
        max_tokens: Maximum tokens
        
    Returns:
        Formatted messages
    """
    result = []
    
    if system_prompt:
        result.append({
            "role": "system",
            "content": system_prompt,
        })
    
    total_tokens = len(system_prompt.split()) if system_prompt else 0
    
    for msg in reversed(messages):
        content = msg.text or ""
        
        if msg.message_type.value == "voice" and not content:
            content = "[Voice message]"
        elif msg.message_type.value == "image" and not content:
            content = "[Image]"
        
        msg_tokens = len(content.split())
        
        if total_tokens + msg_tokens > max_tokens:
            break
        
        result.insert(1, {
            "role": "user" if msg.direction.value == "incoming" else "assistant",
            "content": content,
        })
        
        total_tokens += msg_tokens
    
    return result


def format_user_message(text: str, context: Dict = None) -> str:
    """
    Format user message with context.
    
    Args:
        text: User input text
        context: Optional context dictionary
        
    Returns:
        Formatted message
    """
    if not context:
        return text
    
    parts = []
    
    if context.get("user_name"):
        parts.append(f"User: {context['user_name']}")
    
    if context.get("conversation_topic"):
        parts.append(f"Topic: {context['conversation_topic']}")
    
    if context.get("relevant_facts"):
        parts.append(f"Context: {context['relevant_facts']}")
    
    if parts:
        return f"{' | '.join(parts)}\n\nQuestion: {text}"
    
    return text


def extract_intent_and_entities(text: str) -> Dict:
    """
    Extract intent and entities from text.
    
    Args:
        text: Input text
        
    Returns:
        Dictionary with intent and entities
    """
    text_lower = text.lower()
    
    # Simple intent detection
    intents = {
        "search": ["search", "find", "look up", "what is", "who is", "where is"],
        "code": ["code", "programming", "script", "function", "debug"],
        "image": ["image", "photo", "picture", "screenshot", "analyze"],
        "voice": ["voice", "audio", "speech", "transcribe"],
        "help": ["help", "assist", "support", "how to"],
        "chat": [],  # Default intent
    }
    
    detected_intent = "chat"
    for intent, keywords in intents.items():
        for keyword in keywords:
            if keyword in text_lower:
                detected_intent = intent
                break
    
    return {
        "intent": detected_intent,
        "entities": [],  # Would use NER for actual extraction
        "original_text": text,
    }
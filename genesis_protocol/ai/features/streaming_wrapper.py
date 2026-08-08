"""Genesis Protocol - Streaming Response Wrapper

Wraps LLM responses to support streaming token-by-token output.
Compatible with WebSocket and SSE for real-time display.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai.streaming")


class StreamEventType(Enum):
    """Types of streaming events."""
    TOKEN = "token"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    COMPLETE = "complete"
    METADATA = "metadata"


@dataclass
class StreamEvent:
    """A streaming event."""
    type: StreamEventType
    data: Any
    timestamp: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class StreamConfig:
    """Configuration for streaming."""
    include_thinking: bool = True
    include_metadata: bool = True
    chunk_size: int = 1  # tokens per chunk (1 = real-time)
    buffer_size: int = 10  # buffer before sending
    emit_tool_calls: bool = True


class StreamingWrapper:
    """
    Wrapper for LLM responses that supports streaming.
    
    Features:
    - Token-by-token streaming
    - Thinking/reasoning display
    - Tool call visualization
    - WebSocket/SSE compatible
    """
    
    def __init__(self, config: StreamConfig = None):
        """
        Initialize streaming wrapper.
        
        Args:
            config: Streaming configuration
        """
        self._config = config or StreamConfig()
        self._buffer: List[str] = []
        logger.info("StreamingWrapper initialized")
    
    async def stream_response(
        self, 
        llm_generator: AsyncGenerator[str, None],
        tool_handler: callable = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream an LLM response.
        
        Args:
            llm_generator: Async generator yielding tokens
            tool_handler: Optional async function to handle tool calls
            
        Yields:
            StreamEvent objects
        """
        full_content = ""
        buffer_count = 0
        
        try:
            async for token in llm_generator:
                full_content += token
                
                # Check if this is a tool call (JSON block)
                if token.strip().startswith("```"):
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL,
                        data=token.strip()
                    )
                    continue
                
                # Buffer tokens
                self._buffer.append(token)
                buffer_count += 1
                
                # Emit buffered tokens
                if buffer_count >= self._config.chunk_size:
                    buffered = "".join(self._buffer)
                    yield StreamEvent(
                        type=StreamEventType.TOKEN,
                        data=buffered
                    )
                    self._buffer = []
                    buffer_count = 0
                    
                # Small delay for rate limiting
                await asyncio.sleep(0.001)
            
            # Emit remaining buffer
            if self._buffer:
                yield StreamEvent(
                    type=StreamEventType.TOKEN,
                    data="".join(self._buffer)
                )
            
            # Complete event
            if self._config.include_metadata:
                yield StreamEvent(
                    type=StreamEventType.METADATA,
                    data={
                        "total_tokens": len(full_content.split()),
                        "total_chars": len(full_content)
                    }
                )
            
            yield StreamEvent(
                type=StreamEventType.COMPLETE,
                data={"content": full_content}
            )
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield StreamEvent(
                type=StreamEventType.ERROR,
                data=str(e)
            )
    
    async def stream_to_websocket(self, generator, websocket):
        """
        Stream directly to a WebSocket connection.
        
        Args:
            generator: The stream_response generator
            websocket: WebSocket connection
        """
        try:
            async for event in generator:
                await websocket.send(event.to_json())
        except Exception as e:
            logger.error(f"WebSocket streaming error: {e}")
            await websocket.send(StreamEvent(
                type=StreamEventType.ERROR,
                data=str(e)
            ).to_json())
    
    def format_for_sse(self, event: StreamEvent) -> str:
        """
        Format event for Server-Sent Events (SSE).
        
        Args:
            event: StreamEvent to format
            
        Returns:
            SSE formatted string
        """
        return f"event: {event.type.value}\ndata: {json.dumps(event.data)}\n\n"
    
    @staticmethod
    def create_sse_response(events: List[StreamEvent]) -> str:
        """
        Create SSE response from events.
        
        Args:
            events: List of stream events
            
        Returns:
            SSE formatted string
        """
        wrapper = StreamingWrapper()
        return "".join(wrapper.format_for_sse(e) for e in events)


# WebSocket streaming endpoint helper
async def websocket_chat_stream(websocket, llm_callable, messages: List[Dict]):
    """
    WebSocket endpoint for streaming chat.
    
    Args:
        websocket: WebSocket connection
        llm_callable: LLM function to call
        messages: Chat messages
    """
    wrapper = StreamingWrapper()
    
    try:
        # Call LLM with streaming
        if hasattr(llm_callable, '__wrapped__'):
            # Async generator function
            generator = llm_callable(messages)
        else:
            # Regular async function - wrap result
            result = await llm_callable(messages)
            # For non-streaming, yield full content
            async def content_gen():
                yield result if isinstance(result, str) else result.get("content", "")
            generator = content_gen()
        
        # Stream to WebSocket
        await wrapper.stream_to_websocket(
            wrapper.stream_response(generator),
            websocket
        )
        
    except Exception as e:
        logger.error(f"WebSocket chat error: {e}")
        await websocket.send(json.dumps({
            "type": "error",
            "data": str(e)
        }))


# SSE endpoint helper
async def sse_chat_stream(llm_callable, messages: List[Dict]) -> AsyncGenerator[str, None]:
    """
    SSE endpoint for streaming chat.
    
    Args:
        llm_callable: LLM function to call
        messages: Chat messages
        
    Yields:
        SSE formatted strings
    """
    wrapper = StreamingWrapper()
    
    yield "event: connected\ndata: {}\n\n"
    
    try:
        result = await llm_callable(messages)
        content = result if isinstance(result, str) else result.get("content", "")
        
        async def content_gen():
            yield content
        
        async for event in wrapper.stream_response(content_gen()):
            yield wrapper.format_for_sse(event)
            
    except Exception as e:
        logger.error(f"SSE chat error: {e}")
        yield wrapper.format_for_sse(StreamEvent(
            type=StreamEventType.ERROR,
            data=str(e)
        ))

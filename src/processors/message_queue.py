"""Genesis Protocol - Message Queue

Async message processing queue.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Any

from genesis_protocol.utils.logger import get_logger

logger = get_logger("processors.message_queue")


@dataclass
class QueuedMessage:
    """A message in the processing queue."""
    id: str
    data: Any
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    retries: int = 0
    max_retries: int = 3


class MessageQueue:
    """
    Async message queue for Genesis Protocol.
    
    Processes messages asynchronously with priority support.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize message queue.
        
        Args:
            max_size: Maximum queue size
        """
        self._queue: deque[QueuedMessage] = deque(maxlen=max_size)
        self._processing = False
        self._handlers: dict[str, Callable] = {}
        self._results: dict[str, Any] = {}
        
        logger.info(f"Message queue initialized (max size: {max_size})")
    
    def enqueue(self, message_id: str, data: Any, 
                priority: int = 0) -> bool:
        """
        Add message to queue.
        
        Args:
            message_id: Unique message ID
            data: Message data
            priority: Message priority (higher = more urgent)
            
        Returns:
            True if added successfully
        """
        if len(self._queue) >= self._queue.maxlen:
            logger.warning("Queue full, rejecting message")
            return False
        
        message = QueuedMessage(
            id=message_id,
            data=data,
            priority=priority,
        )
        
        self._queue.append(message)
        
        logger.debug(f"Message enqueued: {message_id}")
        
        return True
    
    def register_handler(self, message_type: str, handler: Callable):
        """
        Register a message handler.
        
        Args:
            message_type: Type of message to handle
            handler: Async handler function
        """
        self._handlers[message_type] = handler
        logger.info(f"Handler registered: {message_type}")
    
    async def process(self, timeout: float = 30.0) -> Optional[Any]:
        """
        Process next message in queue.
        
        Args:
            timeout: Maximum time to wait for message
            
        Returns:
            Processing result or None
        """
        if not self._queue:
            return None
        
        message = self._queue.popleft()
        
        logger.debug(f"Processing message: {message.id}")
        
        try:
            # Get handler
            handler = self._handlers.get(message.data.get("type", "default"))
            
            if handler:
                result = await asyncio.wait_for(
                    handler(message.data),
                    timeout=timeout
                )
                
                self._results[message.id] = result
                
                logger.info(f"Message processed: {message.id}")
                
                return result
            else:
                logger.warning(f"No handler for message: {message.id}")
                return None
                
        except asyncio.TimeoutError:
            logger.error(f"Message timeout: {message.id}")
            
            if message.retries < message.max_retries:
                message.retries += 1
                self._queue.append(message)
                logger.info(f"Message requeued: {message.id} (retry {message.retries})")
            else:
                logger.error(f"Message failed after {message.max_retries} retries: {message.id}")
            
            return None
            
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            
            if message.retries < message.max_retries:
                message.retries += 1
                self._queue.append(message)
            
            return None
    
    async def process_all(self, max_messages: int = None):
        """
        Process all messages in queue.
        
        Args:
            max_messages: Maximum messages to process (None for all)
        """
        processed = 0
        
        while self._queue and (max_messages is None or processed < max_messages):
            result = await self.process()
            if result:
                processed += 1
        
        logger.info(f"Processed {processed} messages")
    
    def get_status(self) -> dict:
        """
        Get queue status.
        
        Returns:
            Status dictionary
        """
        return {
            "queue_size": len(self._queue),
            "max_size": self._queue.maxlen,
            "handlers": list(self._handlers.keys()),
            "results_count": len(self._results),
        }
    
    def clear(self):
        """Clear the queue."""
        self._queue.clear()
        self._results.clear()
        logger.info("Queue cleared")
    
    def get_result(self, message_id: str) -> Optional[Any]:
        """
        Get result for a message.
        
        Args:
            message_id: Message ID
            
        Returns:
            Result or None
        """
        return self._results.get(message_id)
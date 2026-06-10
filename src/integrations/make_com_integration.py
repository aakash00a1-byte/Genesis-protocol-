"""Genesis Protocol - Make.com Integration

Webhook triggers and automation actions via Make.com.
"""

from typing import Dict, Any, Optional
import asyncio

import httpx

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("integrations.make_com")


class MakeComClient:
    """
    Make.com webhook client.
    
    Triggers automations and receives results from Make.com scenarios.
    """
    
    def __init__(self):
        """Initialize Make.com client."""
        config = get_config()
        self.webhook_url = config.make_com.webhook_url
        self.api_key = config.make_com.api_key
        
        if self.webhook_url and self.api_key:
            self._client = httpx.AsyncClient(timeout=30.0)
        else:
            self._client = None
        
        logger.info(
            "Make.com client initialized" if self.webhook_url else "Make.com client not configured"
        )
    
    def is_configured(self) -> bool:
        """Check if Make.com is configured."""
        return bool(self.webhook_url and self.api_key)
    
    async def trigger_webhook(self, event: str, data: Dict[str, Any]) -> bool:
        """
        Trigger a Make.com webhook.
        
        Args:
            event: Event type
            data: Event data
            
        Returns:
            True if successful
        """
        if not self.is_configured():
            logger.warning("Make.com not configured, skipping webhook")
            return False
        
        try:
            payload = {
                "event": event,
                "timestamp": asyncio.get_event_loop().time(),
                "data": data,
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            response = await self._client.post(
                self.webhook_url,
                json=payload,
                headers=headers,
            )
            
            if response.status_code in (200, 201, 202):
                logger.info(f"Make.com webhook triggered", event=event)
                return True
            else:
                logger.error(f"Make.com webhook failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Make.com webhook error: {e}")
            return False
    
    async def send_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        """
        Send task result back to Make.com.
        
        Args:
            task_id: Task ID
            result: Result data
            
        Returns:
            True if successful
        """
        return await self.trigger_webhook("task_result", {
            "task_id": task_id,
            "result": result,
        })
    
    async def report_error(self, error: str, context: Dict = None) -> bool:
        """
        Report error to Make.com.
        
        Args:
            error: Error message
            context: Error context
            
        Returns:
            True if successful
        """
        return await self.trigger_webhook("error", {
            "error": error,
            "context": context or {},
        })
    
    async def send_analytics(self, event: str, properties: Dict[str, Any]) -> bool:
        """
        Send analytics event.
        
        Args:
            event: Event name
            properties: Event properties
            
        Returns:
            True if successful
        """
        return await self.trigger_webhook("analytics", {
            "event": event,
            "properties": properties,
        })
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
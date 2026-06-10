"""Genesis Protocol - Tavily Search Integration

Real-time web search integration using Tavily API.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json

import httpx

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("integrations.tavily")


class TavilyClient:
    """
    Tavily API client for web search.
    
    Provides real-time web search capabilities for Genesis Protocol.
    """
    
    BASE_URL = "https://api.tavily.com/search"
    
    def __init__(self):
        """Initialize Tavily client."""
        config = get_config()
        self.api_key = config.tavily.api_key
        self.search_depth = config.tavily.search_depth
        self.max_results = config.tavily.max_results
        self.cache_ttl = timedelta(hours=config.tavily.cache_ttl_hours)
        
        if self.api_key:
            self._client = httpx.AsyncClient(timeout=30.0)
        else:
            self._client = None
        
        # Simple cache
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        
        logger.info("Tavily client initialized" if self.api_key else "Tavily client not configured")
    
    def is_configured(self) -> bool:
        """Check if Tavily is configured."""
        return bool(self.api_key)
    
    async def search(self, query: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Search the web.
        
        Args:
            query: Search query
            use_cache: Whether to use cached results
            
        Returns:
            Search results dictionary
        """
        if not self.is_configured():
            return {"error": "Tavily not configured", "results": []}
        
        # Check cache
        if use_cache:
            cached = self._get_cached(query)
            if cached:
                logger.debug(f"Tavily cache hit for: {query}")
                return cached
        
        try:
            payload = {
                "query": query,
                "search_depth": self.search_depth,
                "max_results": self.max_results,
                "api_key": self.api_key,
            }
            
            response = await self._client.post(self.BASE_URL, json=payload)
            
            if response.status_code != 200:
                logger.error(f"Tavily API error: {response.status_code}")
                return {"error": f"API error: {response.status_code}", "results": []}
            
            data = response.json()
            
            # Cache results
            self._set_cached(query, data)
            
            logger.info(f"Tavily search completed", query=query, results=len(data.get("results", [])))
            
            return data
            
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return {"error": str(e), "results": []}
    
    async def get_context(self, query: str, max_chars: int = 5000) -> str:
        """
        Get formatted context from search results.
        
        Args:
            query: Search query
            max_chars: Maximum characters to return
            
        Returns:
            Formatted context string
        """
        results = await self.search(query)
        
        if "error" in results:
            return ""
        
        context_parts = []
        char_count = 0
        
        for result in results.get("results", []):
            title = result.get("title", "")
            content = result.get("content", "")
            
            entry = f"Source: {title}\n{content}\n"
            
            if char_count + len(entry) > max_chars:
                break
            
            context_parts.append(entry)
            char_count += len(entry)
        
        return "\n---\n".join(context_parts)
    
    async def search_and_summarize(self, query: str) -> Dict[str, Any]:
        """
        Search and provide a summary.
        
        Args:
            query: Search query
            
        Returns:
            Summary dictionary
        """
        results = await self.search(query)
        
        if "error" in results:
            return {"error": results["error"], "summary": ""}
        
        search_results = results.get("results", [])
        
        if not search_results:
            return {"summary": "No results found.", "sources": []}
        
        # Create summary
        summary_parts = []
        sources = []
        
        for result in search_results[:3]:
            title = result.get("title", "")
            snippet = result.get("content", "")[:200]
            url = result.get("url", "")
            
            summary_parts.append(f"- {title}: {snippet}...")
            sources.append({"title": title, "url": url})
        
        summary = "Based on recent search results:\n\n" + "\n".join(summary_parts)
        
        return {
            "summary": summary,
            "sources": sources,
            "raw_results": search_results,
        }
    
    def _get_cached(self, query: str) -> Optional[Dict]:
        """Get cached search results."""
        if query in self._cache:
            data, timestamp = self._cache[query]
            if datetime.utcnow() - timestamp < self.cache_ttl:
                return data
            del self._cache[query]
        return None
    
    def _set_cached(self, query: str, data: Dict):
        """Cache search results."""
        self._cache[query] = (data, datetime.utcnow())
        
        # Limit cache size
        if len(self._cache) > 100:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
    
    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
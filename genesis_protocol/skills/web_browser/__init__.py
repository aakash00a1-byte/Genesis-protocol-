"""
Web & Browser Skills
=====================
Website navigation, interaction, and content extraction.
"""

import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
from genesis_protocol.skills import Skill, SkillCategory

# Skill definitions
SKILLS = [
    Skill(
        name="web_navigate",
        category=SkillCategory.WEB_BROWSER,
        description="Navigate to websites and interact with pages",
        tools=["browser", "http"],
        version="1.0.0"
    ),
    Skill(
        name="web_form_fill",
        category=SkillCategory.WEB_BROWSER,
        description="Fill web forms and submit data",
        tools=["browser"],
        version="1.0.0"
    ),
    Skill(
        name="web_content_extract",
        category=SkillCategory.WEB_BROWSER,
        description="Extract content from web pages",
        tools=["http", "browser"],
        version="1.0.0"
    ),
    Skill(
        name="web_search",
        category=SkillCategory.WEB_BROWSER,
        description="Search the web for information",
        tools=["tavily", "http"],
        version="1.0.0"
    ),
]


@dataclass
class WebPage:
    """Represents a web page with its content."""
    url: str
    title: str
    content: str
    links: List[str]
    forms: List[Dict[str, Any]]
    images: List[str]
    status_code: int


class WebNavigator:
    """Navigate and interact with websites."""
    
    def __init__(self):
        self.current_url = None
        self.history = []
        self.session_cookies = {}
    
    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme:
                url = "https://" + url
                parsed = urlparse(url)
            
            if not parsed.netloc:
                return {"success": False, "error": "Invalid URL"}
            
            self.current_url = url
            self.history.append(url)
            
            return {
                "success": True,
                "url": url,
                "title": "Page Title",  # Would be extracted from page
                "status": "navigated"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click_element(self, selector: str) -> Dict[str, Any]:
        """Click an element by CSS selector."""
        return {
            "success": True,
            "action": "click",
            "selector": selector,
            "message": f"Would click element: {selector}"
        }
    
    def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into an element."""
        return {
            "success": True,
            "action": "type",
            "selector": selector,
            "text": text,
            "message": f"Would type '{text}' into {selector}"
        }
    
    def get_element_info(self, selector: str) -> Dict[str, Any]:
        """Get information about an element."""
        return {
            "success": True,
            "selector": selector,
            "tag": "element",
            "text": "",
            "attributes": {}
        }


class WebContentExtractor:
    """Extract content from web pages."""
    
    def __init__(self):
        self.parser = ContentParser()
    
    def extract_text(self, html: str, selector: Optional[str] = None) -> str:
        """Extract text content from HTML."""
        if selector:
            # Extract from specific element
            pattern = rf'<{selector}[^>]*>(.*?)</{selector}>'
            match = re.search(pattern, html, re.DOTALL)
            if match:
                return self._clean_text(match.group(1))
        
        # Extract all text
        return self._clean_text(html)
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        return text.strip()
    
    def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract all links from HTML."""
        links = []
        pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>'
        
        for match in re.finditer(pattern, html):
            href = match.group(1)
            # Skip anchors and javascript
            if href.startswith(('#', 'javascript:', 'mailto:')):
                continue
            # Resolve relative URLs
            full_url = urljoin(base_url, href)
            links.append(full_url)
        
        return links
    
    def extract_images(self, html: str, base_url: str) -> List[str]:
        """Extract all image URLs from HTML."""
        images = []
        pattern = r'<img[^>]+src=["\']([^"\']+)["\']'
        
        for match in re.finditer(pattern, html):
            src = match.group(1)
            full_url = urljoin(base_url, src)
            images.append(full_url)
        
        return images
    
    def extract_forms(self, html: str) -> List[Dict[str, Any]]:
        """Extract form information from HTML."""
        forms = []
        
        # Find all forms
        form_pattern = r'<form[^>]*>(.*?)</form>'
        for form_match in re.finditer(form_pattern, html, re.DOTALL):
            form_content = form_match.group(0)
            
            # Extract form attributes
            action_match = re.search(r'action=["\']([^"\']+)["\']', form_content)
            method_match = re.search(r'method=["\']([^"\']+)["\']', form_content)
            
            form = {
                "action": action_match.group(1) if action_match else "",
                "method": method_match.group(1).upper() if method_match else "GET",
                "inputs": []
            }
            
            # Extract inputs
            input_pattern = r'<input[^>]+>'
            for input_match in re.finditer(input_pattern, form_content):
                input_tag = input_match.group(0)
                
                input_info = {
                    "type": re.search(r'type=["\']([^"\']+)["\']', input_tag),
                    "name": re.search(r'name=["\']([^"\']+)["\']', input_tag),
                    "id": re.search(r'id=["\']([^"\']+)["\']', input_tag),
                    "placeholder": re.search(r'placeholder=["\']([^"\']+)["\']', input_tag)
                }
                
                form["inputs"].append({
                    "type": input_info["type"].group(1) if input_info["type"] else "text",
                    "name": input_info["name"].group(1) if input_info["name"] else None,
                    "id": input_info["id"].group(1) if input_info["id"] else None,
                    "placeholder": input_info["placeholder"].group(1) if input_info["placeholder"] else None
                })
            
            forms.append(form)
        
        return forms
    
    def extract_tables(self, html: str) -> List[List[List[str]]]:
        """Extract table data from HTML."""
        tables = []
        
        table_pattern = r'<table[^>]*>(.*?)</table>'
        for table_match in re.finditer(table_pattern, html, re.DOTALL):
            table_content = table_match.group(0)
            rows = []
            
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            for row_match in re.finditer(row_pattern, table_content, re.DOTALL):
                row_content = row_match.group(1)
                cells = []
                
                cell_pattern = r'<(td|th)[^>]*>(.*?)</(td|th)>'
                for cell_match in re.finditer(cell_pattern, row_content, re.DOTALL):
                    cell_text = self._clean_text(cell_match.group(2))
                    cells.append(cell_text)
                
                if cells:
                    rows.append(cells)
            
            if rows:
                tables.append(rows)
        
        return tables
    
    def extract_metadata(self, html: str) -> Dict[str, str]:
        """Extract page metadata."""
        metadata = {}
        
        # Title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
        if title_match:
            metadata["title"] = self._clean_text(title_match.group(1))
        
        # Meta tags
        meta_pattern = r'<meta[^>]+>'
        for match in re.finditer(meta_pattern, html):
            tag = match.group(0)
            
            name_match = re.search(r'name=["\']([^"\']+)["\']', tag)
            prop_match = re.search(r'property=["\']([^"\']+)["\']', tag)
            content_match = re.search(r'content=["\']([^"\']+)["\']', tag)
            
            key = name_match.group(1) if name_match else (prop_match.group(1) if prop_match else None)
            value = content_match.group(1) if content_match else None
            
            if key and value:
                metadata[key] = value
        
        return metadata


class ContentParser:
    """Parse and process web content."""
    
    def parse_html(self, html: str) -> Dict[str, Any]:
        """Parse HTML into structured data."""
        extractor = WebContentExtractor()
        
        return {
            "text": extractor.extract_text(html),
            "links": extractor.extract_links(html, ""),
            "images": extractor.extract_images(html, ""),
            "forms": extractor.extract_forms(html),
            "metadata": extractor.extract_metadata(html)
        }
    
    def extract_json_from_html(self, html: str) -> Optional[Dict]:
        """Extract JSON data embedded in HTML."""
        # Look for JSON in script tags
        script_pattern = r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>'
        match = re.search(script_pattern, html, re.DOTALL)
        
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Look for JSON in data attributes
        data_pattern = r'data-([a-z-]+)=["\']([^"\']+)["\']'
        data = {}
        for match in re.finditer(data_pattern, html):
            key = match.group(1)
            value = match.group(2)
            try:
                data[key] = json.loads(value)
            except json.JSONDecodeError:
                data[key] = value
        
        return data if data else None


class WebSearch:
    """Web search functionality."""
    
    def __init__(self, tavily_api_key: Optional[str] = None):
        self.tavily_api_key = tavily_api_key
        self.config = None
    
    def set_config(self, config) -> None:
        """Set configuration for API keys."""
        self.config = config
    
    async def search(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """Search the web using Tavily API."""
        if not self.tavily_api_key and self.config:
            self.tavily_api_key = self.config.tavily.api_key
        
        if not self.tavily_api_key:
            return {
                "success": False,
                "error": "Tavily API key not configured",
                "results": []
            }
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.tavily_api_key,
                        "query": query,
                        "max_results": max_results,
                        "include_answer": True
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "query": query,
                            "results": data.get("results", []),
                            "answer": data.get("answer", ""),
                            "images": data.get("images", [])
                        }
                    else:
                        return {
                            "success": False,
                            "error": f"API returned status {response.status}",
                            "results": []
                        }
        except ImportError:
            return {
                "success": False,
                "error": "aiohttp not installed",
                "results": []
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": []
            }
    
    def google_search(self, query: str) -> Dict[str, Any]:
        """Fallback: Simple Google search simulation."""
        return {
            "success": True,
            "query": query,
            "results": [
                {
                    "title": f"Result for: {query}",
                    "url": f"https://www.google.com/search?q={query}",
                    "snippet": f"Search results would appear here for: {query}"
                }
            ],
            "note": "Use Tavily API for real web search"
        }


# Export skill execution functions
async def execute_web_navigate(url: str) -> Dict[str, Any]:
    """Execute web navigation."""
    navigator = WebNavigator()
    return navigator.navigate(url)


async def execute_web_content_extract(url: str, selector: Optional[str] = None) -> Dict[str, Any]:
    """Execute content extraction."""
    extractor = WebContentExtractor()
    return {
        "success": True,
        "url": url,
        "selector": selector,
        "message": "Content extraction would be performed here"
    }


async def execute_web_search(query: str, max_results: int = 10) -> Dict[str, Any]:
    """Execute web search."""
    search = WebSearch()
    return await search.search(query, max_results)


# Export skill executors
SKILL_EXECUTORS = {
    "web_navigate": execute_web_navigate,
    "web_content_extract": execute_web_content_extract,
    "web_search": execute_web_search,
}
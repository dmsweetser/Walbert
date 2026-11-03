"""
Web tools - HTTP requests and browser automation.

Adopted from AI-Builder engine best practices:
- Uses ToolResult for consistent return types
- Proper error handling and logging
"""

import json
import logging
import requests
from typing import Dict, Any

from walbert.tools.base import BaseTool, ToolResult

logger = logging.getLogger("walbert.tools.builtins.web")


class HttpGetTool(BaseTool):
    name = "web_get"
    description = "Fetch a URL and return its HTML/text content."
    parameters = {"url": "string", "timeout": "string?"}

    def execute(self, params: dict) -> ToolResult:
        url = params["url"]
        timeout = int(params.get("timeout", "30")) if params.get("timeout") else 30

        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

            # Try to detect encoding
            content_type = response.headers.get("Content-Type", "")
            if "charset=" in content_type:
                response.encoding = content_type.split("charset=")[-1].split(";")[0].strip()
            elif response.text and "<meta" in response.text[:1000]:
                import re
                meta_match = re.search(r'<meta[^>]+charset=["\']?([^"\'>\s]+)', response.text[:1000])
                if meta_match:
                    response.encoding = meta_match.group(1)

            content = response.text
            return ToolResult(
                True, content,
                summary=f"HTTP {response.status_code}, {len(content)} bytes from {url}"
            )
        except requests.RequestException as e:
            return ToolResult(False, "", error=f"HTTP request failed: {e}")
        except Exception as e:
            return ToolResult(False, "", error=f"Error fetching URL: {e}")


class HttpPostTool(BaseTool):
    name = "web_post"
    description = "Send a POST request to a URL with optional JSON body."
    parameters = {"url": "string", "body": "string?", "headers": "string?"}

    def execute(self, params: dict) -> ToolResult:
        url = params["url"]
        body = params.get("body", "")
        headers_str = params.get("headers", "")

        headers = {}
        if headers_str:
            try:
                headers = json.loads(headers_str)
            except json.JSONDecodeError:
                return ToolResult(False, "", error=f"Invalid headers JSON: {headers_str}")

        try:
            response = requests.post(url, data=body, headers=headers, timeout=30)
            response.raise_for_status()

            return ToolResult(
                True, response.text,
                summary=f"POST {url} -> {response.status_code}"
            )
        except requests.RequestException as e:
            return ToolResult(False, "", error=f"POST request failed: {e}")
        except Exception as e:
            return ToolResult(False, "", error=f"Error posting to URL: {e}")


# ===================================================================
# Backward-compatible function wrappers
# ===================================================================

def http_get(url: str, timeout: str = "30", **kwargs) -> str:
    """Legacy wrapper for HttpGetTool."""
    tool = HttpGetTool(kwargs.get("root_dir", ""))
    result = tool.execute({"url": url, "timeout": timeout})
    return result.content if result.success else f"Error: {result.error}"


def http_post(url: str, body: str = "", headers: str = "", **kwargs) -> str:
    """Legacy wrapper for HttpPostTool."""
    tool = HttpPostTool(kwargs.get("root_dir", ""))
    result = tool.execute({"url": url, "body": body, "headers": headers})
    return result.content if result.success else f"Error: {result.error}"


def browser_get(url: str, wait_seconds: str = "2", **kwargs) -> str:
    """Navigate to a URL and extract page content as text."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            content = page.text_content()
            browser.close()

            if not content:
                return "Page loaded but no text content found."
            return content
    except Exception as e:
        return f"Error loading page: {e}"

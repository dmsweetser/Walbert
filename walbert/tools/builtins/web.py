"""
Web tools - HTTP GET/POST and browser-based page fetching.
"""

import json
import logging
import subprocess
import os
import sys

logger = logging.getLogger("walbert.tools.builtins.web")


def http_get(url: str, timeout: int = 30, **kwargs) -> str:
    """Fetch a URL using Python requests (or fallback to curl)."""
    try:
        timeout = int(timeout) if isinstance(timeout, str) else timeout
        import requests
        resp = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Walbert/1.0 (AI Agent)"
        })
        resp.raise_for_status()
        content = resp.text
        
        # Truncate very long responses
        if len(content) > 50000:
            content = content[:50000] + f"\n\n# (truncated, {len(resp.text)} chars total)"
        
        return f"# {url}\n# Status: {resp.status_code}\n# Content-Type: {resp.headers.get('content-type', 'unknown')}\n\n{content}"
    except ImportError:
        # Fallback to curl
        return _curl_get(url, timeout)
    except Exception as e:
        return f"Error fetching {url}: {e}"


def http_post(url: str, body: str = "", headers: str = "", **kwargs) -> str:
    """Send a POST request."""
    try:
        import requests
        hdrs = {}
        if headers:
            try:
                hdrs = json.loads(headers)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON headers: {headers}"
        
        data = json.loads(body) if body and body.strip() else None
        
        resp = requests.post(url, json=data, headers=hdrs, timeout=30)
        resp.raise_for_status()
        
        try:
            result = resp.json()
            return f"# {url}\n# Status: {resp.status_code}\n{json.dumps(result, indent=2)}"
        except:
            return f"# {url}\n# Status: {resp.status_code}\n{resp.text[:5000]}"
    except ImportError:
        return _curl_post(url, body, headers)
    except Exception as e:
        return f"Error posting to {url}: {e}"


def browser_get(url: str, wait_seconds: int = 2, **kwargs) -> str:
    """Navigate to a URL and extract text content using headless browser (playwright or selenium)."""
    # Try playwright first
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            if wait_seconds > 0:
                page.wait_for_timeout(wait_seconds * 1000)
            content = page.content()
            browser.close()
            
            # Strip HTML tags to get text
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if len(text) > 50000:
                text = text[:50000] + "\n...(truncated)"
            
            return f"# Page: {url}\n\n{text}"
    except ImportError:
        pass
    
    # Try selenium
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        driver = webdriver.Chrome(options=opts)
        driver.get(url)
        if wait_seconds > 0:
            import time
            time.sleep(wait_seconds)
        content = driver.page_source
        driver.quit()
        
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) > 50000:
            text = text[:50000] + "\n...(truncated)"
        
        return f"# Page: {url}\n\n{text}"
    except ImportError:
        pass
    
    # Fallback: use curl
    return _curl_get(url, 30)


def _curl_get(url: str, timeout: int) -> str:
    """Fallback: fetch URL using curl."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", "--max-time", str(timeout), "-A", "Walbert/1.0", url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        content = result.stdout
        if len(content) > 50000:
            content = content[:50000] + "\n...(truncated)"
        return f"# {url}\n\n{content}"
    except Exception as e:
        return f"Error fetching {url} (curl fallback): {e}"


def _curl_post(url: str, body: str, headers: str) -> str:
    """Fallback: POST using curl."""
    try:
        hdr_args = []
        if headers:
            hdr_args.extend(["-H", f"Content-Type: application/json"])
        cmd = ["curl", "-s", "-X", "POST", "-d", body] + hdr_args + [url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        return f"# {url}\n{result.stdout}"
    except Exception as e:
        return f"Error posting to {url} (curl fallback): {e}"

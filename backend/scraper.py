import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import asyncio
import re
from typing import Dict, List, Set, Tuple, Callable
from backend.database import log_crawled_page

class AsyncWebScraper:
    def __init__(self, base_url: str, max_depth: int = 2, max_pages: int = 50):
        self.base_url = base_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        
        # Parse host to lock scraping to the same domain
        parsed_base = urlparse(base_url)
        self.allowed_domain = parsed_base.netloc
        self.scheme = parsed_base.scheme
        
        # Tracker sets
        self.visited_urls: Set[str] = set()
        self.scraped_data: List[Dict[str, str]] = [] # list of {"url": url, "title": title, "content": text}
        self.active_tasks = 0
        
    def _is_valid_url(self, url: str) -> bool:
        """Checks if a URL belongs to the allowed domain and is an HTML page (not an image, pdf, etc.)."""
        try:
            parsed_url = urlparse(url)
            # Must match allowed domain (e.g., docs.example.com or subdomains of example.com)
            if self.allowed_domain not in parsed_url.netloc:
                return False
                
            # Filter out typical non-HTML file extensions
            path = parsed_url.path.lower()
            excluded_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip', '.tar', '.gz', '.mp4', '.mp3', '.xml', '.css', '.js', '.json']
            if any(path.endswith(ext) for ext in excluded_extensions):
                return False
                
            return True
        except Exception:
            return False

    def _clean_url(self, url: str) -> str:
        """Cleans URL by removing fragments and query params to avoid duplicate scrapes."""
        parsed = urlparse(url)
        # Remove fragment
        return parsed._replace(fragment="").geturl()

    def _extract_clean_text(self, soup: BeautifulSoup) -> str:
        """Extracts clean text content from the soup object, ignoring typical clutter."""
        # Remove script, style, nav, footer, header elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
            element.decompose()
            
        # Extract text from main container if possible, otherwise fall back to body
        main_content = soup.find('main') or soup.find('article') or soup.find('div', id=re.compile('content|main|body', re.I))
        if not main_content:
            main_content = soup.body or soup
            
        # Get all text
        text = main_content.get_text(separator=' ')
        
        # Clean whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = ' '.join(chunk for chunk in chunks if chunk)
        
        return clean_text

    async def scrape_page(self, client: httpx.AsyncClient, url: str, depth: int, status_callback: Callable[[str], None] = None) -> List[str]:
        """Scrapes a single page, returns a list of discovered URLs within allowed boundary."""
        if url in self.visited_urls or len(self.visited_urls) >= self.max_pages:
            return []
            
        self.visited_urls.add(url)
        found_links = []
        
        if status_callback:
            status_callback(f"Scraping ({len(self.visited_urls)}/{self.max_pages}): {url}")
            
        try:
            # Custom headers to act as a standard browser
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            
            response = await client.get(url, headers=headers, timeout=10.0, follow_redirects=True)
            if response.status_code != 200:
                if status_callback:
                    status_callback(f"Error scraping {url}: HTTP {response.status_code}")
                return []
                
            # Parse response
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type:
                return []
                
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Extract title and clean text
            title = soup.title.string.strip() if (soup.title and soup.title.string) else "Untitled Page"
            clean_text = self._extract_clean_text(soup)
            
            if len(clean_text.strip()) > 50: # Avoid empty or boilerplate pages
                self.scraped_data.append({
                    "url": url,
                    "title": title,
                    "content": clean_text
                })
                # Log page to SQLite database for analytics/history
                word_count = len(clean_text.split())
                log_crawled_page(url, title, word_count)
                
            # Extract links if we haven't reached max depth
            if depth < self.max_depth:
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    # Resolve relative url to absolute
                    absolute_url = urljoin(url, href)
                    cleaned_url = self._clean_url(absolute_url)
                    
                    if self._is_valid_url(cleaned_url) and cleaned_url not in self.visited_urls:
                        found_links.append(cleaned_url)
                        
        except httpx.HTTPError as e:
            if status_callback:
                status_callback(f"Network error scraping {url}: {str(e)}")
        except Exception as e:
            if status_callback:
                status_callback(f"Unexpected error scraping {url}: {str(e)}")
                
        return found_links

    async def crawl(self, status_callback: Callable[[str], None] = None) -> List[Dict[str, str]]:
        """Performs dynamic asynchronous recursive crawl starting from base_url."""
        async with httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)) as client:
            # Queue stores tuple of (url, current_depth)
            queue = asyncio.Queue()
            await queue.put((self.base_url, 0))
            
            # Use a lock to sync queue operations and page limit counts
            lock = asyncio.Lock()
            
            async def worker():
                while True:
                    try:
                        async with lock:
                            if queue.empty():
                                break
                            if len(self.visited_urls) >= self.max_pages:
                                # Drain remaining items in queue to finish gracefully
                                while not queue.empty():
                                    queue.get_nowait()
                                break
                            url, depth = await queue.get()
                            
                        # Process link and get sub-links
                        new_links = await self.scrape_page(client, url, depth, status_callback)
                        
                        # Add newly found links to crawl queue
                        for link in new_links:
                            async with lock:
                                if link not in self.visited_urls and len(self.visited_urls) < self.max_pages:
                                    await queue.put((link, depth + 1))
                                    
                        queue.task_done()
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        if status_callback:
                            status_callback(f"Worker error: {str(e)}")
                        queue.task_done()

            # Run 5 concurrent crawling workers
            workers = [asyncio.create_task(worker()) for _ in range(5)]
            await asyncio.gather(*workers)
            
        if status_callback:
            status_callback(f"Ingestion complete! Successfully scraped {len(self.scraped_data)} pages.")
            
        return self.scraped_data

# Quick testing function if run directly
if __name__ == "__main__":
    async def main():
        scraper = AsyncWebScraper("https://quotes.toscrape.com", max_depth=2, max_pages=10)
        data = await scraper.crawl(print)
        print(f"\nScraped {len(data)} pages:")
        for page in data:
            print(f"- {page['title']} ({page['url']})")
    asyncio.run(main())

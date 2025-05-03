import time
import re
import os
import mimetypes
import asyncio
import json
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import aiohttp
import aiofiles

class WordPressScraper:
    def __init__(self, start_url, output_folder="scraped_data", docs_folder="downloaded_docs", delay=1):
        """
        Initialize the WordPress scraper with improved structure for RAG systems.
        
        Args:
            start_url (str): The URL of the WordPress site to scrape
            output_folder (str): Path to the output folder for JSON files
            docs_folder (str): Folder to save downloaded documents
            delay (int): Delay between requests in seconds
        """
        self.start_url = start_url
        self.output_folder = output_folder
        self.docs_folder = docs_folder
        self.delay = delay
        
        # Create folders if they don't exist
        for folder in [self.output_folder, self.docs_folder]:
            if not os.path.exists(folder):
                os.makedirs(folder)
        
        # Extract the base URL
        parsed_url = urlparse(start_url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Set to track visited URLs
        self.visited_urls = set()
        self.found_urls = set([start_url])
        
        # Track downloaded documents
        self.downloaded_docs = []
        
        # Common navigation and footer patterns
        self.nav_selectors = [
            'nav', 'header', '.nav', '.navbar', '.navigation', '#nav', '#navbar', 
            '.menu', '#menu', '.header', '#header', '.site-header', '#site-header',
            '.main-navigation', '#main-navigation', '.primary-menu', '#primary-menu'
        ]
        
        self.footer_selectors = [
            'footer', '.footer', '#footer', '.site-footer', '#site-footer',
            '.bottom', '#bottom', '.site-info', '#site-info', '.copyright', 
            '#copyright', '.widget-area', '#widget-area', '.sidebar', '#sidebar'
        ]
        
        # List of document extensions to download
        self.document_extensions = [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.csv', '.txt', '.rtf', '.zip', '.rar', '.mp3', '.mp4', '.odt'
        ]
        
        # Index file to maintain a catalog of all content
        self.index_file = os.path.join(self.output_folder, "index.json")
        self.content_index = {
            "base_url": self.base_url,
            "pages": [],
            "documents": []
        }
    
    def is_valid_url(self, url):
        """Check if URL belongs to the same domain and is valid."""
        if not url:
            return False
            
        parsed_url = urlparse(url)
        parsed_base = urlparse(self.base_url)
        
        # Check if the URL is from the same domain
        if parsed_url.netloc and parsed_url.netloc != parsed_base.netloc:
            return False
            
        # Ignore CSS and JS files
        ignore_exts = ['.css', '.js']
        if any(url.lower().endswith(ext) for ext in ignore_exts):
            return False
            
        # Ignore URLs with parameters like wp-admin, feed, etc.
        ignored_patterns = ['wp-admin', 'wp-login', 'feed', 'comment', '?s=', 'wp-json']
        if any(pattern in url for pattern in ignored_patterns):
            return False
            
        return True
    
    def is_document(self, url):
        """Check if URL points to a document file."""
        return any(url.lower().endswith(ext) for ext in self.document_extensions)
    
    def get_clean_filename(self, url):
        """Generate a clean filename from URL."""
        parsed_url = urlparse(url)
        path = parsed_url.path.strip("/")
        if not path:
            path = "homepage"
        else:
            # Replace slashes with underscores and remove extension
            path = path.replace("/", "_")
        
        # Remove query parameters and ensure clean filename
        clean_name = re.sub(r'[^\w\-_\.]', '_', path)
        return clean_name
    
    async def get_page_content(self, page, url):
        """Get content from a URL using Playwright to execute JavaScript."""
        try:
            # Navigate to the URL
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit more for dynamic content
            await page.wait_for_timeout(2000)
            
            # Get the page content after JavaScript execution
            content = await page.content()
            return content
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    async def download_document(self, session, url):
        """Download document from URL and save to docs folder."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    print(f"Error downloading {url}: HTTP {response.status}")
                    return None
                
                # Get filename from URL
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                
                # If filename is empty or has no extension, try to get it from Content-Disposition header
                if not filename or '.' not in filename:
                    content_disposition = response.headers.get('Content-Disposition')
                    if content_disposition:
                        # Extract filename from Content-Disposition header
                        fname = re.findall('filename="?([^"]+)"?', content_disposition)
                        if fname:
                            filename = fname[0]
                    
                    # If still no filename, use the URL path
                    if not filename or '.' not in filename:
                        filename = f"document_{len(self.downloaded_docs) + 1}"
                        
                        # Try to get extension from Content-Type
                        content_type = response.headers.get('Content-Type', '').split(';')[0]
                        extension = mimetypes.guess_extension(content_type)
                        if extension:
                            filename += extension
                        else:
                            filename += '.bin'  # Default extension
                
                # Clean up the filename (remove query parameters)
                filename = filename.split('?')[0]
                
                # Ensure the filename is valid
                filename = re.sub(r'[^\w\-_\. ]', '_', filename)
                
                # Construct full path
                file_path = os.path.join(self.docs_folder, filename)
                
                # Ensure we don't overwrite existing files
                if os.path.exists(file_path):
                    base, ext = os.path.splitext(filename)
                    counter = 1
                    while os.path.exists(file_path):
                        file_path = os.path.join(self.docs_folder, f"{base}_{counter}{ext}")
                        counter += 1
                
                # Save the file
                data = await response.read()
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(data)
                
                # Get content type for metadata
                content_type = response.headers.get('Content-Type', '').split(';')[0]
                
                # Add to document index
                doc_info = {
                    "url": url,
                    "file_path": os.path.abspath(file_path),
                    "title": filename,
                    "content_type": content_type,
                    "size_bytes": len(data)
                }
                
                self.downloaded_docs.append(doc_info)
                self.content_index["documents"].append(doc_info)
                
                print(f"Downloaded: {url} -> {file_path}")
                
                return os.path.abspath(file_path)
                
        except Exception as e:
            print(f"Error downloading {url}: {e}")
            return None
    
    def extract_urls(self, url, html_content):
        """Extract all URLs from the HTML content."""
        if not html_content:
            return
            
        soup = BeautifulSoup(html_content, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            # Skip empty or javascript: links
            if not href or href.startswith('javascript:'):
                continue
                
            full_url = urljoin(url, href)
            
            # Remove URL fragments
            full_url = full_url.split('#')[0]
            
            # Skip empty URLs
            if not full_url:
                continue
                
            # Remove trailing slash for consistency in HTML pages
            if not self.is_document(full_url) and full_url.endswith('/'):
                full_url = full_url[:-1]
                
            if self.is_valid_url(full_url) and full_url not in self.visited_urls:
                self.found_urls.add(full_url)
    
    def remove_elements(self, soup, selectors):
        """Remove specified elements from BeautifulSoup object."""
        for selector in selectors:
            for element in soup.select(selector):
                element.decompose()
        return soup
    
    def extract_structured_content(self, url, html_content):
        """
        Extract structured content from the page, removing navigation, sidebars, 
        footers and other non-content elements.
        """
        if not html_content:
            return None
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Store original title
        title = soup.title.string.strip() if soup.title else "No Title"
        
        # Extract meta description if available
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag and 'content' in meta_tag.attrs:
            meta_desc = meta_tag['content'].strip()
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'meta', 'noscript', 'svg', 'iframe']):
            element.decompose()
        
        # Try to identify and remove navigation elements
        self.remove_elements(soup, self.nav_selectors)
        
        # Try to identify and remove footer elements
        self.remove_elements(soup, self.footer_selectors)
        
        # Extract main content area
        main_content = None
        
        # First try to find the main content using common WordPress content containers
        content_selectors = [
            'article', '.post', '#post', '.post-content', '#post-content',
            '.entry-content', '#entry-content', '.content', '#content',
            '.page-content', '#page-content', 'main', '.main', '#main'
        ]
        
        for selector in content_selectors:
            main_elements = soup.select(selector)
            if main_elements:
                # Use the largest content area if multiple are found
                main_content = max(main_elements, key=lambda x: len(x.get_text(strip=True)))
                break
        
        # If no specific content area found, try to find the largest text block
        if not main_content:
            divs = soup.find_all('div')
            if divs:
                main_content = max(divs, key=lambda x: len(x.get_text(strip=True)))
        
        # If still no content, use body
        if not main_content and soup.body:
            main_content = soup.body
        
        # Create a structured content object
        structured_content = {
            "url": url,
            "title": title,
            "meta_description": meta_desc,
            "headings": [],
            "content_blocks": [],
            "images": [],
            "links": []
        }
        
        # If we found a main content area, process it
        if main_content:
            # Extract headings with hierarchy
            for level in range(1, 7):  # h1 through h6
                for heading in main_content.find_all(f'h{level}'):
                    heading_text = heading.get_text(strip=True)
                    if heading_text:
                        structured_content["headings"].append({
                            "level": level,
                            "text": heading_text
                        })
            
            # Extract content blocks (paragraphs)
            for p in main_content.find_all(['p', 'li', 'blockquote', 'pre']):
                text = p.get_text(strip=True)
                if text and len(text) > 10:  # Skip very short paragraphs
                    structured_content["content_blocks"].append({
                        "type": p.name,
                        "text": text
                    })
            
            # Extract images with alt text and src
            for img in main_content.find_all('img', src=True):
                img_src = urljoin(url, img['src'])
                img_alt = img.get('alt', '').strip()
                if img_src:
                    structured_content["images"].append({
                        "src": img_src,
                        "alt": img_alt
                    })
            
            # Extract links with text and href
            for a in main_content.find_all('a', href=True):
                link_text = a.get_text(strip=True)
                link_href = urljoin(url, a['href'])
                if link_text and link_href:
                    structured_content["links"].append({
                        "text": link_text,
                        "href": link_href
                    })
        
        # Generate plain text version for RAG context (combine headings and paragraphs)
        plain_text = title + "\n\n"
        if meta_desc:
            plain_text += meta_desc + "\n\n"
            
        for heading in structured_content["headings"]:
            plain_text += "#" * heading["level"] + " " + heading["text"] + "\n\n"
            
        for block in structured_content["content_blocks"]:
            plain_text += block["text"] + "\n\n"
        
        structured_content["plain_text"] = plain_text.strip()
        
        return structured_content

    async def save_structured_content(self, structured_content):
        """Save the structured content as a JSON file."""
        if not structured_content:
            return
            
        # Generate filename from URL
        filename = self.get_clean_filename(structured_content["url"])
        file_path = os.path.join(self.output_folder, f"{filename}.json")
        
        # Add chunk info for RAG system
        structured_content["chunk_info"] = {
            "word_count": len(structured_content["plain_text"].split()),
            "char_count": len(structured_content["plain_text"])
        }
        
        # Add file path to structured content
        structured_content["file_path"] = os.path.abspath(file_path)
        
        # Add to content index
        self.content_index["pages"].append({
            "url": structured_content["url"],
            "title": structured_content["title"],
            "file_path": structured_content["file_path"]
        })
        
        # Save to file
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(structured_content, indent=2, ensure_ascii=False))
    
    async def save_index(self):
        """Save the content index to a JSON file."""
        # Add scraping statistics
        self.content_index["stats"] = {
            "total_pages": len(self.content_index["pages"]),
            "total_documents": len(self.content_index["documents"]),
            "scrape_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        async with aiofiles.open(self.index_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.content_index, indent=2, ensure_ascii=False))
    
    async def scrape(self):
        """Start scraping the website."""
        print(f"Starting to scrape {self.start_url}")
        print(f"Results will be saved to {os.path.abspath(self.output_folder)}")
        print(f"Documents will be downloaded to {os.path.abspath(self.docs_folder)}")
        
        start_time = time.time()
        
        # Start playwright
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            page = await context.new_page()
            
            # Create aiohttp session for document downloads
            async with aiohttp.ClientSession() as session:
                while self.found_urls:
                    url = self.found_urls.pop()
                    if url in self.visited_urls:
                        continue
                        
                    print(f"Processing: {url}")
                    self.visited_urls.add(url)
                    
                    # Check if it's a document to download
                    if self.is_document(url):
                        await self.download_document(session, url)
                    else:
                        # Regular HTML page - scrape it with JavaScript support
                        html_content = await self.get_page_content(page, url)
                        if html_content:
                            self.extract_urls(url, html_content)
                            structured_content = self.extract_structured_content(url, html_content)
                            if structured_content:
                                await self.save_structured_content(structured_content)
                        
                    # Be nice to the server
                    await asyncio.sleep(self.delay)
                
                # Save the index file
                await self.save_index()
                
            # Close browser
            await browser.close()
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print(f"Scraping completed in {elapsed_time:.2f} seconds.")
        print(f"Discovered {len(self.visited_urls)} URLs.")
        print(f"Processed {len(self.content_index['pages'])} pages.")
        print(f"Downloaded {len(self.downloaded_docs)} documents.")
        print(f"Index saved to {os.path.abspath(self.index_file)}")


# Async entry point
async def main():
    # Example usage
    target_url = input("Enter the WordPress site URL to scrape: ")
    output_folder = input("Enter output folder for structured data (default: scraped_data): ") or "scraped_data"
    docs_folder = input("Enter folder for downloaded documents (default: downloaded_docs): ") or "downloaded_docs"
    delay = float(input("Enter delay between requests in seconds (default: 1): ") or 1)
    
    scraper = WordPressScraper(target_url, output_folder, docs_folder, delay)
    await scraper.scrape()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
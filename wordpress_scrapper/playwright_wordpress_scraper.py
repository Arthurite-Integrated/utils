import time
import re
import os
import mimetypes
import asyncio
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import aiohttp
import aiofiles

class WordPressScraper:
    def __init__(self, start_url, output_file="scraped_data.txt", docs_folder="downloaded_docs", delay=1):
        """
        Initialize the WordPress scraper with JavaScript support.
        
        Args:
            start_url (str): The URL of the WordPress site to scrape
            output_file (str): Path to the output file
            docs_folder (str): Folder to save downloaded documents
            delay (int): Delay between requests in seconds
        """
        self.start_url = start_url
        self.output_file = output_file
        self.docs_folder = docs_folder
        self.delay = delay
        
        # Create docs folder if it doesn't exist
        if not os.path.exists(self.docs_folder):
            os.makedirs(self.docs_folder)
        
        # Extract the base URL
        parsed_url = urlparse(start_url)
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Set to track visited URLs
        self.visited_urls = set()
        self.found_urls = set([start_url])
        
        # Track downloaded documents
        self.downloaded_docs = []
        
        # List of document extensions to download
        self.document_extensions = [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.csv', '.txt', '.rtf', '.zip', '.rar', '.mp3', '.mp4', '.odt'
        ]
        
        # Create or clear the output file
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(f"Web Scraping Results for {start_url}\n")
            f.write("=" * 50 + "\n\n")
    
    
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
        ignored_patterns = ['wp-admin', 'wp-login', 'feed', 'comment', '?s=']
        if any(pattern in url for pattern in ignored_patterns):
            return False
            
        return True
    
    def is_document(self, url):
        """Check if URL points to a document file."""
        return any(url.lower().endswith(ext) for ext in self.document_extensions)
    
    
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
                
                # Record the downloaded document
                self.downloaded_docs.append((url, file_path))
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
    

    def extract_content(self, url, html_content):
        """Extract all content from the page without assuming any particular CMS structure."""
        if not html_content:
            return "Failed to retrieve content"
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and other non-content elements
        for element in soup(['script', 'style', 'meta', 'noscript', 'svg', 'iframe']):
            element.decompose()
            
        # Get title
        title = soup.title.string if soup.title else "No Title"
        
        # Extract all text from the body
        main_text = ""
        if soup.body:
            main_text = soup.body.get_text(separator='\n', strip=True)
            main_text = re.sub(r'\n+', '\n', main_text)  # Remove multiple newlines
            main_text = re.sub(r'\s+', ' ', main_text)   # Normalize whitespace
        
        # Extract all links
        links_info = []
        for link in soup.find_all('a', href=True):
            link_text = link.get_text(strip=True)
            if link_text:  # Only include links with text
                full_url = urljoin(url, link['href'])
                links_info.append(f"- {link_text}: {full_url}")
        
        links_section = ""
        if links_info:
            links_section = "\n\nLinks found on page:\n" + "\n".join(links_info)
        
        # Extract all images
        images_info = []
        for img in soup.find_all('img', src=True):
            img_alt = img.get('alt', 'No alt text')
            img_src = urljoin(url, img['src'])
            images_info.append(f"- Image: {img_alt} ({img_src})")
        
        images_section = ""
        if images_info:
            images_section = "\n\nImages found on page:\n" + "\n".join(images_info)
        
        # Extract headings for better structure understanding
        headings = []
        for i in range(1, 7):  # h1 through h6
            for heading in soup.find_all(f'h{i}'):
                heading_text = heading.get_text(strip=True)
                if heading_text:
                    headings.append(f"H{i}: {heading_text}")
        
        headings_section = ""
        if headings:
            headings_section = "\n\nHeadings on page:\n" + "\n".join(headings)
        
        # Also try to identify the main content area by finding the div with the most text
        # This can help to separate the main content from navigation, sidebars, etc.
        main_content_area = ""
        divs = soup.find_all('div')
        max_length = 0
        longest_div = None
        
        for div in divs:
            div_text = div.get_text(strip=True)
            if len(div_text) > max_length:
                max_length = len(div_text)
                longest_div = div
        
        if longest_div and max_length > 200:  # Only if substantial content
            main_content_area = "\n\nMain Content Area:\n" + longest_div.get_text(separator='\n', strip=True)
            main_content_area = re.sub(r'\n+', '\n', main_content_area)
        
        # Put it all together
        return f"Title: {title}\n\n{headings_section}\n\nFull Page Text:\n{main_text}{links_section}{images_section}{main_content_area}"

    async def save_content(self, url, content):
        """Save the extracted content to the output file."""
        async with aiofiles.open(self.output_file, 'a', encoding='utf-8') as f:
            await f.write(f"\nURL: {url}\n")
            await f.write("-" * 50 + "\n")
            await f.write(content)
            await f.write("\n\n" + "=" * 50 + "\n")
    
    async def create_url_index(self):
        """Create an index of all discovered URLs at the end of the file."""
        async with aiofiles.open(self.output_file, 'a', encoding='utf-8') as f:
            await f.write("\n\nURL INDEX\n")
            await f.write("=" * 50 + "\n")
            for i, url in enumerate(sorted(self.visited_urls), 1):
                await f.write(f"{i}. {url}\n")
                
    async def create_documents_index(self):
        """Create an index of all downloaded documents."""
        if not self.downloaded_docs:
            return
            
        async with aiofiles.open(self.output_file, 'a', encoding='utf-8') as f:
            await f.write("\n\nDOWNLOADED DOCUMENTS\n")
            await f.write("=" * 50 + "\n")
            for i, (url, file_path) in enumerate(self.downloaded_docs, 1):
                await f.write(f"{i}. {url} -> {file_path}\n")
    

    async def scrape(self):
        """Start scraping the website."""
        print(f"Starting to scrape {self.start_url}")
        print(f"Results will be saved to {self.output_file}")
        print(f"Documents will be downloaded to {os.path.abspath(self.docs_folder)}")
        
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
                        file_path = await self.download_document(session, url)
                        if file_path:
                            await self.save_content(url, f"Document downloaded to: {file_path}")
                    else:
                        # Regular HTML page - scrape it with JavaScript support
                        html_content = await self.get_page_content(page, url)
                        if html_content:
                            self.extract_urls(url, html_content)
                            content = self.extract_content(url, html_content)
                            await self.save_content(url, content)
                        
                    # Be nice to the server
                    await asyncio.sleep(self.delay)
                    
                await self.create_url_index()
                await self.create_documents_index()
                
            # Close browser
            await browser.close()
            
        print(f"Scraping completed. Discovered {len(self.visited_urls)} URLs.")
        print(f"Downloaded {len(self.downloaded_docs)} documents.")
        print(f"Results saved to {os.path.abspath(self.output_file)}")
    


# Async entry point
async def main():
    # Example usage
    target_url = input("Enter the WordPress site URL to scrape: ")
    output_file = input("Enter output filename (default: scraped_data.txt): ") or "scraped_data.txt"
    docs_folder = input("Enter folder for downloaded documents (default: downloaded_docs): ") or "downloaded_docs"
    delay = float(input("Enter delay between requests in seconds (default: 1): ") or 1)
    
    scraper = WordPressScraper(target_url, output_file, docs_folder, delay)
    await scraper.scrape()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
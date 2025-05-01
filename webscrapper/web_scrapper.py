import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re
import os
import mimetypes

class WebsiteScraper:
    def __init__(self, start_url, output_file="scraped_data.txt", docs_folder="downloaded_docs", delay=1):
        """
        Initialize the website scraper.
        
        Args:
            start_url (str): The URL of the site to scrape
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
            
        # Ignore certain extensions that aren't useful for content
        ignore_exts = ['.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico']
        if any(url.lower().endswith(ext) for ext in ignore_exts):
            return False
            
        return True
    
    def is_document(self, url):
        """Check if URL points to a document file."""
        return any(url.lower().endswith(ext) for ext in self.document_extensions)
    
    def get_page_content(self, url):
        """Get content from a URL."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            # Check if content type is HTML
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                return None
                
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def download_document(self, url):
        """Download document from URL and save to docs folder."""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30, stream=True)
            response.raise_for_status()
            
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
                
                # If still no filename, use the URL path with a counter
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
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
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
        """Extract meaningful content from the page."""
        if not html_content:
            return "Failed to retrieve content"
            
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(['script', 'style', 'nav', 'footer', 'header']):
            script_or_style.decompose()
            
        # Get title
        title = soup.title.string if soup.title else "No Title"
        
        # Try to get the main content
        main_content = None
        
        # Check for common content containers
        content_containers = [
            soup.find('main'),
            soup.find('article'),
            soup.find('div', class_=re.compile('content|main|post|article')),
            soup.find('div', id=re.compile('content|main|post|article')),
            soup.find('section', class_=re.compile('content|main')),
            soup.body
        ]
        
        for container in content_containers:
            if container:
                main_content = container
                break
                
        # Clean up the text
        if main_content:
            text = main_content.get_text(separator='\n', strip=True)
            text = re.sub(r'\n+', '\n', text)  # Remove multiple newlines
        else:
            text = "No content found"
        
        return f"Title: {title}\n\n{text}"
    
    def save_content(self, url, content):
        """Save the extracted content to the output file."""
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write(f"\nURL: {url}\n")
            f.write("-" * 50 + "\n")
            f.write(content)
            f.write("\n\n" + "=" * 50 + "\n")
    
    def create_url_index(self):
        """Create an index of all discovered URLs at the end of the file."""
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write("\n\nURL INDEX\n")
            f.write("=" * 50 + "\n")
            for i, url in enumerate(sorted(self.visited_urls), 1):
                f.write(f"{i}. {url}\n")
                
    def create_documents_index(self):
        """Create an index of all downloaded documents."""
        if not self.downloaded_docs:
            return
            
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write("\n\nDOWNLOADED DOCUMENTS\n")
            f.write("=" * 50 + "\n")
            for i, (url, file_path) in enumerate(self.downloaded_docs, 1):
                f.write(f"{i}. {url} -> {file_path}\n")
    
    def scrape(self):
        """Start scraping the website."""
        print(f"Starting to scrape {self.start_url}")
        print(f"Results will be saved to {self.output_file}")
        print(f"Documents will be downloaded to {os.path.abspath(self.docs_folder)}")
        
        while self.found_urls:
            url = self.found_urls.pop()
            if url in self.visited_urls:
                continue
                
            print(f"Processing: {url}")
            self.visited_urls.add(url)
            
            # Check if it's a document to download
            if self.is_document(url):
                file_path = self.download_document(url)
                if file_path:
                    self.save_content(url, f"Document downloaded to: {file_path}")
            else:
                # Regular HTML page - scrape it
                html_content = self.get_page_content(url)
                if html_content:
                    self.extract_urls(url, html_content)
                    content = self.extract_content(url, html_content)
                    self.save_content(url, content)
                
            # Be nice to the server
            time.sleep(self.delay)
            
        self.create_url_index()
        self.create_documents_index()
        print(f"Scraping completed. Discovered {len(self.visited_urls)} URLs.")
        print(f"Downloaded {len(self.downloaded_docs)} documents.")
        print(f"Results saved to {os.path.abspath(self.output_file)}")


if __name__ == "__main__":
    # Example usage
    target_url = input("Enter the website URL to scrape: ")
    output_file = input("Enter output filename (default: scraped_data.txt): ") or "scraped_data.txt"
    docs_folder = input("Enter folder for downloaded documents (default: downloaded_docs): ") or "downloaded_docs"
    delay = float(input("Enter delay between requests in seconds (default: 1): ") or 1)
    
    scraper = WebsiteScraper(target_url, output_file, docs_folder, delay)
    scraper.scrape()
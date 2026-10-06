"""
Website and Document Discovery module.
Fetches official webpages and discovers relevant scheme pages and document links.
"""

from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from app.config import setup_logger

logger = setup_logger("discovery")

# Standard polite browser headers for government websites
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 SchemeWatcher/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

import re

# Keywords in English and Kannada that indicate scheme guidelines, orders, or policies.
# Uses word boundaries (\b) for short English words so '.gov' is not falsely matched as 'go'.
RELEVANT_PATTERNS = [
    # English keywords
    r"\bschemes?\b",
    r"\byojanas?\b",
    r"\byojanes?\b",
    r"\bguidelines?\b",
    r"\borders?\b",
    r"\bnotifications?\b",
    r"\bcirculars?\b",
    r"\bpolic(?:y|ies)\b",
    r"\beligibility\b",
    r"\bcriteria\b",
    r"\bbenefits?\b",
    r"\brules?\b",
    r"\bg\.?o\.?\b",  # G.O. or GO (Government Order)
    r"\bg\.?r\.?\b",  # G.R. or GR (Government Resolution)
    # Kannada keywords
    r"ಯೋಜನೆ",
    r"ಮಾರ್ಗಸೂಚಿ",
    r"ಆದೇಶ",
    r"ಅಧಿಸೂಚನೆ",
    r"ಸುತ್ತೋಲೆ",
    r"ಅರ್ಹತೆ",
    r"ನಿಯಮ",
]

# Pre-compile the regex pattern for fast, case-insensitive matching
KEYWORD_REGEX = re.compile("|".join(RELEVANT_PATTERNS), re.IGNORECASE)

# File extensions that represent scheme documents
DOCUMENT_EXTENSIONS = [".pdf", ".doc", ".docx"]


def fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """
    Fetches the HTML content of a given URL.
    Returns the HTML string, or None if the request fails.
    """
    try:
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        response.raise_for_status()
        return response.text
    except requests.exceptions.SSLError:
        logger.warning(f"SSL certificate verification failed for {url}. Retrying without certificate verification...")
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, verify=False)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url} (SSL fallback): {e}")
            return None
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None


def extract_links(html: str, base_url: str) -> List[Dict[str, str]]:
    """
    Extracts all valid links from HTML content.
    Converts relative links (e.g. '/schemes/test.pdf') to full URLs.
    """
    soup = BeautifulSoup(html, "html.parser")
    found_links: List[Dict[str, str]] = []
    seen_urls = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        # Skip empty links, page anchors (#), and javascript calls
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue

        # Convert relative link to full absolute URL
        absolute_url = urljoin(base_url, href)

        # Ensure it has a valid web scheme (http or https)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https"):
            continue

        # Avoid duplicates on the same page
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        # Get the visible text of the link
        link_text = anchor.get_text(separator=" ", strip=True)

        found_links.append({
            "url": absolute_url,
            "text": link_text,
            "title": anchor.get("title", "").strip(),
        })

    return found_links


def is_document_url(url: str) -> bool:
    """Checks if a URL points directly to a document (like a .pdf)."""
    parsed = urlparse(url.lower())
    path = parsed.path
    return any(path.endswith(ext) for ext in DOCUMENT_EXTENSIONS)


def is_relevant_link(link: Dict[str, str]) -> bool:
    """
    Checks if a link appears relevant to schemes, guidelines, or orders
    based on the URL path or visible text.
    """
    # Direct document files are always candidate documents
    if is_document_url(link["url"]):
        return True

    text_to_check = f"{link.get('text', '')} {link.get('title', '')} {link['url']}"
    return bool(KEYWORD_REGEX.search(text_to_check))


def categorize_links(links: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    """
    Splits discovered links into:
    - 'document_links': Links directly to files (PDFs, docs)
    - 'scheme_page_links': Links to other webpages with scheme keywords
    """
    documents = []
    scheme_pages = []

    for link in links:
        if is_document_url(link["url"]):
            documents.append(link)
        elif is_relevant_link(link):
            scheme_pages.append(link)

    return {
        "document_links": documents,
        "scheme_page_links": scheme_pages,
    }


def discover_from_url(url: str) -> Dict[str, Any]:
    """
    Main discovery function:
    1. Fetches the page HTML
    2. Extracts all links
    3. Categorizes relevant documents and scheme pages
    """
    logger.info(f"Discovering links from source: {url}")
    html = fetch_html(url)

    if not html:
        return {
            "source_url": url,
            "success": False,
            "document_links": [],
            "scheme_page_links": [],
            "all_links_count": 0,
        }

    all_links = extract_links(html, base_url=url)
    categorized = categorize_links(all_links)

    logger.info(
        f"Discovered {len(categorized['document_links'])} documents and "
        f"{len(categorized['scheme_page_links'])} scheme pages from {url}"
    )

    return {
        "source_url": url,
        "success": True,
        "document_links": categorized["document_links"],
        "scheme_page_links": categorized["scheme_page_links"],
        "all_links_count": len(all_links),
    }

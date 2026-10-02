"""
Document Discovery module.
Identifies relevant PDFs, guidelines, government orders, circulars, and notifications
from discovered scheme webpages, extracting titles, dates, and document types.
"""

import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.discovery import fetch_html, is_document_url
from app.config import setup_logger

logger = setup_logger("document_discovery")

# Keywords that indicate the document is NOT a scheme policy document (ignore these)
EXCLUDED_PATTERNS = [
    r"\bholidays?\b",
    r"\btenders?\b",
    r"\bcontacts?\b",
    r"\bdirector(?:y|ies)\b",
    r"\bcug\b",
    r"\btransfers?\b",
    r"\brecruitments?\b",
    r"\bseniority\b",
    r"ರಜೆ",
    r"ಟೆಂಡರ್",
    r"ಸಂಪರ್ಕ",
    r"ದೂರವಾಣಿ",
    r"ವರ್ಗಾವಣೆ",
    r"ನೇಮಕಾತಿ",
    r"ಜಿಲ್ಲಾ\s+ಕಛೇರಿ",
]
EXCLUDE_REGEX = re.compile("|".join(EXCLUDED_PATTERNS), re.IGNORECASE)

# Classification patterns for document type
TYPE_PATTERNS = {
    "guideline": re.compile(r"\bguidelines?\b|ಮಾರ್ಗಸೂಚಿ", re.IGNORECASE),
    "order": re.compile(r"\borders?\b|\bg\.?o\.?\b|ಆದೇಶ", re.IGNORECASE),
    "circular": re.compile(r"\bcirculars?\b|ಸುತ್ತೋಲೆ", re.IGNORECASE),
    "notification": re.compile(r"\bnotifications?\b|ಅಧಿಸೂಚನೆ", re.IGNORECASE),
    "application_form": re.compile(r"\bforms?\b|\bapplications?\b|ಅರ್ಜಿ", re.IGNORECASE),
}

# Regex to find dates like DD-MM-YYYY, DD/MM/YYYY, or YYYY-MM-DD
DATE_REGEX = re.compile(r"\b(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})\b")


def classify_document_type(title: str, url: str) -> str:
    """
    Classifies a document based on its title and URL into:
    - 'guideline'
    - 'order' (Government Order / G.O.)
    - 'circular'
    - 'notification'
    - 'application_form'
    - 'other'
    """
    text = f"{title} {url}"
    for doc_type, pattern in TYPE_PATTERNS.items():
        if pattern.search(text):
            return doc_type
    return "other"


def is_scheme_document(title: str, url: str) -> bool:
    """
    Determines whether a document is likely a scheme document or an administrative file.
    Filters out holiday lists, contact numbers, tenders, and staff transfer lists.
    """
    text = f"{title} {url}"
    # If it matches any excluded topic, it is not a scheme document
    if EXCLUDE_REGEX.search(text):
        return False
    return True


def clean_text(text: str) -> str:
    """Cleans up whitespace and non-breaking spaces from extracted text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def extract_date_from_text(text: str) -> Optional[str]:
    """Finds a date pattern (e.g. 29-01-2026 or 07/08/2021) in text."""
    match = DATE_REGEX.search(text)
    return match.group(1) if match else None


def extract_documents_from_html(
    html: str,
    source_page_url: str,
    scheme_name: Optional[str] = None,
    department: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Parses HTML and finds all downloadable documents (.pdf, .doc, etc.).
    Extracts title from:
    1. Table rows (if document is linked in a table like Government Orders)
    2. Link anchor text or title attribute
    3. Surrounding list item or heading
    """
    soup = BeautifulSoup(html, "html.parser")
    discovered_docs: List[Dict[str, Any]] = []
    seen_urls = set()

    # 1. Process Table Rows: Government websites frequently list orders/guidelines in <table> rows
    for row in soup.find_all("tr"):
        anchors = row.find_all("a", href=True)
        pdf_anchors = [a for a in anchors if is_document_url(a["href"])]

        if not pdf_anchors:
            continue

        # Extract text from all cells in this table row
        cells = [clean_text(td.get_text()) for td in row.find_all(["td", "th"])]
        row_text = " | ".join([c for c in cells if c])

        # Extract date from the row if available
        row_date = extract_date_from_text(row_text)

        for anchor in pdf_anchors:
            href = anchor.get("href", "").strip()
            absolute_url = urljoin(source_page_url, href)

            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            # Determine best title:
            # If the link text is just 'View' or 'ವೀಕ್ಷಣೆ' or 'Download', find the subject cell from the row
            link_text = clean_text(anchor.get_text())
            generic_words = {"ವೀಕ್ಷಣೆ", "view", "download", "pdf", "click here", "click", "ಇಲ್ಲಿ ಕ್ಲಿಕ್ ಮಾಡಿ"}

            title = link_text
            if not title or title.lower() in generic_words:
                # Find a descriptive non-numeric cell from the row
                candidate_cells = [
                    c for c in cells
                    if c and c.lower() not in generic_words and not c.isdigit() and len(c) > 3
                ]
                if candidate_cells:
                    title = candidate_cells[0]
                else:
                    title = anchor.get("title", "").strip() or urlparse(absolute_url).path.split("/")[-1]

            doc_type = classify_document_type(title, absolute_url)
            relevant = is_scheme_document(title, absolute_url)

            discovered_docs.append({
                "document_url": absolute_url,
                "source_page_url": source_page_url,
                "title": title,
                "scheme_name": scheme_name,
                "department": department,
                "document_type": doc_type,
                "published_date": row_date,
                "is_scheme_document": relevant,
            })

    # 2. Process any remaining PDF links outside of tables (e.g. lists, standalone links)
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not is_document_url(href):
            continue

        absolute_url = urljoin(source_page_url, href)
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        link_text = clean_text(anchor.get_text())
        title = link_text or anchor.get("title", "").strip() or urlparse(absolute_url).path.split("/")[-1]

        # Check surrounding parent (like <li> or <p>) for a date
        parent = anchor.find_parent(["li", "p"])
        parent_text = clean_text(parent.get_text()) if parent else ""
        pub_date = extract_date_from_text(parent_text)

        doc_type = classify_document_type(title, absolute_url)
        relevant = is_scheme_document(title, absolute_url)

        discovered_docs.append({
            "document_url": absolute_url,
            "source_page_url": source_page_url,
            "title": title,
            "scheme_name": scheme_name,
            "department": department,
            "document_type": doc_type,
            "published_date": pub_date,
            "is_scheme_document": relevant,
        })

    return discovered_docs


def discover_documents_from_page(
    page_url: str,
    scheme_name: Optional[str] = None,
    department: Optional[str] = None,
    scheme_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetches a scheme page and returns all discovered scheme documents.
    If scheme_only=True, filters out administrative files like holiday lists.
    """
    logger.info(f"Discovering documents on page: {page_url}")
    html = fetch_html(page_url)
    if not html:
        return []

    docs = extract_documents_from_html(
        html=html,
        source_page_url=page_url,
        scheme_name=scheme_name,
        department=department,
    )

    if scheme_only:
        docs = [d for d in docs if d["is_scheme_document"]]

    logger.info(f"Discovered {len(docs)} relevant documents from {page_url}")
    return docs

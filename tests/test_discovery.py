"""
Test Website and Document Discovery (CP4).
Verifies HTML parsing, link extraction, relative URL conversion, and keyword filtering.
"""

from unittest.mock import patch
from app.discovery import (
    extract_links,
    is_document_url,
    is_relevant_link,
    categorize_links,
    discover_from_url,
)

SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Karnataka Department of Agriculture</title></head>
<body>
    <nav>
        <a href="/">Home</a>
        <a href="/about-us">About Us</a>
        <a href="#main-content">Skip to content</a>
        <a href="javascript:void(0)">Print</a>
    </nav>
    <main id="main-content">
        <h1>Schemes & Programs</h1>
        <ul>
            <li>
                <a href="/schemes/raitha-siri">Raitha Siri Scheme</a>
            </li>
            <li>
                <a href="https://raitamitra.karnataka.gov.in/docs/krishi_bhagya_guidelines_2026.pdf">
                    Krishi Bhagya Scheme Guidelines (English PDF)
                </a>
            </li>
            <li>
                <a href="/documents/gruha_lakshmi_yojane.pdf" title="ಗೃಹಲಕ್ಷ್ಮಿ ಯೋಜನೆ ಮಾರ್ಗಸೂಚಿ">
                    ಗೃಹಲಕ್ಷ್ಮಿ ಯೋಜನೆ ಮಾರ್ಗಸೂಚಿ (Kannada PDF)
                </a>
            </li>
            <li>
                <a href="/contact">Contact Officers</a>
            </li>
        </ul>
    </main>
</body>
</html>
"""


def test_extract_links():
    """Verify that relative links are converted to full absolute URLs and junk links are skipped."""
    base_url = "https://raitamitra.karnataka.gov.in/portal"
    links = extract_links(SAMPLE_HTML, base_url)

    urls = [link["url"] for link in links]

    # Relative links converted to absolute
    assert "https://raitamitra.karnataka.gov.in/schemes/raitha-siri" in urls
    assert "https://raitamitra.karnataka.gov.in/documents/gruha_lakshmi_yojane.pdf" in urls
    assert "https://raitamitra.karnataka.gov.in/docs/krishi_bhagya_guidelines_2026.pdf" in urls

    # Junk links skipped
    assert not any("#" in u for u in urls)
    assert not any("javascript:" in u.lower() for u in urls)


def test_is_document_url():
    """Verify document file extension detection."""
    assert is_document_url("https://example.com/file.pdf") is True
    assert is_document_url("https://example.com/file.PDF") is True
    assert is_document_url("https://example.com/order.docx") is True
    assert is_document_url("https://example.com/page.html") is False
    assert is_document_url("https://example.com/schemes") is False


def test_is_relevant_link_english_and_kannada():
    """Verify keyword filtering for English and Kannada scheme terms."""
    # Relevant English
    link_eng = {
        "url": "https://example.com/schemes/farmer-support",
        "text": "Farmer Support Scheme",
        "title": "",
    }
    assert is_relevant_link(link_eng) is True

    # Relevant Kannada
    link_kan = {
        "url": "https://example.com/pages/info",
        "text": "ಯೋಜನೆ ಮಾರ್ಗಸೂಚಿ",
        "title": "",
    }
    assert is_relevant_link(link_kan) is True

    # Irrelevant
    link_irrelevant = {
        "url": "https://example.com/contact-us",
        "text": "Contact Us",
        "title": "",
    }
    assert is_relevant_link(link_irrelevant) is False


def test_categorize_links():
    """Verify splitting links into document files vs scheme web pages."""
    base_url = "https://raitamitra.karnataka.gov.in"
    links = extract_links(SAMPLE_HTML, base_url)
    categorized = categorize_links(links)

    doc_urls = [d["url"] for d in categorized["document_links"]]
    page_urls = [p["url"] for p in categorized["scheme_page_links"]]

    # Documents should contain the 2 PDFs
    assert any("krishi_bhagya_guidelines_2026.pdf" in u for u in doc_urls)
    assert any("gruha_lakshmi_yojane.pdf" in u for u in doc_urls)

    # Scheme pages should contain the scheme HTML link
    assert any("raitha-siri" in u for u in page_urls)

    # Generic links like /about-us or /contact should NOT be in scheme pages
    assert not any("/about-us" in u for u in page_urls)
    assert not any("/contact" in u for u in page_urls)


def test_discover_from_url_with_mock():
    """Verify discover_from_url end-to-end pipeline with mocked HTTP response."""
    with patch("app.discovery.fetch_html", return_value=SAMPLE_HTML):
        result = discover_from_url("https://raitamitra.karnataka.gov.in")

        assert result["success"] is True
        assert len(result["document_links"]) == 2
        assert len(result["scheme_page_links"]) == 1
        assert result["all_links_count"] == 6

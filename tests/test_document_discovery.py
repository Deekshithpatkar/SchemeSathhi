"""
Test Document Discovery (CP5).
Verifies PDF extraction, table-row title pairing, date extraction, and scheme document filtering.
"""

from unittest.mock import patch
from app.document_discovery import (
    classify_document_type,
    is_scheme_document,
    extract_date_from_text,
    extract_documents_from_html,
    discover_documents_from_page,
)

SAMPLE_TABLE_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h1>ಸರ್ಕಾರಿ ಆದೇಶಗಳು (Government Orders)</h1>
    <table border="1">
        <thead>
            <tr>
                <th>ಕ್ರಮ ಸಂ.</th>
                <th>ವಿಷಯ</th>
                <th>ದಿನಾಂಕ</th>
                <th>ಭಾಷೆ</th>
                <th>ವೀಕ್ಷಣೆ</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>1</td>
                <td>ಮುಖ್ಯಮಂತ್ರಿ ರೈತ ವಿದ್ಯಾನಿಧಿ ಕಾರ್ಯಕ್ರಮದ ಮಾರ್ಗಸೂಚಿ</td>
                <td>07-08-2021</td>
                <td>ಕನ್ನಡ</td>
                <td><a href="/storage/pdf-files/cmscholarship.pdf">ವೀಕ್ಷಣೆ</a></td>
            </tr>
            <tr>
                <td>2</td>
                <td>PM-KISAN Scheme Guidelines Final Order</td>
                <td>15/05/2023</td>
                <td>English</td>
                <td><a href="/storage/pdf-files/PM-KISAN_Guidelines.pdf">View</a></td>
            </tr>
            <tr>
                <td>3</td>
                <td>ಜಿಲ್ಲಾ ಕಛೇರಿ ದೂರವಾಣಿ ಸಂಖ್ಯೆಗಳು</td>
                <td>01-01-2024</td>
                <td>ಕನ್ನಡ</td>
                <td><a href="/uploads/CUG_Directory.pdf">ವೀಕ್ಷಣೆ</a></td>
            </tr>
            <tr>
                <td>4</td>
                <td>ಸಾರ್ವತ್ರಿಕ ರಜೆಗಳ ಪಟ್ಟಿ 2024</td>
                <td>01-01-2024</td>
                <td>ಕನ್ನಡ</td>
                <td><a href="/docs/HOLIDAYSLIST2024.pdf">Download</a></td>
            </tr>
        </tbody>
    </table>
    <div>
        <p>Standalone Guideline: <a href="/docs/standalone_guide.pdf">Krishi Bhagya Guidelines 2025</a> (Published: 10-02-2025)</p>
    </div>
</body>
</html>
"""


def test_classify_document_type():
    """Verify classification of documents into guidelines, orders, circulars, etc."""
    assert classify_document_type("Scheme Guidelines", "http://example.com/a.pdf") == "guideline"
    assert classify_document_type("ಯೋಜನೆ ಮಾರ್ಗಸೂಚಿ", "http://example.com/b.pdf") == "guideline"
    assert classify_document_type("ಸರ್ಕಾರಿ ಆದೇಶಗಳು", "http://example.com/c.pdf") == "order"
    assert classify_document_type("Department G.O.", "http://example.com/d.pdf") == "order"
    assert classify_document_type("ಸುತ್ತೋಲೆ", "http://example.com/e.pdf") == "circular"
    assert classify_document_type("ಅಧಿಸೂಚನೆ", "http://example.com/f.pdf") == "notification"
    assert classify_document_type("ಅರ್ಜಿ ನಮೂನೆ", "http://example.com/form.pdf") == "application_form"
    assert classify_document_type("General Report", "http://example.com/rep.pdf") == "other"


def test_is_scheme_document_filtering():
    """Verify that administrative files like holiday lists and telephone directories are filtered out."""
    # Scheme documents
    assert is_scheme_document("ಮುಖ್ಯಮಂತ್ರಿ ರೈತ ವಿದ್ಯಾನಿಧಿ", "http://example.com/scholarship.pdf") is True
    assert is_scheme_document("PM KISAN Guidelines", "http://example.com/pmkisan.pdf") is True

    # Administrative noise (should be False)
    assert is_scheme_document("ಸಾರ್ವತ್ರಿಕ ರಜೆಗಳು", "http://example.com/HOLIDAYSLIST.pdf") is False
    assert is_scheme_document("ಜಿಲ್ಲಾ ಕಛೇರಿ", "http://example.com/CUG.pdf") is False
    assert is_scheme_document("Tender Notification", "http://example.com/tender123.pdf") is False


def test_extract_date_from_text():
    """Verify regex extraction of standard Indian/Govt date formats."""
    assert extract_date_from_text("Published on 07-08-2021 by Govt") == "07-08-2021"
    assert extract_date_from_text("Date: 15/05/2023") == "15/05/2023"
    assert extract_date_from_text("Year 2026-01-29") == "2026-01-29"
    assert extract_date_from_text("No date here") is None


def test_extract_documents_from_html_table():
    """Verify table row title association and date extraction when link text is generic 'ವೀಕ್ಷಣೆ' / 'View'."""
    base_url = "https://raitamitra.karnataka.gov.in/portal"
    docs = extract_documents_from_html(SAMPLE_TABLE_HTML, base_url, scheme_name="Agriculture Schemes")

    assert len(docs) == 5

    # 1. First row: CMScholarship
    doc1 = next(d for d in docs if "cmscholarship.pdf" in d["document_url"])
    # The title should NOT be the generic 'ವೀಕ್ಷಣೆ', but the subject from the row:
    assert "ಮುಖ್ಯಮಂತ್ರಿ ರೈತ ವಿದ್ಯಾನಿಧಿ ಕಾರ್ಯಕ್ರಮದ ಮಾರ್ಗಸೂಚಿ" in doc1["title"]
    assert doc1["published_date"] == "07-08-2021"
    assert doc1["document_type"] == "guideline"
    assert doc1["is_scheme_document"] is True

    # 2. Second row: PM-KISAN
    doc2 = next(d for d in docs if "PM-KISAN_Guidelines.pdf" in d["document_url"])
    assert "PM-KISAN Scheme Guidelines Final Order" in doc2["title"]
    assert doc2["published_date"] == "15/05/2023"
    assert doc2["is_scheme_document"] is True

    # 3. Third row: CUG Directory (administrative)
    doc3 = next(d for d in docs if "CUG_Directory.pdf" in d["document_url"])
    assert doc3["is_scheme_document"] is False

    # 4. Fourth row: Holiday List (administrative)
    doc4 = next(d for d in docs if "HOLIDAYSLIST2024.pdf" in d["document_url"])
    assert doc4["is_scheme_document"] is False

    # 5. Standalone link outside table
    doc5 = next(d for d in docs if "standalone_guide.pdf" in d["document_url"])
    assert "Krishi Bhagya Guidelines 2025" in doc5["title"]
    assert doc5["published_date"] == "10-02-2025"


def test_discover_documents_from_page_with_mock():
    """Verify discover_documents_from_page returns only scheme documents when scheme_only=True."""
    with patch("app.document_discovery.fetch_html", return_value=SAMPLE_TABLE_HTML):
        scheme_docs = discover_documents_from_page(
            "https://raitamitra.karnataka.gov.in/orders",
            scheme_name="Test Scheme",
            scheme_only=True,
        )

        # Out of 5 total PDFs, exactly 3 are genuine scheme documents (2 from table + 1 standalone)
        assert len(scheme_docs) == 3
        assert not any("HOLIDAYSLIST" in d["document_url"] for d in scheme_docs)
        assert not any("CUG_Directory" in d["document_url"] for d in scheme_docs)

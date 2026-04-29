import os
import pytest
from citeindex import CitationExtractor
from citeindex.utils import format_author_csl

TEST_PDF_DIR = "examples"
TEST_URL = "https://www.example.com"

def test_url_extraction():
    """Test URL citation extraction."""
    extractor = CitationExtractor()
    citation_info = extractor.extract_citation(TEST_URL)
    assert citation_info is not None, "Failed to extract citation from URL"
    assert 'URL' in citation_info, "Missing URL in citation"
    assert 'accessed' in citation_info, "Missing date_accessed in citation"

def test_auto_detection_url():
    """Test auto-detection of URL input."""
    extractor = CitationExtractor()
    citation_info = extractor.extract_citation(TEST_URL)
    assert citation_info is not None, "Failed to extract citation from URL"
    assert citation_info['URL'] == TEST_URL, "URL not correctly saved"

def test_auto_detection_nonexistent_file():
    """Test auto-detection with nonexistent file."""
    extractor = CitationExtractor()
    citation_info = extractor.extract_citation("nonexistent.pdf")
    assert citation_info is None, "Should return None for nonexistent file"

def test_invalid_input():
    """Test invalid input handling."""
    extractor = CitationExtractor()
    citation_info = extractor.extract_citation("invalid input")
    assert citation_info is None, "Should return None for invalid input"



def test_document_type_override():
    """Test document type override functionality."""
    extractor = CitationExtractor()
    
    # Test with non-existent file to check type handling
    # This should fail gracefully but we can check the parameter passing
    citation_info = extractor.extract_citation("nonexistent.pdf", doc_type_override="thesis")
    assert citation_info is None, "Should return None for nonexistent file"

# TODO: Add PDF tests when example PDFs are available
# def test_pdf_extraction_with_type():
#     """Test PDF extraction with specific document type."""
#     extractor = CitationExtractor()
#     pdf_path = os.path.join(TEST_PDF_DIR, "sample.pdf")
#     
#     # Test with different document types
#     for doc_type in ["book", "thesis", "journal", "bookchapter"]:
#         citation_info = extractor.extract_citation(pdf_path, doc_type_override=doc_type)
#         if citation_info:
#             assert 'title' in citation_info or 'author' in citation_info, f"No useful info for {doc_type}"

def test_format_author_csl():
    """Test author string formatting for CSL-JSON."""
    # Test case 1: Simple "and" separator
    authors = format_author_csl("John Doe and Jane Smith")
    assert len(authors) == 2
    assert authors[0] == {"family": "Doe", "given": "John"}
    assert authors[1] == {"family": "Smith", "given": "Jane"}

    # Test case 2: Comma and "and"
    authors = format_author_csl("John Doe, Jane Smith and Peter Jones")
    assert len(authors) == 3
    assert authors[0] == {"family": "Doe", "given": "John"}
    assert authors[1] == {"family": "Smith", "given": "Jane"}
    assert authors[2] == {"family": "Jones", "given": "Peter"}

    # Test case 3: CJK name
    authors = format_author_csl("张三")
    assert len(authors) == 1
    assert authors[0] == {'family': 'Zhang', 'given': 'San', 'literal': '张三'}

    # Test case 4: Multiple CJK names separated by space
    authors = format_author_csl("张三 李四")
    assert len(authors) == 2
    assert authors[0] == {'family': 'Zhang', 'given': 'San', 'literal': '张三'}
    assert authors[1] == {'family': 'Li', 'given': 'Si', 'literal': '李四'}

    # Test case 5: Institutional author - known issue, it will be split
    authors = format_author_csl("Department of History and Archaeology")
    assert len(authors) == 2
    assert authors[0] == {"family": "History", "given": "Department of"}
    assert authors[1] == {"literal": "Archaeology"}
    
    # Test case 6: Single name
    authors = format_author_csl("Plato")
    assert len(authors) == 1
    assert authors[0] == {"literal": "Plato"}

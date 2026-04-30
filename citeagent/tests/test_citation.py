import pytest
from citeindex.utils import format_author_csl

# NOTE: CitationExtractor tests removed — CitationExtractor was in the deleted
# citeindex.main module and is now available via the external citeindex package
# as CiteIndexIngestionOrchestrator. The old CitationExtractor API no longer exists.


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
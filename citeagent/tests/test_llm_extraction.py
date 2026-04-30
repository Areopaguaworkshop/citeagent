import pytest
from citeindex.utils import to_csl_json

# NOTE: LLM extraction tests that used CitationExtractor from citeindex.main
# have been removed — CitationExtractor was in the deleted citeindex.main module.
# The CiteIndexIngestionOrchestrator (from the external citeindex package)
# provides a different API. When LLM extraction tests are needed, they should
# be written against the external citeindex package directly.


def test_to_csl_json_basic():
    """Test basic CSL-JSON conversion utility."""
    result = to_csl_json({"title": "Test Title", "URL": "https://example.com"}, "webpage")
    assert result is not None
    assert result.get("title") == "Test Title"
    assert result.get("type") == "webpage"
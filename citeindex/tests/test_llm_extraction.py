import pytest
from citeindex.main import CitationExtractor
from citeindex.utils import to_csl_json

@pytest.mark.parametrize("url, expected_author, expected_date", [
    (
        "https://www.gcdfl.org/2025/02/28/pino-tikhon-Bible-Church-Fathers/",
        {
            "family": "Tikhon",
            "given": "Pino",
            "suffix": "博士"
        },
        "2025-02-28"
    ),
    (
        "https://www.gcdfl.org/2025/05/09/Maximos-Problem-of-Thoughts/",
        {
            "family": "Maximos",
            "suffix": "神父"
        },
        "2025-05-09"
    ),
])
def test_llm_refinement(url, expected_author, expected_date):
    extractor = CitationExtractor()
    result = extractor._extract_from_text_url(url)
    csl_result = to_csl_json(result, "webpage")

    assert csl_result is not None
    
    author = csl_result.get("author")[0]
    assert author.get("family") == expected_author.get("family")
    if "given" in expected_author:
        assert author.get("given") == expected_author.get("given")
    assert author.get("suffix") == expected_author.get("suffix")
    
    issued_date_parts = csl_result.get("issued", {}).get("date-parts", [[]])[0]
    issued_date_str = f"{issued_date_parts[0]}-{issued_date_parts[1]:02d}-{issued_date_parts[2]:02d}"
    assert issued_date_str == expected_date

import requests
import logging
from typing import Dict, Optional

from .model import CitationLLM


def search_for_missing_info(
    title: str,
    author: str,
    llm: CitationLLM,
    doc_type: Optional[str] = None,
    year: Optional[int] = None,
    publisher: Optional[str] = None,
    page: Optional[str] = None,
) -> Optional[Dict]:
    """
    Search for missing citation information using the local perpexica API and parse the result.

    Args:
        title: The title of the document.
        author: The author of the document.
        llm: An instance of the CitationLLM to parse the search response.
        doc_type: The CSL type of the document (e.g., 'article-journal', 'book').
        year: The publication year.
        publisher: The publisher of the document.
        page: The page number or page range of the document.

    Returns:
        A dictionary with the found citation information or None if an error occurs.
    """
    if not title or not author:
        logging.warning("Title or author is missing, cannot perform search.")
        return None

    search_url = "http://localhost:3000/api/search"

    # Build a detailed query with the information we already have
    query_parts = [f"title: '{title}'", f"author: '{author}'"]
    # if doc_type:
    #     query_parts.append(f"type: '{doc_type}'")
    if year:
        query_parts.append(f"year: '{year}'")
    if publisher:
        query_parts.append(f"publisher: '{publisher}'")
    # Do NOT include page in the query to simplify it
    # if page:
    #     query_parts.append(f"page: '{page}'")

    known_info = ", ".join(query_parts)
    query = (
        f"What is the book title and book editor for a publication with the following details: {known_info}. "
    )

    payload = {
        "query": query,
        # webSearch, academicSearch, writingAssistant, wolframAlphaSearch, youtubeSearch, redditSearch
        "focusMode": "webSearch",
        "stream": False,
        "optimizationMode": "speed",
    }

    try:
        logging.info(f"Searching for missing info with query: {query}")
        response = requests.post(search_url, json=payload, timeout=1800)
        response.raise_for_status()

        api_response = response.json()

        if "message" in api_response and api_response["message"]:
            logging.info(
                "Received response from search API. Parsing with LLM...")
            # Use the LLM to parse the natural language response
            parsed_info = llm.parse_search_results(api_response["message"])
            return parsed_info
        else:
            logging.warning(
                "API response did not contain a 'message' field or it was empty."
            )
            return None

    except requests.exceptions.RequestException as e:
        # Handle connection errors, timeouts, etc.
        logging.error(
            f"Could not connect to perpexica API at {
                search_url
            }. Please ensure it is running. Error: {e}"
        )
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during search: {e}")
        return None

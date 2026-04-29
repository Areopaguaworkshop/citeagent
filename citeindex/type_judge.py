import logging
import re
from typing import Tuple, Optional

import fitz  # PyMuPDF


def is_thesis(pdf_path: str) -> bool:
    """
    Check if the document is a thesis by searching for keywords in the text
    of the pages specified by the page range.
    """
    # Keywords to identify a thesis, including common English and Chinese terms
    thesis_keywords = [
        'thesis', 'dissertation', 'phd', 'master',
        '论文', '博士', '硕士'
    ]
    # Compile a single regex for case-insensitive matching
    # \b ensures we match whole words
    keyword_regex = re.compile(r'\b(' + '|'.join(thesis_keywords) + r')\b', re.IGNORECASE)

    try:
        doc = fitz.open(pdf_path)
        # Iterate through all pages of the (subset) PDF
        for page in doc:
            text = page.get_text("text")
            if keyword_regex.search(text):
                logging.info(f"Thesis keyword found on page {page.number + 1}.")
                doc.close()
                return True
        doc.close()
    except Exception as e:
        logging.error(f"Error checking for thesis keywords in {pdf_path}: {e}")
    
    return False


def differentiate_article_or_chapter(pdf_path: str) -> str:
    """
    Differentiates between a journal article and a book chapter using a clear, rule-based hierarchy.
    Defaults to 'journal' if no definitive indicators are found.
    """
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            return "journal"  # Default

        # Analyze text from header, footer, and full first page for efficiency
        text_to_analyze = ""
        for i in range(min(doc.page_count, 5)): # Check first 5 pages
            page = doc[i]
            if i == 0: # Get full text of first page
                text_to_analyze += page.get_text().lower() + "\n"
            else: # Get only header/footer for other pages
                rect = page.rect
                header_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.15)
                footer_rect = fitz.Rect(rect.x0, rect.y1 - rect.height * 0.15, rect.x1, rect.y1)
                text_to_analyze += page.get_text(clip=header_rect).lower() + "\n"
                text_to_analyze += page.get_text(clip=footer_rect).lower() + "\n"

        # --- Rule-Based Judging ---

        # Rule 1: High-confidence journal keywords
        journal_knockout_keywords = [
            'issn', 'journal', 'proceedings', 'zeitschrift', 'revue', 
            '学报', '學報', '期刊', '雑誌', '紀要'  # S. Chinese, T. Chinese, Japanese
        ]
        for keyword in journal_knockout_keywords:
            if keyword in text_to_analyze:
                logging.info(f"Classified as JOURNAL based on knockout keyword: '{keyword}'")
                doc.close()
                return "journal"

        # Rule 2: Journal-specific patterns
        has_volume = re.search(r'\b(volume|vol\.)\b|第\s*\d+\s*卷', text_to_analyze)
        has_issue = re.search(r'\b(issue|no\.)\b|第\s*\d+\s*期', text_to_analyze)
        if has_volume and has_issue:
            logging.info("Classified as JOURNAL based on presence of 'volume'/'issue' or '卷'/'期'")
            doc.close()
            return "journal"

        # Rule 3: High-confidence chapter keywords (immediate decision)
        chapter_knockout_keywords = [
            'edited by', 'editor', 'isbn', 'press', 'herausgeber', 'éditeur', 
            '主编', '主編', '出版社', '編者', 'プレス' # S. Chinese, T. Chinese, Japanese
        ]
        for keyword in chapter_knockout_keywords:
            if keyword in text_to_analyze:
                logging.info(f"Classified as BOOKCHAPTER based on knockout keyword: '{keyword}'")
                doc.close()
                return "bookchapter"

        doc.close()

    except Exception as e:
        logging.error(f"Error during article/chapter differentiation: {e}")
        return "journal" # Default on error

    # Rule 4: Default
    logging.info("No definitive indicators found. Defaulting to JOURNAL.")
    return "journal"


def determine_document_type(pdf_path: str, num_pages: int) -> str:
    """
    Determines the document type by orchestrating checks for thesis, book,
    journal, or book chapter.
    """
    if num_pages >= 70:
        if is_thesis(pdf_path):
            return "thesis"
        else:
            return "book"
    else:
        # For shorter documents, differentiate between journal and chapter
        return differentiate_article_or_chapter(pdf_path)




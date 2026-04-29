"""
OCR Text Cleaning Module for Citation Extraction

This module cleans and filters OCR/searchable text before LLM processing.
It removes irrelevant content and focuses on citation-relevant information.
"""

import logging
import re
import fitz  # PyMuPDF
from typing import Dict, List, Optional, Tuple
import numpy as np

# Import existing functions
from .vertical_handler import is_page_blank, get_structure_engine, extract_text_results
from .model import CitationLLM


def get_multilingual_content_keywords() -> Dict[str, List[str]]:
    """Return content page keywords for all supported languages."""
    return {
        'english': ['contents', 'table of contents', 'toc'],
        'french': ['sommaire', 'table des matières', 'matières'],
        'german': ['inhalt', 'inhaltsverzeichnis', 'verzeichnis'],
        'chinese': ['目录', '目次', '內容', '目錄'],
        'japanese': ['目次', 'もくじ', '目録'],
        'russian': ['содержание', 'оглавление', 'содержанiе']
    }


def clean_extracted_text(
    text: str, 
    num_pages: int, 
    text_direction: str, 
    page_range: str, 
    extracted_pages: List[int]
) -> str:
    """
    Main function to clean extracted text based on document characteristics.
    
    Args:
        text: Raw extracted text from OCR/PDF
        num_pages: Total pages in original document  
        text_direction: 'horizontal', 'vertical', or 'auto'
        page_range: The page range that was extracted (e.g., "1-5, -3")
        extracted_pages: List of actual page numbers that were extracted
        
    Returns:
        Cleaned text ready for LLM processing
    """
    logging.info(f"Starting text cleaning for {len(extracted_pages)} pages, direction: {text_direction}")
    
    # Step 1: Filter blank pages and cover pages
    filtered_text = filter_blank_and_cover_pages(text)
    
    # Step 2: Detect content pages if they exist in extracted range
    content_pages = detect_content_pages_in_range(filtered_text, extracted_pages, text_direction)
    
    # Step 3: Apply cleaning based on document size
    if num_pages >= 70:
        # Large documents: Remove content pages and everything after
        cleaned_text = process_large_document_text(filtered_text, content_pages)
    else:
        # Small documents: Keep first page info, headers/footers only for others
        cleaned_text = process_small_document_text(filtered_text, text_direction)
    
    logging.info(f"Text cleaning completed. Original length: {len(text)}, Cleaned length: {len(cleaned_text)}")
    return cleaned_text


def filter_blank_and_cover_pages(text: str) -> str:
    """
    Remove blank pages and cover pages with images.
    
    This function integrates with existing blank page detection.
    """
    # For now, we'll work with text-based filtering
    # TODO: Integrate with existing image-based cover page detection
    
    # Split text by page markers (if they exist)
    pages = split_text_by_pages(text)
    filtered_pages = []
    
    for page_text in pages:
        # Skip very short pages (likely blank or cover-only)
        if len(page_text.strip()) < 50:
            logging.debug(f"Skipping short page (length: {len(page_text.strip())})")
            continue
            
        # Skip pages that are mostly numbers/symbols (cover pages)
        word_count = len(page_text.split())
        non_word_chars = len(re.findall(r'[^a-zA-Z\u4e00-\u9fff\s]', page_text))
        if word_count > 0 and (non_word_chars / len(page_text)) > 0.7:
            logging.debug("Skipping page with mostly non-text content")
            continue
            
        filtered_pages.append(page_text)
    
    return '\n\n'.join(filtered_pages)


def split_text_by_pages(text: str) -> List[str]:
    """
    Split text into individual pages.
    This is a helper function to work with page-based text.
    """
    # Look for common page separators
    page_separators = [
        r'\n\s*\n\s*\n',  # Multiple newlines
        r'\f',             # Form feed
        r'---PAGE---',     # Explicit page marker
        r'Page \d+',       # Page numbers
    ]
    
    for separator in page_separators:
        pages = re.split(separator, text)
        if len(pages) > 1:
            return pages
    
    # If no separators found, treat as single page
    return [text]


# Placeholder for remaining functions - to be implemented in next steps

def detect_content_pages_in_range(text: str, extracted_pages: List[int], text_direction: str) -> List[int]:
    """
    Detect content pages within the extracted page range.
    Look for "Contents" keywords in first line with larger font size.
    """
    keywords = get_multilingual_content_keywords()
    content_pages = []
    
    # Split text into pages
    pages = split_text_by_pages(text)
    
    for i, page_text in enumerate(pages):
        if i >= len(extracted_pages):
            break
            
        # Check first few lines for content keywords
        lines = page_text.strip().split('\n')[:5]
        
        for line_idx, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Check all multilingual keywords
            for lang, keyword_list in keywords.items():
                for keyword in keyword_list:
                    if keyword.lower() in line_lower:
                        # For now, assume it's large font if it's in first line and standalone
                        if line_idx == 0 and len(line.strip().split()) <= 3:
                            content_pages.append(i)
                            logging.info(f"Content page detected: Page {i+1} with keyword '{keyword}'")
                            break
                if content_pages and i in content_pages:
                    break
            if content_pages and i in content_pages:
                break
    
    return content_pages


def process_large_document_text(text: str, content_pages: List[int]) -> str:
    """
    Process text for documents >= 70 pages.
    Remove content pages and everything after them while preserving structure.
    """
    if not content_pages:
        # No content pages found, return original text
        return text
    
    pages = split_text_by_pages(text)
    
    # Find the last content page
    last_content_page = max(content_pages)
    
    # Keep pages before content pages, remove content pages and after
    filtered_pages = []
    for i, page_text in enumerate(pages):
        if i < min(content_pages):
            # Keep pages before first content page
            filtered_pages.append(page_text)
        elif i in content_pages or i > last_content_page:
            # Remove content pages and everything after
            logging.debug(f"Removing page {i+1} (content page or after)")
            continue
    
    logging.info(f"Large document: Kept {len(filtered_pages)} pages, removed {len(pages) - len(filtered_pages)} pages")
    return '\n\n'.join(filtered_pages)


def process_small_document_text(text: str, text_direction: str) -> str:
    """
    Process text for documents < 70 pages.
    Keep first page with citation info, extract only headers/footers from others.
    """
    pages = split_text_by_pages(text)
    
    if not pages:
        return text
    
    processed_pages = []
    
    for i, page_text in enumerate(pages):
        if i == 0:
            # Keep full content of first page (contains citation info)
            processed_pages.append(page_text)
        else:
            # Extract only headers/footers from subsequent pages
            header_footer_text = extract_headers_footers_by_direction(page_text, text_direction)
            if header_footer_text.strip():
                processed_pages.append(header_footer_text)
    
    logging.info(f"Small document: Processed {len(processed_pages)} pages, kept headers/footers for {len(pages)-1} pages")
    return '\n\n'.join(processed_pages)


def extract_headers_footers_by_direction(page_text: str, text_direction: str) -> str:
    """
    Extract header and footer text based on text direction.
    Uses positional fallback method.
    """
    lines = page_text.split('\n')
    if not lines:
        return ""
    
    if text_direction == 'vertical':
        # For vertical text: header on right (end of lines), footer on left (start of lines)
        # Use 10% of content as fallback
        num_chars_per_side = max(1, int(len(page_text) * 0.1))
        
        header_text = []
        footer_text = []
        
        for line in lines:
            if len(line) > 20:  # Only process substantial lines
                header_text.append(line[-num_chars_per_side:])  # Right side
                footer_text.append(line[:num_chars_per_side])   # Left side
        
        return '\n'.join(footer_text + header_text)
    
    else:
        # For horizontal text: top 10% and bottom 10% of lines
        num_lines = len(lines)
        header_lines = max(1, int(num_lines * 0.1))
        
        header_text = lines[:header_lines]
        footer_text = lines[-header_lines:] if num_lines > header_lines else []
        
        return '\n'.join(header_text + footer_text)

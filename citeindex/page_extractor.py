#!/usr/bin/env python3
"""
Page number extraction utility for MinerU output
Extracts page numbers from discarded blocks and maps them to content
"""
import re
import json
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging

class PageNumberExtractor:
    """Extract page numbers from MinerU middle JSON and map to content"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_text_from_lines(self, lines: List) -> List[str]:
        """Extract text content from lines structure"""
        texts = []
        if not lines:
            return texts
        
        for line in lines:
            if isinstance(line, dict):
                # Look for spans structure (most common in MinerU)
                if 'spans' in line and isinstance(line['spans'], list):
                    for span in line['spans']:
                        if isinstance(span, dict) and 'content' in span:
                            texts.append(span['content'])
                        elif isinstance(span, str):
                            texts.append(span)
                # Also check other possible text fields
                elif 'text' in line:
                    texts.append(line['text'])
                elif 'content' in line:
                    texts.append(line['content'])
            elif isinstance(line, str):
                texts.append(line)
        
        return texts
    
    def extract_number_from_text(self, text: str) -> Optional[int]:
        """Extract page numbers using comprehensive patterns with priority order"""
        if not text:
            return None
        
        text = text.strip()
        if not text:
            return None
        
        # Patterns ordered by specificity - most specific first
        patterns = [
            r'第\s*(\d+)\s*[页頁][，,]\s*共\s*\d+\s*[页頁]',  # "第 1 頁，共 20 頁"
            r'[·•∙・\-]\s*(\d+)\s*[·•∙・\-]',               # "·190·" or "•191•" - HIGH PRIORITY
            r'第\s*(\d+)\s*[页頁]',                            # "第1页" or "第 1 頁" 
            r'([1-9]\d*)\s*[页頁]',                           # "1页" or "123 頁"
            r'[页頁]\s*([1-9]\d*)',                           # "页1" or "頁 123"
            r'[pP]age\s+([1-9]\d*)',                         # "Page 123"
            r'[pP]\.?\s*([1-9]\d*)',                         # "p. 123" or "P.123"
            r'([1-9]\d*)ページ',                             # "123ページ"
            r'[\[\(]([1-9]\d*)[\]\)]',                       # "[123]" or "(123)"
            r'^([1-9]\d*)$',                                 # Pure number: "123" - LOWEST PRIORITY
            r'^([ivxlcdmIVXLCDM]+)$',                        # Roman numerals
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = match.group(1)
                    if value.isdigit():
                        num = int(value)
                        if 1 <= num <= 9999:  # Reasonable page number range
                            return num
                    elif re.match(r'^[ivxlcdmIVXLCDM]+$', value, re.IGNORECASE):
                        # Roman numerals - convert to int if needed
                        return self._roman_to_int(value.upper())
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _roman_to_int(self, roman: str) -> Optional[int]:
        """Convert roman numerals to integers"""
        roman_values = {
            'I': 1, 'V': 5, 'X': 10, 'L': 50, 
            'C': 100, 'D': 500, 'M': 1000
        }
        
        total = 0
        prev_value = 0
        
        for char in reversed(roman):
            if char not in roman_values:
                return None
            value = roman_values[char]
            if value < prev_value:
                total -= value
            else:
                total += value
            prev_value = value
        
        return total if total > 0 else None
    
    def find_page_numbers_in_blocks(self, pdf_info: List[Dict]) -> Dict[int, int]:
        """Find page numbers prioritizing continuous sequences across pages"""
        block_types = ['discarded_blocks', 'preproc_blocks', 'para_blocks']
        
        # Try each block type
        for block_type in block_types:
            # Get all possible number candidates for all pages
            all_candidates = self._get_all_candidates(pdf_info, block_type)
            
            if len(all_candidates) >= 2:  # Need at least 2 pages
                # Find the best continuous sequence
                best_sequence = self._find_best_continuous_sequence(all_candidates)
                
                if best_sequence:
                    self.logger.info(f"Found continuous sequence in {block_type}: {best_sequence}")
                    return best_sequence
        
        self.logger.warning("No continuous page number sequence found in any block type")
        return {}
    
    def _get_all_candidates(self, pdf_info: List[Dict], block_type: str) -> Dict[int, List[Tuple[int, str]]]:
        """Get all number candidates for each page with their source text"""
        all_candidates = {}
        
        for page_info in pdf_info:
            page_idx = page_info.get('page_idx', -1)
            blocks = page_info.get(block_type, [])
            
            candidates = []
            
            for block in blocks:
                if isinstance(block, dict) and 'lines' in block:
                    texts = self.extract_text_from_lines(block['lines'])
                    
                    for text in texts:
                        page_num = self.extract_number_from_text(text)
                        if page_num is not None:
                            candidates.append((page_num, text))
            
            if candidates:
                all_candidates[page_idx] = candidates
        
        return all_candidates
    
    def _find_best_continuous_sequence(self, all_candidates: Dict[int, List[Tuple[int, str]]]) -> Dict[int, int]:
        """Find the best continuous sequence from all candidates"""
        if len(all_candidates) < 2:
            return {}
        
        # Generate all possible combinations of candidates
        import itertools
        
        page_indices = sorted(all_candidates.keys())
        candidate_lists = [all_candidates[page_idx] for page_idx in page_indices]
        
        best_sequence = None
        best_score = 0
        
        # Try all combinations
        for combination in itertools.product(*candidate_lists):
            # Extract just the numbers
            sequence = {}
            for i, (page_num, text) in enumerate(combination):
                sequence[page_indices[i]] = page_num
            
            # Score this sequence based on continuity
            score = self._score_sequence_continuity(sequence)
            
            if score > best_score:
                best_score = score
                best_sequence = sequence
        
        return best_sequence if best_sequence else {}
    
    def _score_sequence_continuity(self, sequence: Dict[int, int]) -> float:
        """Score a sequence based on how continuous the numbers are"""
        if len(sequence) < 2:
            return 0
        
        sorted_pages = sorted(sequence.items())
        continuity_score = 0
        total_pairs = 0
        
        for i in range(len(sorted_pages) - 1):
            page_idx1, page_num1 = sorted_pages[i]
            page_idx2, page_num2 = sorted_pages[i + 1]
            
            expected_diff = page_idx2 - page_idx1
            actual_diff = page_num2 - page_num1
            
            # Perfect continuity: actual_diff == expected_diff
            if actual_diff == expected_diff and actual_diff > 0:
                continuity_score += 100  # Perfect match
            elif actual_diff == 1 and expected_diff == 1:
                continuity_score += 100  # Sequential pages
            elif abs(actual_diff - expected_diff) <= 1:
                continuity_score += 50   # Close match
            else:
                continuity_score -= 50   # Poor match
            
            total_pairs += 1
        
        # Average score, bonus for reasonable page numbers
        avg_score = continuity_score / total_pairs if total_pairs > 0 else 0
        
        # Bonus for reasonable page number range
        page_nums = list(sequence.values())
        if all(1 <= num <= 1000 for num in page_nums):
            avg_score += 20
        
        return avg_score
    
    def _extract_from_block_type(self, pdf_info: List[Dict], block_type: str) -> Dict[int, int]:
        """Extract page numbers from specific block type with pattern priority"""
        page_numbers = {}
        
        for page_info in pdf_info:
            page_idx = page_info.get('page_idx', -1)
            blocks = page_info.get(block_type, [])
            
            # Collect all possible page numbers with their pattern priority
            candidates = []
            
            for block in blocks:
                if isinstance(block, dict) and 'lines' in block:
                    texts = self.extract_text_from_lines(block['lines'])
                    
                    for text in texts:
                        page_num = self.extract_number_from_text(text)
                        if page_num is not None:
                            # Determine pattern priority
                            priority = self._get_pattern_priority(text, page_num)
                            candidates.append((page_num, priority, text))
            
            # Select the best candidate based on priority
            if candidates:
                # Sort by priority (lower number = higher priority), then by reasonableness
                candidates.sort(key=lambda x: (x[1], abs(x[0] - 50) if x[0] <= 1000 else 9999))
                page_numbers[page_idx] = candidates[0][0]
        
        return page_numbers
    
    def _get_pattern_priority(self, text: str, page_num: int) -> int:
        """Get pattern priority - lower number means higher priority"""
        import re
        
        # High priority patterns (lower numbers)
        high_priority_patterns = [
            r'第\s*\d+\s*[页頁][，,]\s*共\s*\d+\s*[页頁]',  # "第 1 頁，共 20 頁" - Priority 1
            r'[·•∙・\-]\s*\d+\s*[·•∙・\-]',                   # "·190·" or "•191•" - Priority 2
            r'第\s*\d+\s*[页頁]',                              # "第1页" - Priority 3
            r'\d+\s*[页頁]',                                   # "1页" - Priority 4
            r'[页頁]\s*\d+',                                   # "页1" - Priority 5
            r'[pP]age\s+\d+',                                 # "Page 123" - Priority 6
            r'[pP]\.?\s*\d+',                                 # "p. 123" - Priority 7
            r'\d+ページ',                                       # "123ページ" - Priority 8
            r'[\[\(]\d+[\]\)]',                               # "[123]" - Priority 9
        ]
        
        for priority, pattern in enumerate(high_priority_patterns, 1):
            if re.search(pattern, text, re.IGNORECASE):
                return priority
        
        # Low priority for pure numbers
        if re.match(r'^\d+$', text.strip()):
            return 100  # Very low priority
        
        # Default priority
        return 50
    
    def _validate_sequence(self, page_numbers: Dict[int, int]) -> bool:
        """Validate that page numbers form a reasonable sequence"""
        if len(page_numbers) < 2:
            return False
        
        # Sort by page index
        sorted_pages = sorted(page_numbers.items())
        
        # Check if page numbers increase consistently with page indices
        prev_page_idx, prev_page_num = sorted_pages[0]
        
        for page_idx, page_num in sorted_pages[1:]:
            expected_page_num = prev_page_num + (page_idx - prev_page_idx)
            if page_num != expected_page_num:
                # Allow some tolerance for missing pages
                if abs(page_num - expected_page_num) > 2:
                    return False
            prev_page_idx, prev_page_num = page_idx, page_num
        
        return True
    
    def complete_sequence(self, page_numbers: Dict[int, int], total_pages: int) -> Dict[int, int]:
        """Complete missing page numbers in sequence"""
        if not page_numbers:
            return {}
        
        # Find the pattern from existing page numbers
        sorted_pages = sorted(page_numbers.items())
        if len(sorted_pages) < 2:
            # If only one page number, assume sequence starts from there
            page_idx, page_num = sorted_pages[0]
            complete_numbers = {}
            for i in range(total_pages):
                complete_numbers[i] = page_num + (i - page_idx)
            return complete_numbers
        
        # Use first two points to determine the pattern
        page_idx_1, page_num_1 = sorted_pages[0]
        page_idx_2, page_num_2 = sorted_pages[1]
        
        # Calculate offset: page_num = page_idx + offset
        offset = page_num_1 - page_idx_1
        
        # Generate complete sequence
        complete_numbers = {}
        for i in range(total_pages):
            complete_numbers[i] = i + offset + 1  # +1 because pages usually start from 1
        
        return complete_numbers
    
    def extract_page_content(self, pdf_info: List[Dict], page_numbers: Dict[int, int]) -> Dict[int, Dict]:
        """Extract content for each page with page numbers"""
        page_content = {}
        
        for page_info in pdf_info:
            page_idx = page_info.get('page_idx', -1)
            page_num = page_numbers.get(page_idx)
            
            if page_num is None:
                continue
            
            # Extract content from para_blocks (main content)
            content_blocks = []
            para_blocks = page_info.get('para_blocks', [])
            
            for block in para_blocks:
                if isinstance(block, dict):
                    block_type = block.get('type', 'unknown')
                    if 'lines' in block:
                        texts = self.extract_text_from_lines(block['lines'])
                        if texts:
                            content_text = '\n'.join(texts)
                            content_blocks.append({
                                'type': block_type,
                                'content': content_text,
                                'bbox': block.get('bbox', [])
                            })
                    elif 'blocks' in block and block_type == 'table':
                        # Handle table blocks specially
                        content_blocks.append({
                            'type': 'table',
                            'content': '[TABLE]',  # Placeholder - could be expanded
                            'bbox': block.get('bbox', [])
                        })
            
            page_content[page_idx] = {
                'page_number': page_num,
                'content_blocks': content_blocks
            }
        
        return page_content


    def extract_from_csl_json(self, csl_json_path: Path, total_pdf_pages: int) -> Dict[int, int]:
        """Extract page numbers from CSL JSON page field"""
        try:
            with open(csl_json_path, 'r', encoding='utf-8') as f:
                csl_data = json.load(f)
            
            # Look for page field
            page_field = csl_data.get('page')
            if not page_field:
                self.logger.info("No 'page' field found in CSL JSON")
                return {}
            
            # Parse page range (e.g., "190-197", "45-67")
            page_range = self._parse_page_range(page_field)
            if not page_range:
                self.logger.warning(f"Could not parse page range: {page_field}")
                return {}
            
            start_page, end_page = page_range
            expected_pages = end_page - start_page + 1
            
            # Validate against actual PDF pages
            if expected_pages != total_pdf_pages:
                self.logger.warning(f"CSL page count ({expected_pages}) doesn't match PDF pages ({total_pdf_pages})")
                # Still try to use it, but adjust
                if expected_pages > total_pdf_pages:
                    # Use only the first part of the range
                    end_page = start_page + total_pdf_pages - 1
                
            # Map PDF page indices to actual page numbers
            page_numbers = {}
            for i in range(total_pdf_pages):
                if i < (end_page - start_page + 1):
                    page_numbers[i] = start_page + i
            
            self.logger.info(f"Mapped {len(page_numbers)} pages from CSL range {start_page}-{end_page}")
            return page_numbers
            
        except Exception as e:
            self.logger.error(f"Error extracting from CSL JSON: {e}")
            return {}
    
    def _parse_page_range(self, page_field: str) -> Optional[Tuple[int, int]]:
        """Parse page range from CSL JSON page field"""
        import re
        
        # Common patterns: "190-197", "45–67", "123 - 145"
        patterns = [
            r'^(\d+)\s*[-–—]\s*(\d+)$',  # "190-197" or "190–197"
            r'^(\d+)$',                   # Single page "190"
            r'^pp?\.\s*(\d+)\s*[-–—]\s*(\d+)$',  # "pp. 190-197"
            r'^(\d+)\s*ff?\.?$',         # "190f" or "190ff"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, page_field.strip(), re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    start_page = int(match.group(1))
                    end_page = int(match.group(2))
                    return (start_page, end_page)
                elif len(match.groups()) == 1:
                    page_num = int(match.group(1))
                    return (page_num, page_num)  # Single page
        
        return None


def extract_page_structure(middle_json_path: Path, csl_json_path: Optional[Path] = None) -> Tuple[Dict[int, int], Dict[int, Dict]]:
    """
    Main function to extract page structure, prioritizing CSL JSON page numbers
    
    Args:
        middle_json_path: Path to MinerU middle JSON
        csl_json_path: Optional path to CSL JSON file with page numbers
    
    Returns:
        Tuple of (page_numbers_dict, page_content_dict)
    """
    extractor = PageNumberExtractor()
    
    try:
        with open(middle_json_path, 'r', encoding='utf-8') as f:
            middle_data = json.load(f)
        
        pdf_info = middle_data.get('pdf_info', [])
        if not pdf_info:
            logging.warning("No pdf_info found in middle JSON")
            return {}, {}
        
        # Try to get page numbers from CSL JSON first
        page_numbers = {}
        if csl_json_path and csl_json_path.exists():
            page_numbers = extractor.extract_from_csl_json(csl_json_path, len(pdf_info))
            if page_numbers:
                logging.info(f"Using page numbers from CSL JSON: {len(page_numbers)} pages")
        
        # Fallback to header/footer extraction if no CSL JSON page info
        if not page_numbers:
            logging.info("No page numbers in CSL JSON, extracting from headers/footers")
            page_numbers = extractor.find_page_numbers_in_blocks(pdf_info)
            
            # Complete the sequence if needed
            if page_numbers:
                page_numbers = extractor.complete_sequence(page_numbers, len(pdf_info))
        
        # Extract content
        page_content = extractor.extract_page_content(pdf_info, page_numbers)
        
        return page_numbers, page_content
        
    except Exception as e:
        logging.error(f"Error extracting page structure: {e}")
        return {}, {}
    
    def extract_from_csl_json(self, csl_json_path: Path, total_pdf_pages: int) -> Dict[int, int]:
        """Extract page numbers from CSL JSON page field"""
        try:
            with open(csl_json_path, 'r', encoding='utf-8') as f:
                csl_data = json.load(f)
            
            # Look for page field
            page_field = csl_data.get('page')
            if not page_field:
                logging.info("No 'page' field found in CSL JSON")
                return {}
            
            # Parse page range (e.g., "190-197", "45-67")
            page_range = self._parse_page_range(page_field)
            if not page_range:
                logging.warning(f"Could not parse page range: {page_field}")
                return {}
            
            start_page, end_page = page_range
            expected_pages = end_page - start_page + 1
            
            # Validate against actual PDF pages
            if expected_pages != total_pdf_pages:
                logging.warning(f"CSL page count ({expected_pages}) doesn't match PDF pages ({total_pdf_pages})")
                # Still try to use it, but adjust
                if expected_pages > total_pdf_pages:
                    # Use only the first part of the range
                    end_page = start_page + total_pdf_pages - 1
                
            # Map PDF page indices to actual page numbers
            page_numbers = {}
            for i in range(total_pdf_pages):
                if i < (end_page - start_page + 1):
                    page_numbers[i] = start_page + i
            
            logging.info(f"Mapped {len(page_numbers)} pages from CSL range {start_page}-{end_page}")
            return page_numbers
            
        except Exception as e:
            logging.error(f"Error extracting from CSL JSON: {e}")
            return {}
    
    def _parse_page_range(self, page_field: str) -> Optional[Tuple[int, int]]:
        """Parse page range from CSL JSON page field"""
        import re
        
        # Common patterns: "190-197", "45–67", "123 - 145"
        patterns = [
            r'^(\d+)\s*[-–—]\s*(\d+)$',  # "190-197" or "190–197"
            r'^(\d+)$',                   # Single page "190"
            r'^pp?\.\s*(\d+)\s*[-–—]\s*(\d+)$',  # "pp. 190-197"
            r'^(\d+)\s*ff?\.?$',         # "190f" or "190ff"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, page_field.strip(), re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    start_page = int(match.group(1))
                    end_page = int(match.group(2))
                    return (start_page, end_page)
                elif len(match.groups()) == 1:
                    page_num = int(match.group(1))
                    return (page_num, page_num)  # Single page
        
        return None

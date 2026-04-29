import dspy
import logging
from typing import Dict, Optional, List
import fitz  # PyMuPDF
from .llm import get_llm_model

import re

class ImprovedPageNumberExtractor:
    """Enhanced page number extraction with pattern recognition and position consistency"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def extract_number_from_text(self, text: str) -> Optional[int]:
        """Extract page numbers using comprehensive patterns with priority order"""
        if not text:
            return None
        
        text = text.strip()
        if not text:
            return None
        
        # First check for vertical number format like "1\n4\n1" = 141
        vertical_match = self._extract_vertical_number(text)
        if vertical_match is not None:
            return vertical_match
        
        # Patterns ordered by priority - most specific first
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
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_vertical_number(self, text: str) -> Optional[int]:
        """Extract vertically formatted page numbers like '1\n4\n1' = 141"""
        lines = text.strip().split('\n')
        
        # Filter out empty lines and keep only single digits
        digits = []
        for line in lines:
            line = line.strip()
            if line.isdigit() and len(line) == 1:
                digits.append(line)
        
        # Check if we have 3 digits that could form a valid page number
        if len(digits) == 3:
            try:
                # Check for special academic paper format where middle and last digits are constant
                # e.g., 1,4,1 -> 141; 2,4,1 -> 142; 3,4,1 -> 143, etc.
                if digits[1] == '4' and digits[2] == '1':  # Pattern like X41 where X is the variable digit
                    # This represents 14X format (141, 142, 143, etc.)
                    base_num = 140 + int(digits[0])  # 140 + 1 = 141, 140 + 2 = 142, etc.
                    if 100 <= base_num <= 999:
                        self.logger.debug(f"Vertical academic format detected: {digits} -> {base_num}")
                        return base_num
                elif digits[1] == '5' and digits[2] == '1':  # Pattern like X51 where X is the variable digit  
                    # This represents 15X format (151, 152, 153, etc.)
                    base_num = 150 + int(digits[0])  # 150 + 1 = 151, 150 + 2 = 152, etc.
                    if 100 <= base_num <= 999:
                        self.logger.debug(f"Vertical academic format detected: {digits} -> {base_num}")
                        return base_num
                else:
                    # Standard vertical format - combine digits directly
                    combined = ''.join(digits)
                    page_num = int(combined)
                    
                    # Check if it's in a reasonable range (100-999 for academic papers)
                    if 100 <= page_num <= 999:
                        self.logger.debug(f"Standard vertical format detected: {digits} -> {page_num}")
                        return page_num
            except ValueError:
                pass
        
        return None
    

    def extract_total_pages_from_text(self, text: str) -> Optional[int]:
        """Extract total page count from patterns like '第 X 頁，共 Y 頁'"""
        if not text:
            return None
        
        # Pattern to extract total pages: "共 20 頁" 
        total_pattern = r'共\s*(\d+)\s*[页頁]'
        match = re.search(total_pattern, text, re.IGNORECASE)
        if match:
            try:
                total = int(match.group(1))
                if 1 <= total <= 9999:  # Reasonable range
                    return total
            except (ValueError, IndexError):
                pass
        
        return None

    def extract_text_by_position(self, page, position_type="footer"):
        """Extract text from specific positions (header/footer)"""
        page_rect = page.rect
        page_height = page_rect.height
        page_width = page_rect.width
        
        # Define position areas
        if position_type == "footer":
            # Bottom 10% of page
            search_rect = fitz.Rect(0, page_height * 0.9, page_width, page_height)
        elif position_type == "header":
            # Top 10% of page
            search_rect = fitz.Rect(0, 0, page_width, page_height * 0.1)
        else:
            # Full page
            search_rect = page_rect
        
        # Get text blocks in the specified area
        text_blocks = page.get_text("dict", clip=search_rect)["blocks"]
        
        position_texts = []
        for block in text_blocks:
            if "lines" in block:
                # First, try to extract the complete block as vertical text
                block_lines = []
                block_bbox = None
                
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    if line_text.strip():
                        block_lines.append(line_text.strip())
                        # Use the first line's bbox for the block position
                        if block_bbox is None:
                            block_bbox = line["bbox"]
                
                # If we have multiple lines in this block, combine them for vertical detection
                if len(block_lines) > 1:
                    combined_text = "\n".join(block_lines)
                    
                    # Calculate relative position using the first line's bbox
                    if block_bbox:
                        center_x = (block_bbox[0] + block_bbox[2]) / 2
                        if center_x < page_width * 0.33:
                            position = "left"
                        elif center_x > page_width * 0.67:
                            position = "right"
                        else:
                            position = "center"
                        
                        position_texts.append({
                            "text": combined_text,
                            "position": position,
                            "bbox": block_bbox
                        })
                
                # Also add individual lines for compatibility with other patterns
                for line in block["lines"]:
                    line_text = ""
                    for span in line["spans"]:
                        line_text += span["text"]
                    if line_text.strip():
                        # Calculate relative position (left, center, right)
                        bbox = line["bbox"]
                        center_x = (bbox[0] + bbox[2]) / 2
                        if center_x < page_width * 0.33:
                            position = "left"
                        elif center_x > page_width * 0.67:
                            position = "right"
                        else:
                            position = "center"
                        
                        position_texts.append({
                            "text": line_text.strip(),
                            "position": position,
                            "bbox": bbox
                        })
        
        return position_texts
    
    def find_continuous_page_sequence(self, pdf_path: str, max_pages: int = 5) -> Dict[int, int]:
        """Find continuous page number sequences with consistent positioning"""
        doc = fitz.open(pdf_path)
        total_pages = min(doc.page_count, max_pages)
        
        # Collect all potential page numbers from each page
        page_candidates = {}
        
        for page_idx in range(total_pages):
            page = doc[page_idx]
            candidates = []
            
            # Check both header and footer
            for position_type in ["footer", "header"]:
                position_texts = self.extract_text_by_position(page, position_type)
                
                for text_info in position_texts:
                    page_num = self.extract_number_from_text(text_info["text"])
                    if page_num is not None:
                        candidates.append({
                            "page_num": page_num,
                            "position_type": position_type,
                            "position": text_info["position"],
                            "text": text_info["text"],
                            "bbox": text_info["bbox"]
                        })
            
            page_candidates[page_idx] = candidates
        
        doc.close()
        
        # Find the best continuous sequence with consistent positioning
        best_sequence = self._find_best_sequence(page_candidates)
        
        return best_sequence
    

    def find_continuous_page_sequence_with_range(self, pdf_path: str, page_range: str, total_pdf_pages: int) -> Dict[int, int]:
        """
        Find continuous page number sequences respecting the page_range structure.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Page range string (e.g., "1-5, -3")
            total_pdf_pages: Total number of pages in the PDF
            
        Returns:
            Dict mapping PDF page indices to actual page numbers
        """
        from .utils import parse_page_range
        
        doc = fitz.open(pdf_path)
        
        # Parse the page range into actual page indices
        pages_to_analyze = parse_page_range(page_range, total_pdf_pages)
        if not pages_to_analyze:
            self.logger.warning(f"Invalid page range: {page_range}")
            doc.close()
            return {}
        
        # Separate first part and last part based on the original page range
        first_part_pages = []
        last_part_pages = []
        
        # Parse the page_range string to identify first and last parts
        parts = [part.strip() for part in page_range.split(',') if part.strip()]
        
        for part in parts:
            if part.startswith('-'):
                # Last N pages
                try:
                    last_n = abs(int(part))
                    last_part_indices = list(range(max(0, total_pdf_pages - last_n), total_pdf_pages))
                    # Convert to 1-based and filter with pages_to_analyze
                    last_part_pages.extend([i for i in last_part_indices if (i + 1) in pages_to_analyze])
                except ValueError:
                    continue
            elif '-' in part and not part.startswith('-'):
                # Range like "1-5"
                try:
                    start, end = map(int, part.split('-', 1))
                    range_indices = list(range(start - 1, min(end, total_pdf_pages)))  # Convert to 0-based
                    first_part_pages.extend([i for i in range_indices if (i + 1) in pages_to_analyze])
                except ValueError:
                    continue
            else:
                # Single page
                try:
                    page_idx = int(part) - 1  # Convert to 0-based
                    if 0 <= page_idx < total_pdf_pages and (page_idx + 1) in pages_to_analyze:
                        first_part_pages.append(page_idx)
                except ValueError:
                    continue
        
        # Remove duplicates and sort
        first_part_pages = sorted(set(first_part_pages))
        last_part_pages = sorted(set(last_part_pages))
        
        self.logger.info(f"First part pages (0-based): {first_part_pages}")
        self.logger.info(f"Last part pages (0-based): {last_part_pages}")
        
        # Extract page number candidates for each part
        first_part_sequence = self._extract_sequence_from_pages(doc, first_part_pages) if first_part_pages else {}
        last_part_sequence = self._extract_sequence_from_pages(doc, last_part_pages) if last_part_pages else {}
        
        doc.close()
        
        # Combine sequences using smart logic
        final_sequence = self._smart_combine_sequences(
            first_part_sequence, last_part_sequence, 
            first_part_pages, last_part_pages, total_pdf_pages
        )
        
        return final_sequence
    
    def _extract_sequence_from_pages(self, doc, page_indices: List[int]) -> Dict[int, int]:
        """Extract continuous page number sequence from specific PDF pages with footer priority"""
        if not page_indices:
            return {}
        
        # Try footer first, then header if footer doesn't work
        for position_type in ["footer", "header"]:
            self.logger.debug(f"Trying position_type: {position_type}")
            page_candidates = self._collect_candidates_by_position(doc, page_indices, position_type)
            
            if page_candidates:
                sequence = self._find_best_sequence_for_part(page_candidates, position_type)
                if sequence:
                    self.logger.info(f"Found sequence in {position_type}: {sequence}")
                    return sequence
        
        self.logger.warning("No valid sequence found in footer or header")
        return {}
    
    def _collect_candidates_by_position(self, doc, page_indices: List[int], position_type: str) -> Dict[int, List[Dict]]:
        """Collect page number candidates for a specific position type"""
        page_candidates = {}
        
        for page_idx in page_indices:
            if page_idx >= doc.page_count:
                continue
                
            page = doc[page_idx]
            candidates = []
            
            position_texts = self.extract_text_by_position(page, position_type)
            
            for text_info in position_texts:
                page_num = self.extract_number_from_text(text_info["text"])
                if page_num is not None:
                    candidates.append({
                        "page_num": page_num,
                        "position_type": position_type,
                        "position": text_info["position"],
                        "text": text_info["text"],
                        "bbox": text_info["bbox"]
                    })
                    self.logger.debug(f"Page {page_idx}: found page_num {page_num} in {position_type} {text_info['position']}: '{text_info['text']}'")
            
            if candidates:
                page_candidates[page_idx] = candidates
        
        return page_candidates
    
    def _find_best_sequence_for_part(self, page_candidates: Dict[int, List[Dict]], position_type: str) -> Dict[int, int]:
        """Find the best continuous sequence for a part (first or last) with enhanced debugging"""
        if len(page_candidates) < 1:
            return {}
        
        import itertools
        
        # Generate all possible combinations
        page_indices = sorted(page_candidates.keys())
        candidate_lists = [page_candidates[page_idx] for page_idx in page_indices]
        
        # Filter out empty candidate lists
        non_empty_indices = []
        non_empty_lists = []
        for i, candidates in enumerate(candidate_lists):
            if candidates:
                non_empty_indices.append(page_indices[i])
                non_empty_lists.append(candidates)
        
        if len(non_empty_lists) < 1:
            return {}
        
        best_sequence = None
        best_score = -1
        best_combination = None
        
        self.logger.debug(f"Testing {len(list(itertools.product(*non_empty_lists)))} combinations for {position_type}")
        
        for combination in itertools.product(*non_empty_lists):
            # Check position consistency (alternating or center)
            position_consistent, pattern_type = self._check_enhanced_position_consistency(combination)
            if not position_consistent:
                continue
            
            # Check numerical continuity
            sequence = {}
            for i, candidate in enumerate(combination):
                sequence[non_empty_indices[i]] = candidate["page_num"]
            
            # Score based on continuity within this part
            continuity_score = self._score_part_continuity(sequence)
            position_score = self._score_enhanced_position_consistency(combination, pattern_type)
            
            total_score = continuity_score + position_score
            
            self.logger.debug(f"Combination {[c['page_num'] for c in combination]} ({pattern_type}): continuity={continuity_score:.1f}, position={position_score:.1f}, total={total_score:.1f}")
            
            if total_score > best_score:
                best_score = total_score
                best_sequence = sequence
                best_combination = combination
        
        if best_sequence:
            self.logger.info(f"Best sequence in {position_type}: {best_sequence} (score: {best_score:.1f})")
            if best_combination:
                pattern_info = [(c['page_num'], c['position'], c['text']) for c in best_combination]
                self.logger.debug(f"Best pattern: {pattern_info}")
        
        return best_sequence if best_sequence else {}
    
    def _score_part_continuity(self, sequence: Dict[int, int]) -> float:
        """Score continuity within a part (allows single pages)"""
        if len(sequence) < 1:
            return 0
        
        if len(sequence) == 1:
            return 50  # Single page gets modest score
            
        sorted_items = sorted(sequence.items())
        continuity_score = 0
        continuous_pairs = 0
        
        for i in range(len(sorted_items) - 1):
            page_idx1, page_num1 = sorted_items[i]
            page_idx2, page_num2 = sorted_items[i + 1]
            
            expected_diff = page_idx2 - page_idx1
            actual_diff = page_num2 - page_num1
            
            # Perfect continuity: numbers increase by 1 for consecutive pages
            if actual_diff == expected_diff and actual_diff > 0:
                continuity_score += 100
                continuous_pairs += 1
            elif actual_diff == 1:  # Sequential pages
                continuity_score += 90
                continuous_pairs += 1
            elif abs(actual_diff - expected_diff) <= 1:  # Close match
                continuity_score += 50
            else:
                continuity_score -= 30  # Penalty for poor continuity
        
        return continuity_score / (len(sorted_items) - 1) if len(sorted_items) > 1 else continuity_score
    
    def _smart_combine_sequences(
        self, 
        first_sequence: Dict[int, int], 
        last_sequence: Dict[int, int], 
        first_pages: List[int], 
        last_pages: List[int], 
        total_pdf_pages: int
    ) -> Dict[int, int]:
        """Smart combination of first and last part sequences with deduction for missing pages"""
        
        # Case 1: Both sequences found
        if first_sequence and last_sequence:
            combined = self._combine_both_sequences(first_sequence, last_sequence, first_pages, last_pages, total_pdf_pages)
            # Try to deduce missing pages after combination
            return self._deduce_missing_pages(combined, last_pages, total_pdf_pages)
        
        # Case 2: Only first sequence found
        elif first_sequence and not last_sequence:
            return first_sequence
        
        # Case 3: Only last sequence found  
        elif not first_sequence and last_sequence:
            # Try to deduce missing pages even with only last sequence
            return self._deduce_missing_pages(last_sequence, last_pages, total_pdf_pages)
        
        # Case 4: No sequences found
        else:
            self.logger.warning("No continuous sequences found in either part")
            return {}
    
    def _combine_both_sequences(
        self, 
        first_sequence: Dict[int, int], 
        last_sequence: Dict[int, int], 
        first_pages: List[int], 
        last_pages: List[int], 
        total_pdf_pages: int
    ) -> Dict[int, int]:
        """Combine both sequences with smart gap validation"""
        
        # Get the ranges from each sequence
        first_page_nums = sorted(first_sequence.values())
        last_page_nums = sorted(last_sequence.values())
        
        first_start = min(first_page_nums)
        first_end = max(first_page_nums)
        last_start = min(last_page_nums)
        last_end = max(last_page_nums)
        
        # Calculate expected gap based on PDF page positions
        first_last_pdf_page = max(first_pages)  # Last PDF page of first part
        last_first_pdf_page = min(last_pages)   # First PDF page of last part
        
        pdf_gap = last_first_pdf_page - first_last_pdf_page
        actual_gap = last_start - first_end
        
        self.logger.info(f"Gap analysis - PDF gap: {pdf_gap}, Actual gap: {actual_gap}")
        self.logger.info(f"First sequence: {first_start}-{first_end}, Last sequence: {last_start}-{last_end}")
        
        # Smart combine: Check if sequences belong to the same document
        # For academic papers with page gaps, we need more flexible gap analysis
        
        # Calculate the expected page progression based on PDF structure
        first_pdf_pages = sorted([k for k in first_sequence.keys()])
        last_pdf_pages = sorted([k for k in last_sequence.keys()])
        
        # Check if there's a reasonable progression (not necessarily continuous)
        # Allow larger gaps for academic papers that might skip pages
        max_reasonable_gap = max(20, pdf_gap * 10)  # More flexible tolerance
        
        if actual_gap > 0 and actual_gap <= max_reasonable_gap:
            # Create combined sequence
            self.logger.info(f"Smart combined sequences: {first_start} to {last_end} (gap acceptable for academic document)")
            combined = first_sequence.copy()
            combined.update(last_sequence)
            self.logger.debug(f"Combined sequence: {combined}")
            return combined
        elif last_sequence and len(last_sequence) >= len(first_sequence):
            # If last sequence is substantial and first sequence has issues, prefer last
            self.logger.info(f"Using last sequence due to better coverage: {last_start} to {last_end}")
            return last_sequence
        else:
            # Gap too large or negative, return first sequence as fallback
            self.logger.warning(f"Gap not suitable for combination ({actual_gap}), using first sequence")
            return first_sequence

    def _find_best_sequence(self, page_candidates: Dict[int, List[Dict]]) -> Dict[int, int]:
        """Find the best continuous sequence with consistent positioning"""
        if len(page_candidates) < 2:
            return {}
        
        import itertools
        
        # Generate all possible combinations
        page_indices = sorted(page_candidates.keys())
        candidate_lists = [page_candidates[page_idx] for page_idx in page_indices]
        
        # Filter out empty candidate lists
        non_empty_indices = []
        non_empty_lists = []
        for i, candidates in enumerate(candidate_lists):
            if candidates:
                non_empty_indices.append(page_indices[i])
                non_empty_lists.append(candidates)
        
        if len(non_empty_lists) < 2:
            return {}
        
        best_sequence = None
        best_score = -1
        
        for combination in itertools.product(*non_empty_lists):
            # Check position consistency
            if not self._check_position_consistency(combination):
                continue
            
            # Check numerical continuity
            sequence = {}
            for i, candidate in enumerate(combination):
                sequence[non_empty_indices[i]] = candidate["page_num"]
            
            continuity_score = self._score_continuity(sequence)
            position_score = self._score_position_consistency(combination)
            
            total_score = continuity_score + position_score
            
            if total_score > best_score:
                best_score = total_score
                best_sequence = sequence
        
        return best_sequence if best_sequence else {}
    
    def _deduce_missing_pages(self, sequence: Dict[int, int], last_pages: List[int], total_pdf_pages: int) -> Dict[int, int]:
        """Deduce missing page numbers for pages without explicit numbers"""
        if not sequence:
            return sequence
        
        enhanced_sequence = sequence.copy()
        
        # Deduce backwards from the first known page
        sorted_keys = sorted(enhanced_sequence.keys())
        if sorted_keys:
            first_known_pdf_page = sorted_keys[0]
            first_known_page_num = enhanced_sequence[first_known_pdf_page]
            self.logger.debug(f"First known for backward deduction: PDF page {first_known_pdf_page+1} = page number {first_known_page_num}")

            for pdf_page_idx in range(first_known_pdf_page - 1, -1, -1):
                if pdf_page_idx not in enhanced_sequence:
                    deduced_page_num = first_known_page_num - (first_known_pdf_page - pdf_page_idx)
                    enhanced_sequence[pdf_page_idx] = deduced_page_num
                    self.logger.info(f"Deduced backwards: PDF page {pdf_page_idx+1} = page number {deduced_page_num}")

        # If we have pages in last_pages, deduce from the highest known page
        if last_pages:
            # Find the highest PDF page with a known number that's in or before last_pages
            candidates_in_last = [(pdf_idx, page_num) for pdf_idx, page_num in sequence.items() 
                                  if pdf_idx in last_pages or pdf_idx <= max(last_pages)]
            
            if candidates_in_last:
                # Use the latest known page as reference
                last_known_pdf_page = max(candidates_in_last, key=lambda x: x[0])[0]
                last_known_page_num = sequence[last_known_pdf_page]
                
                self.logger.debug(f"Last known: PDF page {last_known_pdf_page+1} = page number {last_known_page_num}")
                
                # Deduce for all pages after the last known page up to the end of last_pages
                max_last_page = max(last_pages)
                
                for pdf_page_idx in range(last_known_pdf_page + 1, max_last_page + 1):
                    if pdf_page_idx < total_pdf_pages and pdf_page_idx not in enhanced_sequence:
                        # Deduce the page number by adding the difference
                        deduced_page_num = last_known_page_num + (pdf_page_idx - last_known_pdf_page)
                        enhanced_sequence[pdf_page_idx] = deduced_page_num
                        self.logger.info(f"Deduced: PDF page {pdf_page_idx+1} = page number {deduced_page_num}")
        
        return enhanced_sequence
    
    def _check_position_consistency(self, combination: List[Dict]) -> bool:
        """Legacy position consistency check for backward compatibility"""
        position_consistent, _ = self._check_enhanced_position_consistency(combination)
        return position_consistent
    
    def _score_position_consistency(self, combination: List[Dict]) -> float:
        """Legacy position scoring for backward compatibility"""
        _, pattern_type = self._check_enhanced_position_consistency(combination)
        return self._score_enhanced_position_consistency(combination, pattern_type)
    
    def _check_enhanced_position_consistency(self, combination: List[Dict]) -> tuple[bool, str]:
        """Check if page numbers appear in consistent patterns (alternating or center)"""
        if len(combination) < 2:
            return True, "single"
        
        positions = [c["position"] for c in combination]
        page_nums = [c["page_num"] for c in combination]
        
        # Check for center pattern first (higher priority for decorative symbols)
        if all(pos == "center" for pos in positions):
            self.logger.debug(f"Center pattern found: {list(zip(page_nums, positions))}")
            return True, "center"
        
        # Check for alternating pattern based on actual page numbers (odd/even)
        if self._is_valid_alternating_pattern(combination):
            self.logger.debug(f"Alternating pattern found: {list(zip(page_nums, positions))}")
            return True, "alternating"
        
        # Check for consistent single position (all left or all right)
        unique_positions = set(positions)
        if len(unique_positions) == 1 and list(unique_positions)[0] in ["left", "right"]:
            self.logger.debug(f"Consistent {positions[0]} pattern found: {list(zip(page_nums, positions))}")
            return True, f"consistent_{positions[0]}"
        
        self.logger.debug(f"No consistent pattern found: {list(zip(page_nums, positions))}")
        return False, "none"
    
    def _is_valid_alternating_pattern(self, combination: List[Dict]) -> bool:
        """Check if the pattern follows alternating left-right based on page numbers"""
        for candidate in combination:
            page_num = candidate["page_num"]
            position = candidate["position"]
            
            # Odd pages should be in LEFT, even pages should be in RIGHT (or vice versa)
            expected_odd_position = "left" if combination[0]["page_num"] % 2 == 1 and combination[0]["position"] == "left" else "right"
            expected_even_position = "right" if expected_odd_position == "left" else "left"
            
            if page_num % 2 == 1:  # Odd page
                if position != expected_odd_position:
                    return False
            else:  # Even page
                if position != expected_even_position:
                    return False
        
        return True
    
    def _score_continuity(self, sequence: Dict[int, int]) -> float:
        """Score sequence based on numerical continuity (Rule 1)"""
        if len(sequence) < 2:
            return 0
        
        sorted_items = sorted(sequence.items())
        continuity_score = 0
        
        for i in range(len(sorted_items) - 1):
            page_idx1, page_num1 = sorted_items[i]
            page_idx2, page_num2 = sorted_items[i + 1]
            
            expected_diff = page_idx2 - page_idx1
            actual_diff = page_num2 - page_num1
            
            # Perfect continuity: numbers increase by 1 for consecutive pages
            if actual_diff == expected_diff and actual_diff > 0:
                continuity_score += 100
            elif actual_diff == 1:  # Sequential pages
                continuity_score += 90
            elif abs(actual_diff - expected_diff) <= 1:  # Close match
                continuity_score += 50
            else:
                continuity_score -= 30  # Penalty for poor continuity
        
        return continuity_score / (len(sorted_items) - 1) if len(sorted_items) > 1 else 0
    
    def _score_enhanced_position_consistency(self, combination: List[Dict], pattern_type: str) -> float:
        """Score position consistency based on detected pattern type"""
        if len(combination) < 1:
            return 0
        
        if pattern_type == "center":
            return 100  # Center patterns get full score
        elif pattern_type == "alternating":
            return 90   # Alternating patterns get high score
        elif pattern_type.startswith("consistent_"):
            return 80   # Consistent single position gets good score
        elif pattern_type == "single":
            return 50   # Single page gets modest score
        else:
            return 0    # No pattern gets zero score




# Add the new signature for refining web citations
class FindCitationString(dspy.Signature):
    """
    Scans the text to find a specific Chinese citation instruction string.
    """
    page_content = dspy.InputField(desc="The full text content of the page.")
    citation_string = dspy.OutputField(desc="If a string like '若要引用本文，请按以下格式：...' or '引用格式：' is found, return the entire citation string (e.g., 'Maximos神父《心念之病》（伦敦：光从东方来，2025年05月09日）'). Otherwise, return an empty string.")

class ParseCitationString(dspy.Signature):
    """
    Parses a structured citation string to extract its components.
    """
    citation_string = dspy.InputField(desc="A citation string in the format 'Author《Title》（Location：Publisher，Date）'.")
    
    author = dspy.OutputField(desc="The author of the work (e.g., 'Maximos神父').")
    title = dspy.OutputField(desc="The title of the work (e.g., '心念之病').")
    publisher = dspy.OutputField(desc="The publisher of the work (e.g., '光从东方来').")
    publication_date = dspy.OutputField(desc="The publication date in YYYY-MM-DD format.")

class RefineWebCitation(dspy.Signature):
    """
    Analyzes webpage content to find the real author, title, and date, following specific rules.
    This is a multi-step process. First, check for explicit citation instructions, then look for author names in the title, and finally search for author bylines.
    """
    initial_title = dspy.InputField(desc="The title extracted by the initial metadata parser.")
    initial_author = dspy.InputField(desc="The author extracted by the initial parser (e.g., 'Ephremyuan'). This might be a username and not the real author.")
    page_content = dspy.InputField(desc="The main text content of the page (up to 1500 characters).")
    url = dspy.InputField(desc="The URL of the webpage, which may contain the date.")

    correct_author = dspy.OutputField(desc="The full name of the author. Follow these rules:\n1. Look for Chinese citation instructions like '引用格式' or '若要引用本文'. Extract the author from there.\n2. Check if the main title includes the author's name (e.g., 'Maximos神父：心念之病').\n3. Look for bylines like 'by [name]' or 'author:' near the top of the content.\n4. If no specific author is found, return the initial_author.")
    correct_title = dspy.OutputField(desc="The corrected, full title of the article. If the title contains the author, remove the author's name from the title.")
    publication_date = dspy.OutputField(desc="The publication date in YYYY-MM-DD format. First, check the text for a date. If not found, extract it from the URL.")

class CitationLLM:
    """LLM handler for citation extraction using DSPy."""

    def __init__(self, llm_model="ollama/qwen3"):
        """Initialize the LLM."""
        self.llm = get_llm_model(llm_model, temperature=0.1)
        dspy.settings.configure(lm=self.llm)

    def _truncate_text(self, text: str, max_chars: int = 1500) -> str:
        """Truncate text to a maximum number of characters."""
        return text[:max_chars]

    def refine_citation_from_web_structured(self, page_content: str) -> Dict:
        """
        A structured, multi-step process to extract citation info from web content.
        """
        try:
            # Step 1: Find the explicit citation string
            find_predictor = dspy.Predict(FindCitationString)
            find_result = find_predictor(page_content=self._truncate_text(page_content, max_chars=2000))
            
            if find_result.citation_string:
                logging.info(f"Found citation string: {find_result.citation_string}")
                
                # Step 2: Parse the found string
                parse_predictor = dspy.Predict(ParseCitationString)
                parse_result = parse_predictor(citation_string=find_result.citation_string)
                
                refined_info = {
                    "author": parse_result.author,
                    "title": parse_result.title,
                    "publisher": parse_result.publisher,
                    "date": parse_result.publication_date,
                }
                return {k: v for k, v in refined_info.items() if v}

            logging.info("No explicit citation string found. Skipping structured extraction.")
            return {}

        except Exception as e:
            logging.error(f"Error in structured web citation refinement: {e}")
            return {}

    def refine_citation_from_web(self, initial_title: str, initial_author: str, page_content: str, url: str) -> Dict:
        """Refines citation information from a webpage using a dedicated LLM call."""
        try:
            # First, try the new structured approach
            structured_result = self.refine_citation_from_web_structured(page_content)
            if structured_result:
                logging.info(f"Structured extraction successful: {structured_result}")
                return structured_result

            # Fallback to the general refinement if structured approach fails
            logging.info("Falling back to general web citation refinement.")
            predictor = dspy.Predict(RefineWebCitation)
            result = predictor(
                initial_title=initial_title,
                initial_author=initial_author,
                page_content=self._truncate_text(page_content, max_tokens=1500),
                url=url
            )

            refined_info = {
                "author": result.correct_author,
                "title": result.correct_title,
                "date": result.publication_date,
            }
            # Filter out empty fields
            return {k: v for k, v in refined_info.items() if v and v.lower() != initial_author.lower()}
        except Exception as e:
            logging.error(f"Error refining web citation with LLM: {e}")
            return {}

    def extract_book_citation(self, pdf_text: str) -> Dict:
        """Extract citation from book PDF text."""
        try:
            signature = dspy.Signature(
                "pdf_text -> title, author, publisher, year, location, editor, translator, volume, series, isbn, doi",
                "Extract citation information from book PDF text. Focus on cover and copyright pages (usually in first 5 pages). "
                "Look for title in the middle and upper part with biggest font size. "
                'Author field: CRITICAL for Chinese Names - Do NOT split multi-character names. "程俊英" is ONE author. Extract each full name, including dynasty or role indicators (e.g., "【明】王陽明撰", "朱熹注"). '
                "In copyright page, find publish year and publisher. For Chinese text, extract information similarly. "
                "Return 'Unknown' for missing fields.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(pdf_text=pdf_text)

            # Convert result to dictionary
            citation_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    citation_info[key] = value.strip()

            logging.info(f"Book LLM extraction result: {citation_info}")
            return citation_info

        except Exception as e:
            logging.error(f"Error with book LLM extraction: {e}")
            return {}


    def extract_thesis_citation(self, pdf_text: str) -> Dict:
        """Extract citation from thesis PDF text."""
        try:
            signature = dspy.Signature(
                "pdf_text -> title, author, thesis_type, year, publisher, location, doi",
                "Extract citation information from thesis PDF text. Focus on cover and title pages (usually in first 5 pages). "
                "Look for title in the middle and upper part with biggest font size. "
                'Author field: CRITICAL for Chinese Names - Do NOT split multi-character names. "程俊英" is ONE author. Extract each full name, including dynasty or role indicators (e.g., "【明】王陽明撰", "朱熹注"). '
                "Identify if it's a PhD thesis or Master thesis. Publisher should be a university or college. "
                "For Chinese text, extract information similarly. Return 'Unknown' for missing fields.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(pdf_text=pdf_text)

            # Convert result to dictionary
            citation_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    citation_info[key] = value.strip()

            logging.info(f"Thesis LLM extraction result: {citation_info}")
            return citation_info

        except Exception as e:
            logging.error(f"Error with thesis LLM extraction: {e}")
            return {}

    def extract_journal_citation(self, pdf_text: str) -> Dict:
        """Extract citation from journal PDF text."""
        try:
            signature = dspy.Signature(
                "pdf_text -> title, author, container_title, year, volume, issue, page_numbers, isbn, doi",
                "Extract citation information from journal PDF text. Focus on first page header and footer. "
                "Look for title in first line with biggest font size. "
                'Author field: CRITICAL for Chinese Names - Do NOT split multi-character names. "程俊英" is ONE author. Extract each full name, including dynasty or role indicators (e.g., "【明】王陽明撰", "朱熹注"). '
                "Find journal name (as container_title), year, volume, and issue number in header or footer of first page. "
                "Page numbers format should be 'start-end' (e.g., '20-41'). "
                "For Chinese text, extract information similarly. Return 'Unknown' for missing fields.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(pdf_text=pdf_text)

            # Convert result to dictionary
            citation_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    # Convert container_title back to container-title for compatibility
                    if key == "container_title":
                        citation_info["container-title"] = value.strip()
                    else:
                        citation_info[key] = value.strip()

            logging.info(f"Journal LLM extraction result: {citation_info}")
            return citation_info

        except Exception as e:
            logging.error(f"Error with journal LLM extraction: {e}")
            return {}

    def extract_bookchapter_citation(self, pdf_text: str) -> Dict:
        """Extract citation from book chapter PDF text."""
        try:
            signature = dspy.Signature(
                "pdf_text -> title, author, container_title, editor, publisher, year, location, page_numbers, isbn, doi",
                "Analyze the text from a book chapter and extract its citation metadata. "
                "Identify the following fields: "
                "- title: The title of the chapter itself. "
                '- author: The author(s) of the chapter. CRITICAL for Chinese Names - Do NOT split multi-character names. "程俊英" is ONE author. Extract each full name, including dynasty or role indicators (e.g., "【明】王陽明撰", "朱熹注"). '
                "- container-title: The title of the book that contains the chapter. "
                "- editor: The editor(s) of the book, often found near 'edited by'. "
                "- publisher: The publisher of the book. "
                "- year: The publication year of the book. "
                "- page_numbers: The page range of the chapter (e.g., '20-41'). "
                "- location, isbn, doi: If available. "
                "For Chinese text, extract the information similarly. If a field is not found, return 'Unknown'.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(pdf_text=pdf_text)

            # Convert result to dictionary
            citation_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    # Convert container_title back to container-title for compatibility
                    if key == "container_title":
                        citation_info["container-title"] = value.strip()
                    else:
                        citation_info[key] = value.strip()

            logging.info(f"Book chapter LLM extraction result: {citation_info}")
            return citation_info

        except Exception as e:
            logging.error(f"Error with book chapter LLM extraction: {e}")
            return {}

    def extract_page_numbers_for_journal_chapter(
        self,
        pdf_path: str,
        page_range: str = "1-5, -3"
    ) -> Dict:
        """
        Enhanced page number extraction using pattern recognition and position consistency.
        
        Args:
            pdf_path: Path to the PDF file
            page_range: Page range to analyze (e.g., "1-5, -3")
        
        Returns:
            Dict with page_numbers field if found
        """
        try:
            # Step 1: Try advanced pattern-based extraction first
            extractor = ImprovedPageNumberExtractor()
            
            # Use the enhanced pattern recognition with max 5 pages for now
            # TODO: Implement full page-range awareness as discussed
            # Get PDF page count for page-range aware extraction
            doc_temp = fitz.open(pdf_path)
            total_pdf_pages = doc_temp.page_count
            doc_temp.close()
            
            # Use page-range aware extraction
            page_sequence = extractor.find_continuous_page_sequence_with_range(
                pdf_path, page_range, total_pdf_pages
            )
            
            if page_sequence:
                # Convert to page range format
                page_numbers = list(page_sequence.values())
                start_page = min(page_numbers)
                
                # Try to extract total page count from any page text
                doc = fitz.open(pdf_path)
                total_pages = None
                for i in range(min(3, doc.page_count)):  # Check first 3 pages for total
                    page = doc[i]
                    for position_type in ["header", "footer"]:
                        position_texts = extractor.extract_text_by_position(page, position_type)
                        for text_info in position_texts:
                            total = extractor.extract_total_pages_from_text(text_info["text"])
                            if total:
                                total_pages = total
                                break
                        if total_pages:
                            break
                    if total_pages:
                        break
                doc.close()
                
                if total_pages and total_pages > start_page:
                    # Use the full document range
                    page_result = f"{start_page}-{total_pages}"
                    logging.info(f"Pattern-based page extraction found full range: {page_result} (from 共 {total_pages} 頁)")
                    return {"page_numbers": page_result}
                elif len(page_numbers) >= 2:
                    # Fallback to detected range
                    end_page = max(page_numbers)
                    page_result = f"{start_page}-{end_page}"
                    logging.info(f"Pattern-based page extraction found sample range: {page_result}")
                    return {"page_numbers": page_result}
                elif len(page_numbers) == 1:
                    # Single page
                    page_result = str(page_numbers[0])
                    logging.info(f"Pattern-based page extraction found single page: {page_result}")
                    return {"page_numbers": page_result}
            
            logging.info("Pattern-based extraction found no continuous sequence, falling back to LLM")
            
            # Step 2: Fallback to LLM-based method if pattern-based fails
            doc = fitz.open(pdf_path)
            if doc.page_count == 0:
                doc.close()
                return {}
            
            # Extract text from strategic pages for LLM analysis
            first_page_text = doc[0].get_text() if doc.page_count > 0 else ""
            second_page_text = doc[1].get_text() if doc.page_count > 1 else ""
            last_page_text = doc[doc.page_count - 1].get_text() if doc.page_count > 0 else ""
            second_to_last_page_text = doc[doc.page_count - 2].get_text() if doc.page_count > 1 else ""
            
            doc.close()
            
            signature = dspy.Signature(
                "first_page_text, second_page_text, last_page_text, second_to_last_page_text -> page_numbers",
                "Determine the page range (e.g., '20-41') for a document. "
                "1. Look for a number in the header or footer of the 'first_page_text'. This is the starting page. "
                "2. If not found, look for a number in the header or footer of the 'second_page_text'. If found, the starting page is that number minus 1. "
                "3. Look for a number in the header or footer of the 'last_page_text'. This is the ending page. "
                "4. If not found, look for a number in the header or footer of the 'second_to_last_page_text'. If found, the ending page is that number plus 1. "
                "If you can determine both a start and end page, return them as 'start-end'. Otherwise, return 'Unknown'.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(
                first_page_text=first_page_text,
                second_page_text=second_page_text,
                last_page_text=last_page_text,
                second_to_last_page_text=second_to_last_page_text,
            )

            citation_info = {}
            if result.page_numbers and result.page_numbers.lower() != "unknown":
                citation_info["page_numbers"] = result.page_numbers.strip()
                logging.info(f"LLM fallback page extraction result: {citation_info}")
            else:
                logging.warning("LLM fallback also failed to extract page numbers")

            return citation_info

        except Exception as e:
            logging.error(f"Error with page number extraction: {e}")
            return {}

    def extract_citation_from_text(self, text: str, doc_type: str) -> Dict:
        """Extract citation based on document type after truncating long text."""
        truncated_text = self._truncate_text(text)

        if doc_type == "book":
            return self.extract_book_citation(truncated_text)
        elif doc_type == "thesis":
            return self.extract_thesis_citation(truncated_text)
        elif doc_type == "journal":
            return self.extract_journal_citation(truncated_text)
        elif doc_type == "bookchapter":
            return self.extract_bookchapter_citation(truncated_text)
        else:
            # Default fallback
            logging.warning(f"Unknown document type: {doc_type}, using book extraction")
            return self.extract_book_citation(truncated_text)

    def extract_citation_from_text_url(self, markdown_text: str) -> Dict:
        """Extracts citation fields from the markdown content of a text-based URL."""
        try:
            signature = dspy.Signature(
                "markdown_content -> title, author, date, container_title",
                "Analyze the markdown content of a webpage to find the real author and title. "
                "Follow these rules in order: "
                "1. Check if the main title includes the author's name (e.g., 'Author Name: Article Title' or '博士 Author Name: Article Title'). If so, separate them. "
                "2. Look for explicit author tags like 'by [name]' or 'posted by [name]' near the top of the content. "
                "3. Search for Chinese citation blocks starting with '引用', '引用此文', or '以下格式：' and look for a title enclosed in `《...》` and the author nearby. "
                "The 'container-title' is the name of the overall website. "
                "Prioritize information found with these rules. Return 'Unknown' for any fields that cannot be found.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(markdown_content=self._truncate_text(markdown_text))

            citation_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    citation_info[key] = value.strip()

            logging.info(f"LLM extraction from text URL result: {citation_info}")
            return citation_info

        except Exception as e:
            logging.error(f"Error with text URL LLM extraction: {e}")
            return {}

    def parse_search_results(self, search_response: str) -> Dict:
        """Parse the response from a search API to extract citation fields."""
        try:
            signature = dspy.Signature(
                "search_results -> container_title, editor, publisher, year, volume, issue, page_numbers, doi",
                "Parse the provided search engine results to find missing citation information for a book chapter or journal article. "
                "Extract fields like the book/journal title (as container-title), editor, publisher, year, etc. "
                "Return 'Unknown' for any fields that cannot be found.",
            )

            predictor = dspy.Predict(signature)
            result = predictor(search_results=search_response)

            # Convert result to dictionary
            parsed_info = {}
            for key, value in result.items():
                if value and value.strip() and value.strip().lower() != "unknown":
                    # Handle key conversion for CSL compatibility
                    if key == "container_title":
                        parsed_info["container-title"] = value.strip()
                    else:
                        parsed_info[key] = value.strip()

            logging.info(f"Parsed search results: {parsed_info}")
            return parsed_info
        except Exception as e:
            logging.error(f"Error parsing search results with LLM: {e}")
            return {}

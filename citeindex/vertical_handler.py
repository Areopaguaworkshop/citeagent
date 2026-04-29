import logging
import os
import tempfile
import fitz  # PyMuPDF
from paddleocr import PaddleOCR, PPStructureV3
import numpy as np
from typing import Optional, List
import traceback

# Global variable to hold the initialized OCR engine
structure_engine = None
current_ocr_config = {}

def get_structure_engine(lang: str = 'ch'):
    """
    Initializes or re-initializes the PPStructureV3 engine with a configured language.
    """
    global structure_engine, current_ocr_config
    
    new_config = {'lang': lang}
    
    if structure_engine is None or current_ocr_config != new_config:
        logging.info(f"Initializing PPStructureV3 with language: {lang}")
        
        try:
            # Initialize PPStructureV3 without the unsupported parameters
            # Language configuration is handled internally by PPStructureV3
            structure_engine = PPStructureV3()
        except Exception as e:
            logging.error(f"Failed to initialize PPStructureV3: {e}")
            traceback.print_exc()
            return None
        
        current_ocr_config = new_config
    return structure_engine

def is_page_blank(pix: fitz.Pixmap, threshold: float = 1.0) -> bool:
    """
    Check if a page image is mostly blank.
    """
    img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
    
    if img_array.shape[2] > 1:
        gray_img = np.mean(img_array, axis=2)
    else:
        gray_img = img_array.squeeze()

    non_white_pixels = np.sum(gray_img < 250)
    total_pixels = pix.width * pix.height
    non_white_percentage = (non_white_pixels / total_pixels) * 100
    
    return non_white_percentage < threshold

def is_pdf_vertical(pdf_path: str, vertical_lang: str) -> bool:
    """
    Checks if the PDF has a predominantly vertical text layout by analyzing the first content page.
    """
    doc = None
    try:
        doc = fitz.open(pdf_path)
        first_content_page_pix = None
        for page in doc:
            pix = page.get_pixmap()
            if not is_page_blank(pix):
                first_content_page_pix = pix
                break
        
        if first_content_page_pix is None:
            logging.warning("PDF appears to be blank or has no detectable content.")
            return False

        print("🔍 Detecting layout and orientation with PP-Structure...")
        return is_vertical_from_layout(first_content_page_pix, vertical_lang)

    except Exception as e:
        logging.error(f"Error in vertical PDF detection: {e}", exc_info=True)
        return False
    finally:
        if doc:
            doc.close()

def process_vertical_pdf(pdf_path: str, vertical_lang: str, page_limit: Optional[int] = None) -> Optional[str]:
    """
    Handles the end-to-end OCR and text extraction for a vertical PDF.
    """
    doc = None
    try:
        doc = fitz.open(pdf_path)
        
        page_images = []
        pages_to_process = doc if page_limit is None else doc.pages(stop=page_limit)
        for page in pages_to_process:
            page_images.append(page.get_pixmap())
        
        print("📋 Extracting text from all pages of vertical PDF...")
        full_text = extract_text_from_images_paddleocr(page_images, vertical_lang)
        return full_text

    except Exception as e:
        logging.error(f"Error in vertical PDF processing: {e}", exc_info=True)
        return None
    finally:
        if doc:
            doc.close()

def extract_layout_boxes(result):
    """
    Extract layout boxes from PPStructureV3 result format.
    """
    boxes = []
    if not result:
        return boxes
    
    try:
        for page_result in result:
            # Extract from layout detection results
            if 'layout_det_res' in page_result and 'boxes' in page_result['layout_det_res']:
                for box in page_result['layout_det_res']['boxes']:
                    if 'coordinate' in box and 'label' in box:
                        coord = box['coordinate']
                        # Convert coordinate to list if it's a numpy array
                        bbox = coord.tolist() if hasattr(coord, 'tolist') else coord
                        boxes.append({
                            'type': box['label'],
                            'bbox': bbox,
                            'score': box.get('score', 0.0)
                        })
    except Exception as e:
        logging.error(f"Error extracting layout boxes: {e}")
        traceback.print_exc()
    
    return boxes

def extract_text_results(result):
    """
    Extract text results from PPStructureV3 result format.
    """
    text_results = []
    if not result:
        return text_results
    
    try:
        for page_result in result:
            # Extract from overall OCR results
            if 'overall_ocr_res' in page_result:
                ocr_res = page_result['overall_ocr_res']
                if 'rec_texts' in ocr_res and 'rec_boxes' in ocr_res:
                    texts = ocr_res['rec_texts']
                    boxes = ocr_res['rec_boxes']
                    for i, (text, box) in enumerate(zip(texts, boxes)):
                        if text.strip():  # Only include non-empty text
                            text_results.append({
                                'text': text,
                                'bbox': box.tolist() if hasattr(box, 'tolist') else box
                            })
    except Exception as e:
        logging.error(f"Error extracting text results: {e}")
        traceback.print_exc()
    
    return text_results

def is_vertical_from_layout(pix: fitz.Pixmap, lang: str) -> bool:
    """
    Detects if the text layout is predominantly vertical by analyzing the layout regions.
    """
    engine = get_structure_engine(lang=lang)
    if engine is None:
        logging.error("Failed to get PPStructureV3 engine")
        return False
    
    try:
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)

        # Use the predict method with the correct API
        result = engine.predict(img_array)
        logging.info(f"PP-Structure raw result for layout detection: {result}")

        # Extract layout boxes from the new result format
        layout_boxes = extract_layout_boxes(result)
        
        if not layout_boxes:
            logging.info("No layout boxes detected, falling back to text regions")
            # Fallback to text results if no layout boxes
            text_results = extract_text_results(result)
            if not text_results:
                return False
            
            aspect_ratios = []
            for text_result in text_results:
                bbox = text_result['bbox']
                # Correctly handle bbox format - it should be [x1, y1, x2, y2]
                if len(bbox) >= 4:
                    width = bbox[2] - bbox[0]
                    height = bbox[3] - bbox[1]
                    if width > 0:
                        aspect_ratios.append(height / width)
        else:
            # Analyze layout boxes
            aspect_ratios = []
            for box in layout_boxes:
                # Focus on text-like regions
                if box['type'].lower() in ['text', 'paragraph', 'title', 'header']:
                    bbox = box['bbox']
                    # Handle bbox format - should be [x1, y1, x2, y2]
                    if len(bbox) >= 4:
                        width = bbox[2] - bbox[0]
                        height = bbox[3] - bbox[1]
                        if width > 0:
                            aspect_ratios.append(height / width)
        
        if not aspect_ratios:
            logging.info("No text regions found for vertical analysis")
            return False
            
        median_ratio = np.median(aspect_ratios)
        logging.info(f"Median aspect ratio of text regions: {median_ratio:.2f}")
        
        return median_ratio > 1.5  # Use a stricter threshold for layout blocks
        
    except Exception as e:
        logging.error(f"Error in PPStructureV3 prediction: {e}")
        traceback.print_exc()
        return False

def extract_text_from_images_paddleocr(images: List[fitz.Pixmap], lang: str) -> str:
    """
    Extracts and sorts text from a list of page images using PP-Structure.
    """
    engine = get_structure_engine(lang=lang)
    if engine is None:
        logging.error("Failed to get PPStructureV3 engine")
        return ""
    
    full_doc_text = []

    for pix in images:
        if is_page_blank(pix):
            continue

        try:
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            # Use the predict method with the correct API
            result = engine.predict(img_array)

            if not result:
                continue

            # Extract text results from the new format
            text_results = extract_text_results(result)
            
            if not text_results:
                continue
            
            # Sort regions by right-to-left, then top-to-bottom.
            # For bbox format [x1, y1, x2, y2], sort by -x2 (right edge) then by y1 (top edge)
            text_results.sort(key=lambda r: (-r['bbox'][2], r['bbox'][1]))
            
            page_text_parts = []
            for text_result in text_results:
                page_text_parts.append(text_result['text'])
            
            page_text = "\n".join(page_text_parts)
            full_doc_text.append(page_text)
        except Exception as e:
            logging.error(f"Error processing page with PPStructureV3: {e}")
            traceback.print_exc()
            continue

    return "\n\n---\n\n".join(full_doc_text)

import logging
import fitz  # PyMuPDF
import subprocess
import tempfile
import os
import fasttext
import requests
from typing import Optional


# --- FastText Model Management ---
MODEL_DIR = os.path.expanduser("~/.cache/fasttext")
MODEL_PATH = os.path.join(MODEL_DIR, "lid.176.bin")
MODEL_URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin"

def download_fasttext_model():
    """Downloads the fastText language identification model if it doesn't exist."""
    if os.path.exists(MODEL_PATH):
        print("✅ fastText model found.")
        return

    print("⬇️ fastText model not found. Downloading...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    try:
        with requests.get(MODEL_URL, stream=True) as r:
            r.raise_for_status()
            with open(MODEL_PATH, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        print("✅ Model downloaded successfully.")
    except Exception as e:
        print(f"❌ Error downloading fastText model: {e}")
        # Clean up partial download if it exists
        if os.path.exists(MODEL_PATH):
            os.remove(MODEL_PATH)

# --- Language Mapping ---
def map_lang_to_tesseract(lang_code: str) -> str:
    """Maps a fastText language code to a Tesseract language code."""
    # fastText uses ISO 639-1 codes, which need to be mapped to Tesseract's codes
    mapping = {
        "zh": "chi_sim",  # Default Chinese to simplified
        "ja": "jpn",
        "de": "deu",
        "fr": "fra",
        "ru": "rus",
        "ar": "ara",
        # Add other mappings as needed
    }
    return mapping.get(lang_code, lang_code)

# --- Language Detection ---
def detect_language_from_scanned_pdf(pdf_path: str) -> Optional[str]:
    """Detect language from a scanned (non-searchable) PDF by OCRing one page."""
    download_fasttext_model()
    if not os.path.exists(MODEL_PATH):
        print("❌ fastText model is not available. Cannot perform language detection.")
        return None

    print("🔍 Detecting language from scanned PDF with fastText...")
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            doc.close()
            return None

        detected_lang = None
        detection_languages = "eng+chi_sim+chi_tra+fra+deu+rus+jpn"
        # Start check from page 2 (index 1), but fall back to page 1 if it's a single-page doc
        start_page_index = 1 if doc.page_count > 1 else 0

        for page_num in range(start_page_index, doc.page_count):
            temp_single_page = None
            temp_ocr_pdf = None
            try:
                print(f"📄 Checking page {page_num + 1} for text to perform language detection...")
                
                # Create a temporary PDF of the single page
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as single_page_file:
                    temp_single_page = single_page_file.name
                
                single_doc = fitz.open()
                single_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                single_doc.save(temp_single_page)
                single_doc.close()

                # Create a temporary file for the OCR output
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as ocr_file:
                    temp_ocr_pdf = ocr_file.name

                # Run OCR on the single page
                cmd = ["ocrmypdf", "--force-ocr", "-l", detection_languages, temp_single_page, temp_ocr_pdf]
                process = subprocess.run(cmd, capture_output=True, text=True, timeout=45)

                if process.returncode == 0:
                    ocr_doc = fitz.open(temp_ocr_pdf)
                    text = ocr_doc[0].get_text("text").replace("\n", " ").strip()
                    ocr_doc.close()

                    # If text is found, perform language detection
                    if text and len(text) > 50:
                        print(f"✅ Text found on page {page_num + 1}. Performing language detection.")
                        model = fasttext.load_model(MODEL_PATH)
                        predictions = model.predict(text, k=1)
                        lang_code = predictions[0][0].replace("__label__", "")
                        
                        tesseract_lang = map_lang_to_tesseract(lang_code)
                        
                        if lang_code == "zh":
                            # Simple character check for Traditional vs. Simplified
                            if any("\u4e00" <= char <= "\u9fff" and char > "\u9fa5" for char in text):
                                tesseract_lang = "chi_tra"
                            else:
                                tesseract_lang = "chi_sim"
                            print(f"✅ Chinese detected as {tesseract_lang}")
                        else:
                            print(f"✅ Language detected: {lang_code} → {tesseract_lang}")
                        
                        detected_lang = tesseract_lang
                        break  # Exit loop once language is detected
                    else:
                        print(f"⚠️ Page {page_num + 1} is blank or has insufficient text. Moving to next page.")
                else:
                    print(f"⚠️ OCR failed on page {page_num + 1}. Stderr: {process.stderr}")

            except Exception as e:
                print(f"⚠️ An error occurred while processing page {page_num + 1}: {e}")
                continue # Move to the next page
            finally:
                # Clean up temporary files for the current page
                if temp_single_page and os.path.exists(temp_single_page):
                    os.remove(temp_single_page)
                if temp_ocr_pdf and os.path.exists(temp_ocr_pdf):
                    os.remove(temp_ocr_pdf)

        doc.close()
        return detected_lang

    except Exception as e:
        print(f"❌ Error during language detection: {e}")
        return None


# --- OCR Language String Generation ---
def get_ocr_language_string(detected_lang: Optional[str] = None) -> str:
    """Get OCR language string with English and Simplified Chinese as priority base."""
    base_langs = "eng+chi_sim"
    if detected_lang and detected_lang not in base_langs.split("+"):
        return f"{base_langs}+{detected_lang}"
    return base_langs

def get_vertical_ocr_languages() -> str:
    """Get OCR languages for vertical text processing."""
    return "chi_tra_vert+jpn_vert"

def get_auto_mode_horizontal_ocr_languages() -> str:
    """Get OCR languages for horizontal pages in auto mode."""
    return "chi_tra+jpn"

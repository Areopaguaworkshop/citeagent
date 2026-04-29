import os
import subprocess
import logging
import fitz  # PyMuPDF
import requests
from urllib.parse import urlparse
from typing import Optional, Dict, Tuple, List
import re
import tempfile
from pypinyin import pinyin, Style

# --- Supported File Extensions ---

PYMUPDF_SUPPORTED_EXTENSIONS = [
    '.pdf', '.xps', '.oxps', '.epub', '.mobi', '.azw', '.fb2', '.cbz', 
]

OFFICE_SUPPORTED_EXTENSIONS = [
    '.docx', '.doc', '.rtf', '.odt', 
    '.pptx', '.ppt', '.odp',
]

DJVU_SUPPORTED_EXTENSIONS = [
    '.djvu'  # DjVu format
]

MEDIA_EXTENSIONS = [
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",  # video
    ".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a"  # audio
]

def get_input_type(input_string: str) -> str:
    """
    Determines the type of input (URL, PYMUPDF_DOCUMENT, OFFICE_DOCUMENT, DJVU_DOCUMENT, MEDIA_FILE, UNSUPPORTED).
    """
    # 1. Check if it's a URL
    try:
        result = urlparse(input_string)
        if all([result.scheme, result.netloc]):
            return "URL"
    except:
        pass

    # 2. Check if it's a file and determine its type by extension
    if os.path.exists(input_string):
        _, ext = os.path.splitext(input_string)
        ext = ext.lower()

        if ext in PYMUPDF_SUPPORTED_EXTENSIONS:
            return "PYMUPDF_DOCUMENT"
        if ext in OFFICE_SUPPORTED_EXTENSIONS:
            return "OFFICE_DOCUMENT"
        if ext in DJVU_SUPPORTED_EXTENSIONS:
            return "DJVU_DOCUMENT"
        if ext in MEDIA_EXTENSIONS:
            return "MEDIA_FILE"

    # 3. If none of the above, it's unsupported
    return "UNSUPPORTED"


def parse_page_range(page_range_str: str, total_pages: int) -> List[int]:
    """
    Parse a page range string (e.g., "1-5, -3") into a sorted list of 1-based page numbers.
    Returns an empty list if the range is invalid or empty.
    """
    if not page_range_str:
        return []

    pages_to_process = set()
    parts = page_range_str.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith("-"):
            # Last N pages
            try:
                last_n = int(part)
                if last_n > 0:
                    logging.warning(
                        f"Invalid last page range '{part}', should be negative. Skipping."
                    )
                    continue
                start_page = max(1, total_pages + last_n + 1)
                pages_to_process.update(range(start_page, total_pages + 1))
            except ValueError:
                logging.warning(f"Invalid page range format: {part}. Skipping.")
                continue
        elif "-" in part:
            # A range of pages (e.g., "1-5")
            try:
                start, end = map(int, part.split("-"))
                if start > end:
                    logging.warning(f"Invalid page range {start}-{end}. Skipping.")
                    continue
                pages_to_process.update(
                    range(start, min(end, total_pages) + 1))
            except ValueError:
                logging.warning(f"Invalid page range format: {part}. Skipping.")
                continue
        else:
            # A single page
            try:
                page = int(part)
                if 1 <= page <= total_pages:
                    pages_to_process.add(page)
            except ValueError:
                logging.warning(f"Invalid page number: {part}. Skipping.")

    return sorted(list(pages_to_process))


def ensure_searchable_pdf(pdf_path: str, lang: str = "eng+chi_sim") -> str:
    """Ensure PDF is searchable using OCR if needed."""
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count > 0 and doc[0].get_text().strip():
            logging.info("PDF appears to be searchable, skipping OCR.")
            doc.close()
            return pdf_path
        doc.close()

        # --- OCR is needed ---
        logging.info("PDF is not searchable or empty, proceeding with OCR.")

        # Use provided language string directly
        ocr_lang = lang  # Use provided language directly
        
        logging.info(f"Running OCR with lang='{ocr_lang}'...")

        # Step 2: Run ocrmypdf
        output_dir = os.path.dirname(pdf_path) or "."
        base_name = os.path.basename(pdf_path)
        ocr_output_path = os.path.join(output_dir, f"ocr_{base_name}")

        cmd = [
            "ocrmypdf",
            "--deskew",
            "--force-ocr",
            "-l",
            ocr_lang,
            pdf_path,
            ocr_output_path,
        ]

        logging.info(f"Running command: {' '.join(cmd)}")
        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if process.returncode == 0:
            logging.info(f"OCR completed successfully: {ocr_output_path}")
            if "temp" in pdf_path.lower() and os.path.basename(pdf_path).startswith("tmp"):
                os.remove(pdf_path)
            return ocr_output_path
        else:
            logging.error(f"OCR failed with return code {process.returncode}.")
            logging.error(f"Stderr: {process.stderr}")
            return pdf_path

    except Exception as e:
        logging.error(f"Error in ensure_searchable_pdf: {e}")
        return pdf_path


def create_subset_pdf(
    doc_path: str, page_range: str, total_pages: int
) -> Optional[str]:
    """
    Creates a temporary PDF file containing only the pages specified in the page range
    from any PyMuPDF-supported document.
    """
    pages_to_include = parse_page_range(page_range, total_pages)
    if not pages_to_include:
        logging.error("Failed to create subset PDF: No valid pages specified.")
        return None

    try:
        source_doc = fitz.open(doc_path)
        new_doc = fitz.open()  # Create a new, empty PDF

        # Convert 1-based page numbers to 0-based indices
        page_indices = [p - 1 for p in pages_to_include]

        # Insert each page individually to handle non-contiguous ranges
        for page_idx in page_indices:
            if 0 <= page_idx < source_doc.page_count:
                new_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)

        # Create a temporary file to save the new PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_path = temp_file.name

        new_doc.save(temp_path, garbage=4, deflate=True, clean=True)

        source_doc.close()
        new_doc.close()

        logging.info(
            f"Created temporary subset PDF with {len(pages_to_include)} pages at: {temp_path}"
        )
        return temp_path

    except Exception as e:
        logging.error(f"Error creating subset PDF: {e}")
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        return None


def extract_pdf_text(pdf_path: str, page_number: int) -> str:
    """Extract text from a specific page in a PDF."""
    try:
        doc = fitz.open(pdf_path)
        if 0 <= page_number < doc.page_count:
            page = doc[page_number]
            text = page.get_text()
            doc.close()
            return text
        else:
            logging.warning(
                f"Page number {page_number} is out of range for PDF with {doc.page_count} pages."
            )
            doc.close()
            return ""
    except Exception as e:
        logging.error(f"Error extracting text from page {page_number} of PDF: {e}")
        return ""


def determine_url_type(url: str) -> str:
    """Determine URL type with enhanced platform detection."""
    try:
        # First, check for known video/audio platforms by domain
        from urllib.parse import urlparse
        parsed_url = urlparse(url.lower())
        domain = parsed_url.netloc.replace("www.", "")
        
        # Video platforms - these should return "media" for motion_picture CSL type
        video_platforms = {
            "youtube.com",
            "youtu.be", 
            "vimeo.com",
            "dailymotion.com", 
            "twitch.tv",
            "tiktok.com",
            "bilibili.com",
            "rumble.com",
        }
        
        # Audio platforms
        audio_platforms = {
            "soundcloud.com",
            "spotify.com", 
            "anchor.fm",
            "podcasts.google.com",
        }
        
        # Check video platforms first
        if domain in video_platforms:
            return "media"  # This will trigger motion_picture CSL type
        
        # Check audio platforms  
        if domain in audio_platforms:
            return "media"  # This will trigger motion_picture CSL type
        
        # For social media platforms, check URL patterns for video content
        if domain in ["facebook.com", "instagram.com", "twitter.com", "x.com"]:
            if any(pattern in url.lower() for pattern in ["/video/", "/watch/", "/reel/", "/status/"]):
                return "media"
        
        # Fallback to header-based detection for other URLs
        response = requests.head(url, timeout=10)
        content_type = response.headers.get("content-type", "").lower()
        
        if "video" in content_type or "audio" in content_type:
            return "media"
        else:
            return "text"
            
    except Exception as e:
        logging.error(f"Error determining URL type: {e}")
        return "text"

def save_citation(csl_data: Dict, output_dir: str):
    """Save citation information as a CSL JSON file."""
    import json

    try:
        os.makedirs(output_dir, exist_ok=True)

        # Generate base filename from the CSL ID
        base_name = csl_data.get("id", "citation")

        # Save as JSON
        json_path = os.path.join(output_dir, f"{base_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(csl_data, f, indent=2, ensure_ascii=False)

        logging.info(f"CSL JSON citation saved to: {json_path}")

    except Exception as e:
        logging.error(f"Error saving citation: {e}")


def clean_url(url: str) -> str:
    """Clean URL by removing tracking parameters while preserving original format."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    # Common tracking parameters to remove
    tracking_params = {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "ref",
        "source",
        "campaign",
        "medium",
        "term",
        "content",
        "_ga",
        "_gid",
        "_gac",
        "mc_eid",
        "mc_cid",
    }

    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        # Remove tracking parameters
        cleaned_params = {
            k: v for k, v in query_params.items() if k not in tracking_params
        }

        # Reconstruct URL
        cleaned_query = urlencode(cleaned_params, doseq=True)
        cleaned_url = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                cleaned_query,
                parsed.fragment,
            )
        )

        return cleaned_url
    except Exception as e:
        logging.error(f"Error cleaning URL: {e}")
        return url


# Patterns for author titles/honorifics in English and Chinese
AUTHOR_TITLES = [
    "Dr.", "Fr.", "Professor", "Prof.",
    "博士", "神父", "教授", "老师", "先生"
]

def extract_dynasty_author_role(text: str) -> Tuple[str, str, str]:
    """Extract dynasty, author name, and role from text like '【宋】朱熹撰'"""
    dynasty = ""
    author_name = ""
    role = ""

    # Extract dynasty from various bracket styles
    dynasty_pattern = r"[【\[\(](.*?)[】\]\〕\)]"
    dynasty_match = re.search(dynasty_pattern, text)

    if dynasty_match:
        dynasty = dynasty_match.group(1).strip()
        # Remove the matched bracketed part and any immediate OCR noise after it
        text_after_dynasty = text[dynasty_match.end():].lstrip()

        # Clean up common OCR noise where dynasty name is repeated
        if text_after_dynasty.startswith(dynasty):
            text_after_dynasty = text_after_dynasty[len(dynasty):]

        # Further clean stray characters
        text = text_after_dynasty.lstrip("】』」)》] ")

    # Extract role indicators (撰, 著, 注, 編, etc.)
    role_pattern = r"(集撰|點校|[撰著注註編輯譯序跋])"
    role_match = re.search(role_pattern, text)
    if role_match:
        role = role_match.group(1)
        text = re.sub(role_pattern, "", text)

    # Remaining text is the author name
    author_name = text.strip()

    return dynasty, author_name, role

def parse_multiple_authors(author_string: str) -> List[Dict]:
    """
    Parse multiple authors with dynasty and role indicators, and split CJK names.
    Returns a list of structured dictionaries for each author.
    """
    if not author_string:
        return []

    # Regex to check for CJK characters
    def is_cjk(s): return re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", s)

    normalized = re.sub(r"\s+", " ", author_string).strip()

    # CJK author lists are often separated by spaces only.
    if (
        " and " not in normalized.lower()
        and not re.search(r"[,，;；]", normalized)
        and all(is_cjk(part) for part in normalized.split() if part)
    ):
        author_parts = normalized.split()
    else:
        author_parts = []
        for chunk in re.split(r"[;；]", normalized):
            chunk = chunk.strip()
            if not chunk:
                continue
            for part in re.split(r"\s+and\s+|,|，", chunk, flags=re.IGNORECASE):
                part = part.strip()
                if part:
                    author_parts.append(part)

    parsed_authors = []

    for part in author_parts:
        part = part.strip()
        if not part:
            continue

        dynasty, author_name, role = extract_dynasty_author_role(part)
        
        author_info = {
            "literal": author_name,
            "dynasty": dynasty,
            "role": role,
            "family": "",
            "given": ""
        }

        # Split CJK names into family and given
        if is_cjk(author_name):
            literal_name = author_name.replace(" ", "")
            if len(literal_name) == 2:
                author_info["family"] = literal_name[0]
                author_info["given"] = literal_name[1]
            elif len(literal_name) == 3:
                author_info["family"] = literal_name[0]
                author_info["given"] = literal_name[1:]
            elif len(literal_name) == 4:
                author_info["family"] = literal_name[:2]
                author_info["given"] = literal_name[2:]
            else: # Default for other lengths
                author_info["family"] = literal_name[0]
                author_info["given"] = literal_name[1:]
        else:
            western_tokens = author_name.split()
            if len(western_tokens) >= 2:
                author_info["family"] = western_tokens[-1]
                author_info["given"] = " ".join(western_tokens[:-1])
        
        parsed_authors.append(author_info)

    return parsed_authors

def format_author_csl(author_input) -> list:
    """
    Formats author input (string or list of dicts) into CSL-JSON compliant list.
    """
    if not author_input:
        return []

    # If input is a raw string, parse it first
    if isinstance(author_input, str):
        author_list = parse_multiple_authors(author_input)
    elif isinstance(author_input, list):
        # If it's a list of dicts, ensure it has the right structure, otherwise parse it
        if all(isinstance(d, dict) and "literal" in d for d in author_input):
             author_list = author_input
        else:
             # Re-parse if the list is not in the expected structured format
             author_list = parse_multiple_authors(" ".join(map(str, author_input)))
    else:
        return []

    authors_csl = []
    for author_data in author_list:
        if not isinstance(author_data, dict):
            continue

        literal_value = author_data.get("literal", "")
        csl_author = {}

        # Handle family/given names, converting to Pinyin for CJK
        family = author_data.get("family", "")
        given = author_data.get("given", "")

        if family and given:
            if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", family + given):
                try:
                    family_pinyin = "".join(item[0] for item in pinyin(family, style=Style.NORMAL)).title()
                    given_pinyin = "".join(item[0] for item in pinyin(given, style=Style.NORMAL)).title()
                    csl_author["family"] = family_pinyin
                    csl_author["given"] = given_pinyin
                except Exception:
                    # Fallback for non-pinyin convertible names
                    csl_author["family"] = family
                    csl_author["given"] = given
            else:
                csl_author["family"] = family
                csl_author["given"] = given
        elif family:
            if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", family):
                try:
                    csl_author["family"] = "".join(
                        item[0] for item in pinyin(family, style=Style.NORMAL)
                    ).title()
                except Exception:
                    csl_author["family"] = family
            else:
                csl_author["family"] = family
        elif given:
            if re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", given):
                try:
                    csl_author["given"] = "".join(
                        item[0] for item in pinyin(given, style=Style.NORMAL)
                    ).title()
                except Exception:
                    csl_author["given"] = given
            else:
                csl_author["given"] = given
        
        if literal_value and (
            not csl_author
            or re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", literal_value)
        ):
            csl_author["literal"] = literal_value

        # Assemble suffix from dynasty and role
        suffix_parts = []
        if author_data.get("dynasty"):
            suffix_parts.append(f"【{author_data['dynasty']}】")
        if author_data.get("role"):
            suffix_parts.append(author_data['role'])
        
        if suffix_parts:
            csl_author["suffix"] = " ".join(suffix_parts)
            
        authors_csl.append(csl_author)

    return authors_csl




def to_csl_json(data: Dict, doc_type: str) -> Dict:
    """Converts the internal dictionary to a CSL-JSON compliant dictionary."""
    csl = {}

    # 1. Map Type
    type_mapping = {
        "book": "book",
        "thesis": "thesis",
        "journal": "article-journal",
        "bookchapter": "chapter",
        "url": "webpage",
        "media": "motion_picture",  # Default for media, can be refined
        "video": "motion_picture",
        "motion_picture": "motion_picture",
        "audio": "song",
    }
    csl["type"] = type_mapping.get(
        doc_type, "document")  # Fallback to 'document'

    # 2. Format Authors and Editors
    if "author" in data:
        csl["author"] = format_author_csl(data["author"])
    if "editor" in data:
        csl["editor"] = format_author_csl(data["editor"])

    # 3. Format Dates
    if "date" in data or "year" in data:
        try:
            # Attempt to parse a full date if available, otherwise just use year
            date_str = str(data.get("date", data.get("year")))
            date_parts = [int(p) for p in date_str.split("-")]
            csl["issued"] = {"date-parts": [date_parts]}
        except (ValueError, TypeError):
            if "year" in data:
                try:
                    csl["issued"] = {"date-parts": [[int(data["year"])]]}
                except (ValueError, TypeError):
                    pass # Ignore if year is not a valid integer
    
    if "date_accessed" in data:
        try:
            date_parts = [int(p) for p in data["date_accessed"].split("-")]
            csl["accessed"] = {"date-parts": [date_parts]}
        except:
            pass  # Don't add if format is wrong

    # 4. Map Fields
    field_mapping = {
        "title": "title",
        "publisher": "publisher",
        "city": "publisher-place",
        "container-title": "container-title",
        "volume": "volume",
        "issue": "issue",
        "page_numbers": "page",
        "url": "URL",
        "doi": "DOI",
        "isbn": "ISBN",
        "genre": "genre",
        "abstract": "abstract",
        "keyword": "keyword",
    }
    for old_key, new_key in field_mapping.items():
        if old_key in data:
            csl[new_key] = data[old_key]

    # 5. Generate ID
    id_parts = []
    if csl.get("author"):
        author = csl["author"][0]
        # Use pinyin version if available
        family_name = author.get("family", "")
        given_name = author.get("given", "")
        if family_name:
            id_parts.append(family_name)
        if given_name:
            id_parts.append(given_name)

    if csl.get("issued"):
        id_parts.append(str(csl["issued"]["date-parts"][0][0]))

    if csl.get("title"):
        title = csl["title"]
        # Shorten title if it's too long
        if len(title) > 100:
            title = " ".join(title.split()[:20])  # take first 5 words
        id_parts.append(title)

    if csl.get("publisher"):
        id_parts.append(csl.get("publisher"))

    # Function to clean each part for the ID
    def clean_for_id(part):
        # Remove non-alphanumeric characters except for spaces and hyphens
        part = str(part)  # Ensure part is a string
        part = re.sub(r"[^\w\s-]", "", part).strip()
        # Replace spaces and hyphens with a single underscore
        part = re.sub(r"[\s-]+", "_", part)
        return part

    # Clean and join the parts
    cleaned_parts = [clean_for_id(p) for p in id_parts if p]
    base_id = "_".join(cleaned_parts)

    if not base_id:
        csl["id"] = "citation-" + os.urandom(4).hex()
    else:
        csl["id"] = base_id

    return csl



def extract_publisher_from_domain(url: str) -> Optional[str]:
    """Extract publisher name from domain."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]

        # Common domain to publisher mappings
        domain_mappings = {
            "nytimes.com": "New York Times",
            "washingtonpost.com": "Washington Post",
            "cnn.com": "CNN",
            "bbc.com": "BBC",
            "reuters.com": "Reuters",
            "theguardian.com": "The Guardian",
            "wsj.com": "Wall Street Journal",
            "forbes.com": "Forbes",
            "bloomberg.com": "Bloomberg",
            "npr.org": "NPR",
            "medium.com": "Medium",
            "github.com": "GitHub",
            "stackoverflow.com": "Stack Overflow",
            "wikipedia.org": "Wikipedia",
        }

        if domain in domain_mappings:
            return domain_mappings[domain]

        # For other domains, use the domain name as publisher
        # Remove common TLDs and make it more readable
        domain_parts = domain.split(".")
        if len(domain_parts) >= 2:
            # Use the main domain part
            main_domain = domain_parts[0]
            # Capitalize first letter
            return main_domain.capitalize()

        return domain

    except Exception as e:
        logging.error(f"Error extracting publisher from domain: {e}")
        return None



def ensure_searchable_pdf_with_detection(pdf_path: str) -> str:
    """Ensure PDF is searchable with language detection for horizontal mode."""
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count > 0 and doc[0].get_text().strip():
            logging.info("PDF appears to be searchable, skipping OCR.")
            doc.close()
            return pdf_path
        doc.close()

        # --- OCR is needed with language detection ---
        from .ocr_lang_detect import detect_language_from_first_text_page, get_ocr_language_string
        
        print("🔍 Performing language detection...")
        # First, try a quick OCR with basic languages for detection
        temp_ocr = f"/tmp/detect_{os.path.basename(pdf_path)}"
        
        cmd = ["ocrmypdf", "--force-ocr", "-l", "eng+chi_sim+chi_tra", 
               pdf_path, temp_ocr]
        
        process = subprocess.run(cmd, capture_output=True, text=True)
        detected_lang = None
        
        if process.returncode == 0:
            detected_lang = detect_language_from_first_text_page(temp_ocr)
            os.remove(temp_ocr)
        
        # Get final OCR language string
        ocr_lang = get_ocr_language_string(detected_lang)
        print(f"🔍 Using OCR languages: {ocr_lang}")
        
        return ensure_searchable_pdf(pdf_path, ocr_lang)

    except Exception as e:
        logging.error(f"Error in language detection OCR: {e}")
        # Fallback to basic OCR
        return ensure_searchable_pdf(pdf_path, "eng+chi_sim")


def ensure_searchable_pdf_with_detection(pdf_path: str) -> str:
    """Ensure PDF is searchable with language detection for scanned PDFs."""
    try:
        # First check if already searchable
        doc = fitz.open(pdf_path)
        has_text = False
        for i in range(min(3, doc.page_count)):
            if doc[i].get_text().strip():
                has_text = True
                break
        doc.close()
        
        if has_text:
            print("📄 PDF is already searchable, no OCR needed.")  
            return pdf_path

        # --- PDF is scanned, needs OCR with language detection ---
        print("🔍 PDF is scanned, performing language detection...")
        from .ocr_lang_detect import detect_language_from_scanned_pdf, get_ocr_language_string
        
        detected_lang = detect_language_from_scanned_pdf(pdf_path)
        ocr_lang = get_ocr_language_string(detected_lang)
        print(f"🔍 Using OCR languages: {ocr_lang}")
        
        return ensure_searchable_pdf(pdf_path, ocr_lang)

    except Exception as e:
        logging.error(f"Error in language detection OCR: {e}")
        # Fallback to basic OCR
        return ensure_searchable_pdf(pdf_path, "eng+chi_sim")

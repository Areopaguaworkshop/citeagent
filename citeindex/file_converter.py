import os
import subprocess
import logging
import tempfile
from typing import Optional, List

def parse_page_range(page_range_str: str, total_pages: int) -> List[int]:
    """
    Parse a page range string (e.g., "1-5, -3") into a sorted list of 1-based page numbers.
    Returns an empty list if the range is invalid or empty.
    Note: This returns 1-based page numbers for ddjvu compatibility.
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
                    logging.warning(f"Invalid negative page number: {last_n}")
                    continue
                last_n = abs(last_n)
                start_page = max(1, total_pages - last_n + 1)
                for page_num in range(start_page, total_pages + 1):
                    pages_to_process.add(page_num)  # Keep 1-based for ddjvu
            except ValueError:
                logging.warning(f"Invalid page range format: {part}")
                continue

        elif "-" in part:
            # Range like "1-5"
            try:
                start, end = part.split("-", 1)
                start_page = int(start)
                end_page = int(end)
                if start_page < 1 or end_page > total_pages or start_page > end_page:
                    logging.warning(f"Invalid page range: {part}")
                    continue
                for page_num in range(start_page, end_page + 1):
                    pages_to_process.add(page_num)  # Keep 1-based for ddjvu
            except ValueError:
                logging.warning(f"Invalid page range format: {part}")
                continue

        else:
            # Single page
            try:
                page_num = int(part)
                if 1 <= page_num <= total_pages:
                    pages_to_process.add(page_num)  # Keep 1-based for ddjvu
                else:
                    logging.warning(f"Page number out of range: {page_num}")
            except ValueError:
                logging.warning(f"Invalid page number: {part}")
                continue

    # Return sorted list of 1-based page numbers
    return sorted(list(pages_to_process))

def convert_to_pdf(file_path: str) -> Optional[str]:
    """
    Converts a document to a temporary PDF file using LibreOffice or ddjvu.
    Returns the path to the temporary PDF, or None if the conversion fails.
    """
    print(f"⚙️ Converting {os.path.basename(file_path)} to PDF...")

    temp_dir = tempfile.gettempdir()
    
    # Check if it's a DJVU file - use ddjvu
    if file_path.lower().endswith('.djvu'):
        return convert_djvu_to_pdf(file_path, temp_dir)
    
    # For other office documents, use LibreOffice
    try:
        # Run LibreOffice in headless mode to perform the conversion
        cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            file_path,
            "--outdir",
            temp_dir,
        ]
        
        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if process.returncode != 0:
            # Check for common error: LibreOffice not found
            if "command not found" in process.stderr.lower() or "no such file" in process.stderr.lower():
                logging.error(
                    "LibreOffice is not installed or not in the system's PATH. "
                    "Please install it to process Office documents."
                )
            else:
                logging.error(f"Failed to convert file with LibreOffice. Error: {process.stderr}")
            return None

        # Construct the expected output path
        base_name, _ = os.path.splitext(os.path.basename(file_path))
        converted_pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")

        if not os.path.exists(converted_pdf_path):
            logging.error(f"Conversion appeared to succeed, but the output file was not found at: {converted_pdf_path}")
            return None
            
        logging.info(f"Successfully converted to temporary PDF: {converted_pdf_path}")
        return converted_pdf_path

    except FileNotFoundError:
        logging.error(
            "LibreOffice is not installed or not in the system's PATH. "
            "Please install it to process Office documents."
        )
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during file conversion: {e}")
        return None

def convert_djvu_to_pdf(djvu_path: str, temp_dir: str) -> Optional[str]:
    """
    Converts a DJVU file to PDF using ddjvu, only converting first 10 pages to avoid memory issues.
    Returns the path to the temporary PDF, or None if the conversion fails.
    """
    try:
        base_name, _ = os.path.splitext(os.path.basename(djvu_path))
        output_pdf_path = os.path.join(temp_dir, f"{base_name}.pdf")
        
        # Use ddjvu to convert only first 10 pages of DJVU to PDF
        cmd = ["ddjvu", "-format=pdf", "-page=1-10", djvu_path, output_pdf_path]
        
        logging.info(f"Converting first 10 pages of DJVU to PDF using ddjvu: {' '.join(cmd)}")
        
        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        
        if process.returncode != 0:
            if "command not found" in process.stderr.lower() or "not found" in process.stderr.lower():
                logging.error(
                    "ddjvu is not installed or not in the system's PATH. "
                    "Please install djvulibre-bin to process DJVU files."
                )
            else:
                logging.error(f"Failed to convert DJVU file with ddjvu. Error: {process.stderr}")
            return None
        
        if not os.path.exists(output_pdf_path):
            logging.error(f"DJVU conversion appeared to succeed, but the output file was not found at: {output_pdf_path}")
            return None
        
        logging.info(f"Successfully converted DJVU to temporary PDF: {output_pdf_path}")
        return output_pdf_path
        
    except FileNotFoundError:
        logging.error(
            "ddjvu is not installed or not in the system's PATH. "
            "Please install djvulibre-bin to process DJVU files."
        )
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during DJVU conversion: {e}")
        return None

def convert_djvu_to_pdf_range(djvu_path: str, page_range: str, num_pages: int) -> Optional[str]:
    """
    Converts a specified page range of a DJVU file to PDF using ddjvu.
    Returns the path to the temporary PDF, or None if the conversion fails.
    """
    try:
        base_name, _ = os.path.splitext(os.path.basename(djvu_path))
        temp_dir = tempfile.gettempdir()
        output_pdf_path = os.path.join(temp_dir, f"{base_name}_subset.pdf")

        # Parse the page range string to get 1-based page numbers
        page_numbers = parse_page_range(page_range, num_pages)
        if not page_numbers:
            logging.error(f"Invalid or empty page range for DJVU conversion: {page_range}")
            return None

        # Convert page numbers to ddjvu format
        if len(page_numbers) == 1:
            page_spec = str(page_numbers[0])
        else:
            # Create range specification - ddjvu supports comma-separated pages and ranges
            page_spec = ','.join(str(p) for p in page_numbers)

        logging.info(f"Converting DJVU pages {page_numbers} to PDF using ddjvu (page spec: {page_spec})")

        # Use ddjvu to convert specified pages
        cmd = ["ddjvu", "-format=pdf", f"-page={page_spec}", djvu_path, output_pdf_path]
        
        logging.info(f"Running ddjvu command: {' '.join(cmd)}")

        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        if process.returncode != 0:
            if "command not found" in process.stderr.lower() or "not found" in process.stderr.lower():
                logging.error(
                    "ddjvu is not installed or not in the system's PATH. "
                    "Please install djvulibre-bin to process DJVU pages."
                )
            else:
                logging.error(f"Failed to convert DJVU page range to PDF with ddjvu. Error: {process.stderr}")
            return None

        if not os.path.exists(output_pdf_path):
            logging.error(f"DJVU page range conversion appeared to succeed, but the output file was not found at: {output_pdf_path}")
            return None

        logging.info(f"Successfully converted DJVU page range to temporary PDF: {output_pdf_path}")
        return output_pdf_path

    except Exception as e:
        logging.error(f"An unexpected error occurred during DJVU page range conversion: {e}")
        return None

def count_djvu_pages(djvu_path: str) -> int:
    """Count pages in DJVU file using djvudump."""
    try:
        cmd = ["djvudump", djvu_path]
        result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode == 0:
            # Parse the output to find the page count
            # Look for lines like "Document directory (bundled, X files Y pages)"
            for line in result.stdout.split('\n'):
                if 'pages)' in line and 'Document directory' in line:
                    # Extract number before 'pages)'
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'pages)' and i > 0:
                            try:
                                num_pages = int(parts[i-1])
                                logging.info(f"DJVU file has {num_pages} pages")
                                return num_pages
                            except ValueError:
                                continue
            
            logging.error(f"Could not parse page count from djvudump output")
            return 0
            
        logging.error(f"Failed to run djvudump on DJVU file")
        return 0
        
    except Exception as e:
        logging.error(f"Error counting DJVU pages: {e}")
        return 0

def count_pymupdf_document_pages(doc_path: str) -> int:
    """Count pages in PyMuPDF-supported documents (PDF, XPS, EPUB, etc.)."""
    try:
        import fitz
        doc = fitz.open(doc_path)
        num_pages = doc.page_count
        doc.close()
        logging.info(f"PyMuPDF document has {num_pages} pages")
        return num_pages
    except Exception as e:
        logging.error(f"Error counting PyMuPDF document pages: {e}")
        return 0

def count_office_document_pages(doc_path: str) -> int:
    """Count pages in Office documents using LibreOffice."""
    try:
        # Convert to PDF first to get page count, then delete temp file
        temp_dir = tempfile.gettempdir()
        base_name, _ = os.path.splitext(os.path.basename(doc_path))
        temp_pdf_path = os.path.join(temp_dir, f"{base_name}_pagecount.pdf")
        
        cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            doc_path,
            "--outdir",
            temp_dir,
        ]
        
        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        
        if process.returncode != 0:
            logging.error(f"Failed to convert office document for page counting: {process.stderr}")
            return 0
        
        # The actual output file will have the base name
        actual_temp_pdf = os.path.join(temp_dir, f"{base_name}.pdf")
        
        if not os.path.exists(actual_temp_pdf):
            logging.error(f"Temp PDF for page counting not found at: {actual_temp_pdf}")
            return 0
        
        # Count pages using PyMuPDF
        import fitz
        doc = fitz.open(actual_temp_pdf)
        num_pages = doc.page_count
        doc.close()
        
        # Clean up temp file
        os.remove(actual_temp_pdf)
        
        logging.info(f"Office document has {num_pages} pages")
        return num_pages
        
    except Exception as e:
        logging.error(f"Error counting office document pages: {e}")
        return 0

def convert_pymupdf_to_pdf_range(doc_path: str, page_range: str, num_pages: int) -> Optional[str]:
    """
    Extract specified page range from PyMuPDF document to a new PDF.
    Returns the path to the temporary PDF, or None if the conversion fails.
    """
    try:
        import fitz
        base_name, _ = os.path.splitext(os.path.basename(doc_path))
        temp_dir = tempfile.gettempdir()
        output_pdf_path = os.path.join(temp_dir, f"{base_name}_subset.pdf")

        # Parse the page range string to get 0-based page indices
        page_indices = [p - 1 for p in parse_page_range(page_range, num_pages)]  # Convert to 0-based
        if not page_indices:
            logging.error(f"Invalid or empty page range for PyMuPDF conversion: {page_range}")
            return None

        logging.info(f"Extracting PyMuPDF pages {[i+1 for i in page_indices]} to PDF (0-based indices: {page_indices})")

        # Open source document and create new PDF with selected pages
        source_doc = fitz.open(doc_path)
        target_doc = fitz.open()  # Create empty PDF
        
        for page_idx in page_indices:
            if 0 <= page_idx < source_doc.page_count:
                target_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)
            else:
                logging.warning(f"Page index {page_idx} out of range for document with {source_doc.page_count} pages")
        
        target_doc.save(output_pdf_path)
        target_doc.close()
        source_doc.close()

        if not os.path.exists(output_pdf_path):
            logging.error(f"PyMuPDF page range extraction failed - output file not found")
            return None

        logging.info(f"Successfully extracted PyMuPDF page range to temporary PDF: {output_pdf_path}")
        return output_pdf_path

    except Exception as e:
        logging.error(f"An unexpected error occurred during PyMuPDF page range extraction: {e}")
        return None

def convert_office_to_pdf_range(doc_path: str, page_range: str, num_pages: int) -> Optional[str]:
    """
    Convert specified page range from Office document to PDF using LibreOffice.
    Returns the path to the temporary PDF, or None if the conversion fails.
    """
    try:
        base_name, _ = os.path.splitext(os.path.basename(doc_path))
        temp_dir = tempfile.gettempdir()
        
        # First convert entire document to PDF
        full_pdf_path = os.path.join(temp_dir, f"{base_name}_full.pdf")
        
        cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            doc_path,
            "--outdir",
            temp_dir,
        ]
        
        process = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        
        if process.returncode != 0:
            logging.error(f"Failed to convert office document to PDF: {process.stderr}")
            return None
        
        # LibreOffice creates file with base name
        actual_full_pdf = os.path.join(temp_dir, f"{base_name}.pdf")
        
        if not os.path.exists(actual_full_pdf):
            logging.error(f"LibreOffice conversion output not found at: {actual_full_pdf}")
            return None
        
        # Now extract the page range using PyMuPDF
        output_pdf_path = os.path.join(temp_dir, f"{base_name}_subset.pdf")
        page_indices = [p - 1 for p in parse_page_range(page_range, num_pages)]  # Convert to 0-based
        
        if not page_indices:
            os.remove(actual_full_pdf)
            logging.error(f"Invalid or empty page range for office document conversion: {page_range}")
            return None
        
        logging.info(f"Extracting office document pages {[i+1 for i in page_indices]} from converted PDF")
        
        import fitz
        source_doc = fitz.open(actual_full_pdf)
        target_doc = fitz.open()  # Create empty PDF
        
        for page_idx in page_indices:
            if 0 <= page_idx < source_doc.page_count:
                target_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)
            else:
                logging.warning(f"Page index {page_idx} out of range for document with {source_doc.page_count} pages")
        
        target_doc.save(output_pdf_path)
        target_doc.close()
        source_doc.close()
        
        # Clean up full PDF
        os.remove(actual_full_pdf)

        if not os.path.exists(output_pdf_path):
            logging.error(f"Office document page range extraction failed - output file not found")
            return None

        logging.info(f"Successfully converted office document page range to temporary PDF: {output_pdf_path}")
        return output_pdf_path

    except Exception as e:
        logging.error(f"An unexpected error occurred during office document page range conversion: {e}")
        return None

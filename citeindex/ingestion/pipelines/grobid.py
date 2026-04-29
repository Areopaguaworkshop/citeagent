import logging
from typing import Any, Dict, List, Optional

import requests
from lxml import etree

logger = logging.getLogger(__name__)

TEI_NS = "http://www.tei-c.org/ns/1.0"
_NS = {"tei": TEI_NS}


def is_grobid_available(grobid_url: str = "http://localhost:8070") -> bool:
    """Check whether a GROBID service is reachable."""
    try:
        resp = requests.get(f"{grobid_url}/api/isalive", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# TEI XML parsing helpers
# ---------------------------------------------------------------------------

def _text_or_none(element: Optional[etree._Element]) -> Optional[str]:
    """Return stripped text content of an element, or None."""
    if element is None:
        return None
    text = element.text
    if text is None:
        # Collect all inner text (handles mixed content)
        text = "".join(element.itertext())
    text = text.strip()
    return text if text else None


def _parse_author(author_el: etree._Element) -> Optional[Dict[str, str]]:
    """Parse a single TEI <author> into a CSL name dict."""
    # Personal name
    persname = author_el.find("tei:persName", _NS)
    if persname is not None:
        given = _text_or_none(persname.find("tei:forename", _NS))
        family = _text_or_none(persname.find("tei:surname", _NS))
        if family:
            name: Dict[str, str] = {"family": family}
            if given:
                name["given"] = given
            return name

    # Institutional / organizational name
    orgname = _text_or_none(author_el.find("tei:orgName", _NS))
    if orgname:
        return {"literal": orgname}

    return None


def _parse_date_parts(date_el: Optional[etree._Element]) -> Optional[List[List[int]]]:
    """Convert a TEI <date> element to CSL date-parts."""
    if date_el is None:
        return None
    when = date_el.get("when")
    if not when:
        return None
    parts = when.split("-")
    try:
        int_parts = [int(p) for p in parts if p]
    except ValueError:
        return None
    return [int_parts] if int_parts else None


def _parse_bibl_struct(bibl: etree._Element) -> Dict[str, Any]:
    """Convert a single <biblStruct> element to a CSL JSON dict."""
    csl: Dict[str, Any] = {"type": "article-journal"}

    # --- analytic level (article title, authors) ---
    analytic = bibl.find("tei:analytic", _NS)
    monogr = bibl.find("tei:monogr", _NS)

    # Title
    if analytic is not None:
        title = _text_or_none(analytic.find("tei:title", _NS))
    else:
        title = None
    if not title and monogr is not None:
        title = _text_or_none(monogr.find("tei:title", _NS))
    if title:
        csl["title"] = title

    # Authors
    authors: List[Dict[str, str]] = []
    author_source = analytic if analytic is not None else monogr
    if author_source is not None:
        for author_el in author_source.findall("tei:author", _NS):
            parsed = _parse_author(author_el)
            if parsed:
                authors.append(parsed)
    if authors:
        csl["author"] = authors

    # --- monogr level (journal / container metadata) ---
    if monogr is not None:
        container_title = _text_or_none(monogr.find("tei:title", _NS))
        if container_title and analytic is not None:
            csl["container-title"] = container_title

        # Date
        imprint = monogr.find("tei:imprint", _NS)
        if imprint is not None:
            date_parts = _parse_date_parts(imprint.find("tei:date", _NS))
            if date_parts:
                csl["issued"] = {"date-parts": date_parts}

            volume = _text_or_none(imprint.find("tei:biblScope[@unit='volume']", _NS))
            if volume:
                csl["volume"] = volume

            issue = _text_or_none(imprint.find("tei:biblScope[@unit='issue']", _NS))
            if issue:
                csl["issue"] = issue

            page_el = imprint.find("tei:biblScope[@unit='page']", _NS)
            if page_el is not None:
                page_from = page_el.get("from")
                page_to = page_el.get("to")
                if page_from and page_to:
                    csl["page"] = f"{page_from}-{page_to}"
                elif page_from:
                    csl["page"] = page_from
                else:
                    page_text = _text_or_none(page_el)
                    if page_text:
                        csl["page"] = page_text

    # --- identifiers (DOI, ISBN) ---
    for idno in bibl.findall("tei:analytic/tei:idno", _NS) + bibl.findall("tei:monogr/tei:idno", _NS):
        id_type = (idno.get("type") or "").upper()
        value = _text_or_none(idno)
        if not value:
            continue
        if id_type == "DOI":
            csl["DOI"] = value
        elif id_type == "ISBN":
            csl["ISBN"] = value

    return csl


def _parse_tei_references(tei_xml: str) -> List[Dict[str, Any]]:
    """Parse TEI XML and extract bibliographic references as CSL JSON dicts.

    Looks for ``<biblStruct>`` elements inside the back-matter
    ``<listBibl>`` section produced by GROBID's fulltext processing.
    """
    try:
        root = etree.fromstring(tei_xml.encode("utf-8"))
    except etree.XMLSyntaxError:
        logger.warning("Failed to parse TEI XML response")
        return []

    bibl_structs = root.findall(
        f".//{{{TEI_NS}}}text/{{{TEI_NS}}}back//{{{TEI_NS}}}listBibl/{{{TEI_NS}}}biblStruct"
    )
    if not bibl_structs:
        # Fallback: search anywhere in the document
        bibl_structs = root.findall(f".//{{{TEI_NS}}}biblStruct")

    references: List[Dict[str, Any]] = []
    for bibl in bibl_structs:
        ref = _parse_bibl_struct(bibl)
        if ref.get("title"):
            references.append(ref)

    return references


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_citations_grobid(
    pdf_path: str,
    grobid_url: str = "http://localhost:8070",
) -> Dict[str, Any]:
    """Extract cited references from a PDF using GROBID's fulltext endpoint.

    Sends the PDF to ``/api/processFulltextDocument``, parses the returned
    TEI XML, and converts the back-matter bibliography to CSL JSON.

    Returns a dict with a ``references`` key containing a list of CSL JSON
    dicts, or an empty dict if GROBID is unavailable or processing fails.
    """
    try:
        with open(pdf_path, "rb") as fh:
            resp = requests.post(
                f"{grobid_url}/api/processFulltextDocument",
                files={"input": (pdf_path, fh, "application/pdf")},
                timeout=60,
            )
        if resp.status_code != 200:
            logger.warning(
                "GROBID fulltext request failed with status %d", resp.status_code
            )
            return {}

        references = _parse_tei_references(resp.text)
        return {"references": references} if references else {}

    except requests.ConnectionError:
        logger.warning("GROBID service not reachable at %s", grobid_url)
        return {}
    except Exception:
        logger.error("Unexpected error during GROBID citation extraction", exc_info=True)
        return {}


def _parse_ris_csl(ris_text: str) -> Dict[str, Any]:
    """Parse RIS format response into CSL dict."""
    csl: Dict[str, Any] = {}
    lines = ris_text.strip().split("\n")
    authors = []
    
    for line in lines:
        if not line.strip():
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().rstrip(",")
        
        if key == "TY" and value == "MISCC":
            csl["type"] = "article-journal"
        elif key == "TI" or key == "T1":
            csl["title"] = value
        elif key == "AU" or key == "A1":
            if " " in value:
                parts = value.rsplit(" ", 1)
                family = parts[0]
                given = parts[1] if len(parts) > 1 else ""
            else:
                family = value
                given = ""
            authors.append({"family": family, "given": given})
        elif key == "PY" or key == "Y1":
            try:
                year = value[:4]
                csl["issued"] = {"date-parts": [[int(year)]]}
            except (ValueError, IndexError):
                pass
        elif key == "DO":
            csl["DOI"] = value
        elif key == "AB" or key == "N2":
            csl["abstract"] = value
    
    if authors:
        csl["author"] = authors
    
    return csl


def _extract_metadata_from_tei(root: etree._Element) -> Dict[str, Any]:
    """Extract metadata from TEI XML response."""
    csl: Dict[str, Any] = {}

    # Title - try main title first, then any title
    title_el = root.find(f".//{{{TEI_NS}}}titleStmt/{{{TEI_NS}}}title[@level='a'][@type='main']")
    if title_el is None:
        title_el = root.find(f".//{{{TEI_NS}}}titleStmt/{{{TEI_NS}}}title")
    title = _text_or_none(title_el)
    if title:
        csl["title"] = title

    # Authors
    authors: List[Dict[str, str]] = []
    for author_el in root.findall(
        f".//{{{TEI_NS}}}fileDesc/{{{TEI_NS}}}sourceDesc"
        f"//{{{TEI_NS}}}author"
    ):
        parsed = _parse_author(author_el)
        if parsed:
            authors.append(parsed)
    if authors:
        csl["author"] = authors

    # Abstract
    abstract_el = root.find(f".//{{{TEI_NS}}}profileDesc/{{{TEI_NS}}}abstract")
    if abstract_el is not None:
        abstract_text = " ".join(abstract_el.itertext()).strip()
        if abstract_text:
            csl["abstract"] = abstract_text

    # Date
    date_el = root.find(
        f".//{{{TEI_NS}}}fileDesc/{{{TEI_NS}}}sourceDesc"
        f"//{{{TEI_NS}}}date"
    )
    date_parts = _parse_date_parts(date_el)
    if date_parts:
        csl["issued"] = {"date-parts": date_parts}

    # DOI
    doi_el = root.find(f".//{{{TEI_NS}}}idno[@type='DOI']")
    if doi_el is not None:
        doi = _text_or_none(doi_el)
        if doi:
            csl["DOI"] = doi

    return csl


def extract_document_metadata_grobid(
    pdf_path: str,
    grobid_url: str = "http://localhost:8070",
) -> Dict[str, Any]:
    """Extract the document's own metadata via GROBID.

    Tries fulltext endpoint first (returns TEI), then header endpoint.
    Handles both TEI XML and RIS format responses.

    Returns a CSL-compatible dict with title, authors, abstract, and date.
    Returns an empty dict if GROBID is unavailable or processing fails.
    """
    # Try fulltext endpoint first (more reliable, returns TEI)
    csl = _try_grobid_fulltext(pdf_path, grobid_url)
    if csl and csl.get("title"):
        logger.info("GROBID fulltext metadata extraction succeeded")
        return csl

    # Fallback to header endpoint
    csl = _try_grobid_header(pdf_path, grobid_url)
    if csl and csl.get("title"):
        logger.info("GROBID header metadata extraction succeeded")
        return csl

    logger.info("GROBID returned no title, treating as empty")
    return {}


def _try_grobid_fulltext(pdf_path: str, grobid_url: str) -> Dict[str, Any]:
    """Try extracting metadata via fulltext endpoint."""
    try:
        with open(pdf_path, "rb") as fh:
            resp = requests.post(
                f"{grobid_url}/api/processFulltextDocument",
                files={"input": (pdf_path, fh, "application/pdf")},
                timeout=120,
            )
        if resp.status_code != 200:
            logger.warning("GROBID fulltext request failed with status %d", resp.status_code)
            return {}

        # Try TEI XML first
        try:
            root = etree.fromstring(resp.text.encode("utf-8"))
            return _extract_metadata_from_tei(root)
        except etree.XMLSyntaxError:
            # Try RIS format
            if resp.text.strip().startswith("@"):
                return _parse_ris_csl(resp.text)
            logger.warning("GROBID fulltext returned neither TEI nor RIS")
            return {}

    except requests.ConnectionError:
        logger.warning("GROBID service not reachable at %s", grobid_url)
        return {}
    except Exception:
        logger.error("Unexpected error during GROBID fulltext extraction", exc_info=True)
        return {}


def _try_grobid_header(pdf_path: str, grobid_url: str) -> Dict[str, Any]:
    """Try extracting metadata via header endpoint."""
    try:
        with open(pdf_path, "rb") as fh:
            resp = requests.post(
                f"{grobid_url}/api/processHeaderDocument",
                files={"input": (pdf_path, fh, "application/pdf")},
                timeout=60,
            )
        if resp.status_code != 200:
            logger.warning("GROBID header request failed with status %d", resp.status_code)
            return {}

        # Try TEI XML first
        try:
            root = etree.fromstring(resp.text.encode("utf-8"))
            return _extract_metadata_from_tei(root)
        except etree.XMLSyntaxError:
            # Try RIS format
            if resp.text.strip().startswith("@"):
                return _parse_ris_csl(resp.text)
            logger.warning("GROBID header returned neither TEI nor RIS")
            return {}

    except requests.ConnectionError:
        logger.warning("GROBID service not reachable at %s", grobid_url)
        return {}
    except Exception:
        logger.error("Unexpected error during GROBID header extraction", exc_info=True)
        return {}

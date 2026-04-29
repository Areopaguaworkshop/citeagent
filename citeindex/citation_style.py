import os
from citeproc import Citation, CitationItem, CitationStylesStyle, CitationStylesBibliography
from citeproc.source.json import CiteProcJSON
from typing import Dict, List
import logging

def get_style_path(style_name: str) -> str:
    """
    Gets the full path to a CSL style file.
    Searches in the bundled 'styles' directory.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # The 'styles' directory is now a sibling to the 'citation' directory
    style_dir = os.path.join(script_dir, 'styles')
    style_file = f"{style_name}.csl"
    
    # Check for style in the packaged 'styles' directory first
    packaged_style_path = os.path.join(style_dir, style_file)
    if os.path.exists(packaged_style_path):
        return packaged_style_path
    
    # Fallback to checking the current working directory
    local_style_path = os.path.join(os.getcwd(), style_file)
    if os.path.exists(local_style_path):
        return local_style_path

    # Fallback to looking inside the citation package itself (for development)
    dev_style_path = os.path.join(script_dir, 'styles', style_file)
    if os.path.exists(dev_style_path):
        return dev_style_path

    return None # Return None if not found

def format_bibliography(csl_json_data: List[Dict], style_name: str) -> (str, str):
    """
    Formats a bibliography and in-text citations using citeproc-py.
    """
    try:
        style_path = get_style_path(style_name)
        if not style_path:
            return f"Error: Style '{style_name}' not found.", ""

        bib_source = CiteProcJSON(csl_json_data)
        bib_style = CitationStylesStyle(style_path, validate=False)
        
        bibliography = CitationStylesBibliography(bib_style, bib_source)

        # Create and register Citation objects
        citations_to_register = []
        for item in csl_json_data:
            citation_id = item.get('id')
            if citation_id:
                citation = Citation([CitationItem(citation_id)])
                bibliography.register(citation)
                citations_to_register.append(citation)

        # Generate the formatted bibliography
        formatted_bib_list = bibliography.bibliography()
        formatted_bib = "\n".join(str(item) for item in formatted_bib_list)

        # Generate a sample in-text citation for the first item
        formatted_citation = ""
        if citations_to_register:
            # Use the first registered citation to generate the in-text format
            in_text_citation = citations_to_register[0]
            # We need to provide a callback function to cite()
            def callback(s):
                pass
            if hasattr(bibliography.style, 'citation'):
                bibliography.cite(in_text_citation, callback)
                formatted_citation = str(in_text_citation)
            else:
                formatted_citation = "No in-text citation format defined in this style."

        return formatted_bib, formatted_citation

    except Exception as e:
        logging.error(f"Error formatting citation: {e}", exc_info=True)
        return f"Error during formatting: {e}", ""
"""
PyMuPDF (fitz) utilities for PDF operations.
"""

import io
import logging
from pathlib import Path
from typing import List, Dict

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def open_pdf(pdf_path: str) -> fitz.Document:
    """
    Open a PDF document.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Opened fitz.Document
        
    Raises:
        Exception: If PDF cannot be opened
    """
    try:
        doc = fitz.open(pdf_path)
        logger.info(f"Opened PDF: {pdf_path} ({len(doc)} pages)")
        return doc
    except Exception as e:
        logger.error(f"Failed to open PDF: {e}")
        raise


def get_page_count(doc: fitz.Document) -> int:
    """
    Get the total number of pages in a PDF document.
    
    Args:
        doc: Opened fitz.Document
        
    Returns:
        Number of pages
    """
    return len(doc)


def extract_images_from_page(page: fitz.Page, page_num: int, output_dir: Path) -> List[Dict]:
    """
    Extract all images from a specific page.
    
    Args:
        page: fitz.Page object
        page_num: Page number (0-indexed)
        output_dir: Directory to save extracted images
        
    Returns:
        List of dictionaries with image info:
        [{"page": int, "index": int, "filename": str, "filepath": str, "relative_path": str}, ...]
    """
    image_list = page.get_images(full=True)
    extracted = []
    
    # Get the document from the page
    doc = page.parent
    
    for img_index, img in enumerate(image_list):
        try:
            xref = img[0]
            base_image = doc.extract_image(xref)
            
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # Create filename
            filename = f"page_{page_num + 1}_img_{img_index + 1}.png"
            filepath = output_dir / filename
            
            # Convert to PNG if not already
            if image_ext.lower() != "png":
                img_obj = Image.open(io.BytesIO(image_bytes))
                img_obj.save(filepath, "PNG")
            else:
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
            
            extracted.append({
                "page": page_num + 1,
                "index": img_index + 1,
                "filename": filename,
                "filepath": str(filepath),
                "relative_path": f"images/{filename}"
            })
            
            logger.info(f"Extracted image: {filename}")
            
        except Exception as e:
            logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
    
    return extracted


def extract_text_from_page(page: fitz.Page, page_num: int) -> str:
    """
    Extract text from a specific page with layout preservation.
    
    Args:
        page: fitz.Page object
        page_num: Page number (0-indexed)
        
    Returns:
        Formatted text content
    """
    # Extract text with layout information
    text_dict = page.get_text("dict")
    blocks = text_dict.get("blocks", [])
    
    page_content = []
    page_content.append(f"\n## Page {page_num + 1}\n")
    
    # Extract text blocks
    text_blocks = []
    for block in blocks:
        if block.get("type") == 0:  # Text block
            block_text = ""
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span.get("text", "")
                block_text += " "
            
            if block_text.strip():
                text_blocks.append(block_text.strip())
    
    # Add text content
    if text_blocks:
        page_content.append("\n")
        page_content.append("\n\n".join(text_blocks))
        page_content.append("\n")
    
    return "".join(page_content)


def render_page_to_png(page: fitz.Page, page_num: int, output_path: Path, scale: float = 2.0) -> Path:
    """
    Render a PDF page to PNG image.
    
    Args:
        page: fitz.Page object
        page_num: Page number (0-indexed)
        output_path: Path where PNG should be saved
        scale: Scaling factor for resolution (default 2.0 for high quality)
        
    Returns:
        Path to the rendered PNG file
    """
    # Render page at specified resolution
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    
    # Save as PNG
    pix.save(str(output_path))
    
    logger.info(f"Rendered page {page_num + 1} to PNG: {output_path.name}")
    return output_path



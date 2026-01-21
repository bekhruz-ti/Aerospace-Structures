"""
File I/O, path management, and cleanup utilities.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)


def create_temp_directory(pdf_name: str) -> Path:
    """
    Create temporary directory for intermediate files.
    
    Args:
        pdf_name: Name of the PDF (without extension)
        
    Returns:
        Path to temporary directory
    """
    # Use pdf-parser/tmp/{pdf_name}/ structure
    tmp_dir = Path(__file__).parent.parent / "tmp" / pdf_name
    tmp_dir.mkdir(parents=True, exist_ok=True)
    
    # Also create images subdirectory
    (tmp_dir / "images").mkdir(exist_ok=True)
    
    logger.info(f"Created temp directory: {tmp_dir}")
    return tmp_dir


def get_final_output_paths(pdf_path: Path) -> Dict[str, Path]:
    """
    Get final output paths next to the original PDF.
    
    Args:
        pdf_path: Path to the original PDF file
        
    Returns:
        Dictionary with keys: 'html', 'images_dir'
    """
    pdf_path = Path(pdf_path)
    pdf_dir = pdf_path.parent
    pdf_name = pdf_path.stem
    
    return {
        'html': pdf_dir / f"{pdf_name}.html",
        'images_dir': pdf_dir / "images" / pdf_name
    }


def save_html(html_content: str, output_path: Path) -> None:
    """
    Save HTML content to file.
    
    Args:
        html_content: HTML string to save
        output_path: Path where HTML should be saved
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Saved HTML: {output_path}")


def save_markdown(markdown_content: str, output_path: Path) -> None:
    """
    Save markdown content to file.
    
    Args:
        markdown_content: Markdown string to save
        output_path: Path where markdown should be saved
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    logger.info(f"Saved markdown: {output_path}")


def save_json(data: Dict, output_path: Path) -> None:
    """
    Save dictionary as JSON file.
    
    Args:
        data: Dictionary to save
        output_path: Path where JSON should be saved
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved JSON: {output_path}")


def copy_images_to_final(
    src_dir: Path, 
    dest_dir: Path, 
    image_filter: Optional[Callable[[Path], bool]] = None
) -> int:
    """
    Copy images from source to destination directory.
    
    Args:
        src_dir: Source directory containing images
        dest_dir: Destination directory
        image_filter: Optional filter function that returns True for files to copy
        
    Returns:
        Number of images copied
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    copied_count = 0
    
    for img_file in src_dir.glob("*.png"):
        if image_filter and not image_filter(img_file):
            continue
        
        dest = dest_dir / img_file.name
        shutil.copy2(img_file, dest)
        copied_count += 1
    
    logger.info(f"Copied {copied_count} images to {dest_dir}")
    return copied_count


def update_image_paths_in_html(html_content: str, old_prefix: str, new_prefix: str) -> str:
    """
    Update image paths in HTML content.
    
    Args:
        html_content: HTML string
        old_prefix: Old path prefix to replace (e.g., "images/")
        new_prefix: New path prefix (e.g., "images/pdf_name/")
        
    Returns:
        Updated HTML string
    """
    return html_content.replace(f'src="{old_prefix}', f'src="{new_prefix}')


def cleanup_temp_directory(temp_dir: Path, keep_temp: bool = False) -> None:
    """
    Clean up temporary directory.
    
    Args:
        temp_dir: Path to temporary directory
        keep_temp: If True, preserve temporary files
    """
    if keep_temp:
        logger.info(f"Keeping temp files (--keep-temp flag): {temp_dir}")
        return
    
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Could not clean temp directory: {e}")



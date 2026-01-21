"""
Vision-guided PDF to HTML processor.

Uses page PNGs with text reference for accurate layout-preserving HTML generation.
"""

import logging
from pathlib import Path
from typing import Optional, List

from utils import (
    open_pdf,
    extract_text_from_page,
    render_page_to_png,
    encode_image_to_base64,
    llm_call,
    LLM,
    filter_content_by_page_range
)

logger = logging.getLogger(__name__)


class VisionGuidedProcessor:
    """Converts PDF to HTML using page PNGs + text reference."""
    
    def __init__(
        self,
        pdf_path: str,
        temp_dir: Path,
        start_page: Optional[int] = None,
        end_page: Optional[int] = None,
        model: LLM = LLM.CLAUDE_4_5_SONNET,
        temperature: float = 0
    ):
        """
        Initialize vision-guided processor.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for intermediate files
            start_page: Starting page number (1-indexed), None for all pages
            end_page: Ending page number (1-indexed), None for all pages
            model: LLM model to use
            temperature: Temperature for generation
        """
        self.pdf_path = Path(pdf_path)
        self.pdf_name = self.pdf_path.stem
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.start_page = start_page
        self.end_page = end_page
        self.model = model
        self.temperature = temperature
        
        self.doc = None
        
    def process(self) -> str:
        """
        Main processing method - returns HTML content.
        
        Returns:
            HTML content as string
        """
        logger.info(f"Starting VisionGuidedProcessor for {self.pdf_name}")
        
        # Open PDF
        self.doc = open_pdf(str(self.pdf_path))
        
        # Determine page range
        if self.start_page is None or self.end_page is None:
            actual_start = 0
            actual_end = len(self.doc)
        else:
            actual_start = self.start_page - 1  # Convert to 0-indexed
            actual_end = self.end_page
        
        # Extract text reference
        text_reference = self._extract_text_reference(actual_start, actual_end)
        
        # Render pages to PNG
        page_pngs = self._render_pages(actual_start, actual_end)
        
        # Generate HTML
        html = self._generate_html(page_pngs, text_reference)
        
        # Close PDF
        if self.doc:
            self.doc.close()
        
        logger.info(f"✓ VisionGuidedProcessor completed ({len(html)} characters)")
        return html
        
    def _extract_text_reference(self, start_page: int, end_page: int) -> str:
        """
        Extract text reference from pages.
        
        Args:
            start_page: Starting page (0-indexed)
            end_page: Ending page (0-indexed, exclusive)
            
        Returns:
            Markdown text content
        """
        markdown_lines = []
        markdown_lines.append(f"# {self.pdf_name}\n")
        
        # Process each page
        for page_num in range(start_page, end_page):
            page = self.doc[page_num]
            page_text = extract_text_from_page(page, page_num)
            markdown_lines.append(page_text)
        
        markdown_content = "".join(markdown_lines)
        logger.info(f"Extracted text reference from {end_page - start_page} pages")
        
        return markdown_content
        
    def _render_pages(self, start_page: int, end_page: int) -> List[Path]:
        """
        Render pages to PNG images.
        
        Args:
            start_page: Starting page (0-indexed)
            end_page: Ending page (0-indexed, exclusive)
            
        Returns:
            List of PNG file paths
        """
        logger.info(f"Rendering {end_page - start_page} pages to PNG...")
        
        page_pngs = []
        for page_num in range(start_page, end_page):
            page = self.doc[page_num]
            png_filename = f"page_{page_num + 1}.png"
            png_path = self.temp_dir / png_filename
            
            render_page_to_png(page, page_num, png_path, scale=2.0)
            page_pngs.append(png_path)
        
        logger.info(f"Rendered {len(page_pngs)} pages")
        return page_pngs
        
    def _generate_html(self, page_pngs: List[Path], text_reference: str) -> str:
        """
        Generate HTML using Claude Vision API.
        
        Args:
            page_pngs: List of page PNG paths
            text_reference: Text content for reference
            
        Returns:
            HTML content string
        """
        # Load HTML conversion prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "pdf_to_html_conversion.md"
        if not prompt_path.exists():
            logger.error(f"Prompt file not found: {prompt_path}")
            return ""
        
        system_prompt = prompt_path.read_text(encoding='utf-8')
        
        # Prepare content blocks for Claude Vision
        content_blocks = []
        
        # Calculate page display info
        if self.start_page and self.end_page:
            num_pages = self.end_page - self.start_page + 1
            page_display = f"{self.start_page}-{self.end_page}"
        else:
            num_pages = len(self.doc)
            page_display = f"1-{num_pages}"
        
        # Add initial instruction
        content_blocks.append({
            "type": "text",
            "text": f"""Convert pages {page_display} of this PDF to HTML with MAXIMUM ACCURACY.

**REFERENCE TEXT (for accurate transcription):**
{text_reference}

**INSTRUCTIONS:**
Below are PNG images of each page. Use these images to:
1. Verify exact layout and positioning
2. Ensure correct placement of all elements
3. Match visual structure precisely
4. Use the reference text above for EXACT transcription

Create a complete HTML document with:
- ALL text from reference (with MathJax for math notation)
- Images inserted at exact positions (use paths: images/page_X_img_Y.png)
- Professional academic styling
- Proper structure matching the visual layout

I will now show you each page:"""
        })
        
        # Add each page image
        for idx, png_path in enumerate(page_pngs):
            actual_page_num = (self.start_page + idx) if self.start_page else (idx + 1)
            content_blocks.append({
                "type": "text",
                "text": f"\n--- PAGE {actual_page_num} ---"
            })
            
            # Encode PNG to base64
            png_base64 = encode_image_to_base64(png_path)
            
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": png_base64
                }
            })
        
        # Add final instruction
        content_blocks.append({
            "type": "text",
            "text": "\n\nReturn ONLY the complete HTML document (no explanations, no markdown code blocks)."
        })
        
        try:
            # Call Claude Vision API
            logger.info("Sending page images to Claude Vision API...")
            _, html_content = llm_call(
                system_prompt=system_prompt,
                user_prompt=content_blocks,
                model=self.model,
                temperature=self.temperature
            )
            
            if html_content:
                logger.info(f"✓ HTML generated ({len(html_content)} characters)")
                return html_content
            else:
                logger.warning("No HTML content returned from Claude")
                return ""
                
        except Exception as e:
            logger.error(f"Error in HTML conversion: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""



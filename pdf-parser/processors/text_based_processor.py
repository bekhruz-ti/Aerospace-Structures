"""
Text-based PDF to HTML processor.

Uses extracted text content and image descriptions to generate HTML.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict

from utils import (
    open_pdf,
    extract_images_from_page,
    extract_text_from_page,
    describe_images_with_claude,
    llm_call,
    LLM,
    parse_page_range,
    filter_content_by_page_range
)

logger = logging.getLogger(__name__)


class TextBasedProcessor:
    """Converts PDF to HTML using extracted text + image descriptions."""
    
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
        Initialize text-based processor.
        
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
        self.temp_images_dir = temp_dir / "images"
        self.temp_images_dir.mkdir(parents=True, exist_ok=True)
        
        self.start_page = start_page
        self.end_page = end_page
        self.model = model
        self.temperature = temperature
        
        self.doc = None
        self.extracted_images = []
        self.image_descriptions = {}
        
    def process(self) -> str:
        """
        Main processing method - returns HTML content.
        
        Returns:
            HTML content as string
        """
        logger.info(f"Starting TextBasedProcessor for {self.pdf_name}")
        
        # Open PDF
        self.doc = open_pdf(str(self.pdf_path))
        
        # Determine page range
        if self.start_page is None or self.end_page is None:
            actual_start = 0
            actual_end = len(self.doc)
        else:
            actual_start = self.start_page - 1  # Convert to 0-indexed
            actual_end = self.end_page
        
        # Extract content
        markdown_content, image_paths = self._extract_content(actual_start, actual_end)
        
        # Describe images
        if image_paths:
            self.image_descriptions = self._describe_images(image_paths)
        
        # Generate HTML
        html = self._generate_html(markdown_content, self.image_descriptions)
        
        # Close PDF
        if self.doc:
            self.doc.close()
        
        logger.info(f"✓ TextBasedProcessor completed ({len(html)} characters)")
        return html
        
    def _extract_content(self, start_page: int, end_page: int) -> tuple[str, list[Path]]:
        """
        Extract text and images from PDF pages.
        
        Args:
            start_page: Starting page (0-indexed)
            end_page: Ending page (0-indexed, exclusive)
            
        Returns:
            Tuple of (markdown_content, image_paths)
        """
        markdown_lines = []
        markdown_lines.append(f"# {self.pdf_name}\n")
        markdown_lines.append(f"Extracted from: `{self.pdf_path}`\n")
        
        page_range_str = f"pages {start_page + 1}-{end_page}" if self.start_page else f"{len(self.doc)} pages"
        markdown_lines.append(f"Processing: {page_range_str}\n")
        
        image_paths = []
        
        # Process each page
        for page_num in range(start_page, end_page):
            logger.info(f"Processing page {page_num + 1}/{end_page}")
            
            page = self.doc[page_num]
            
            # Extract images from this page
            page_images = extract_images_from_page(page, page_num, self.temp_images_dir)
            self.extracted_images.extend(page_images)
            
            # Collect image paths
            for img_info in page_images:
                img_path = Path(img_info['filepath'])
                if img_path.exists():
                    image_paths.append(img_path)
            
            # Extract text from this page
            page_text = extract_text_from_page(page, page_num)
            
            # Add image references at the start of the page
            if page_images:
                page_text_lines = page_text.split('\n')
                # Insert image refs after the page header
                insert_pos = 1  # After "## Page N"
                for img in page_images:
                    page_text_lines.insert(insert_pos, f"![Image {img['index']}]({img['relative_path']})")
                    insert_pos += 1
                page_text = '\n'.join(page_text_lines)
            
            markdown_lines.append(page_text)
        
        markdown_content = "".join(markdown_lines)
        
        logger.info(f"Extracted {len(image_paths)} images and text from {end_page - start_page} pages")
        return markdown_content, image_paths
        
    def _describe_images(self, image_paths: list[Path]) -> Dict[str, Dict]:
        """
        Describe images using Claude Vision API.
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            Dictionary mapping filenames to {suggested_name, description}
        """
        # Load engineering-focused prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "engineering_image_analysis.md"
        if not prompt_path.exists():
            logger.warning(f"Prompt file not found: {prompt_path}")
            return {}
        
        system_prompt = prompt_path.read_text(encoding='utf-8')
        
        # Describe images
        descriptions = describe_images_with_claude(
            image_paths=image_paths,
            system_prompt=system_prompt,
            model=self.model
        )
        
        return descriptions
        
    def _generate_html(self, markdown_content: str, image_descriptions: Dict) -> str:
        """
        Generate HTML using Claude API.
        
        Args:
            markdown_content: Markdown text with image references
            image_descriptions: Image description dictionary
            
        Returns:
            HTML content string
        """
        # Load HTML conversion prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "pdf_to_html_conversion.md"
        if not prompt_path.exists():
            logger.error(f"Prompt file not found: {prompt_path}")
            return ""
        
        system_prompt = prompt_path.read_text(encoding='utf-8')
        
        # Prepare user prompt
        page_info = f"{self.start_page}-{self.end_page}" if self.start_page and self.end_page else f"All ({len(self.doc)})"
        
        user_prompt = f"""Convert the following PDF content to HTML with maximum accuracy.

**PDF Title:** {self.pdf_name}
**Pages:** {page_info}

**TEXT CONTENT (extracted from PDF):**
{markdown_content}

**IMAGE INFORMATION:**
{json.dumps(image_descriptions, indent=2) if image_descriptions else "No images"}

**INSTRUCTIONS:**
1. Reproduce ALL text EXACTLY as shown above
2. Use MathJax for ALL mathematical notation (variables, equations, symbols, units)
3. Insert images at their EXACT positions using the paths shown (e.g., images/page_1_img_1.png)
4. Use the image descriptions for alt text and figcaptions
5. Create a complete, standalone HTML document with embedded CSS and MathJax
6. Maintain proper document structure with headings, paragraphs, sections
7. Style it professionally for an academic/technical document

Return ONLY the complete HTML document, no explanations."""
        
        try:
            logger.info("Sending request to Claude API for HTML generation...")
            _, html_content = llm_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
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



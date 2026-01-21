"""
Handwritten PDF processor with diagram extraction.

Designed for handwritten exam pages with embedded diagrams.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple

from utils import (
    open_pdf,
    render_page_to_png,
    detect_diagram_bounding_boxes,
    extract_diagrams_from_pages,
    encode_image_to_base64,
    llm_call,
    LLM,
    system_message,
    user_message
)

logger = logging.getLogger(__name__)


class HandwrittenProcessor:
    """Converts handwritten PDF pages with diagram extraction."""
    
    def __init__(
        self,
        pdf_path: str,
        temp_dir: Path,
        model: LLM = LLM.CLAUDE_4_5_OPUS_THINKING,
        temperature: float = 1
    ):
        """
        Initialize handwritten processor.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for intermediate files
            model: LLM model to use (default: thinking model for better handwriting recognition)
            temperature: Temperature for generation
        """
        self.pdf_path = Path(pdf_path)
        self.pdf_name = self.pdf_path.stem
        self.temp_dir = temp_dir
        self.temp_images_dir = temp_dir / "images"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_images_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = model
        self.temperature = temperature
        
        self.doc = None
        self.image_descriptions = {}
        
    def process(self) -> str:
        """
        Main processing method - returns HTML content.
        
        Three-step process:
        1. Render all pages to PNG
        2. Detect and extract diagrams
        3. Generate HTML with handwriting transcription
        
        Returns:
            HTML content as string
        """
        logger.info(f"Starting HandwrittenProcessor for {self.pdf_name}")
        
        # Open PDF
        self.doc = open_pdf(str(self.pdf_path))
        
        # Step 1: Render all pages to PNG
        page_pngs = self._render_all_pages()
        
        # Step 2: Detect and extract diagrams
        diagram_data, extracted_diagrams = self._detect_and_extract_diagrams(page_pngs)
        
        # Step 3: Generate HTML
        html = self._generate_html(page_pngs, diagram_data)
        
        # Close PDF
        if self.doc:
            self.doc.close()
        
        logger.info(f"✓ HandwrittenProcessor completed ({len(html)} characters)")
        return html
        
    def _render_all_pages(self) -> List[Path]:
        """
        Render all PDF pages to PNG.
        
        Returns:
            List of PNG file paths
        """
        logger.info(f"Rendering all {len(self.doc)} pages to PNG...")
        
        page_pngs = []
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            png_filename = f"page_{page_num + 1}.png"
            png_path = self.temp_dir / png_filename
            
            # Check if already rendered
            if not png_path.exists():
                render_page_to_png(page, page_num, png_path, scale=2.0)
            
            page_pngs.append(png_path)
        
        logger.info(f"Rendered {len(page_pngs)} pages")
        return page_pngs
        
    def _detect_and_extract_diagrams(self, page_pngs: List[Path]) -> Tuple[List[Dict], Dict[str, str]]:
        """
        Detect diagram bounding boxes and extract diagrams.
        
        Args:
            page_pngs: List of page PNG paths
            
        Returns:
            Tuple of (diagram_data, extracted_diagram_paths)
        """
        logger.info("Step 1: Detecting diagram bounding boxes...")
        
        # Load bounding box detection prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "diagram_bounding_box_detection.md"
        if not prompt_path.exists():
            logger.error(f"Prompt file not found: {prompt_path}")
            return [], {}
        
        system_prompt = prompt_path.read_text(encoding='utf-8')
        
        # Prepare page_pngs with page numbers
        page_pngs_with_nums = [(idx + 1, path) for idx, path in enumerate(page_pngs)]
        
        # Detect diagrams
        diagram_data = detect_diagram_bounding_boxes(
            page_pngs=page_pngs_with_nums,
            system_prompt=system_prompt,
            model=LLM.CLAUDE_4_5_SONNET
        )
        
        if not diagram_data:
            logger.warning("No diagrams detected - proceeding without diagrams")
            return [], {}
        
        logger.info("Step 2: Extracting diagrams...")
        
        # Extract diagrams
        extracted_diagrams = extract_diagrams_from_pages(
            diagram_data=diagram_data,
            page_png_dir=self.temp_dir,
            output_dir=self.temp_images_dir
        )
        
        # Store in image_descriptions for later use
        for diagram in diagram_data:
            name = diagram['name']
            self.image_descriptions[f"{name}.png"] = {
                "suggested_name": name,
                "description": diagram.get('description', '')
            }
        
        return diagram_data, extracted_diagrams
        
    def _chunk_pages(self, page_pngs: List[Path], max_per_chunk: int = 8) -> List[List[Tuple[int, Path]]]:
        """
        Split pages into chunks of max 8, distributed evenly.
        
        Args:
            page_pngs: List of page PNG paths
            max_per_chunk: Maximum pages per chunk (default 8)
            
        Returns:
            List of chunks, where each chunk is a list of (page_num, path) tuples
        """
        total = len(page_pngs)
        if total <= max_per_chunk:
            return [[(i + 1, path) for i, path in enumerate(page_pngs)]]
        
        # Calculate number of chunks needed
        num_chunks = (total + max_per_chunk - 1) // max_per_chunk
        chunk_size = total // num_chunks
        remainder = total % num_chunks
        
        chunks = []
        start = 0
        for i in range(num_chunks):
            # Distribute remainder among first chunks
            size = chunk_size + (1 if i < remainder else 0)
            chunk = [(start + j + 1, page_pngs[start + j]) for j in range(size)]
            chunks.append(chunk)
            start += size
        
        return chunks
    
    def _generate_html(self, page_pngs: List[Path], diagram_data: List[Dict]) -> str:
        """
        Generate HTML using chunked transcription + final synthesis.
        
        Multi-call process:
        1. Split pages into chunks of max 8
        2. For each chunk: transcription-only call (accumulate history)
        3. Final call: synthesize all transcriptions into HTML
        
        Args:
            page_pngs: List of page PNG paths
            diagram_data: List of detected diagram information
            
        Returns:
            HTML content string
        """
        logger.info("Step 3: Generating HTML with chunked transcription...")
        
        # Load prompts
        transcription_prompt_path = Path(__file__).parent.parent / "prompts" / "handwritten_transcription.md"
        synthesis_prompt_path = Path(__file__).parent.parent / "prompts" / "handwritten_synthesis.md"
        
        if not transcription_prompt_path.exists():
            logger.error(f"Prompt file not found: {transcription_prompt_path}")
            return ""
        if not synthesis_prompt_path.exists():
            logger.error(f"Prompt file not found: {synthesis_prompt_path}")
            return ""
        
        transcription_prompt = transcription_prompt_path.read_text(encoding='utf-8')
        synthesis_prompt = synthesis_prompt_path.read_text(encoding='utf-8')
        
        # Prepare diagram information
        diagram_info = json.dumps([
            {
                "name": d['name'],
                "page": d['page'],
                "description": d['description'],
                "path": f"images/{d['name']}.png"
            }
            for d in diagram_data
        ], indent=2) if diagram_data else "No diagrams detected"
        
        # Chunk pages
        chunks = self._chunk_pages(page_pngs)
        logger.info(f"Split {len(page_pngs)} pages into {len(chunks)} chunks: {[len(c) for c in chunks]}")
        
        # Initialize history with system message
        history = [system_message(transcription_prompt)]
        
        try:
            # Process each chunk with transcription calls
            for chunk_idx, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {chunk_idx + 1}/{len(chunks)} ({len(chunk)} pages)...")
                
                # Prepare content blocks for this chunk
                content_blocks = []
                
                # Add context on first chunk
                if chunk_idx == 0:
                    content_blocks.append({
                        "type": "text",
                        "text": f"""I have a {len(page_pngs)}-page handwritten exam to transcribe.

**EXTRACTED DIAGRAMS (for reference):**
{diagram_info}

I will show you the pages in chunks. Please transcribe each page thoroughly.

Here are pages {chunk[0][0]}-{chunk[-1][0]}:"""
                    })
                else:
                    content_blocks.append({
                        "type": "text",
                        "text": f"Continuing transcription. Here are pages {chunk[0][0]}-{chunk[-1][0]}:"
                    })
                
                # Add page images for this chunk
                for page_num, png_path in chunk:
                    content_blocks.append({
                        "type": "text",
                        "text": f"\n=== PAGE {page_num} ==="
                    })
                    
                    png_base64 = encode_image_to_base64(png_path)
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": png_base64
                        }
                    })
                
                # Make transcription call with history
                history, transcription = llm_call(
                    system_prompt=transcription_prompt,
                    user_prompt=content_blocks,
                    model=self.model,
                    history=history if chunk_idx > 0 else None
                )
                
                logger.info(f"✓ Chunk {chunk_idx + 1} transcribed ({len(transcription)} characters)")
            
            # Final synthesis call
            logger.info("Making final synthesis call...")
            
            # Update system prompt for synthesis
            history[0] = system_message(synthesis_prompt)
            
            synthesis_prompt_text = f"""You have now transcribed all {len(page_pngs)} pages.

**DIAGRAM PATHS FOR HTML:**
{diagram_info}

Please synthesize ALL transcriptions from our conversation into a complete HTML document.
Follow the synthesis prompt instructions exactly. Return ONLY the HTML."""
            
            history, html_content = llm_call(
                system_prompt=synthesis_prompt,
                user_prompt=synthesis_prompt_text,
                model=self.model,
                history=history
            )
            
            if html_content:
                logger.info(f"✓ HTML synthesized ({len(html_content)} characters)")
                return html_content
            else:
                logger.warning("No HTML content returned from synthesis call")
                return ""
                
        except Exception as e:
            logger.error(f"Error in HTML generation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""



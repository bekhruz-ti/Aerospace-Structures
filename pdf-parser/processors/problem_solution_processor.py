"""
Problem-Solution processor for two-stage PDF processing.

First generates HTML for problems, then extracts and inserts solutions.
"""

import logging
from pathlib import Path
from typing import Optional

from utils import (
    open_pdf,
    render_page_to_png,
    encode_image_to_base64,
    llm_call,
    LLM,
    parse_page_range
)

from .text_based_processor import TextBasedProcessor
from .vision_guided_processor import VisionGuidedProcessor

logger = logging.getLogger(__name__)


class ProblemSolutionProcessor:
    """Two-stage processor: generates problems, then extracts/inserts solutions."""
    
    def __init__(
        self,
        pdf_path: str,
        temp_dir: Path,
        problem_pages: str,  # e.g., "1-4"
        solution_pages: str,  # e.g., "5-end"
        base_processor: str = "vision-guided",  # or "text-based"
    ):
        """
        Initialize problem-solution processor.
        
        Args:
            pdf_path: Path to PDF file
            temp_dir: Temporary directory for intermediate files
            problem_pages: Page range for problems (e.g., "1-4")
            solution_pages: Page range for solutions (e.g., "5-end")
            base_processor: Which processor to use for Stage 1 ("vision-guided" or "text-based")
        """
        self.pdf_path = Path(pdf_path)
        self.pdf_name = self.pdf_path.stem
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.problem_pages = problem_pages
        self.solution_pages = solution_pages
        self.base_processor_type = base_processor
        
        self.doc = None
        self.problem_start = None
        self.problem_end = None
        self.solution_start = None
        self.solution_end = None
        
    def process(self) -> str:
        """
        Main processing method - returns HTML with solutions.
        
        Two stages:
        1. Generate problem HTML using base processor
        2. Extract and insert solutions using Claude Opus Thinking
        
        Returns:
            HTML content string with problems and solutions
        """
        logger.info(f"Starting ProblemSolutionProcessor for {self.pdf_name}")
        logger.info(f"Problem pages: {self.problem_pages}")
        logger.info(f"Solution pages: {self.solution_pages}")
        logger.info(f"Using base processor: {self.base_processor_type}")
        
        # Open PDF to get total pages
        self.doc = open_pdf(str(self.pdf_path))
        total_pages = len(self.doc)
        
        # Parse page ranges
        self.problem_start, self.problem_end = parse_page_range(self.problem_pages, total_pages)
        self.solution_start, self.solution_end = parse_page_range(self.solution_pages, total_pages)
        
        # Stage 1: Generate problem HTML
        logger.info("=== STAGE 1: Generating Problem HTML ===")
        problems_html = self._generate_problem_html()
        
        if not problems_html:
            logger.error("Stage 1 failed - cannot proceed")
            if self.doc:
                self.doc.close()
            return ""
        
        logger.info(f"✓ Stage 1 completed - Problems HTML generated ({len(problems_html)} characters)")
        
        # Save intermediate problems HTML
        problems_path = self.temp_dir / "problems_only.html"
        problems_path.write_text(problems_html, encoding='utf-8')
        logger.info(f"Saved intermediate: {problems_path}")
        
        # Stage 2: Extract and insert solutions
        logger.info("=== STAGE 2: Extracting and Inserting Solutions ===")
        solutions_html = self._extract_and_insert_solutions(problems_html)
        
        if not solutions_html:
            logger.error("Stage 2 failed - returning problems-only HTML")
            if self.doc:
                self.doc.close()
            return problems_html
        
        logger.info(f"✓ Stage 2 completed - Solutions inserted ({len(solutions_html)} characters)")
        
        # Save final HTML
        final_path = self.temp_dir / "problems_with_solutions.html"
        final_path.write_text(solutions_html, encoding='utf-8')
        logger.info(f"Saved final: {final_path}")
        
        # Close PDF
        if self.doc:
            self.doc.close()
        
        logger.info(f"✓ ProblemSolutionProcessor completed")
        return solutions_html
        
    def _generate_problem_html(self) -> str:
        """
        Generate HTML for problem pages using the base processor.
        
        Returns:
            HTML content string
        """
        # Instantiate the appropriate base processor
        if self.base_processor_type == "text-based":
            processor = TextBasedProcessor(
                pdf_path=str(self.pdf_path),
                temp_dir=self.temp_dir,
                start_page=self.problem_start,
                end_page=self.problem_end,
                model=LLM.CLAUDE_4_5_SONNET,
                temperature=0
            )
        else:  # vision-guided (default)
            processor = VisionGuidedProcessor(
                pdf_path=str(self.pdf_path),
                temp_dir=self.temp_dir,
                start_page=self.problem_start,
                end_page=self.problem_end,
                model=LLM.CLAUDE_4_5_SONNET,
                temperature=0
            )
        
        # Process and return HTML
        return processor.process()
        
    def _extract_and_insert_solutions(self, problem_html: str) -> str:
        """
        Extract solutions from solution pages and insert into problem HTML.
        
        Args:
            problem_html: HTML with problems and empty answer spaces
            
        Returns:
            Updated HTML with solutions inserted
        """
        # Load solution extraction prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "solution_extraction_matching.md"
        if not prompt_path.exists():
            logger.error(f"Prompt file not found: {prompt_path}")
            return ""
        
        system_prompt = prompt_path.read_text(encoding='utf-8')
        
        # Render solution pages to PNGs
        logger.info(f"Rendering solution pages {self.solution_start}-{self.solution_end} to PNG...")
        solution_pngs = []
        
        for page_num in range(self.solution_start - 1, self.solution_end):  # Convert to 0-indexed
            page = self.doc[page_num]
            png_filename = f"page_{page_num + 1}.png"
            png_path = self.temp_dir / png_filename
            
            # Check if already rendered
            if not png_path.exists():
                render_page_to_png(page, page_num, png_path, scale=2.0)
            
            solution_pngs.append((page_num + 1, png_path))  # Store with 1-indexed page num
        
        # Prepare content blocks for Claude
        content_blocks = []
        
        # Add problem HTML
        content_blocks.append({
            "type": "text",
            "text": f"""PROBLEM HTML (with empty answer spaces to be filled):

{problem_html}

---

Now I will show you the SOLUTION PAGES. Analyze each one carefully and extract the solutions."""
        })
        
        # Add solution page images
        for page_num, png_path in solution_pngs:
            content_blocks.append({
                "type": "text",
                "text": f"\n=== SOLUTION PAGE {page_num} ==="
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
            "text": """\n\nNow:
1. Use <scratchpad> to analyze each solution page and extract solutions
2. Match solutions to their corresponding problems
3. In <result> tags, return the COMPLETE HTML with solutions inserted

Remember: Use MathJax for ALL mathematical content!"""
        })
        
        try:
            # Call Claude Opus 4.5 Thinking
            logger.info("Sending solution pages to Claude Opus 4.5 Thinking for analysis...")
            _, response = llm_call(
                system_prompt=system_prompt,
                user_prompt=content_blocks,
                model=LLM.CLAUDE_4_5_OPUS_THINKING,
                tag="result"
            )
            
            if response:
                logger.info(f"✓ Solutions extracted and inserted ({len(response)} characters)")
                return response
            else:
                logger.warning("No response returned from Claude")
                return ""
                
        except Exception as e:
            logger.error(f"Error in solution extraction: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""



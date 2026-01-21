"""
CLI entry point for PDF parser with parallel batch processing support.

Examples:
  # Single file with specific processor
  python main.py --processor text-based input.pdf
  
  # Multiple files in parallel
  python main.py --processor handwritten file1.pdf file2.pdf file3.pdf
  
  # Problem-solution workflow
  python main.py --processor problem-solution --problem-pages 1-4 --solution-pages 5-end exam.pdf
  
  # All PDFs in directory with max workers
  python main.py --processor vision-guided --max-workers 4 *.pdf
"""

import argparse
import logging
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Tuple
import multiprocessing

from processors import (
    TextBasedProcessor,
    VisionGuidedProcessor,
    HandwrittenProcessor,
    ProblemSolutionProcessor
)
from utils import (
    create_temp_directory,
    get_final_output_paths,
    save_html,
    save_json,
    copy_images_to_final,
    update_image_paths_in_html,
    cleanup_temp_directory
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_single_pdf(pdf_path: str, args) -> Tuple[str, bool]:
    """
    Process one PDF file.
    
    Args:
        pdf_path: Path to PDF file
        args: Parsed command-line arguments
        
    Returns:
        Tuple of (pdf_name, success_status)
    """
    pdf_path = Path(pdf_path)
    pdf_name = pdf_path.stem
    
    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        return pdf_name, False
    
    try:
        logger.info(f"Processing: {pdf_name}")
        logger.info("=" * 80)
        
        # Create temporary directory
        temp_dir = create_temp_directory(pdf_name)
        
        # Instantiate appropriate processor
        html_content = ""
        
        if args.processor == "text-based":
            processor = TextBasedProcessor(
                pdf_path=str(pdf_path),
                temp_dir=temp_dir,
                start_page=None,
                end_page=None
            )
            html_content = processor.process()
            image_descriptions = processor.image_descriptions
            
        elif args.processor == "vision-guided":
            processor = VisionGuidedProcessor(
                pdf_path=str(pdf_path),
                temp_dir=temp_dir,
                start_page=None,
                end_page=None
            )
            html_content = processor.process()
            image_descriptions = {}
            
        elif args.processor == "handwritten":
            processor = HandwrittenProcessor(
                pdf_path=str(pdf_path),
                temp_dir=temp_dir
            )
            html_content = processor.process()
            image_descriptions = processor.image_descriptions
            
        elif args.processor == "problem-solution":
            processor = ProblemSolutionProcessor(
                pdf_path=str(pdf_path),
                temp_dir=temp_dir,
                problem_pages=args.problem_pages,
                solution_pages=args.solution_pages,
                base_processor=args.base_processor
            )
            html_content = processor.process()
            image_descriptions = {}
            
        else:
            logger.error(f"Unknown processor: {args.processor}")
            return pdf_name, False
        
        if not html_content:
            logger.error(f"Failed to generate HTML for {pdf_name}")
            return pdf_name, False
        
        # Save final outputs
        final_paths = get_final_output_paths(pdf_path)
        
        # Copy images to final directory
        temp_images_dir = temp_dir / "images"
        if temp_images_dir.exists():
            if args.processor == "handwritten":
                # For handwritten, copy extracted diagrams
                image_filter = lambda p: not p.name.startswith("page_") or "_img_" not in p.name
            else:
                # For others, copy embedded images
                image_filter = lambda p: p.name.startswith("page_") and "_img_" in p.name
            
            copy_images_to_final(
                src_dir=temp_images_dir,
                dest_dir=final_paths['images_dir'],
                image_filter=image_filter
            )
        
        # Update image paths in HTML
        updated_html = update_image_paths_in_html(
            html_content=html_content,
            old_prefix="images/",
            new_prefix=f"images/{pdf_name}/"
        )
        
        # Save final HTML
        save_html(updated_html, final_paths['html'])
        
        # Save image descriptions if available
        if image_descriptions:
            json_path = final_paths['images_dir'] / "image_descriptions.json"
            save_json(image_descriptions, json_path)
        
        # Cleanup temp directory
        cleanup_temp_directory(temp_dir, keep_temp=args.keep_temp)
        
        logger.info("=" * 80)
        logger.info(f"[SUCCESS] {pdf_name}")
        logger.info(f"HTML: {final_paths['html']}")
        logger.info(f"Images: {final_paths['images_dir']}/")
        logger.info("=" * 80)
        
        return pdf_name, True
        
    except Exception as e:
        logger.error(f"Error processing {pdf_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return pdf_name, False


def batch_process_parallel(pdf_paths: List[str], args) -> Dict[str, bool]:
    """
    Process multiple PDFs in parallel using ProcessPoolExecutor.
    
    Args:
        pdf_paths: List of PDF file paths
        args: Parsed command-line arguments
        
    Returns:
        Dictionary mapping PDF names to success status
    """
    if args.max_workers is None:
        max_workers = min(multiprocessing.cpu_count(), len(pdf_paths))
    else:
        max_workers = args.max_workers
    
    logger.info(f"Processing {len(pdf_paths)} PDFs with {max_workers} parallel workers...")
    logger.info("=" * 80)
    
    results = {}
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_pdf = {
            executor.submit(process_single_pdf, pdf_path, args): Path(pdf_path).stem
            for pdf_path in pdf_paths
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_pdf):
            pdf_name = future_to_pdf[future]
            try:
                result_name, success = future.result()
                results[result_name] = success
            except Exception as e:
                logger.error(f"Exception processing {pdf_name}: {e}")
                results[pdf_name] = False
    
    return results


def main():
    """Parse arguments and orchestrate processing."""
    parser = argparse.ArgumentParser(
        description="PDF Parser - Convert PDFs to HTML using various approaches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Required arguments
    parser.add_argument(
        "files",
        nargs="+",
        help="PDF file(s) to process"
    )
    parser.add_argument(
        "--processor",
        choices=["text-based", "vision-guided", "handwritten", "problem-solution"],
        required=True,
        help="Processor type to use"
    )
    
    # Processor-specific arguments
    parser.add_argument(
        "--problem-pages",
        default="1-4",
        help="Page range for problems (for problem-solution processor)"
    )
    parser.add_argument(
        "--solution-pages",
        default="5-end",
        help="Page range for solutions (for problem-solution processor)"
    )
    parser.add_argument(
        "--base-processor",
        choices=["text-based", "vision-guided"],
        default="vision-guided",
        help="Base processor for problem-solution workflow"
    )
    
    # General options
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files for debugging"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Maximum number of parallel workers (default: auto-detect)"
    )
    
    args = parser.parse_args()
    
    # Validate processor-specific arguments
    if args.processor == "problem-solution":
        if not args.problem_pages or not args.solution_pages:
            logger.error("problem-solution processor requires --problem-pages and --solution-pages")
            sys.exit(1)
    
    # Process files
    if len(args.files) == 1:
        # Single file processing
        pdf_name, success = process_single_pdf(args.files[0], args)
        sys.exit(0 if success else 1)
    else:
        # Batch processing
        results = batch_process_parallel(args.files, args)
        
        # Print summary
        print("\n" + "=" * 80)
        print("BATCH PROCESSING SUMMARY")
        print("=" * 80)
        
        successful = sum(1 for v in results.values() if v)
        failed = sum(1 for v in results.values() if not v)
        
        print(f"Total PDFs: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        
        if failed > 0:
            print("\nFailed PDFs:")
            for pdf_name, success in results.items():
                if not success:
                    print(f"  - {pdf_name}")
        
        print("=" * 80)
        sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()



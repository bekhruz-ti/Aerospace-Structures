"""
Utilities for parsing and handling page ranges.
"""

from typing import Tuple


def parse_page_range(page_range: str, total_pages: int = None) -> Tuple[int, int]:
    """
    Parse a page range string like "1-4", "5-end", or "1" into start and end page numbers.
    
    Args:
        page_range: String like "1-4", "5-17", "5-end", or "1" (single page)
        total_pages: Total number of pages (required if using "end" keyword)
        
    Returns:
        Tuple of (start_page, end_page) as 1-indexed integers
    """
    parts = page_range.split('-')
    
    # Handle single page number (e.g., "1" means pages 1-1)
    if len(parts) == 1:
        try:
            page_num = int(parts[0])
            return page_num, page_num
        except ValueError:
            raise ValueError(f"Invalid page number: {page_range}")
    
    if len(parts) != 2:
        raise ValueError(f"Invalid page range format: {page_range}. Expected format: '1-4', '5-end', or '1'")
    
    try:
        start = int(parts[0])
        
        # Handle "end" keyword
        if parts[1].lower() == "end":
            if total_pages is None:
                raise ValueError(f"Cannot use 'end' keyword without total_pages parameter")
            end = total_pages
        else:
            end = int(parts[1])
            
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError(f"Invalid page numbers in range: {page_range}")
        raise
    
    if start < 1 or end < start:
        raise ValueError(f"Invalid page range: {page_range}. Start must be >= 1 and end >= start")
    
    return start, end


def filter_content_by_page_range(content: str, start: int, end: int) -> str:
    """
    Filter markdown content to only include specified page range.
    
    Args:
        content: Markdown content with page markers (## Page N)
        start: Starting page number (1-indexed)
        end: Ending page number (1-indexed)
        
    Returns:
        Filtered markdown content
    """
    lines = content.split('\n')
    filtered_lines = []
    in_range = False
    
    for line in lines:
        # Check for page markers
        if line.startswith("## Page "):
            try:
                page_num = int(line.split()[2])
                in_range = (start <= page_num <= end)
            except (IndexError, ValueError):
                # If we can't parse page number, keep current state
                pass
        
        if in_range:
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)



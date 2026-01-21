"""
Utility modules for PDF parsing operations.
"""

from .llm_utils import llm_call, LLM, system_message, user_message
from .pdf_utils import (
    open_pdf,
    extract_images_from_page,
    extract_text_from_page,
    render_page_to_png,
    get_page_count
)
from .image_utils import (
    convert_image_to_png,
    encode_image_to_base64,
    detect_diagram_bounding_boxes,
    extract_diagrams_from_pages,
    crop_image,
    describe_images_with_claude
)
from .output_utils import (
    create_temp_directory,
    save_html,
    save_markdown,
    save_json,
    copy_images_to_final,
    update_image_paths_in_html,
    cleanup_temp_directory,
    get_final_output_paths
)
from .page_range_utils import (
    parse_page_range,
    filter_content_by_page_range
)

__all__ = [
    # LLM utils
    "llm_call",
    "LLM",
    "system_message",
    "user_message",
    # PDF utils
    "open_pdf",
    "extract_images_from_page",
    "extract_text_from_page",
    "render_page_to_png",
    "get_page_count",
    # Image utils
    "convert_image_to_png",
    "encode_image_to_base64",
    "detect_diagram_bounding_boxes",
    "extract_diagrams_from_pages",
    "crop_image",
    "describe_images_with_claude",
    # Output utils
    "create_temp_directory",
    "save_html",
    "save_markdown",
    "save_json",
    "copy_images_to_final",
    "update_image_paths_in_html",
    "cleanup_temp_directory",
    "get_final_output_paths",
    # Page range utils
    "parse_page_range",
    "filter_content_by_page_range",
]



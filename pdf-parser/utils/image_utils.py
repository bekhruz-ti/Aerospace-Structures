"""
Image processing utilities including diagram extraction and Claude Vision integration.
"""

import base64
import io
import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from .llm_utils import llm_call, LLM

logger = logging.getLogger(__name__)


def convert_image_to_png(image_bytes: bytes, image_ext: str, output_path: Path) -> None:
    """
    Convert image bytes to PNG format.
    
    Args:
        image_bytes: Image data as bytes
        image_ext: Original image extension
        output_path: Path where PNG should be saved
    """
    if image_ext.lower() != "png":
        img = Image.open(io.BytesIO(image_bytes))
        img.save(output_path, "PNG")
    else:
        with open(output_path, "wb") as f:
            f.write(image_bytes)


def encode_image_to_base64(image_path: Path) -> str:
    """
    Encode an image file to base64 string.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Base64 encoded string
    """
    with open(image_path, 'rb') as f:
        image_data = f.read()
    return base64.standard_b64encode(image_data).decode('utf-8')


def annotate_image_with_grid(img: Image.Image) -> Image.Image:
    """
    Annotate an image with a grid overlay at 0.1 increments.
    
    Draws vertical and horizontal lines at 10% intervals with labels
    to help the LLM estimate normalized bounding box coordinates.
    
    Args:
        img: PIL Image to annotate
        
    Returns:
        New PIL Image with grid overlay (original unchanged)
    """
    # Create a copy to avoid modifying the original
    annotated = img.copy()
    
    # Convert to RGBA if needed for transparency support
    if annotated.mode != 'RGBA':
        annotated = annotated.convert('RGBA')
    
    # Create a transparent overlay for the grid
    overlay = Image.new('RGBA', annotated.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    width, height = annotated.size
    
    # Grid line color (semi-transparent red)
    line_color = (255, 0, 0, 100)
    # Label background color (semi-transparent white)
    label_bg_color = (255, 255, 255, 180)
    # Label text color
    text_color = (255, 0, 0, 255)
    
    # Try to get a font, fall back to default if not available
    try:
        # Calculate font size based on image dimensions (roughly 1.5% of smaller dimension)
        font_size = max(12, min(width, height) // 60)
        font = ImageFont.truetype("arial.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()
    
    # Draw grid lines and labels at 0.1 increments
    for i in range(1, 10):  # 0.1 to 0.9
        normalized = i / 10
        label = f"{normalized:.1f}"
        
        # Vertical line at x = normalized
        x = int(normalized * width)
        draw.line([(x, 0), (x, height)], fill=line_color, width=2)
        
        # Label at top of vertical line
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        label_x = x - text_width // 2
        label_y = 5
        # Draw label background
        draw.rectangle(
            [label_x - 2, label_y - 2, label_x + text_width + 2, label_y + text_height + 2],
            fill=label_bg_color
        )
        draw.text((label_x, label_y), label, fill=text_color, font=font)
        
        # Horizontal line at y = normalized
        y = int(normalized * height)
        draw.line([(0, y), (width, y)], fill=line_color, width=2)
        
        # Label at left of horizontal line
        label_x = 5
        label_y = y - text_height // 2
        # Draw label background
        draw.rectangle(
            [label_x - 2, label_y - 2, label_x + text_width + 2, label_y + text_height + 2],
            fill=label_bg_color
        )
        draw.text((label_x, label_y), label, fill=text_color, font=font)
    
    # Composite the overlay onto the annotated image
    annotated = Image.alpha_composite(annotated, overlay)
    
    # Convert back to RGB for PNG encoding
    annotated = annotated.convert('RGB')
    
    return annotated


def describe_images_with_claude(
    image_paths: List[Path], 
    system_prompt: str,
    model: LLM = LLM.CLAUDE_4_5_SONNET,
    user_message_modifier: Optional[str] = None,
    context_image_paths: Optional[List[Path]] = None
) -> Dict[str, Dict[str, str]]:
    """
    Use Claude Vision API to describe images with engineering focus.
    
    Args:
        image_paths: List of paths to image files
        system_prompt: System prompt for Claude
        model: LLM model to use
        user_message_modifier: Optional text to append to the user prompt
        context_image_paths: Optional list of context images (e.g., full page) mapping 1:1 with image_paths
        
    Returns:
        Dictionary mapping filenames to {suggested_name, description}
    """
    if not image_paths:
        logger.info("No images to describe")
        return {}
    
    logger.info(f"Describing {len(image_paths)} images with Claude Vision API...")
    
    # Process all images in one batch for efficiency
    content_blocks = []
    image_filenames = []
    
    for idx, img_path in enumerate(image_paths):
        if not img_path.exists():
            logger.warning(f"Image file not found: {img_path}")
            continue
        
        filename = img_path.name
        image_filenames.append(filename)
        
        try:
            # Add context image first (full page) if provided
            if context_image_paths and idx < len(context_image_paths):
                context_path = context_image_paths[idx]
                if context_path and context_path.exists():
                    context_base64 = encode_image_to_base64(context_path)
                    content_blocks.append({
                        "type": "text",
                        "text": f"[Full page context for {filename}]"
                    })
                    content_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": context_base64
                        }
                    })
            
            # Encode diagram image to base64
            image_base64 = encode_image_to_base64(img_path)
            
            # Add diagram to content blocks
            content_blocks.append({
                "type": "text",
                "text": f"[Diagram: {filename}]"
            })
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_base64
                }
            })
            
        except Exception as e:
            logger.warning(f"Failed to encode image {filename}: {e}")
    
    if not content_blocks:
        logger.warning("No images successfully encoded")
        return {}
    
    # Add instruction at the beginning
    base_instruction = f"Analyze these {len(image_filenames)} engineering diagrams and provide suggested filenames and technical descriptions for each."
    if user_message_modifier:
        base_instruction += f"\n\n{user_message_modifier}"
    
    content_blocks.insert(0, {
        "type": "text",
        "text": base_instruction
    })
    
    try:
        # Call Claude Vision API
        _, response = llm_call(
            system_prompt=system_prompt,
            user_prompt=content_blocks,
            model=model,
            tag="result"
        )
        
        if not response:
            logger.warning("No response from Claude API")
            return {}
        
        # Parse response - extract suggested names and descriptions for each image
        image_descriptions = {}
        
        for filename in image_filenames:
            # Pattern: <filename>...<suggested_name>...</suggested_name>...<description>...</description>...</filename>
            file_pattern = rf'<{re.escape(filename)}>(.*?)</{re.escape(filename)}>'
            file_match = re.search(file_pattern, response, re.DOTALL)
            
            if file_match:
                file_content = file_match.group(1)
                
                # Extract suggested name
                name_match = re.search(r'<suggested_name>\s*(.*?)\s*</suggested_name>', file_content, re.DOTALL)
                suggested_name = name_match.group(1).strip() if name_match else ""
                
                # Extract description
                desc_match = re.search(r'<description>\s*(.*?)\s*</description>', file_content, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else "No description available"
                
                image_descriptions[filename] = {
                    "suggested_name": suggested_name,
                    "description": description
                }
                
                logger.info(f"✓ {filename} -> {suggested_name}: {description[:80]}...")
            else:
                logger.warning(f"No description found for {filename}")
                image_descriptions[filename] = {
                    "suggested_name": "",
                    "description": "Description not available"
                }
        
        logger.info(f"✓ Completed descriptions for {len(image_descriptions)} images")
        return image_descriptions
        
    except Exception as e:
        logger.error(f"Error describing images with Claude: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}


def detect_diagram_bounding_boxes(
    page_pngs: List[Tuple[int, Path]], 
    system_prompt: str,
    model: LLM = LLM.CLAUDE_4_5_SONNET
) -> List[Dict]:
    """
    Detect engineering diagrams in pages and return bounding boxes.
    
    Args:
        page_pngs: List of tuples (page_num, png_path)
        system_prompt: System prompt for diagram detection
        model: LLM model to use
        
    Returns:
        List of diagram data: [{"page": int, "bbox": tuple, "description": str, "name": str}, ...]
        bbox is tuple of (x1, y1, x2, y2) in normalized 0-1 range
    """
    logger.info("Detecting diagram bounding boxes with Claude Vision...")
    
    if not page_pngs:
        logger.warning("No pages to analyze")
        return []
    
    # Prepare content blocks for Claude
    content_blocks = []
    content_blocks.append({
        "type": "text",
        "text": f"""Analyze these {len(page_pngs)} pages and identify the MAIN engineering diagram for EACH PROBLEM.

CRITICAL: Each page typically has 2-3 problems. Extract ONE diagram per problem (expect 2-3 diagrams per page). Do not skip any problems - if there's a problem, extract its diagram.

For each diagram found, provide:
- Normalized bounding box (0-1 range) with safety margins
- Technical description
- Suggested filename"""
    })
    
    # Add each page image with grid overlay
    for page_num, png_path in page_pngs:
        content_blocks.append({
            "type": "text",
            "text": f"\n--- PAGE {page_num} ---"
        })
        
        # Load image, annotate with grid, and encode to base64 in memory
        img = Image.open(png_path)
        annotated_img = annotate_image_with_grid(img)
        
        # Encode annotated image to base64
        buffer = io.BytesIO()
        annotated_img.save(buffer, format='PNG')
        png_base64 = base64.standard_b64encode(buffer.getvalue()).decode('utf-8')
        
        # # Print base64 for viewing with online tools (data URL format)
        # print(f"\n=== PAGE {page_num} ANNOTATED IMAGE (base64) ===")
        # print(f"data:image/png;base64,{png_base64}")
        # print("=" * 50)
        
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": png_base64
            }
        })
    
    try:
        # Call Claude Vision API
        logger.info("Sending pages to Claude for diagram detection...")
        messages, response = llm_call(
            system_prompt=system_prompt,
            user_prompt=content_blocks,
            model=model,
            tag="result"
        )
        
        if not response:
            logger.warning("No response from Claude")
            return []
        
        # Parse response to extract bounding boxes
        diagrams = []
        
        for page_num, _ in page_pngs:
            page_pattern = rf'<page_{page_num}>(.*?)</page_{page_num}>'
            page_match = re.search(page_pattern, response, re.DOTALL)
            
            if not page_match:
                continue
            
            page_content = page_match.group(1)
            
            # Check for no_diagrams tag
            if '<no_diagrams/>' in page_content or '<no_diagrams />' in page_content:
                logger.info(f"Page {page_num}: No diagrams detected")
                continue
            
            # Find all diagrams on this page
            diagram_pattern = r'<diagram_(\d+)>(.*?)</diagram_\1>'
            for diagram_match in re.finditer(diagram_pattern, page_content, re.DOTALL):
                diagram_content = diagram_match.group(2)
                
                # Extract bbox
                bbox_match = re.search(r'<bbox>\s*([\d.,\s]+)\s*</bbox>', diagram_content)
                if not bbox_match:
                    logger.warning(f"Page {page_num}: No bbox found for diagram")
                    continue
                
                bbox_str = bbox_match.group(1).strip()
                bbox_parts = [float(x.strip()) for x in bbox_str.split(',')]
                if len(bbox_parts) != 4:
                    logger.warning(f"Page {page_num}: Invalid bbox format: {bbox_str}")
                    continue
                
                bbox = tuple(bbox_parts)
                
                # Extract description
                desc_match = re.search(r'<description>\s*(.*?)\s*</description>', diagram_content, re.DOTALL)
                description = desc_match.group(1).strip() if desc_match else "Diagram"
                
                # Extract name
                name_match = re.search(r'<name>\s*(.*?)\s*</name>', diagram_content, re.DOTALL)
                name = name_match.group(1).strip() if name_match else f"diagram_page{page_num}"
                
                diagrams.append({
                    "page": page_num,
                    "bbox": bbox,
                    "description": description,
                    "name": name
                })
                
                logger.info(f"✓ Page {page_num}: {name} at {bbox}")
        
        logger.info(f"✓ Detected {len(diagrams)} diagrams across {len(page_pngs)} pages")
        
        # === FEEDBACK LOOP: Verify bounding boxes with cropped images ===
        if diagrams:
            logger.info("Starting feedback loop to verify bounding boxes...")
            
            # Build page_num -> png_path mapping
            page_png_map = {page_num: png_path for page_num, png_path in page_pngs}
            
            # Create verification content blocks with cropped images
            feedback_blocks = []
            feedback_blocks.append({
                "type": "text",
                "text": """I've cropped the diagrams using your bounding boxes. Please review each cropped image below.

For each diagram, check if the bounding box correctly captured the COMPLETE diagram including all labels, annotations, and margins.

If a crop is CORRECT, respond with:
<diagram_name>correct</diagram_name>

If a crop needs adjustment (cut off labels, too tight, includes too much extra content), provide the UPDATED bounding box:
<diagram_name>
  <bbox>x1,y1,x2,y2</bbox>
</diagram_name>

Here are the cropped diagrams:"""
            })
            
            # Crop each diagram and add to feedback
            for diagram in diagrams:
                page_num = diagram['page']
                bbox = diagram['bbox']
                name = diagram['name']
                
                png_path = page_png_map.get(page_num)
                if not png_path or not png_path.exists():
                    continue
                
                try:
                    # Crop image in memory
                    img = Image.open(png_path)
                    width, height = img.size
                    
                    x1 = int(bbox[0] * width)
                    y1 = int(bbox[1] * height)
                    x2 = int(bbox[2] * width)
                    y2 = int(bbox[3] * height)
                    
                    # Validate coordinates
                    if x1 >= x2 or y1 >= y2:
                        logger.warning(f"Invalid bbox for {name}, skipping feedback")
                        continue
                    
                    cropped = img.crop((x1, y1, x2, y2))
                    
                    # Encode cropped image to base64
                    buffer = io.BytesIO()
                    cropped.save(buffer, format='PNG')
                    cropped_base64 = base64.standard_b64encode(buffer.getvalue()).decode('utf-8')
                    
                    # Add diagram label and cropped image
                    feedback_blocks.append({
                        "type": "text",
                        "text": f"\n--- {name} (page {page_num}, bbox: {bbox}) ---"
                    })
                    feedback_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": cropped_base64
                        }
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to crop {name} for feedback: {e}")
            
            # Make second LLM call with feedback
            if len(feedback_blocks) > 1:  # More than just the instruction text
                logger.info("Sending cropped images for verification...")
                _, feedback_response = llm_call(
                    system_prompt=system_prompt,
                    user_prompt=feedback_blocks,
                    model=model,
                    tag="result",
                    history=messages
                )
                
                if feedback_response:
                    # Parse feedback and update bounding boxes
                    updates_applied = 0
                    for diagram in diagrams:
                        name = diagram['name']
                        
                        # Look for updated bbox
                        update_pattern = rf'<{re.escape(name)}>\s*<bbox>\s*([\d.,\s]+)\s*</bbox>\s*</{re.escape(name)}>'
                        update_match = re.search(update_pattern, feedback_response, re.DOTALL)
                        
                        if update_match:
                            bbox_str = update_match.group(1).strip()
                            try:
                                bbox_parts = [float(x.strip()) for x in bbox_str.split(',')]
                                if len(bbox_parts) == 4:
                                    old_bbox = diagram['bbox']
                                    diagram['bbox'] = tuple(bbox_parts)
                                    logger.info(f"✓ Updated bbox for {name}: {old_bbox} -> {diagram['bbox']}")
                                    updates_applied += 1
                            except ValueError:
                                logger.warning(f"Failed to parse updated bbox for {name}: {bbox_str}")
                        else:
                            # Check if marked as correct
                            correct_pattern = rf'<{re.escape(name)}>\s*correct\s*</{re.escape(name)}>'
                            if re.search(correct_pattern, feedback_response, re.IGNORECASE):
                                logger.info(f"✓ Bbox confirmed correct for {name}")
                    
                    logger.info(f"Feedback loop complete: {updates_applied} bounding boxes updated")
        
        return diagrams
        
    except Exception as e:
        logger.error(f"Error detecting diagrams: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []


def crop_image(image_path: Path, bbox: Tuple[float, float, float, float], output_path: Path) -> None:
    """
    Crop an image using normalized bounding box coordinates.
    
    Args:
        image_path: Path to source image
        bbox: Bounding box as (x1, y1, x2, y2) in 0-1 normalized range
        output_path: Path where cropped image should be saved
    """
    img = Image.open(image_path)
    width, height = img.size
    
    # Convert normalized bbox to pixel coordinates
    x1 = int(bbox[0] * width)
    y1 = int(bbox[1] * height)
    x2 = int(bbox[2] * width)
    y2 = int(bbox[3] * height)
    
    # Validate coordinates
    if x1 >= x2 or y1 >= y2:
        raise ValueError(f"Invalid bbox coordinates: {bbox}")
    
    # Crop and save
    cropped = img.crop((x1, y1, x2, y2))
    cropped.save(output_path)
    
    logger.info(f"Cropped image: {output_path.name} ({x2-x1}x{y2-y1} px)")


def extract_diagrams_from_pages(
    diagram_data: List[Dict], 
    page_png_dir: Path, 
    output_dir: Path
) -> Dict[str, str]:
    """
    Extract diagrams using bounding boxes and save as separate images.
    Also generates detailed descriptions for each extracted diagram.
    
    Args:
        diagram_data: List of diagram info [{"page": int, "bbox": tuple, "description": str, "name": str}, ...]
        page_png_dir: Directory containing page PNG files
        output_dir: Directory to save extracted diagrams
        
    Returns:
        Dictionary mapping diagram names to file paths {name: path}
    """
    if not diagram_data:
        logger.info("No diagrams to extract")
        return {}
    
    logger.info(f"Extracting {len(diagram_data)} diagrams...")
    
    extracted = {}
    
    for diagram in diagram_data:
        page_num = diagram['page']
        bbox = diagram['bbox']
        name = diagram['name']
        
        try:
            # Load page PNG
            page_png = page_png_dir / f"page_{page_num}.png"
            if not page_png.exists():
                logger.warning(f"Page PNG not found: {page_png}")
                continue
            
            # Extract diagram using crop
            output_path = output_dir / f"{name}.png"
            crop_image(page_png, bbox, output_path)
            
            extracted[name] = str(output_path)
            
        except Exception as e:
            logger.warning(f"Failed to extract diagram {name}: {e}")
    
    logger.info(f"✓ Successfully extracted {len(extracted)} diagrams")
    
    # Get detailed descriptions for extracted diagrams
    if extracted:
        # Build diagram paths and corresponding context paths (full page images)
        diagram_paths = []
        context_paths = []
        for diagram in diagram_data:
            diagram_path = output_dir / f"{diagram['name']}.png"
            if diagram_path.exists():
                diagram_paths.append(diagram_path)
                # Add corresponding page image as context
                page_png = page_png_dir / f"page_{diagram['page']}.png"
                context_paths.append(page_png if page_png.exists() else None)
        
        # Load engineering prompt for detailed descriptions
        prompt_path = Path(__file__).parent.parent / "prompts" / "engineering_image_analysis.md"
        system_prompt = prompt_path.read_text(encoding='utf-8') if prompt_path.exists() else ""
        
        logger.info("Getting detailed diagram descriptions with page context...")
        detailed = describe_images_with_claude(
            image_paths=diagram_paths,
            system_prompt=system_prompt,
            user_message_modifier="""IMPORTANT: For each diagram, I'm showing you:
1. The FULL PAGE - to understand the problem context, labels, and annotations
2. The CROPPED DIAGRAM - the specific figure to describe

Use the full page to understand what the diagram represents (problem statement, given values, etc.).
The cropped diagram may have captured some surrounding text - ignore peripheral artifacts.

Provide a DETAILED technical description including:
- What the diagram represents in the context of the problem
- All geometric shapes, dimensions, and spatial relationships
- All labels, variables, and annotations visible
- Force vectors, moments, and their directions
- Coordinate systems and reference points
- Enough detail to accurately reproduce the diagram""",
            context_image_paths=context_paths
        )
        
        # Update diagram_data with detailed descriptions (in-place)
        for diagram in diagram_data:
            filename = f"{diagram['name']}.png"
            if filename in detailed:
                diagram['description'] = detailed[filename].get('description', diagram['description'])
                logger.info(f"✓ Updated description for {diagram['name']}")
    
    return extracted



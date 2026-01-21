# PDF Parser - Modular Architecture

A modular PDF parsing system with multiple conversion approaches for different use cases.

## Architecture

The codebase is organized into clean, modular components:

```
pdf-parser/
├── processors/          # Conversion processors
│   ├── text_based_processor.py
│   ├── vision_guided_processor.py
│   ├── handwritten_processor.py
│   └── problem_solution_processor.py
├── utils/              # Utility modules
│   ├── pdf_utils.py
│   ├── image_utils.py
│   ├── output_utils.py
│   ├── page_range_utils.py
│   └── llm_utils.py
├── prompts/            # LLM prompts
├── main.py             # CLI entry point
└── requirements.txt
```

## Processors

### 1. TextBasedProcessor
**Use case:** Standard PDFs with text and embedded images

**How it works:**
- Extracts text and images using PyMuPDF
- Describes images with Claude Vision API
- Generates HTML using text content + image descriptions

**Command:**
```bash
python main.py --processor text-based document.pdf
```

### 2. VisionGuidedProcessor
**Use case:** PDFs requiring accurate layout preservation

**How it works:**
- Extracts text reference using PyMuPDF
- Renders each page as high-resolution PNG
- Sends page images + text reference to Claude Vision
- Generates HTML matching exact visual layout

**Command:**
```bash
python main.py --processor vision-guided document.pdf
```

### 3. HandwrittenProcessor
**Use case:** Handwritten exams or notes with diagrams

**How it works:**
- Renders all pages as PNG images
- Detects diagram bounding boxes with Claude Vision
- Extracts diagrams as separate images
- Transcribes handwritten content using Claude Opus 4.5 Thinking
- Generates HTML with transcribed text and embedded diagrams

**Command:**
```bash
python main.py --processor handwritten exam.pdf
```

### 4. ProblemSolutionProcessor
**Use case:** Exam PDFs with separate problem and solution sections

**How it works:**
- **Stage 1:** Generates HTML for problem pages using a base processor (text-based or vision-guided)
- **Stage 2:** Extracts solutions from solution pages and inserts them into problem HTML using Claude Opus 4.5 Thinking

**Command:**
```bash
python main.py --processor problem-solution \
  --problem-pages 1-4 \
  --solution-pages 5-end \
  --base-processor vision-guided \
  exam.pdf
```

## Usage Examples

### Single File Processing

```bash
# Text-based conversion
python main.py --processor text-based document.pdf

# Vision-guided conversion
python main.py --processor vision-guided document.pdf

# Handwritten with diagram extraction
python main.py --processor handwritten notes.pdf

# Problem-solution workflow
python main.py --processor problem-solution \
  --problem-pages 1-4 \
  --solution-pages 5-17 \
  exam.pdf
```

### Batch Processing (Parallel)

```bash
# Process multiple files in parallel
python main.py --processor handwritten exam1.pdf exam2.pdf exam3.pdf

# Process all PDFs in directory
python main.py --processor vision-guided *.pdf

# Control parallelism
python main.py --processor text-based --max-workers 4 *.pdf
```

### Development Options

```bash
# Keep temporary files for debugging
python main.py --processor handwritten --keep-temp exam.pdf
```

## Output

For each PDF, the system generates:

1. **HTML file:** `{pdf_name}.html` (next to original PDF)
2. **Images directory:** `images/{pdf_name}/` (next to original PDF)
3. **Image descriptions:** `images/{pdf_name}/image_descriptions.json` (if applicable)

### Temporary Files

During processing, intermediate files are stored in:
- `pdf-parser/tmp/{pdf_name}/`

These are automatically cleaned up unless `--keep-temp` is specified.

## Requirements

Install dependencies:

```bash
pip install -r requirements.txt
```

Required packages:
- `PyMuPDF` (fitz) - PDF operations
- `Pillow` - Image processing
- `anthropic` - Claude API
- `python-dotenv` - Environment variables
- `tenacity` - Retry logic
- `markdown` - Markdown conversion

## Environment Variables

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_api_key_here
```

## Architecture Benefits

### Modularity
- Each processor is independent (~200-300 lines)
- Utilities are reusable across processors
- Easy to add new processors without touching existing code

### Maintainability
- Clear separation of concerns
- Single responsibility per module
- Easy to test individual components

### Extensibility
- Add new processors by extending base pattern
- Customize utilities without affecting processors
- Swap out LLM models easily

## Adding a New Processor

1. Create new file in `processors/`
2. Follow the standard pattern:
   - Constructor accepts `pdf_path`, `temp_dir`, and configuration
   - Implement `process()` method that returns HTML string
   - Use utilities from `utils/` module
3. Add to `processors/__init__.py`
4. Add command-line option in `main.py`

Example skeleton:

```python
from pathlib import Path
from utils import open_pdf, llm_call, LLM

class MyCustomProcessor:
    def __init__(self, pdf_path: str, temp_dir: Path):
        self.pdf_path = Path(pdf_path)
        self.temp_dir = temp_dir
        self.doc = None
        
    def process(self) -> str:
        """Main processing method - returns HTML content."""
        self.doc = open_pdf(str(self.pdf_path))
        
        # Your custom logic here
        html = self._generate_html()
        
        if self.doc:
            self.doc.close()
        
        return html
        
    def _generate_html(self) -> str:
        # Implementation
        pass
```

## Troubleshooting

### Import Errors

If you get import errors, ensure you're running from the `pdf-parser` directory:

```bash
cd pdf-parser
python main.py --processor text-based input.pdf
```

### Memory Issues with Large PDFs

For very large PDFs or batch processing:
- Reduce `--max-workers` to limit parallelism
- Process files in smaller batches
- Use `--keep-temp` to debug memory issues

### Claude API Timeouts

For complex PDFs that timeout:
- The system has automatic retry logic (5 attempts with exponential backoff)
- Check your API quota and rate limits
- Consider breaking large PDFs into smaller sections

## License

See parent project for license information.



"""
LandingAI OCR Service for Aadhaar Document Extraction

Uses LandingAI DPT-2 (dpt-2-20251103) for:
1. Parsing document images to markdown
2. Extracting structured Aadhaar data using JSON schema

NOTE: Uses synchronous HTTP calls to avoid event loop issues with LangGraph.
"""

import base64
import json
import httpx
import os
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..config import settings


# OCR Output Directory for storing JSON responses
OCR_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "ocr_output")


def _ensure_output_dir():
    """Ensure the OCR output directory exists."""
    os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)


def _save_ocr_json(data: Dict, prefix: str) -> str:
    """
    Save OCR response JSON to local file for debugging.
    
    Args:
        data: The JSON data to save
        prefix: Prefix for the filename (e.g., 'parse_front', 'extract_back')
        
    Returns:
        Path to the saved file
    """
    _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OCR_OUTPUT_DIR, f"{prefix}_{timestamp}.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[OCR Debug] Saved: {filepath}")
        return filepath
    except Exception as e:
        print(f"[OCR Debug] Failed to save JSON: {e}")
        return ""


# LandingAI API Configuration
LANDINGAI_PARSE_URL = "https://api.va.landing.ai/v1/ade/parse"
LANDINGAI_EXTRACT_URL = "https://api.va.landing.ai/v1/ade/extract"
LANDINGAI_MODEL = "dpt-2-20251103"

# Aadhaar Extraction Schema
AADHAAR_FRONT_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {
            "title": "Full Name",
            "description": "The full name of the person as printed on the Aadhaar card",
            "type": "string"
        },
        "date_of_birth": {
            "title": "Date of Birth",
            "description": "Date of birth in DD/MM/YYYY or DD-MM-YYYY format",
            "type": "string"
        },
        "aadhaar_number": {
            "title": "Aadhaar Number",
            "description": "The 12-digit Aadhaar identification number, may have spaces",
            "type": "string"
        },
        "gender": {
            "title": "Gender",
            "description": "Gender: Male, Female, or Other",
            "type": "string"
        }
    },
    "required": ["full_name", "aadhaar_number"]
}

AADHAAR_BACK_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "title": "Address",
            "description": "Full residential address including house number, street, city, state and PIN code",
            "type": "string"
        },
        "aadhaar_number": {
            "title": "Aadhaar Number",
            "description": "The 12-digit Aadhaar identification number (for verification)",
            "type": "string"
        }
    },
    "required": ["address"]
}


@dataclass
class AadhaarData:
    """Extracted Aadhaar card data"""
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    aadhaar_number: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    raw_front_response: Optional[Dict[str, Any]] = None
    raw_back_response: Optional[Dict[str, Any]] = None
    extraction_error: Optional[str] = None


def _get_headers() -> Dict[str, str]:
    """Get authorization headers for LandingAI API."""
    return {
        "Authorization": f"Bearer {settings.landingai_api_key}"
    }


def _decode_base64_image(base64_string: str) -> bytes:
    """Decode base64 image string to bytes."""
    # Handle data URL format (data:image/jpeg;base64,...)
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    return base64.b64decode(base64_string)


def parse_document(image_base64: str) -> Dict[str, Any]:
    """
    Parse a document image using LandingAI ADE Parse API (synchronous).
    
    Args:
        image_base64: Base64 encoded image string
        
    Returns:
        Parsed document response with markdown content
    """
    if not settings.landingai_api_key:
        return {"error": "LANDINGAI_API_KEY not configured"}
    
    try:
        image_bytes = _decode_base64_image(image_base64)
        
        # Use synchronous httpx client
        with httpx.Client(timeout=60.0) as client:
            files = {
                "document": ("aadhaar.jpg", image_bytes, "image/jpeg")
            }
            data = {
                "model": LANDINGAI_MODEL
            }
            
            response = client.post(
                LANDINGAI_PARSE_URL,
                files=files,
                data=data,
                headers=_get_headers()
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "error": f"Parse API error: {response.status_code}",
                    "detail": response.text
                }
                
    except Exception as e:
        return {"error": f"Parse failed: {str(e)}"}


def extract_from_markdown(markdown: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured data from markdown using LandingAI ADE Extract API (synchronous).
    
    Args:
        markdown: Markdown content from parse step
        schema: JSON extraction schema
        
    Returns:
        Extracted data according to schema
    """
    if not settings.landingai_api_key:
        return {"error": "LANDINGAI_API_KEY not configured"}
    
    try:
        # Use synchronous httpx client
        with httpx.Client(timeout=30.0) as client:
            # Convert markdown to file-like object
            markdown_bytes = markdown.encode('utf-8')
            
            files = {
                "markdown": ("content.md", markdown_bytes, "text/markdown")
            }
            data = {
                "schema": json.dumps(schema),
                "model": "extract-latest"
            }
            
            response = client.post(
                LANDINGAI_EXTRACT_URL,
                files=files,
                data=data,
                headers=_get_headers()
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "error": f"Extract API error: {response.status_code}",
                    "detail": response.text
                }
                
    except Exception as e:
        return {"error": f"Extraction failed: {str(e)}"}


def process_aadhaar_front(image_base64: str) -> Dict[str, Any]:
    """
    Process Aadhaar front image: parse and extract data (synchronous).
    
    Args:
        image_base64: Base64 encoded image of Aadhaar front
        
    Returns:
        Dict with extracted data and raw responses
    """
    print("[OCR Debug] Processing Aadhaar front...")
    
    # Step 1: Parse the image
    parse_result = parse_document(image_base64)
    _save_ocr_json(parse_result, "parse_front")
    
    if "error" in parse_result:
        print(f"[OCR Debug] Parse error: {parse_result.get('error')}")
        return {"error": parse_result["error"], "raw_parse": parse_result}
    
    # Step 2: Extract data from markdown
    markdown = parse_result.get("markdown", "")
    print(f"[OCR Debug] Markdown length: {len(markdown)} chars")
    if not markdown:
        return {"error": "No markdown content from parse", "raw_parse": parse_result}
    
    extract_result = extract_from_markdown(markdown, AADHAAR_FRONT_SCHEMA)
    _save_ocr_json(extract_result, "extract_front")
    
    if "error" in extract_result:
        print(f"[OCR Debug] Extract error: {extract_result.get('error')}")
        return {
            "error": extract_result["error"],
            "raw_parse": parse_result,
            "raw_extract": extract_result
        }
    
    # Return combined result
    extraction = extract_result.get("extraction", {})
    print(f"[OCR Debug] Extracted front data: {extraction}")
    return {
        "full_name": extraction.get("full_name"),
        "date_of_birth": extraction.get("date_of_birth"),
        "aadhaar_number": _normalize_aadhaar_number(extraction.get("aadhaar_number")),
        "gender": extraction.get("gender"),
        "raw_parse": parse_result,
        "raw_extract": extract_result
    }


def process_aadhaar_back(image_base64: str) -> Dict[str, Any]:
    """
    Process Aadhaar back image: parse and extract address (synchronous).
    
    Args:
        image_base64: Base64 encoded image of Aadhaar back
        
    Returns:
        Dict with extracted address and raw responses
    """
    print("[OCR Debug] Processing Aadhaar back...")
    
    # Step 1: Parse the image
    parse_result = parse_document(image_base64)
    _save_ocr_json(parse_result, "parse_back")
    
    if "error" in parse_result:
        print(f"[OCR Debug] Parse error: {parse_result.get('error')}")
        return {"error": parse_result["error"], "raw_parse": parse_result}
    
    # Step 2: Extract data from markdown
    markdown = parse_result.get("markdown", "")
    print(f"[OCR Debug] Markdown length: {len(markdown)} chars")
    if not markdown:
        return {"error": "No markdown content from parse", "raw_parse": parse_result}
    
    extract_result = extract_from_markdown(markdown, AADHAAR_BACK_SCHEMA)
    _save_ocr_json(extract_result, "extract_back")
    
    if "error" in extract_result:
        print(f"[OCR Debug] Extract error: {extract_result.get('error')}")
        return {
            "error": extract_result["error"],
            "raw_parse": parse_result,
            "raw_extract": extract_result
        }
    
    # Return combined result
    extraction = extract_result.get("extraction", {})
    print(f"[OCR Debug] Extracted back data: {extraction}")
    return {
        "address": extraction.get("address"),
        "aadhaar_number_back": _normalize_aadhaar_number(extraction.get("aadhaar_number")),
        "raw_parse": parse_result,
        "raw_extract": extract_result
    }


def _normalize_aadhaar_number(raw_number: Optional[str]) -> Optional[str]:
    """
    Normalize Aadhaar number by removing spaces and validating format.
    
    Args:
        raw_number: Raw Aadhaar number string (may have spaces)
        
    Returns:
        12-digit Aadhaar number or None if invalid
    """
    if not raw_number:
        return None
    
    # Remove spaces, dashes, and other non-digits
    digits_only = ''.join(c for c in raw_number if c.isdigit())
    
    # Validate 12 digits
    if len(digits_only) == 12:
        return digits_only
    
    return raw_number  # Return original if can't normalize


def mask_aadhaar_number(aadhaar_number: str) -> str:
    """
    Mask Aadhaar number for display (show only last 4 digits).
    
    Args:
        aadhaar_number: Full 12-digit Aadhaar number
        
    Returns:
        Masked format: XXXX XXXX 1234
    """
    if not aadhaar_number or len(aadhaar_number) < 4:
        return "XXXX XXXX XXXX"
    
    last_four = aadhaar_number[-4:]
    return f"XXXX XXXX {last_four}"


def format_aadhaar_for_display(aadhaar_number: str) -> str:
    """
    Format Aadhaar number with spaces for display.
    
    Args:
        aadhaar_number: 12-digit Aadhaar number
        
    Returns:
        Formatted: 1234 5678 9012
    """
    if not aadhaar_number:
        return ""
    
    # Remove any existing formatting
    digits = ''.join(c for c in aadhaar_number if c.isdigit())
    
    if len(digits) == 12:
        return f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"
    
    return aadhaar_number

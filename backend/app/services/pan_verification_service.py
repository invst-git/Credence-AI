"""
PAN Verification Service - Verifies PAN against CIBIL records and cross-validates with Aadhaar.

Uses Supabase PostgreSQL to:
1. Look up PAN number in cibil_records table
2. Get credit score
3. Compare extracted Name/DOB with Aadhaar (exact match)
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..config import settings


# Minimum credit score required for loan approval
MIN_CREDIT_SCORE = 700


@dataclass
class CIBILRecord:
    """CIBIL record from database"""
    pan_number: str
    full_name: str
    date_of_birth: str
    phone_number: str
    address: str
    credit_score: int


@dataclass
class PANVerificationResult:
    """Result of PAN verification"""
    pan_found: bool
    credit_score: Optional[int] = None
    credit_approved: bool = False
    name_match: bool = False
    dob_match: bool = False
    is_verified: bool = False
    rejection_reason: Optional[str] = None
    mismatch_details: Optional[str] = None
    cibil_record: Optional[CIBILRecord] = None


def get_db_connection():
    """Get database connection to Supabase PostgreSQL."""
    if not settings.database_url:
        raise Exception("DATABASE_URL not configured")
    
    return psycopg2.connect(settings.database_url, cursor_factory=RealDictCursor)


def lookup_cibil_by_pan(pan_number: str) -> Optional[CIBILRecord]:
    """
    Look up a CIBIL record by PAN number.
    
    Args:
        pan_number: 10-character alphanumeric PAN
        
    Returns:
        CIBILRecord or None if not found
    """
    if not pan_number:
        return None
    
    # Normalize: uppercase, remove spaces
    pan_clean = pan_number.upper().replace(" ", "").strip()
    
    # Validate PAN format (10 alphanumeric)
    if len(pan_clean) != 10:
        print(f"[PAN Verification] Invalid PAN length: {len(pan_clean)}")
        return None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT pan_number, full_name, date_of_birth, phone_number, address, credit_score
            FROM cibil_records
            WHERE UPPER(REPLACE(pan_number, ' ', '')) = %s
            LIMIT 1
            """,
            (pan_clean,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return CIBILRecord(
                pan_number=result["pan_number"],
                full_name=result["full_name"],
                date_of_birth=str(result["date_of_birth"]),
                phone_number=result["phone_number"],
                address=result["address"],
                credit_score=int(result["credit_score"])
            )
        return None
        
    except Exception as e:
        print(f"[PAN Verification] Database lookup error: {e}")
        return None


def normalize_name(name: str) -> str:
    """Normalize name for exact comparison."""
    if not name:
        return ""
    # Remove extra spaces, convert to uppercase
    return " ".join(name.upper().split())


def normalize_dob(dob: str) -> str:
    """
    Normalize date of birth to YYYY-MM-DD format for comparison.
    Handles various input formats.
    """
    if not dob:
        return ""
    
    dob = dob.strip()
    
    # Already in YYYY-MM-DD
    if len(dob) == 10 and dob[4] == "-" and dob[7] == "-":
        return dob
    
    # DD/MM/YYYY or DD-MM-YYYY
    separators = ["/", "-", "."]
    for sep in separators:
        if sep in dob:
            parts = dob.split(sep)
            if len(parts) == 3:
                # Check if first part is year (YYYY-MM-DD)
                if len(parts[0]) == 4:
                    return f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                # DD/MM/YYYY format
                elif len(parts[2]) == 4:
                    return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    
    # Return as-is if can't parse
    return dob


def exact_match_name(pan_name: str, aadhaar_name: str) -> bool:
    """
    Exact match two names (case-insensitive, whitespace-normalized).
    
    Returns:
        True if names match exactly
    """
    norm_pan = normalize_name(pan_name)
    norm_aadhaar = normalize_name(aadhaar_name)
    
    return norm_pan == norm_aadhaar


def exact_match_dob(pan_dob: str, aadhaar_dob: str) -> bool:
    """
    Exact match two dates of birth.
    
    Returns:
        True if DOBs match exactly
    """
    norm_pan = normalize_dob(pan_dob)
    norm_aadhaar = normalize_dob(aadhaar_dob)
    
    return norm_pan == norm_aadhaar


def verify_pan(
    pan_number: str,
    pan_name: str,
    pan_dob: str,
    aadhaar_name: str,
    aadhaar_dob: str
) -> PANVerificationResult:
    """
    Verify PAN against CIBIL records and cross-validate with Aadhaar.
    
    Args:
        pan_number: Extracted PAN number from OCR
        pan_name: Extracted name from PAN OCR  
        pan_dob: Extracted DOB from PAN OCR
        aadhaar_name: Name from Aadhaar (already verified)
        aadhaar_dob: DOB from Aadhaar (already verified)
        
    Returns:
        PANVerificationResult with verification status
    """
    # Step 1: Lookup PAN in CIBIL database
    cibil_record = lookup_cibil_by_pan(pan_number)
    
    if not cibil_record:
        return PANVerificationResult(
            pan_found=False,
            rejection_reason=f"PAN number '{pan_number}' not found in our credit records. Please ensure the PAN is correct."
        )
    
    # Step 2: Check credit score
    credit_score = cibil_record.credit_score
    credit_approved = credit_score >= MIN_CREDIT_SCORE
    
    if not credit_approved:
        return PANVerificationResult(
            pan_found=True,
            credit_score=credit_score,
            credit_approved=False,
            cibil_record=cibil_record,
            rejection_reason=f"Your credit score ({credit_score}) does not meet our minimum requirement of {MIN_CREDIT_SCORE}. We are unable to proceed with your loan application at this time."
        )
    
    # Step 3: Exact match Name with Aadhaar
    name_match = exact_match_name(pan_name, aadhaar_name)
    
    # Step 4: Exact match DOB with Aadhaar
    dob_match = exact_match_dob(pan_dob, aadhaar_dob)
    
    # Step 5: Build mismatch details if any
    mismatch_parts = []
    if not name_match:
        mismatch_parts.append(
            f"**Name Mismatch:**\n"
            f"- PAN shows: '{pan_name}'\n"
            f"- Aadhaar shows: '{aadhaar_name}'"
        )
    if not dob_match:
        mismatch_parts.append(
            f"**Date of Birth Mismatch:**\n"
            f"- PAN shows: '{pan_dob}'\n"
            f"- Aadhaar shows: '{aadhaar_dob}'"
        )
    
    mismatch_details = "\n\n".join(mismatch_parts) if mismatch_parts else None
    
    # Overall verification
    is_verified = name_match and dob_match
    
    return PANVerificationResult(
        pan_found=True,
        credit_score=credit_score,
        credit_approved=True,
        name_match=name_match,
        dob_match=dob_match,
        is_verified=is_verified,
        mismatch_details=mismatch_details,
        cibil_record=cibil_record
    )


def extract_pan_from_ocr(ocr_result: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """
    Extract PAN number, name, and DOB from OCR result.
    
    Args:
        ocr_result: OCR result dictionary from LandingAI
        
    Returns:
        Dict with 'pan_number', 'full_name', 'date_of_birth' keys
    """
    import re
    
    result = {
        "pan_number": None,
        "full_name": None,
        "date_of_birth": None
    }
    
    if not ocr_result:
        print("[PAN OCR] No OCR result provided")
        return result
    
    # Get markdown content - check multiple possible locations
    markdown = ""
    
    # Path 1: data.markdown (LandingAI Parse Jobs response)
    if "data" in ocr_result and isinstance(ocr_result["data"], dict):
        markdown = ocr_result["data"].get("markdown", "")
    
    # Path 2: result.markdown (alternative format)
    if not markdown and "result" in ocr_result and isinstance(ocr_result["result"], dict):
        markdown = ocr_result["result"].get("markdown", "")
    
    # Path 3: Direct markdown field
    if not markdown:
        markdown = ocr_result.get("markdown", "")
    
    if not markdown:
        print("[PAN OCR] No markdown content found in OCR result")
        print(f"[PAN OCR] Available keys: {list(ocr_result.keys())}")
        return result
    
    print(f"[PAN OCR] Found markdown content ({len(markdown)} chars)")
    
    # Extract PAN number (10 alphanumeric, format: AAAAA1234A)
    pan_pattern = r'\b[A-Z]{5}[0-9]{4}[A-Z]\b'
    pan_matches = re.findall(pan_pattern, markdown.upper())
    if pan_matches:
        result["pan_number"] = pan_matches[0]
        print(f"[PAN OCR] Extracted PAN: {result['pan_number']}")
    
    # Extract DOB (various formats)
    dob_patterns = [
        r'(\d{2}[/-]\d{2}[/-]\d{4})',  # DD/MM/YYYY or DD-MM-YYYY
        r'(\d{4}[/-]\d{2}[/-]\d{2})',  # YYYY-MM-DD or YYYY/MM/DD
    ]
    for pattern in dob_patterns:
        dob_matches = re.findall(pattern, markdown)
        if dob_matches:
            result["date_of_birth"] = dob_matches[0]
            print(f"[PAN OCR] Extracted DOB: {result['date_of_birth']}")
            break
    
    # Extract name - look for text after "Name" or "नाम / Name" label
    # Pattern for: "नाम / Name\nDANDU VENKATA NITISH CHANDRA\nTEJA"
    name_patterns = [
        # Match name after "Name" label, possibly on next line(s)
        r"(?:नाम\s*/\s*Name|Name)\s*\n([A-Z][A-Z\s]+?)(?:\n\n|\n(?:[A-Z]{5}[0-9]{4}|पिता|Father))",
        # Match multi-line name
        r"(?:नाम\s*/\s*Name|Name)\s*\n([A-Z][A-Z\s\n]+?)(?:\n\nपिता|Father)",
        # Simple pattern after Name label
        r"(?:Name|नाम)\s*[:\-/]?\s*\n?([A-Z][A-Za-z\s]+)",
    ]
    
    for pattern in name_patterns:
        name_matches = re.findall(pattern, markdown, re.IGNORECASE | re.MULTILINE)
        if name_matches:
            # Clean up the name - join multiple lines, remove extra spaces
            name = " ".join(name_matches[0].split())
            # Remove common non-name words
            non_names = ["INCOME", "TAX", "DEPARTMENT", "GOVT", "INDIA", "PERMANENT", "ACCOUNT", "NUMBER", "CARD"]
            if not any(word in name.upper() for word in non_names) and len(name) > 3:
                result["full_name"] = name
                print(f"[PAN OCR] Extracted Name: {result['full_name']}")
                break
    
    return result


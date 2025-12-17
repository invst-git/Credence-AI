"""
Citizen Verification Service - Verifies Aadhaar details against database.

Uses Supabase PostgreSQL to:
1. Look up Aadhaar number in citizens table
2. Fuzzy match extracted details (name, DOB, address)
3. Return verification result with phone number for OTP
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from thefuzz import fuzz

from ..config import settings


# Fuzzy match thresholds
NAME_MATCH_THRESHOLD = 75  # 75% similarity required for names
ADDRESS_MATCH_THRESHOLD = 60  # 60% similarity for addresses (more lenient)


@dataclass
class VerificationResult:
    """Result of citizen verification"""
    is_verified: bool
    citizen_found: bool
    name_match: bool
    dob_match: bool
    address_match: bool
    phone_number: Optional[str] = None
    mismatch_details: Optional[str] = None
    db_record: Optional[Dict[str, Any]] = None


def get_db_connection():
    """Get database connection to Supabase PostgreSQL."""
    if not settings.database_url:
        raise Exception("DATABASE_URL not configured")
    
    return psycopg2.connect(settings.database_url, cursor_factory=RealDictCursor)


def lookup_citizen_by_aadhaar(aadhaar_number: str) -> Optional[Dict[str, Any]]:
    """
    Look up a citizen by Aadhaar number.
    
    Args:
        aadhaar_number: 12-digit Aadhaar number (digits only)
        
    Returns:
        Citizen record dict or None if not found
    """
    if not aadhaar_number:
        return None
    
    # Normalize: remove spaces
    aadhaar_clean = aadhaar_number.replace(" ", "").replace("-", "")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Query with normalized Aadhaar number
        cursor.execute(
            """
            SELECT id, aadhaar_number, full_name, date_of_birth, phone_number, gender
            FROM citizens
            WHERE REPLACE(REPLACE(aadhaar_number, ' ', ''), '-', '') = %s
            LIMIT 1
            """,
            (aadhaar_clean,)
        )
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return dict(result)
        return None
        
    except Exception as e:
        print(f"Database lookup error: {e}")
        return None


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    # Remove extra spaces, convert to uppercase
    return " ".join(name.upper().split())


def normalize_dob(dob: str) -> str:
    """Normalize date of birth for comparison."""
    if not dob:
        return ""
    # Remove separators and normalize format
    dob_clean = dob.replace("/", "").replace("-", "").replace(".", "")
    return dob_clean


def fuzzy_match_name(extracted: str, db_value: str) -> Tuple[bool, int]:
    """
    Fuzzy match two names.
    
    Returns:
        Tuple of (is_match, similarity_score)
    """
    if not extracted or not db_value:
        return False, 0
    
    norm_extracted = normalize_name(extracted)
    norm_db = normalize_name(db_value)
    
    # Use token sort ratio for better name matching
    # (handles "John Smith" vs "Smith John")
    score = fuzz.token_sort_ratio(norm_extracted, norm_db)
    
    return score >= NAME_MATCH_THRESHOLD, score


def match_dob(extracted: str, db_value: str) -> Tuple[bool, str]:
    """
    Match date of birth.
    
    Returns:
        Tuple of (is_match, reason)
    """
    if not extracted or not db_value:
        return False, "DOB not available"
    
    norm_extracted = normalize_dob(extracted)
    norm_db = normalize_dob(db_value)
    
    # Exact match after normalization
    if norm_extracted == norm_db:
        return True, "DOB matches"
    
    # Try partial match (in case year is different format)
    if len(norm_extracted) >= 8 and len(norm_db) >= 8:
        # Compare day/month at least
        if norm_extracted[:4] == norm_db[:4]:
            return True, "DOB partially matches (day/month match)"
    
    return False, f"DOB mismatch: OCR extracted '{extracted}', records show '{db_value}'"


def fuzzy_match_address(extracted: str, db_value: str) -> Tuple[bool, int]:
    """
    Fuzzy match addresses (more lenient).
    
    Returns:
        Tuple of (is_match, similarity_score)
    """
    if not extracted or not db_value:
        # Address matching is optional if not in DB
        return True, 100 if not db_value else 0
    
    # Normalize: uppercase, remove extra spaces
    norm_extracted = " ".join(extracted.upper().split())
    norm_db = " ".join(db_value.upper().split())
    
    # Use partial ratio for addresses (substrings match well)
    score = fuzz.partial_ratio(norm_extracted, norm_db)
    
    return score >= ADDRESS_MATCH_THRESHOLD, score


def verify_citizen(
    aadhaar_number: str,
    extracted_name: str,
    extracted_dob: str,
    extracted_address: Optional[str] = None
) -> VerificationResult:
    """
    Verify extracted Aadhaar details against database.
    
    Args:
        aadhaar_number: Extracted Aadhaar number
        extracted_name: Extracted name from OCR
        extracted_dob: Extracted DOB from OCR
        extracted_address: Extracted address from OCR (optional)
        
    Returns:
        VerificationResult with match details
    """
    # Step 1: Look up citizen by Aadhaar
    citizen = lookup_citizen_by_aadhaar(aadhaar_number)
    
    if not citizen:
        return VerificationResult(
            is_verified=False,
            citizen_found=False,
            name_match=False,
            dob_match=False,
            address_match=False,
            mismatch_details=f"Aadhaar number '{aadhaar_number}' not found in our records. Please ensure you have an account with us."
        )
    
    # Step 2: Fuzzy match name
    name_match, name_score = fuzzy_match_name(extracted_name, citizen.get("full_name"))
    
    # Step 3: Match DOB
    dob_match, dob_reason = match_dob(extracted_dob, citizen.get("date_of_birth"))
    
    # Step 4: Fuzzy match address (if provided)
    # Note: Our DB doesn't have address, so we'll skip this for now
    address_match = True  # Assume match since DB doesn't have address
    address_score = 100
    
    # Step 5: Determine overall verification
    is_verified = name_match and dob_match
    
    # Build mismatch details
    mismatch_parts = []
    if not name_match:
        mismatch_parts.append(
            f"Name mismatch (similarity: {name_score}%): OCR extracted '{extracted_name}', "
            f"records show '{citizen.get('full_name')}'"
        )
    if not dob_match:
        mismatch_parts.append(dob_reason)
    
    mismatch_details = "\n".join(mismatch_parts) if mismatch_parts else None
    
    return VerificationResult(
        is_verified=is_verified,
        citizen_found=True,
        name_match=name_match,
        dob_match=dob_match,
        address_match=address_match,
        phone_number=citizen.get("phone_number") if is_verified else None,
        mismatch_details=mismatch_details,
        db_record=citizen
    )


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for display.
    
    Args:
        phone: Full phone number
        
    Returns:
        Masked format: ******1234
    """
    if not phone or len(phone) < 4:
        return "**********"
    
    last_four = phone[-4:]
    return f"******{last_four}"

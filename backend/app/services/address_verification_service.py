"""
Address Proof Verification Service

Validates:
1. Name match with Aadhaar
2. Address match with Aadhaar (fuzzy 65%)
3. Document freshness (< 3 months old)
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from thefuzz import fuzz

from .llm_extraction_service import extract_address_proof_details


# Thresholds
NAME_MATCH_THRESHOLD = 80
ADDRESS_MATCH_THRESHOLD = 65
FRESHNESS_MONTHS = 3


@dataclass
class AddressVerificationResult:
    """Result of address proof verification"""
    is_verified: bool
    name_match: bool
    name_match_score: int = 0
    address_match: bool = False
    address_match_score: int = 0
    is_fresh: bool = False
    bill_date: Optional[str] = None
    document_type: Optional[str] = None
    extracted_name: Optional[str] = None
    extracted_address: Optional[str] = None
    failure_reason: Optional[str] = None
    requires_retry: bool = False
    extracted_data: Optional[Dict] = None


def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    return " ".join(text.upper().split())


def fuzzy_match(text1: str, text2: str, threshold: int) -> Tuple[bool, int]:
    """Fuzzy match two strings."""
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    
    # Use token_set_ratio for addresses (handles different ordering)
    score = fuzz.token_set_ratio(norm1, norm2)
    return score >= threshold, score


def check_freshness(bill_date_str: Optional[str], max_months: int = FRESHNESS_MONTHS) -> Tuple[bool, Optional[date]]:
    """
    Check if document is within freshness period.
    
    Returns:
        (is_fresh, parsed_date)
    """
    if not bill_date_str:
        return False, None
    
    try:
        bill_date = datetime.strptime(bill_date_str, "%Y-%m-%d").date()
        today = date.today()
        
        cutoff = today - relativedelta(months=max_months)
        is_fresh = bill_date >= cutoff
        
        return is_fresh, bill_date
    except:
        return False, None


def verify_address_proof(
    ocr_markdown: str,
    aadhaar_name: str,
    aadhaar_address: str
) -> AddressVerificationResult:
    """
    Verify address proof against requirements.
    
    Args:
        ocr_markdown: OCR markdown of address proof document
        aadhaar_name: Name from Aadhaar
        aadhaar_address: Address from Aadhaar
        
    Returns:
        AddressVerificationResult
    """
    # Extract details using LLM
    extracted = extract_address_proof_details(ocr_markdown)
    
    doc_name = extracted.get("name")
    doc_address = extracted.get("address")
    doc_type = extracted.get("document_type")
    bill_date_str = extracted.get("bill_date")
    
    # Check 1: Name match with Aadhaar
    name_match, name_score = fuzzy_match(doc_name or "", aadhaar_name, NAME_MATCH_THRESHOLD)
    
    if not name_match:
        return AddressVerificationResult(
            is_verified=False,
            name_match=False,
            name_match_score=name_score,
            extracted_name=doc_name,
            extracted_address=doc_address,
            document_type=doc_type,
            failure_reason=f"Name mismatch: Document shows '{doc_name}', Aadhaar shows '{aadhaar_name}' (Match: {name_score}%)",
            requires_retry=True,  # Allow one retry
            extracted_data=extracted
        )
    
    # Check 2: Address match with Aadhaar (fuzzy 65%)
    address_match, address_score = fuzzy_match(doc_address or "", aadhaar_address, ADDRESS_MATCH_THRESHOLD)
    
    if not address_match:
        return AddressVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            address_match=False,
            address_match_score=address_score,
            extracted_name=doc_name,
            extracted_address=doc_address,
            document_type=doc_type,
            failure_reason=f"Address mismatch: Document address does not match Aadhaar address (Match: {address_score}%)",
            requires_retry=False,  # Direct reject
            extracted_data=extracted
        )
    
    # Check 3: Document freshness (< 3 months)
    is_fresh, bill_date = check_freshness(bill_date_str)
    
    if not is_fresh:
        return AddressVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            address_match=True,
            address_match_score=address_score,
            is_fresh=False,
            bill_date=bill_date_str,
            extracted_name=doc_name,
            extracted_address=doc_address,
            document_type=doc_type,
            failure_reason=f"Document is outdated. Bill date: {bill_date_str}. Please provide a document from the last 3 months.",
            requires_retry=False,  # Direct reject
            extracted_data=extracted
        )
    
    # All checks passed
    return AddressVerificationResult(
        is_verified=True,
        name_match=True,
        name_match_score=name_score,
        address_match=True,
        address_match_score=address_score,
        is_fresh=True,
        bill_date=bill_date_str,
        document_type=doc_type,
        extracted_name=doc_name,
        extracted_address=doc_address,
        extracted_data=extracted
    )

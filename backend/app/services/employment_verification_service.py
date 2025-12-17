"""
Employment Certificate Verification Service

Validates:
1. Name match with Aadhaar (fuzzy 80%)
2. Work Experience: Total ≥1 year, Current job ≥6 months
3. Document Freshness: Issued within 6 months
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import date
from dateutil.relativedelta import relativedelta
from thefuzz import fuzz

from .llm_extraction_service import extract_employment_details
from ..config import settings


# Thresholds
NAME_MATCH_THRESHOLD = 80
MIN_TOTAL_EXPERIENCE_MONTHS = 12  # 1 year
MIN_CURRENT_JOB_MONTHS = 6
FRESHNESS_MONTHS = 6


@dataclass
class EmploymentVerificationResult:
    """Result of employment certificate verification"""
    is_verified: bool
    name_match: bool
    name_match_score: int = 0
    experience_valid: bool = False
    total_experience_months: Optional[int] = None
    current_job_months: Optional[int] = None
    is_fresh: bool = False
    issue_date: Optional[str] = None
    employer_name: Optional[str] = None
    employee_name: Optional[str] = None
    failure_reason: Optional[str] = None
    requires_retry: bool = False
    extracted_data: Optional[Dict] = None


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    return " ".join(name.upper().split())


def fuzzy_match_name(name1: str, name2: str, threshold: int = NAME_MATCH_THRESHOLD) -> tuple[bool, int]:
    """
    Fuzzy match two names.
    
    Returns:
        (is_match, score)
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    score = fuzz.token_sort_ratio(norm1, norm2)
    return score >= threshold, score


def check_document_freshness(issue_date_str: Optional[str], max_months: int = FRESHNESS_MONTHS) -> tuple[bool, Optional[date]]:
    """
    Check if document was issued within the specified months.
    
    Returns:
        (is_fresh, parsed_date)
    """
    if not issue_date_str:
        return False, None
    
    try:
        from datetime import datetime
        issue_date = datetime.strptime(issue_date_str, "%Y-%m-%d").date()
        today = date.today()
        
        cutoff = today - relativedelta(months=max_months)
        is_fresh = issue_date >= cutoff
        
        return is_fresh, issue_date
    except:
        return False, None


def verify_employment_certificate(
    ocr_markdown: str,
    aadhaar_name: str
) -> EmploymentVerificationResult:
    """
    Verify employment certificate against requirements.
    
    Args:
        ocr_markdown: OCR markdown content of the certificate
        aadhaar_name: Name from Aadhaar for comparison
        
    Returns:
        EmploymentVerificationResult with verification status
    """
    # Extract details using LLM
    extracted = extract_employment_details(ocr_markdown)
    
    employee_name = extracted.get("employee_name")
    employer_name = extracted.get("employer_name")
    total_exp_months = extracted.get("total_experience_months")
    issue_date_str = extracted.get("issue_date")
    joining_date_str = extracted.get("joining_date")
    
    # Check 1: Name match with Aadhaar (fuzzy 80%)
    name_match, name_score = fuzzy_match_name(employee_name or "", aadhaar_name)
    
    if not name_match:
        return EmploymentVerificationResult(
            is_verified=False,
            name_match=False,
            name_match_score=name_score,
            failure_reason=f"Name mismatch: Certificate shows '{employee_name}', Aadhaar shows '{aadhaar_name}' (Match: {name_score}%)",
            requires_retry=True,
            extracted_data=extracted,
            employee_name=employee_name,
            employer_name=employer_name
        )
    
    # Check 2: Work Experience
    # Calculate current job tenure from joining date
    current_job_months = None
    if joining_date_str:
        try:
            from datetime import datetime
            join_date = datetime.strptime(joining_date_str, "%Y-%m-%d").date()
            today = date.today()
            diff = relativedelta(today, join_date)
            current_job_months = diff.years * 12 + diff.months
        except:
            pass
    
    # Check experience requirements
    experience_valid = True
    exp_failure = None
    
    if total_exp_months is not None and total_exp_months < MIN_TOTAL_EXPERIENCE_MONTHS:
        experience_valid = False
        exp_failure = f"Total experience ({total_exp_months} months) is less than required ({MIN_TOTAL_EXPERIENCE_MONTHS} months)"
    
    if current_job_months is not None and current_job_months < MIN_CURRENT_JOB_MONTHS:
        experience_valid = False
        exp_failure = f"Current job tenure ({current_job_months} months) is less than required ({MIN_CURRENT_JOB_MONTHS} months)"
    
    if not experience_valid:
        return EmploymentVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            experience_valid=False,
            total_experience_months=total_exp_months,
            current_job_months=current_job_months,
            failure_reason=exp_failure,
            requires_retry=False,  # Direct reject for experience
            extracted_data=extracted,
            employee_name=employee_name,
            employer_name=employer_name
        )
    
    # Check 3: Document Freshness
    is_fresh, issue_date = check_document_freshness(issue_date_str)
    
    if not is_fresh and issue_date_str:
        return EmploymentVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            experience_valid=True,
            total_experience_months=total_exp_months,
            current_job_months=current_job_months,
            is_fresh=False,
            issue_date=issue_date_str,
            failure_reason=f"Employment certificate is outdated (issued on {issue_date_str}). Please provide a certificate issued within the last 6 months.",
            requires_retry=True,  # Warning, request fresh
            extracted_data=extracted,
            employee_name=employee_name,
            employer_name=employer_name
        )
    
    # All checks passed
    return EmploymentVerificationResult(
        is_verified=True,
        name_match=True,
        name_match_score=name_score,
        experience_valid=True,
        total_experience_months=total_exp_months,
        current_job_months=current_job_months,
        is_fresh=is_fresh,
        issue_date=issue_date_str,
        employer_name=employer_name,
        employee_name=employee_name,
        extracted_data=extracted
    )

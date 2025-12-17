"""
Salary Slip Verification Service

Validates:
1. Name match with Aadhaar (fuzzy 80%)
2. Consecutive months (last 2 consecutive months)
3. Gross salary matches declared income (±10%)
4. Employer matches Employment Certificate
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from thefuzz import fuzz

from .llm_extraction_service import extract_salary_slip_details
from ..config import settings


# Thresholds
NAME_MATCH_THRESHOLD = 80
EMPLOYER_MATCH_THRESHOLD = 80
INCOME_VARIANCE_PERCENT = 10


@dataclass
class SalaryVerificationResult:
    """Result of salary slip verification"""
    is_verified: bool
    name_match: bool
    name_match_score: int = 0
    consecutive_months: bool = False
    income_match: bool = False
    employer_match: bool = False
    employer_match_score: int = 0
    average_gross_salary: Optional[int] = None
    declared_income: Optional[int] = None
    slips_found: int = 0
    failure_reason: Optional[str] = None
    requires_retry: bool = False
    employer_warning: bool = False  # First warning before reject
    extracted_data: Optional[Dict] = None


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    return " ".join(name.upper().split())


def fuzzy_match_name(name1: str, name2: str, threshold: int = NAME_MATCH_THRESHOLD) -> tuple[bool, int]:
    """Fuzzy match two names."""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    score = fuzz.token_sort_ratio(norm1, norm2)
    return score >= threshold, score


def check_consecutive_months(slips: List[Dict]) -> tuple[bool, List[str]]:
    """
    Check if slips are from last 2 consecutive months.
    
    Returns:
        (is_consecutive, list of months found)
    """
    if len(slips) < 2:
        return False, []
    
    today = date.today()
    last_month = today - relativedelta(months=1)
    two_months_ago = today - relativedelta(months=2)
    
    # Expected months
    expected = {
        (last_month.year, last_month.month),
        (two_months_ago.year, two_months_ago.month)
    }
    
    # Found months
    found = set()
    months_list = []
    
    for slip in slips:
        year = slip.get("year")
        month = slip.get("month_number")
        if year and month:
            found.add((year, month))
            months_list.append(slip.get("month", f"{month}/{year}"))
    
    # Check if we have at least 2 consecutive months
    is_consecutive = len(found) >= 2
    
    # Also check chronological order
    if is_consecutive:
        sorted_months = sorted(found)
        for i in range(len(sorted_months) - 1):
            curr = sorted_months[i]
            next_m = sorted_months[i + 1]
            # Check if next month is consecutive
            curr_date = date(curr[0], curr[1], 1)
            next_date = date(next_m[0], next_m[1], 1)
            diff = relativedelta(next_date, curr_date)
            if diff.months != 1 and diff.years == 0:
                is_consecutive = False
                break
    
    return is_consecutive, months_list


def check_income_match(slips: List[Dict], declared_income: int) -> tuple[bool, int, float]:
    """
    Check if average gross salary matches declared income within ±10%.
    
    Returns:
        (is_match, average_salary, variance_percent)
    """
    if not slips or declared_income <= 0:
        return False, 0, 0
    
    gross_salaries = [s.get("gross_salary", 0) for s in slips if s.get("gross_salary")]
    
    if not gross_salaries:
        return False, 0, 0
    
    avg_salary = sum(gross_salaries) // len(gross_salaries)
    
    # Calculate variance
    variance = abs(avg_salary - declared_income) / declared_income * 100
    
    is_match = variance <= INCOME_VARIANCE_PERCENT
    
    return is_match, avg_salary, variance


def verify_salary_slips(
    ocr_markdown: str,
    aadhaar_name: str,
    declared_monthly_income: int,
    employment_cert_employer: Optional[str] = None,
    employer_warning_given: bool = False
) -> SalaryVerificationResult:
    """
    Verify salary slips against requirements.
    
    Args:
        ocr_markdown: OCR markdown of salary slips PDF
        aadhaar_name: Name from Aadhaar
        declared_monthly_income: Income declared during eligibility
        employment_cert_employer: Employer name from Employment Certificate
        employer_warning_given: Whether employer mismatch warning was already given
        
    Returns:
        SalaryVerificationResult
    """
    # Extract details using LLM
    extracted = extract_salary_slip_details(ocr_markdown)
    
    employee_name = extracted.get("employee_name")
    employer_name = extracted.get("employer_name")
    slips = extracted.get("slips", [])
    
    # Check 1: Name match with Aadhaar
    name_match, name_score = fuzzy_match_name(employee_name or "", aadhaar_name)
    
    if not name_match:
        return SalaryVerificationResult(
            is_verified=False,
            name_match=False,
            name_match_score=name_score,
            slips_found=len(slips),
            failure_reason=f"Name mismatch: Salary slip shows '{employee_name}', Aadhaar shows '{aadhaar_name}' (Match: {name_score}%)",
            requires_retry=False,  # Direct reject
            extracted_data=extracted
        )
    
    # Check 2: Consecutive months
    consecutive, months_found = check_consecutive_months(slips)
    
    if not consecutive:
        return SalaryVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            consecutive_months=False,
            slips_found=len(slips),
            failure_reason=f"Salary slips must be for last 2 consecutive months. Found: {', '.join(months_found) if months_found else 'None'}",
            requires_retry=True,  # Request correct slips
            extracted_data=extracted
        )
    
    # Check 3: Income match (±10%)
    income_match, avg_salary, variance = check_income_match(slips, declared_monthly_income)
    
    if not income_match:
        return SalaryVerificationResult(
            is_verified=False,
            name_match=True,
            name_match_score=name_score,
            consecutive_months=True,
            income_match=False,
            average_gross_salary=avg_salary,
            declared_income=declared_monthly_income,
            slips_found=len(slips),
            failure_reason=f"Income mismatch: Salary slips show avg ₹{avg_salary:,}/month, you declared ₹{declared_monthly_income:,}/month (variance: {variance:.1f}%)",
            requires_retry=False,  # Direct reject
            extracted_data=extracted
        )
    
    # Check 4: Employer match with Employment Certificate
    if employment_cert_employer:
        emp_match, emp_score = fuzzy_match_name(employer_name or "", employment_cert_employer)
        
        if not emp_match:
            if not employer_warning_given:
                # First warning
                return SalaryVerificationResult(
                    is_verified=False,
                    name_match=True,
                    name_match_score=name_score,
                    consecutive_months=True,
                    income_match=True,
                    employer_match=False,
                    employer_match_score=emp_score,
                    average_gross_salary=avg_salary,
                    declared_income=declared_monthly_income,
                    slips_found=len(slips),
                    failure_reason=f"Employer mismatch: Salary slip shows '{employer_name}', Employment Certificate shows '{employment_cert_employer}' (Match: {emp_score}%)",
                    requires_retry=True,
                    employer_warning=True,  # Warning flag
                    extracted_data=extracted
                )
            else:
                # Second attempt - reject
                return SalaryVerificationResult(
                    is_verified=False,
                    name_match=True,
                    name_match_score=name_score,
                    consecutive_months=True,
                    income_match=True,
                    employer_match=False,
                    employer_match_score=emp_score,
                    average_gross_salary=avg_salary,
                    declared_income=declared_monthly_income,
                    slips_found=len(slips),
                    failure_reason=f"Employer mismatch persists after retry. Cannot proceed.",
                    requires_retry=False,  # Reject
                    extracted_data=extracted
                )
    
    # All checks passed
    return SalaryVerificationResult(
        is_verified=True,
        name_match=True,
        name_match_score=name_score,
        consecutive_months=True,
        income_match=True,
        employer_match=True,
        average_gross_salary=avg_salary,
        declared_income=declared_monthly_income,
        slips_found=len(slips),
        extracted_data=extracted
    )

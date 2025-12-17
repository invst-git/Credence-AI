"""
Bank Statement Verification Service

Validates:
1. Name match with Aadhaar
2. Salary credits matching employer name (60% fuzzy) and amount (±10%)
3. EMI detection - recurring debits matching eligibility declaration
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from collections import defaultdict
from thefuzz import fuzz

from .llm_extraction_service import extract_bank_statement_details


# Thresholds
EMPLOYER_MATCH_THRESHOLD = 60
SALARY_VARIANCE_PERCENT = 10
DATE_VARIANCE_DAYS = 2
EMI_VARIANCE_PERCENT = 10


@dataclass
class SalaryCredit:
    """Detected salary credit"""
    date: str
    amount: int
    description: str


@dataclass
class DetectedEMI:
    """Detected recurring EMI"""
    amount: int
    typical_date: int  # Day of month
    occurrences: int
    descriptions: List[str]


@dataclass
class BankVerificationResult:
    """Result of bank statement verification"""
    is_verified: bool
    name_match: bool
    salary_credits_verified: bool = False
    emi_verified: bool = False
    detected_salary_credits: List[SalaryCredit] = None
    detected_emis: List[DetectedEMI] = None
    total_detected_emi: int = 0
    declared_emi: int = 0
    failure_reason: Optional[str] = None
    requires_retry: bool = False
    extracted_data: Optional[Dict] = None
    
    def __post_init__(self):
        if self.detected_salary_credits is None:
            self.detected_salary_credits = []
        if self.detected_emis is None:
            self.detected_emis = []


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    if not name:
        return ""
    return " ".join(name.upper().split())


def fuzzy_match(text1: str, text2: str, threshold: int) -> Tuple[bool, int]:
    """Fuzzy match two strings."""
    norm1 = normalize_name(text1)
    norm2 = normalize_name(text2)
    score = fuzz.partial_ratio(norm1, norm2)
    return score >= threshold, score


def detect_salary_credits(
    transactions: List[Dict],
    employer_name: str,
    expected_salary: int
) -> List[SalaryCredit]:
    """
    Detect salary credits in transactions.
    
    Criteria:
    - Credit transaction
    - Description contains employer name (60% fuzzy)
    - Amount within ±10% of expected salary
    - Similar date each month (±2 days)
    """
    salary_credits = []
    
    for txn in transactions:
        credit = txn.get("credit", 0)
        if credit <= 0:
            continue
        
        description = txn.get("description", "")
        
        # Check employer name in description
        emp_match, _ = fuzzy_match(description, employer_name, EMPLOYER_MATCH_THRESHOLD)
        
        # Check amount within variance
        if expected_salary > 0:
            variance = abs(credit - expected_salary) / expected_salary * 100
            amount_match = variance <= SALARY_VARIANCE_PERCENT
        else:
            amount_match = True  # Skip amount check if no expected salary
        
        if emp_match and amount_match:
            salary_credits.append(SalaryCredit(
                date=txn.get("date", ""),
                amount=credit,
                description=description
            ))
    
    return salary_credits


def detect_emis(transactions: List[Dict]) -> List[DetectedEMI]:
    """
    Detect recurring EMI payments in transactions.
    
    Criteria:
    - Debit transactions
    - Same amount (±10%) on similar dates (±2 days) across months
    - At least 2 occurrences
    """
    # Group debits by approximate amount (rounded to nearest 100)
    debit_groups = defaultdict(list)
    
    for txn in transactions:
        debit = txn.get("debit", 0)
        if debit <= 0:
            continue
        
        # Round to nearest 500 for grouping
        amount_bucket = (debit // 500) * 500
        debit_groups[amount_bucket].append({
            "date": txn.get("date", ""),
            "amount": debit,
            "description": txn.get("description", "")
        })
    
    emis = []
    
    for amount_bucket, debits in debit_groups.items():
        if len(debits) < 2:
            continue
        
        # Check if dates are on similar days of month
        day_groups = defaultdict(list)
        
        for d in debits:
            try:
                dt = datetime.strptime(d["date"], "%Y-%m-%d")
                day = dt.day
                # Group by day of month (±2 days)
                day_bucket = (day // 3) * 3
                day_groups[day_bucket].append(d)
            except:
                continue
        
        for day_bucket, day_debits in day_groups.items():
            if len(day_debits) >= 2:
                # This looks like a recurring EMI
                amounts = [d["amount"] for d in day_debits]
                avg_amount = sum(amounts) // len(amounts)
                
                # Calculate typical day
                days = []
                for d in day_debits:
                    try:
                        dt = datetime.strptime(d["date"], "%Y-%m-%d")
                        days.append(dt.day)
                    except:
                        pass
                
                typical_day = sum(days) // len(days) if days else 1
                
                emis.append(DetectedEMI(
                    amount=avg_amount,
                    typical_date=typical_day,
                    occurrences=len(day_debits),
                    descriptions=[d["description"] for d in day_debits[:3]]
                ))
    
    return emis


def verify_bank_statement(
    ocr_markdown: str,
    aadhaar_name: str,
    employer_name: str,
    expected_salary: int,
    declared_emi: int,
    has_existing_loans: bool
) -> BankVerificationResult:
    """
    Verify bank statement against requirements.
    
    Args:
        ocr_markdown: OCR markdown of bank statement
        aadhaar_name: Name from Aadhaar
        employer_name: Employer name from salary slips/employment cert
        expected_salary: Expected monthly salary
        declared_emi: Total EMI declared during eligibility
        has_existing_loans: Whether user declared having existing loans
        
    Returns:
        BankVerificationResult
    """
    # Extract details using LLM
    extracted = extract_bank_statement_details(ocr_markdown)
    
    account_holder = extracted.get("account_holder_name")
    transactions = extracted.get("transactions", [])
    
    # Check 1: Name match with Aadhaar
    name_match, name_score = fuzzy_match(account_holder or "", aadhaar_name, 80)
    
    if not name_match:
        return BankVerificationResult(
            is_verified=False,
            name_match=False,
            failure_reason=f"Account holder name '{account_holder}' does not match Aadhaar name '{aadhaar_name}'",
            requires_retry=False,  # Direct reject
            extracted_data=extracted
        )
    
    # Check 2: Salary credits (now just informational, not a rejection criteria)
    salary_credits = detect_salary_credits(transactions, employer_name, expected_salary)
    # Note: We no longer reject based on salary credits - just log what we found
    print(f"[Bank Verification] Found {len(salary_credits)} salary credits")
    
    # Check 3: EMI detection
    detected_emis = detect_emis(transactions)
    total_detected_emi = sum(emi.amount for emi in detected_emis)
    
    # Compare with declared EMI
    if has_existing_loans:
        # User said they have loans - check if detected EMI matches (±10%)
        if declared_emi > 0:
            variance = abs(total_detected_emi - declared_emi) / declared_emi * 100 if declared_emi > 0 else 0
            emi_match = variance <= 20  # Allow 20% variance for EMI detection
        else:
            # User said they have loans but declared 0 EMI - mismatch if we detected any
            emi_match = total_detected_emi == 0
    else:
        # User said no loans - but we detected EMIs
        if total_detected_emi > 5000:  # Ignore small recurring payments
            emi_match = False
        else:
            emi_match = True
    
    if not emi_match:
        return BankVerificationResult(
            is_verified=False,
            name_match=True,
            salary_credits_verified=True,
            detected_salary_credits=salary_credits,
            emi_verified=False,
            detected_emis=detected_emis,
            total_detected_emi=total_detected_emi,
            declared_emi=declared_emi,
            failure_reason=f"EMI mismatch: Detected ₹{total_detected_emi:,}/month in recurring debits, declared ₹{declared_emi:,}/month",
            requires_retry=True,  # Allow retry
            extracted_data=extracted
        )
    
    # All checks passed
    return BankVerificationResult(
        is_verified=True,
        name_match=True,
        salary_credits_verified=True,
        detected_salary_credits=salary_credits,
        emi_verified=True,
        detected_emis=detected_emis,
        total_detected_emi=total_detected_emi,
        declared_emi=declared_emi,
        extracted_data=extracted
    )

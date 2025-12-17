"""
Underwriting Service - Final scoring and decision making for loan applications.

Scoring Matrix (100 points max):
- CIBIL Score (40%): 750+: 40pts, 700-749: 30pts, <700: 0pts
- FOIR (30%): ≤40%: 30pts, 41-50%: 20pts, >50%: 0pts
- Employment Stability (15%): >2yrs: 15pts, 1-2yrs: 10pts, <1yr: 5pts
- Income Verification (10%): <10% variance: 10pts, 10-20%: 5pts, >20%: 0pts
- Bank Balance (5%): >3x EMI: 5pts, 1-3x: 3pts, <1x: 0pts

Decision:
- ≥70: Approve
- 50-69: Conditional (co-applicant or modified terms)
- <50: Reject
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class ScoreBreakdown:
    """Individual score component"""
    factor: str
    weight: int
    score: int
    max_score: int
    reason: str


@dataclass
class UnderwritingResult:
    """Result of underwriting decision"""
    total_score: int
    decision: str  # "approved", "conditional", "rejected"
    breakdown: List[ScoreBreakdown]
    loan_amount: int
    interest_rate: float
    tenure_months: int
    emi: int
    processing_fee: int
    total_interest: int
    total_payable: int
    conditions: Optional[List[str]] = None
    rejection_reasons: Optional[List[str]] = None
    suggested_amount: Optional[int] = None
    suggested_tenure: Optional[int] = None


def calculate_cibil_score_points(cibil_score: int) -> tuple[int, str]:
    """
    Calculate CIBIL score points (40% weight).
    750+: 40pts, 700-749: 30pts, <700: 0pts
    """
    if cibil_score >= 750:
        return 40, f"Excellent CIBIL score ({cibil_score})"
    elif cibil_score >= 700:
        return 30, f"Good CIBIL score ({cibil_score})"
    else:
        return 0, f"Low CIBIL score ({cibil_score})"


def calculate_foir_points(foir_percentage: float) -> tuple[int, str]:
    """
    Calculate FOIR points (30% weight).
    ≤40%: 30pts, 41-50%: 20pts, >50%: 0pts
    """
    if foir_percentage <= 40:
        return 30, f"Excellent FOIR ({foir_percentage:.1f}%)"
    elif foir_percentage <= 50:
        return 20, f"Acceptable FOIR ({foir_percentage:.1f}%)"
    else:
        return 0, f"High FOIR ({foir_percentage:.1f}%)"


def calculate_employment_stability_points(current_job_months: int) -> tuple[int, str]:
    """
    Calculate employment stability points (15% weight).
    >2yrs: 15pts, 1-2yrs: 10pts, <1yr: 5pts
    """
    if current_job_months >= 24:
        return 15, f"Stable employment ({current_job_months} months)"
    elif current_job_months >= 12:
        return 10, f"Moderate employment tenure ({current_job_months} months)"
    else:
        return 5, f"Short employment tenure ({current_job_months} months)"


def calculate_income_verification_points(declared: int, verified: int) -> tuple[int, str]:
    """
    Calculate income verification points (10% weight).
    <10% variance: 10pts, 10-20%: 5pts, >20%: 0pts
    """
    if declared <= 0:
        return 0, "No declared income"
    
    variance = abs(verified - declared) / declared * 100
    
    if variance < 10:
        return 10, f"Income verified (variance {variance:.1f}%)"
    elif variance <= 20:
        return 5, f"Income partially verified (variance {variance:.1f}%)"
    else:
        return 0, f"Income mismatch (variance {variance:.1f}%)"


def calculate_bank_balance_points(closing_balance: int, monthly_emi: int) -> tuple[int, str]:
    """
    Calculate bank balance points (5% weight).
    >3x EMI: 5pts, 1-3x: 3pts, <1x: 0pts
    """
    if monthly_emi <= 0:
        return 3, "No EMI to compare"
    
    ratio = closing_balance / monthly_emi
    
    if ratio > 3:
        return 5, f"Healthy bank balance ({ratio:.1f}x EMI)"
    elif ratio >= 1:
        return 3, f"Adequate bank balance ({ratio:.1f}x EMI)"
    else:
        return 0, f"Low bank balance ({ratio:.1f}x EMI)"


def calculate_emi(principal: int, annual_rate: float, tenure_months: int) -> int:
    """Calculate EMI using standard formula."""
    if tenure_months <= 0 or annual_rate <= 0:
        return principal // max(tenure_months, 1)
    
    monthly_rate = annual_rate / 12 / 100
    emi = principal * monthly_rate * ((1 + monthly_rate) ** tenure_months) / (((1 + monthly_rate) ** tenure_months) - 1)
    return int(emi)


def perform_underwriting(
    cibil_score: int,
    foir_percentage: float,
    current_job_months: int,
    declared_income: int,
    verified_income: int,
    closing_balance: int,
    loan_amount: int,
    interest_rate: float,
    tenure_months: int,
    processing_fee_rate: float = 1.5  # 1.5% of loan amount
) -> UnderwritingResult:
    """
    Perform final underwriting and return decision.
    
    Args:
        cibil_score: Credit score from CIBIL
        foir_percentage: Fixed Obligation to Income Ratio
        current_job_months: Months in current job
        declared_income: Monthly income declared by user
        verified_income: Income verified from salary slips
        closing_balance: Bank account closing balance
        loan_amount: Requested loan amount
        interest_rate: Annual interest rate (%)
        tenure_months: Loan tenure in months
        processing_fee_rate: Processing fee as % of loan
        
    Returns:
        UnderwritingResult with decision and details
    """
    # Calculate EMI first (needed for bank balance scoring)
    monthly_emi = calculate_emi(loan_amount, interest_rate, tenure_months)
    
    # Calculate individual scores
    breakdown = []
    
    # 1. CIBIL Score (40%)
    cibil_pts, cibil_reason = calculate_cibil_score_points(cibil_score)
    breakdown.append(ScoreBreakdown("CIBIL Score", 40, cibil_pts, 40, cibil_reason))
    
    # 2. FOIR (30%)
    foir_pts, foir_reason = calculate_foir_points(foir_percentage)
    breakdown.append(ScoreBreakdown("FOIR", 30, foir_pts, 30, foir_reason))
    
    # 3. Employment Stability (15%)
    emp_pts, emp_reason = calculate_employment_stability_points(current_job_months)
    breakdown.append(ScoreBreakdown("Employment Stability", 15, emp_pts, 15, emp_reason))
    
    # 4. Income Verification (10%)
    income_pts, income_reason = calculate_income_verification_points(declared_income, verified_income)
    breakdown.append(ScoreBreakdown("Income Verification", 10, income_pts, 10, income_reason))
    
    # 5. Bank Balance (5%)
    bank_pts, bank_reason = calculate_bank_balance_points(closing_balance, monthly_emi)
    breakdown.append(ScoreBreakdown("Bank Balance", 5, bank_pts, 5, bank_reason))
    
    # Total score
    total_score = cibil_pts + foir_pts + emp_pts + income_pts + bank_pts
    
    # Calculate loan details
    processing_fee = int(loan_amount * processing_fee_rate / 100)
    total_interest = (monthly_emi * tenure_months) - loan_amount
    total_payable = loan_amount + total_interest + processing_fee
    
    # Make decision
    if total_score >= 70:
        decision = "approved"
        conditions = None
        rejection_reasons = None
        suggested_amount = None
        suggested_tenure = None
    elif total_score >= 50:
        decision = "conditional"
        conditions = []
        
        # Suggest modifications based on weak areas
        if foir_pts < 20:
            # Suggest lower loan amount or longer tenure
            suggested_amount = int(loan_amount * 0.7)  # 30% reduction
            suggested_tenure = min(tenure_months + 12, 84)  # Add 12 months, max 84
            conditions.append(f"Consider reduced loan amount of ₹{suggested_amount:,}")
            conditions.append(f"Or extend tenure to {suggested_tenure} months for lower EMI")
        
        if emp_pts < 15:
            conditions.append("Add a co-applicant with stable employment")
        
        if cibil_pts < 40:
            conditions.append("Add a co-applicant with higher credit score")
        
        if not conditions:
            conditions.append("Add a co-applicant with stable income")
        
        rejection_reasons = None
    else:
        decision = "rejected"
        conditions = None
        
        # Explain rejection reasons
        rejection_reasons = []
        for item in breakdown:
            if item.score < item.max_score * 0.5:  # Less than 50% of max
                rejection_reasons.append(item.reason)
        
        if not rejection_reasons:
            rejection_reasons.append("Overall score does not meet minimum requirements")
        
        suggested_amount = None
        suggested_tenure = None
    
    return UnderwritingResult(
        total_score=total_score,
        decision=decision,
        breakdown=breakdown,
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        tenure_months=tenure_months,
        emi=monthly_emi,
        processing_fee=processing_fee,
        total_interest=total_interest,
        total_payable=total_payable,
        conditions=conditions,
        rejection_reasons=rejection_reasons,
        suggested_amount=suggested_amount,
        suggested_tenure=suggested_tenure
    )


def format_loan_details_table(result: UnderwritingResult) -> str:
    """Format loan details as a markdown table for display."""
    table = """
| Detail | Value |
|--------|-------|
| Loan Amount | ₹{:,} |
| Interest Rate | {:.2f}% p.a. |
| Tenure | {} months |
| Monthly EMI | ₹{:,} |
| Processing Fee | ₹{:,} |
| Total Interest | ₹{:,} |
| **Total Payable** | **₹{:,}** |
""".format(
        result.loan_amount,
        result.interest_rate,
        result.tenure_months,
        result.emi,
        result.processing_fee,
        result.total_interest,
        result.total_payable
    )
    return table.strip()


def format_score_breakdown(result: UnderwritingResult) -> str:
    """Format score breakdown as markdown."""
    lines = ["| Factor | Score | Max |", "|--------|-------|-----|"]
    for item in result.breakdown:
        lines.append(f"| {item.factor} | {item.score} | {item.max_score} |")
    lines.append(f"| **Total** | **{result.total_score}** | **100** |")
    return "\n".join(lines)

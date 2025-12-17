from typing import Dict
from math import pow
from ..state import EligibilityState
from ..config import settings


def _emi(principal: int, tenure_months: int) -> int:
    r = settings.annual_interest_rate / 12.0
    n = tenure_months
    if principal <= 0 or n <= 0 or r <= 0:
        return 0
    num = principal * r * pow(1 + r, n)
    den = pow(1 + r, n) - 1
    if den == 0:
        return 0
    return int(num / den)


def _has_all_required_fields(state: EligibilityState) -> bool:
    """Check if all required fields are present based on employment type."""
    if state.get("age_years") is None:
        return False
    if state.get("employment_type") not in ("salaried", "self_employed"):
        return False
    
    # Bug 3 Fix: Check appropriate income field based on employment type
    emp_type = state.get("employment_type")
    if emp_type == "salaried" and state.get("monthly_income") is None:
        return False
    if emp_type == "self_employed":
        # Self-employed can have either annual_income or monthly_income (derived)
        if state.get("monthly_income") is None and state.get("annual_income") is None:
            return False
    
    if state.get("has_existing_loans") is None or state.get("total_existing_emi") is None:
        return False
    if state.get("requested_loan_amount") is None or state.get("requested_tenure_months") is None:
        return False

    if emp_type == "salaried":
        if state.get("total_experience_months") is None:
            return False
        if state.get("current_job_months") is None:
            return False
    elif emp_type == "self_employed":
        if state.get("business_vintage_months") is None:
            return False

    return True


def apply_hard_rules(state: EligibilityState) -> Dict:
    updates: Dict = {}

    if state.get("done"):
        return {}

    age = state.get("age_years")
    emp_type = state.get("employment_type")
    monthly_income = state.get("monthly_income")
    annual_income = state.get("annual_income")
    total_exp = state.get("total_experience_months")
    current_job = state.get("current_job_months")
    business_vintage = state.get("business_vintage_months")
    total_existing_emi = state.get("total_existing_emi")
    requested_loan_amount = state.get("requested_loan_amount")
    requested_tenure_months = state.get("requested_tenure_months")

    # 1. Age gate
    if age is not None:
        if age < settings.min_age or age > settings.max_age:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Age criteria not met: your age is {age}, but eligibility requires between "
                f"{settings.min_age} and {settings.max_age} years."
            )
            return updates

    # 2. Employment type gate
    if emp_type is not None and emp_type not in ("salaried", "self_employed"):
        updates["is_eligible"] = False
        updates["done"] = True
        updates["ineligibility_reason"] = (
            "To be eligible, you must be either salaried or self-employed with a running business."
        )
        return updates

    # 3. Income gates
    if emp_type == "salaried" and monthly_income is not None:
        if monthly_income < settings.min_salaried_income:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Income criteria not met: your monthly income is Rs {monthly_income:,}, "
                f"but the minimum required for salaried applicants is Rs {settings.min_salaried_income:,}."
            )
            return updates

    if emp_type == "self_employed" and annual_income is not None:
        if annual_income < settings.min_self_employed_income_annual:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Income criteria not met: your annual income is Rs {annual_income:,}, "
                f"but the minimum required for self-employed applicants is "
                f"Rs {settings.min_self_employed_income_annual:,}."
            )
            return updates

    # 4. Experience / vintage
    if emp_type == "salaried":
        if total_exp is not None and total_exp < settings.min_total_exp_months:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Work experience criteria not met: you have {total_exp} months of experience, "
                f"but at least {settings.min_total_exp_months} months (1 year) total is required."
            )
            return updates
        if current_job is not None and current_job < settings.min_current_job_months:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Current job stability criteria not met: you have been in your current job for "
                f"{current_job} months, but at least {settings.min_current_job_months} months are required."
            )
            return updates

    if emp_type == "self_employed" and business_vintage is not None:
        if business_vintage < settings.min_business_vintage_months:
            updates["is_eligible"] = False
            updates["done"] = True
            updates["ineligibility_reason"] = (
                f"Business vintage criteria not met: your business is {business_vintage} months old, "
                f"but it must be at least {settings.min_business_vintage_months} months (1 year) old."
            )
            return updates

    # 5. Max loan cap
    if requested_loan_amount is not None and requested_loan_amount > settings.max_loan_amount:
        updates["is_eligible"] = False
        updates["done"] = True
        updates["ineligibility_reason"] = (
            f"Loan amount exceeds product limit: you requested Rs {requested_loan_amount:,}, "
            f"but Tata Capital personal loans are capped at Rs {settings.max_loan_amount:,}."
        )
        return updates

    # 6. FOIR - triggers sales mode, not hard stop
    if (
        monthly_income is not None
        and total_existing_emi is not None
        and requested_loan_amount is not None
        and requested_tenure_months is not None
        and monthly_income > 0
    ):
        emi_new = _emi(requested_loan_amount, requested_tenure_months)
        total_emi = total_existing_emi + emi_new
        foir = total_emi / monthly_income

        updates["approx_new_emi"] = emi_new
        updates["foir"] = foir

        if foir > settings.max_foir:
            updates["is_eligible"] = False
            updates["sales_mode"] = True
            updates["sales_stage"] = None
            updates["ineligibility_reason"] = (
                f"FOIR limit exceeded: your total EMIs (existing + new) would be about Rs {total_emi:,} per month "
                f"on an income of Rs {monthly_income:,}, giving a FOIR of {foir:.0%}, which is above the "
                f"allowed {settings.max_foir:.0%} limit."
            )
            return updates

    # 7. Full data and no fail => eligible
    if _has_all_required_fields(state):
        updates["is_eligible"] = True
        updates["done"] = True

    return updates

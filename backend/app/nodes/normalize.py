import re
from datetime import datetime, date
from typing import Dict, Any
from ..state import EligibilityState


def _parse_dob_to_age(dob_raw: str) -> int | None:
    """Parse DOB string and compute age in years."""
    if not dob_raw:
        return None
    
    dob_raw = dob_raw.strip()
    
    # Common date formats to try
    formats = [
        "%d-%m-%Y",    # 27-07-2000
        "%d/%m/%Y",    # 27/07/2000
        "%Y-%m-%d",    # 2000-07-27
        "%d-%m-%y",    # 27-07-00
        "%d/%m/%y",    # 27/07/00
        "%B %d, %Y",   # July 27, 2000
        "%b %d, %Y",   # Jul 27, 2000
        "%d %B %Y",    # 27 July 2000
        "%d %b %Y",    # 27 Jul 2000
    ]
    
    parsed_date = None
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(dob_raw, fmt).date()
            break
        except ValueError:
            continue
    
    if not parsed_date:
        return None
    
    today = date.today()
    age = today.year - parsed_date.year
    
    # Adjust if birthday hasn't occurred yet this year
    if (today.month, today.day) < (parsed_date.month, parsed_date.day):
        age -= 1
    
    return age if age > 0 else None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.lower().strip()
        s = s.replace(",", "").replace(chr(0x20B9), "").replace("rs", "").strip()

        # lakhs / lacs
        if "lakh" in s or "lac" in s or s.endswith("l"):
            num = re.findall(r"[\d.]+", s)
            if not num:
                return None
            val = float(num[0])
            return int(val * 100000)

        # thousands like "50k"
        if "k" in s:
            num = re.findall(r"[\d.]+", s)
            if not num:
                return None
            val = float(num[0])
            return int(val * 1000)

        nums = re.findall(r"-?\d+", s)
        if nums:
            return int(nums[0])
    return None


def _parse_months(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.lower()
        nums = re.findall(r"[\d.]+", s)
        if not nums:
            return None
        num = float(nums[0])

        if "year" in s or "yr" in s:
            return int(round(num * 12))
        if "month" in s or "mon" in s:
            return int(round(num))
        # default assume months
        return int(round(num))
    return None


def _parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"yes", "y", "true", "t"}:
            return True
        if s in {"no", "n", "false", "f"}:
            return False
    return None


def normalize_and_compute_derived(state: EligibilityState) -> Dict:
    updates: Dict[str, Any] = {}

    # Income normalisation
    if "monthly_income" in state:
        mi = _parse_int(state.get("monthly_income"))
        if mi is not None:
            updates["monthly_income"] = mi

    if "annual_income" in state:
        ai = _parse_int(state.get("annual_income"))
        if ai is not None:
            updates["annual_income"] = ai

    # Experience / tenure
    if "total_experience_months" in state:
        te = _parse_months(state.get("total_experience_months"))
        if te is not None:
            updates["total_experience_months"] = te

    if "current_job_months" in state:
        cj = _parse_months(state.get("current_job_months"))
        if cj is not None:
            updates["current_job_months"] = cj

    if "business_vintage_months" in state:
        bv = _parse_months(state.get("business_vintage_months"))
        if bv is not None:
            updates["business_vintage_months"] = bv

    if "requested_tenure_months" in state:
        tn = _parse_months(state.get("requested_tenure_months"))
        if tn is not None:
            updates["requested_tenure_months"] = tn

    if "requested_loan_amount" in state:
        ra = _parse_int(state.get("requested_loan_amount"))
        if ra is not None:
            updates["requested_loan_amount"] = ra

    if "total_existing_emi" in state:
        eemi = _parse_int(state.get("total_existing_emi"))
        if eemi is not None:
            updates["total_existing_emi"] = eemi

    if "has_existing_loans" in state:
        h = _parse_bool(state.get("has_existing_loans"))
        if h is not None:
            updates["has_existing_loans"] = h

    # Employment type normalisation
    emp = state.get("employment_type")
    if isinstance(emp, str):
        s = emp.lower()
        if "salaried" in s or "employee" in s or "teacher" in s:
            updates["employment_type"] = "salaried"
        elif "self" in s or "business" in s or "freelance" in s:
            updates["employment_type"] = "self_employed"

    # ====== BUG FIXES ======

    # Bug 1: If no existing loans, set EMI to 0
    has_loans = state.get("has_existing_loans")
    if has_loans is False and state.get("total_existing_emi") is None:
        updates["total_existing_emi"] = 0

    # Bug 2: Derive monthly_income from annual_income for self-employed
    current_emp_type = updates.get("employment_type") or state.get("employment_type")
    if current_emp_type == "self_employed":
        current_annual = updates.get("annual_income") or state.get("annual_income")
        current_monthly = updates.get("monthly_income") or state.get("monthly_income")
        if current_annual and current_monthly is None:
            updates["monthly_income"] = current_annual // 12

    # Bug 4: Convert DOB to age if age not already set
    dob_raw = state.get("dob_raw")
    current_age = updates.get("age_years") or state.get("age_years")
    if dob_raw and current_age is None:
        computed_age = _parse_dob_to_age(dob_raw)
        if computed_age:
            updates["age_years"] = computed_age

    return updates

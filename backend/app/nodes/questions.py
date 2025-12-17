from typing import Dict
from ..state import EligibilityState


def _append_assistant(state: EligibilityState, text: str) -> Dict:
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}


def _missing_required_fields(state: EligibilityState) -> Dict[str, bool]:
    """Return a dict of missing required fields based on employment type."""
    emp_type = state.get("employment_type")
    missing = {
        "age_years": state.get("age_years") is None and state.get("dob_raw") is None,
        "employment_type": emp_type not in ("salaried", "self_employed"),
        "monthly_income": emp_type == "salaried" and state.get("monthly_income") is None,
        "annual_income": emp_type == "self_employed" and state.get("annual_income") is None,
        "total_experience_months": emp_type == "salaried" and state.get("total_experience_months") is None,
        "current_job_months": emp_type == "salaried" and state.get("current_job_months") is None,
        "business_vintage_months": emp_type == "self_employed" and state.get("business_vintage_months") is None,
        "has_existing_loans": state.get("has_existing_loans") is None,
        "total_existing_emi": state.get("has_existing_loans") and state.get("total_existing_emi") is None,
        "requested_loan_amount": state.get("requested_loan_amount") is None,
        "requested_tenure_months": state.get("requested_tenure_months") is None,
    }
    return {k: v for k, v in missing.items() if v}


def decide_next_question(state: EligibilityState) -> Dict:
    updates: Dict = {}

    if state.get("done"):
        return {}

    # Avoid repeating the processing prompt
    if state.get("stage") == "processing":
        return {}

    emp_type = state.get("employment_type")

    # 1. Age
    if state.get("age_years") is None and state.get("dob_raw") is None:
        # If master agent already set the stage/intro, we might skip the preamble, 
        # but safe to repeat the specific question.
        text = (
            "To get started, could you please tell me your age? You can just type the number or your date of birth."
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_age"
        return updates

    # 2. Employment type
    if emp_type not in ("salaried", "self_employed"):
        text = (
            "Thanks. Now, do you work for a company (salaried) or do you have your own business (self-employed)?"
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_employment_type"
        return updates

    # 3. Income - salaried
    if emp_type == "salaried" and state.get("monthly_income") is None:
        text = (
            "Got it. What is your approximate monthly take-home salary?"
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_monthly_income"
        return updates

    # 3b. Income - self employed
    if emp_type == "self_employed" and state.get("annual_income") is None:
        text = (
            "Great. Could you share your business's approximate annual turnover or income?"
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_annual_income"
        return updates

    # 4. Experience / business vintage
    if emp_type == "salaried":
        if state.get("total_experience_months") is None:
            text = (
                "How long have you been working in total? You can answer in years or months,\n"
                'for example: "1.5 years" or "18 months".'
            )
            updates |= _append_assistant(state, text)
            updates["stage"] = "ask_total_experience"
            return updates

        if state.get("current_job_months") is None:
            text = (
                "And how long have you been in your current job at this company?\n"
                'You can reply like: "8 months" or "2 years".'
            )
            updates |= _append_assistant(state, text)
            updates["stage"] = "ask_current_job"
            return updates

    if emp_type == "self_employed" and state.get("business_vintage_months") is None:
        text = (
            "How long ago did you start this business? You can answer in years or months,\n"
            'for example: "3 years" or "24 months".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_business_vintage"
        return updates

    # 5. Existing loans
    if state.get("has_existing_loans") is None:
        text = (
            "Do you have any existing loans right now? This includes home, car, personal loans or ongoing EMIs on "
            'credit cards. Please reply "yes" or "no".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_has_loans"
        return updates

    if state.get("has_existing_loans") and state.get("total_existing_emi") is None:
        text = (
            "What is the total EMI you pay each month for all your existing loans combined?\n"
            'You can reply like: "12,000 per month".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_total_emi"
        return updates

    # 6. Loan amount and tenure
    if state.get("requested_loan_amount") is None and state.get("requested_tenure_months") is None:
        text = (
            "What loan amount do you need, and for how long do you want to take it?\n"
            'You can reply like: "10 lakhs for 3 years" or "5L for 24 months".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_amount_and_tenure"
        return updates

    if state.get("requested_loan_amount") is None:
        text = (
            "How much personal loan are you looking for from Tata Capital?\n"
            'You can reply like: "15 lakhs" or "10L".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_amount"
        return updates

    if state.get("requested_tenure_months") is None:
        text = (
            "For how long do you want to take the loan?\n"
            'You can reply like: "3 years" or "36 months".'
        )
        updates |= _append_assistant(state, text)
        updates["stage"] = "ask_tenure"
        return updates

    # Fallback: if anything somehow missing, ask for it explicitly; otherwise move to processing
    missing = _missing_required_fields(state)
    if missing:
        parts = ["I still need a couple of details before I can give you an answer:"]
        if missing.get("age_years"):
            parts.append("- Your age (or date of birth)")
        if missing.get("employment_type"):
            parts.append("- Whether you are salaried or self-employed")
        if missing.get("monthly_income"):
            parts.append("- Your monthly take-home income")
        if missing.get("annual_income"):
            parts.append("- Your annual business income")
        if missing.get("total_experience_months"):
            parts.append("- Your total work experience")
        if missing.get("current_job_months"):
            parts.append("- How long you have been in your current job")
        if missing.get("business_vintage_months"):
            parts.append("- How long your business has been running")
        if missing.get("has_existing_loans"):
            parts.append("- Whether you have any existing loans")
        if missing.get("total_existing_emi"):
            parts.append("- Your total monthly EMI on existing loans")
        if missing.get("requested_loan_amount") or missing.get("requested_tenure_months"):
            parts.append("- The loan amount and tenure you need")
        text = "\n".join(parts)
        updates |= _append_assistant(state, text)
        return updates

    text = (
        "Thanks, I have your details. Let me quickly run them against our eligibility rules and see where you stand."
    )
    updates |= _append_assistant(state, text)
    updates["stage"] = "processing"
    return updates

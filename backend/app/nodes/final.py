from typing import Dict
from ..state import EligibilityState


def final_response(state: EligibilityState) -> Dict:
    messages = list(state.get("messages", []))

    if state.get("is_eligible"):
        emi = state.get("approx_new_emi")
        foir = state.get("foir")
        amount = state.get("requested_loan_amount")
        tenure = state.get("requested_tenure_months")

        parts = []
        parts.append("Based on your answers, you **are eligible** for this Tata Capital personal loan in principle.")
        if amount and tenure:
            parts.append(
                f"\n\nProposed structure:\n- Loan amount: **Rs {amount:,}**\n"
                f"- Tenure: **{tenure} months (~{tenure/12:.1f} years)**"
            )
        if emi is not None:
            parts.append(f"- Estimated EMI: **Rs {emi:,}** per month")
        if foir is not None:
            parts.append(f"- FOIR: **{foir:.0%}**, within our safe limit")

        parts.append(
            "\n\nThis is a preliminary check. Final approval will depend on verification of your documents "
            "(ID, address, income proofs, and bank statements)."
        )
        text = "\n".join(parts)
    else:
        reason = state.get("ineligibility_reason") or "You do not currently meet the internal policy criteria."
        text = (
            "Based on your answers, you are **not eligible** for this Tata Capital personal loan in this structure.\n\n"
            f"Reason: {reason}\n\n"
            "If your income increases, any EMIs close, or your requirement changes, you can try again anytime."
        )

    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}

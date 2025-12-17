from typing import Dict, List, Any
from ..state import EligibilityState
from ..config import settings
from .rules import _emi


def _append_assistant(state: EligibilityState, text: str) -> Dict:
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}


def _round_down_to(p: int, step: int) -> int:
    if p <= 0:
        return 0
    return (p // step) * step


def _parse_choice(text: str) -> int | None:
    t = text.lower().strip()

    if any(w in t for w in ["reject", "none", "no option", "no thanks", "no thank", "nothing"]):
        return 0

    if "1" in t and "2" not in t and "3" not in t:
        return 1
    if "2" in t and "3" not in t:
        return 2
    if "3" in t:
        return 3

    if "first" in t:
        return 1
    if "second" in t:
        return 2
    if "third" in t:
        return 3

    return None


def sales_offers(state: EligibilityState) -> Dict:
    updates: Dict = {}

    if not state.get("sales_mode"):
        return {}

    monthly_income = state.get("monthly_income")
    total_existing_emi = state.get("total_existing_emi", 0)
    requested_amount = state.get("requested_loan_amount")
    requested_tenure = state.get("requested_tenure_months")
    ineligibility_reason = state.get("ineligibility_reason") or ""

    if (
        monthly_income is None
        or requested_amount is None
        or requested_tenure is None
        or monthly_income <= 0
    ):
        text = (
            "Right now I don't have enough details (income / loan / tenure) to restructure this offer.\n"
            "Please re-enter your income, existing EMIs, required loan amount and tenure so I can try again."
        )
        updates |= _append_assistant(state, text)
        return updates

    # Phase 2: handle user's choice
    if state.get("sales_stage") == "awaiting_choice":
        last_user = state.get("user_message") or ""
        choice = _parse_choice(last_user)
        offers: List[Dict[str, Any]] = state.get("sales_offers") or []

        if choice == 0:
            text = (
                "I understand. Based on your current income and EMI obligations, we won't be able to approve this "
                "loan safely without adjusting either the loan amount, tenure, or your existing EMIs.\n\n"
                "If your income increases, an EMI closes, or your requirement changes, you can come back and "
                "I'll be happy to recheck your eligibility."
            )
            updates |= _append_assistant(state, text)
            updates["done"] = True
            updates["is_eligible"] = False
            updates["sales_mode"] = False
            updates["sales_stage"] = None
            return updates

        if choice is None or choice < 0 or choice > len(offers):
            text = (
                "Just to confirm, could you please choose one of the options by typing **1**, **2**, or **3** "
                "(or say 'reject' if none of them work)?"
            )
            updates |= _append_assistant(state, text)
            return updates

        selected = offers[choice - 1]
        kind = selected.get("kind")

        if kind in ("reduce_amount", "increase_tenure"):
            new_amount = selected["new_amount"]
            new_tenure = selected["tenure_months"]
            emi_new = selected["emi"]
            total_emi = total_existing_emi + emi_new
            foir = total_emi / monthly_income if monthly_income > 0 else 0.0
            max_foir = settings.max_foir

            if foir > max_foir:
                text = (
                    "I tried restructuring based on your choice, but the EMI still keeps your FOIR above our "
                    "safe limit. We might need to reduce the amount further or consider a longer tenure."
                )
                updates |= _append_assistant(state, text)
                updates["sales_stage"] = None
                return updates

            updates["requested_loan_amount"] = new_amount
            updates["requested_tenure_months"] = new_tenure
            updates["approx_new_emi"] = emi_new
            updates["foir"] = foir
            updates["is_eligible"] = True
            updates["done"] = True
            updates["sales_mode"] = False
            updates["sales_stage"] = None

            years = new_tenure / 12.0
            if kind == "reduce_amount":
                lead = "Great, let's optimise the loan amount a bit."
            else:
                lead = "Perfect, let's make the EMI more comfortable by stretching the tenure slightly."

            text = (
                f"{lead}\n\n"
                f"Here is the updated structure I can move ahead with:\n"
                f"- Loan amount: **Rs {new_amount:,}**\n"
                f"- Tenure: **{new_tenure} months (~{years:.1f} years)**\n"
                f"- Estimated EMI: **Rs {emi_new:,}** per month\n"
                f"- Total EMIs (existing + new): **Rs {total_emi:,}** per month\n"
                f"- FOIR: **{foir:.0%}** (within our safe limit of {max_foir:.0%})\n\n"
                "With this structure, you pass the hard eligibility filters. Next, we will just need to verify your "
                "documents (ID, address, income proofs, and bank statements) to complete the process."
            )
            updates |= _append_assistant(state, text)
            return updates

        if kind == "reduce_existing_emi":
            reduce_by = selected["reduce_by"]
            text = (
                "Understood. To keep your requested loan amount and tenure while staying safe on EMIs, "
                "you'd need to reduce your **existing EMIs by about "
                f"Rs {reduce_by:,} per month** (for example by prepaying or closing a loan).\n\n"
                "Once that happens, your FOIR will drop within the required range and we can re-run this "
                "eligibility check and proceed."
            )
            updates |= _append_assistant(state, text)
            updates["done"] = True
            updates["is_eligible"] = False
            updates["sales_mode"] = False
            updates["sales_stage"] = None
            return updates

        text = (
            "I couldn't process that option correctly. Let's try again with a simpler structure or come back later "
            "when your EMI situation changes."
        )
        updates |= _append_assistant(state, text)
        updates["done"] = True
        updates["is_eligible"] = False
        updates["sales_mode"] = False
        updates["sales_stage"] = None
        return updates

    # Phase 1: propose offers
    emi_current = _emi(requested_amount, requested_tenure)
    if emi_current <= 0:
        text = (
            "I tried to compute a restructured EMI but something looks off with the loan amount or tenure.\n"
            "Please double-check the amount and tenure and try again."
        )
        updates |= _append_assistant(state, text)
        return updates

    max_total_emi = monthly_income * settings.max_foir
    allowed_new_emi = max_total_emi - total_existing_emi

    if allowed_new_emi <= 0:
        text = (
            "Right now, your existing EMIs already use up the safe limit of your income.\n\n"
            "To become eligible for a new personal loan, you'd need to reduce your current EMIs first "
            "(for example, by closing or restructuring a loan). Once that drops, we can re-check your eligibility."
        )
        updates |= _append_assistant(state, text)
        updates["done"] = True
        updates["is_eligible"] = False
        updates["sales_mode"] = False
        updates["sales_stage"] = None
        return updates

    offers: List[Dict[str, Any]] = []

    # Offer 1: reduce amount, keep tenure
    factor = emi_current / requested_amount
    max_amount_linear = int(allowed_new_emi / factor)
    amount1 = _round_down_to(max_amount_linear, 50_000)

    if amount1 >= 50_000:
        emi1 = _emi(amount1, requested_tenure)
        foir1 = (total_existing_emi + emi1) / monthly_income
        offers.append(
            {
                "kind": "reduce_amount",
                "new_amount": amount1,
                "tenure_months": requested_tenure,
                "emi": emi1,
                "foir": foir1,
            }
        )

    # Offer 2: keep amount, increase tenure (up to 84 months)
    offer2 = None
    for t in range(requested_tenure + 12, 85, 6):
        emi_t = _emi(requested_amount, t)
        if emi_t <= allowed_new_emi:
            foir2 = (total_existing_emi + emi_t) / monthly_income
            offer2 = {
                "kind": "increase_tenure",
                "new_amount": requested_amount,
                "tenure_months": t,
                "emi": emi_t,
                "foir": foir2,
            }
            break
    if offer2:
        offers.append(offer2)

    # Offer 3: reduce existing EMI by X
    total_emi_current = total_existing_emi + emi_current
    need_reduction = int(total_emi_current - max_total_emi)
    if need_reduction > 0:
        offers.append(
            {
                "kind": "reduce_existing_emi",
                "reduce_by": need_reduction,
            }
        )

    if not offers:
        text = (
            "Given your current income, existing EMIs, loan amount and tenure, I'm not able to find a safe "
            "structure that fits our policy right now.\n\n"
            "If you're open to changing the loan amount, tenure, or reducing existing EMIs, we can try again."
        )
        updates |= _append_assistant(state, text)
        updates["done"] = True
        updates["is_eligible"] = False
        updates["sales_mode"] = False
        updates["sales_stage"] = None
        return updates

    lines: List[str] = []

    if ineligibility_reason:
        lines.append("Right now, you're not eligible **in this exact structure** because:")
        lines.append(f"- {ineligibility_reason}")
        lines.append("")

    lines.append("But the good news is, we can **restructure the loan** in a few realistic ways so you can still move ahead:\n")

    option_num = 1
    for offer in offers:
        kind = offer["kind"]
        if kind == "reduce_amount":
            amt = offer["new_amount"]
            emi1 = offer["emi"]
            foir1 = offer["foir"]
            yrs = requested_tenure / 12.0
            lines.append(
                f"**Option {option_num} - Slightly reduce loan amount**\n"
                f"- Loan amount: **Rs {amt:,}** (instead of Rs {requested_amount:,})\n"
                f"- Tenure: **{requested_tenure} months (~{yrs:.1f} years)**\n"
                f"- Estimated EMI: **Rs {emi1:,}** per month\n"
                f"- FOIR: **{foir1:.0%}** (within the safe limit)\n"
            )
        elif kind == "increase_tenure":
            amt = offer["new_amount"]
            t = offer["tenure_months"]
            emi2 = offer["emi"]
            foir2 = offer["foir"]
            yrs2 = t / 12.0
            lines.append(
                f"**Option {option_num} - Keep Rs {amt:,} but stretch tenure**\n"
                f"- Loan amount: **Rs {amt:,}** (same as requested)\n"
                f"- Tenure: **{t} months (~{yrs2:.1f} years)**\n"
                f"- Estimated EMI: **Rs {emi2:,}** per month\n"
                f"- FOIR: **{foir2:.0%}** (within the safe limit)\n"
            )
        elif kind == "reduce_existing_emi":
            cut = offer["reduce_by"]
            lines.append(
                f"**Option {option_num} - Reduce existing EMIs**\n"
                f"- If you can reduce your current EMIs by about **Rs {cut:,} per month** "
                f"(for example by closing or prepaying a loan), we can keep your requested amount and tenure.\n"
            )
        option_num += 1

    # Bug 5 Fix: Dynamic message based on actual number of options
    num_offers = len(offers)
    if num_offers == 1:
        lines.append(
            "Please reply with **1** to accept this option, or type **\"reject\"** if it doesn't work for you."
        )
    elif num_offers == 2:
        lines.append(
            "Please reply with **1** or **2** to pick an option, or type **\"reject\"** if neither works for you."
        )
    else:
        lines.append(
            "Please reply with **1**, **2**, or **3** to pick an option, or type **\"reject\"** if none of these work for you."
        )

    text = "\n".join(lines)
    updates |= _append_assistant(state, text)
    updates["sales_offers"] = offers
    updates["sales_stage"] = "awaiting_choice"
    return updates

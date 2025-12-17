"""
Sales Agent - Handles initial customer engagement, requirement gathering, and loan negotiation.

Responsibilities:
- Engage with the customer like a human sales executive
- Understand customer needs (loan purpose, amount, preferred tenure)
- Discuss loan terms, interest rates, and benefits
- Handle objections and negotiate terms
- Gather requirements before eligibility check
- Upsell and cross-sell when appropriate
"""

from typing import Dict, List
from anthropic import Anthropic
from ..config import settings
from ..state import AgentState

client = Anthropic(api_key=settings.anthropic_api_key)

SALES_CONVERSATION_PROMPT = """
You are a professional sales executive for Tata Capital Personal Loans.

Your role is to:
1. Understand the customer's loan requirements
2. Build rapport and trust
3. Explain loan benefits
4. Gather key information for eligibility check

Current conversation context:
{context}

Customer's latest message: {user_message}

Already gathered information:
- Loan amount needed: {loan_amount}
- Preferred tenure: {tenure}
- Purpose of loan: {purpose}

Respond naturally as a sales executive would. Keep responses conversational and professional.
If you have enough info (loan amount and tenure), end with: "[READY_FOR_ELIGIBILITY]"

Important guidelines:
- Be warm and professional
- Do not be pushy
- Explain benefits naturally in conversation
- Do not use emojis
- Keep responses concise (2-4 sentences)
- If customer mentions amount and tenure, confirm and move to eligibility

Return ONLY the response text, no JSON or special formatting.
"""


def _append_assistant(state: AgentState, text: str) -> Dict:
    """Helper to append assistant message to conversation."""
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}


def _get_conversation_context(state: AgentState) -> str:
    """Get recent conversation context for the LLM."""
    messages = state.get("messages", [])
    recent = messages[-6:] if len(messages) > 6 else messages
    
    lines = []
    for m in recent:
        role = m.get("role", "user").upper()
        content = m.get("content", "")[:200]  # Truncate long messages
        lines.append(f"{role}: {content}")
    
    return "\n".join(lines) if lines else "No prior conversation"


def sales_conversation(state: AgentState) -> Dict:
    """
    Main sales conversation handler.
    Engages with customer to gather requirements and build rapport.
    """
    updates: Dict = {}
    
    # Only run if sales agent is active
    if state.get("current_agent") != "sales":
        return {}
    
    # Skip if requirements already gathered
    if state.get("customer_requirements_gathered"):
        return {}
    
    user_message = state.get("user_message", "")
    if not user_message:
        # First interaction - start the sales pitch
        return sales_opening(state)
    
    # Get current gathered info
    loan_amount = state.get("requested_loan_amount")
    tenure = state.get("requested_tenure_months")
    
    # Check if we have enough info to move to eligibility
    if loan_amount and tenure:
        # Confirm and hand off
        years = tenure / 12 if tenure else 0
        text = (
            f"Perfect. So you are looking at a loan of **Rs {loan_amount:,}** for **{tenure} months** "
            f"(about {years:.1f} years).\n\n"
            "Let me quickly run an eligibility check for you. This will take just a couple of minutes."
        )
        updates |= _append_assistant(state, text)
        updates["customer_requirements_gathered"] = True
        updates["current_agent"] = "eligibility"
        updates["previous_agent"] = "sales"
        updates["agent_handoff_reason"] = "Requirements gathered, starting eligibility"
        return updates
    
    # Use LLM for natural conversation
    context = _get_conversation_context(state)
    
    prompt = SALES_CONVERSATION_PROMPT.format(
        context=context,
        user_message=user_message,
        loan_amount=f"₹{loan_amount:,}" if loan_amount else "Not specified",
        tenure=f"{tenure} months" if tenure else "Not specified",
        purpose="Not specified"  # Can be enhanced to track this
    )
    
    try:
        resp = client.messages.create(
            model=settings.model_name,
            max_tokens=300,
            system="You are a helpful Tata Capital loan sales executive. Be friendly and concise.",
            messages=[{"role": "user", "content": prompt}],
        )
        
        response_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                response_text += block.text
        
        # Check if LLM signaled ready for eligibility
        if "[READY_FOR_ELIGIBILITY]" in response_text:
            response_text = response_text.replace("[READY_FOR_ELIGIBILITY]", "").strip()
            updates["customer_requirements_gathered"] = True
            updates["current_agent"] = "eligibility"
            updates["previous_agent"] = "sales"
        
        if response_text:
            updates |= _append_assistant(state, response_text)
        
    except Exception as e:
        print(f"[Sales Agent Error] {e}")
        # Fallback response
        text = ask_for_requirements(state, loan_amount, tenure)
        updates |= _append_assistant(state, text)
    
    return updates


def sales_opening(state: AgentState) -> Dict:
    """Initial sales opening when conversation starts."""
    updates: Dict = {}
    
    text = (
        "Hello. I am here to help you with your personal loan.\n\n"
        "To find the best loan option for you, I just need a couple of quick details:\n\n"
        "- **How much loan** are you looking for?\n"
        "- **How long** would you like to repay it (tenure in months/years)?\n\n"
        "For example, you can say: \"I need 5 lakhs for 3 years\""
    )
    
    updates |= _append_assistant(state, text)
    updates["sales_negotiation_round"] = 1
    return updates


def ask_for_requirements(state: AgentState, loan_amount: int | None, tenure: int | None) -> str:
    """Generate appropriate question based on what's missing."""
    if not loan_amount and not tenure:
        return (
            "Could you share how much loan you are looking for and for how long?\n\n"
            "For example: \"10 lakhs for 4 years\" or \"Rs 3,00,000 for 24 months\""
        )
    elif not loan_amount:
        return (
            f"Great, you are looking at a tenure of {tenure} months. "
            "How much loan amount do you need?\n\n"
            "You can say something like: \"5 lakhs\" or \"Rs 2,50,000\""
        )
    elif not tenure:
        return (
            f"Perfect, you need Rs {loan_amount:,}. "
            "How long would you like to repay this?\n\n"
            "You can say: \"3 years\" or \"36 months\""
        )
    return ""


def sales_handle_objection(state: AgentState) -> Dict:
    """Handle customer objections about interest rates, terms, etc."""
    updates: Dict = {}
    
    user_message = state.get("user_message", "").lower()
    
    if "interest" in user_message or "rate" in user_message:
        text = (
            "I understand interest rates are important.\n\n"
            "At Tata Capital, our personal loan rates start from **10.99% p.a.*** "
            "The exact rate depends on your profile, income, and credit score.\n\n"
            "*Subject to credit assessment.\n\n"
            "Shall I check your eligibility? Based on your profile, I can give you a better estimate."
        )
        updates |= _append_assistant(state, text)
        return updates
    
    if "document" in user_message or "paperwork" in user_message:
        text = (
            "Great question. We have made the documentation simple.\n\n"
            "You will just need:\n"
            "- Aadhaar card (for identity and address)\n"
            "- Recent bank statements\n"
            "- Salary slips or ITR (for income proof)\n\n"
            "Most of this can be done digitally. Want me to check your eligibility first?"
        )
        updates |= _append_assistant(state, text)
        return updates
    
    if "time" in user_message or "how long" in user_message or "fast" in user_message:
        text = (
            "Speed is our specialty.\n\n"
            "- **Eligibility check**: 2 minutes\n"
            "- **Document verification**: 10 minutes\n"
            "- **Approval**: 24-48 hours\n"
            "- **Disbursal**: Same day after approval\n\n"
            "Ready to start?"
        )
        updates |= _append_assistant(state, text)
        return updates
    
    return {}


def sales_confirm_and_proceed(state: AgentState) -> Dict:
    """Confirm gathered requirements and proceed to eligibility."""
    updates: Dict = {}
    
    loan_amount = state.get("requested_loan_amount")
    tenure = state.get("requested_tenure_months")
    
    if not loan_amount or not tenure:
        return {}
    
    years = tenure / 12
    approx_emi = loan_amount / tenure if tenure > 0 else 0  # Simple estimate
    
    text = (
        f"Excellent choice. Here is a summary of what you are looking for:\n\n"
        f"**Loan Summary**\n"
        f"- Amount: **Rs {loan_amount:,}**\n"
        f"- Tenure: **{tenure} months** (~{years:.1f} years)\n"
        f"- Estimated EMI: ~**Rs {int(approx_emi):,}**/month\n\n"
        f"*EMI is approximate. Exact amount depends on interest rate after eligibility check.\n\n"
        f"Shall I proceed with the eligibility check?"
    )
    
    updates |= _append_assistant(state, text)
    updates["customer_requirements_gathered"] = True
    
    return updates

"""
Master Agent - Orchestrates the conversation flow and routes to appropriate sub-agents.

Responsibilities:
- Start and end conversations
- Detect customer intent
- Route to appropriate agent (Sales, Eligibility, Document Verification)
- Handle transitions between agents
- Provide greetings and farewells
"""

from typing import Dict, List
from anthropic import Anthropic
from ..config import settings
from ..state import AgentState

client = Anthropic(api_key=settings.anthropic_api_key)

INTENT_DETECTION_PROMPT = """
You are an intent classifier for a Tata Capital personal loan assistant.

Given the user's message, classify their intent into one of these categories:
- "apply_loan": User wants to apply for a loan or start the loan application process
- "check_eligibility": User wants to check if they are eligible for a loan
- "inquiry": User has questions about loan products, interest rates, terms, etc.
- "continue_flow": User is responding to a previous question or continuing an ongoing conversation
- "greeting": User is just saying hello or starting a conversation
- "farewell": User is ending the conversation
- "other": Anything else that doesn't fit above

Return ONLY the intent category as a single word, nothing else.
""".strip()


def _append_assistant(state: AgentState, text: str) -> Dict:
    """Helper to append assistant message to conversation."""
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}


def _detect_intent(user_message: str) -> str:
    """Use LLM to detect user intent."""
    try:
        resp = client.messages.create(
            model=settings.model_name,
            max_tokens=50,
            system=INTENT_DETECTION_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        intent = text.strip().lower().replace('"', "").replace("'", "")

        valid_intents = [
            "apply_loan",
            "check_eligibility",
            "inquiry",
            "continue_flow",
            "greeting",
            "farewell",
            "other",
        ]
        if intent in valid_intents:
            return intent
        return "other"
    except Exception as e:
        print(f"[Intent Detection Error] {e}")
        return "continue_flow"


def master_greeting(state: AgentState) -> Dict:
    """
    Initial greeting when conversation starts.
    Called when no current_agent is set or conversation hasn't started.
    """
    updates: Dict = {}

    # Check if this is a fresh conversation
    if state.get("conversation_started"):
        return {}

    greeting_text = "Hi! I am Credence, your personal loan assistant. How can I help you today?"

    updates |= _append_assistant(state, greeting_text)
    updates["conversation_started"] = True
    updates["current_agent"] = "master"

    return updates


def master_router(state: AgentState) -> Dict:
    """
    Main routing logic - determines which agent should handle the next interaction.
    This is called after ingesting user message to decide the flow.
    """
    updates: Dict = {}

    user_message = state.get("user_message", "")
    current_agent = state.get("current_agent")

    # If already in a sub-agent flow, let them continue
    if current_agent in ("eligibility", "sales", "document_verification"):
        return {}

    # Detect intent for new interactions or master agent
    if not user_message:
        return {}

    intent = _detect_intent(user_message)
    updates["customer_intent"] = intent

    # Route based on intent
    if intent == "greeting":
        text = (
            "Hi there! How can I help you with your personal loan needs today?\n\n"
            "You can say something like:\n"
            '- "I want to apply for a loan"\n'
            '- "Check my eligibility"\n'
            '- "Tell me about interest rates"'
        )
        updates |= _append_assistant(state, text)
        return updates

    if intent == "farewell":
        text = (
            "Thank you for choosing Tata Capital!\n\n"
            "If you have any more questions about personal loans, feel free to come back anytime. "
            "Have a great day!"
        )
        updates |= _append_assistant(state, text)
        updates["conversation_ended"] = True
        updates["done"] = True
        return updates

    # Direct routing to Eligibility based on strictly defined flow
    if intent == "apply_loan":
        text = (
            "Excellent choice! Let's get your loan application moving.\n\n"
            "I need to check your eligibility with a few quick questions. "
            "It's a strict process but will only take 2 minutes.\n\n"
            "First, let's start with your age."
        )
        updates |= _append_assistant(state, text)
        updates["current_agent"] = "eligibility"
        updates["previous_agent"] = "master"
        updates["agent_handoff_reason"] = "User wants to apply, starting strict eligibility check"
        updates["stage"] = "ask_age"  # Ensure we start from the top
        return updates

    if intent == "check_eligibility":
        text = (
            "Sure, I can check that for you right now.\n\n"
            "I'll ask you 6 simple questions to see if you qualify. "
            "Let's begin."
        )
        updates |= _append_assistant(state, text)
        updates["current_agent"] = "eligibility"
        updates["previous_agent"] = "master"
        updates["agent_handoff_reason"] = "User wants to check eligibility"
        updates["stage"] = "ask_age"
        return updates

    if intent == "inquiry":
        text = (
            "I'd be happy to help with your questions!\n\n"
            "**Tata Capital Personal Loan Highlights:**\n"
            "- Loan amount: Rs 150,000 to Rs 3,500,000\n"
            "- Tenure: 12 to 84 months\n"
            "- Interest rates: Starting from 10.99% p.a.*\n"
            "- Quick approval in 24-48 hours\n"
            "- Minimal documentation\n\n"
            "*Terms and conditions apply. Rates are subject to credit assessment.\n\n"
            "Would you like to check your eligibility now?"
        )
        updates |= _append_assistant(state, text)
        return updates

    if intent == "continue_flow":
        # User is responding to something - check what stage we're in
        # If no active flow, start eligibility
        if not state.get("sales_conversation_active") and not state.get("doc_verification_started"):
            updates["current_agent"] = "sales"
            updates["sales_conversation_active"] = True
        return updates

    # Default: offer options
    text = (
        "I'm not quite sure what you need help with. Could you tell me:\n\n"
        "- Do you want to **apply for a personal loan**?\n"
        "- Do you want to **check your eligibility**?\n"
        "- Do you have **questions about our loan products**?"
    )
    updates |= _append_assistant(state, text)
    return updates


def master_handoff_to_eligibility(state: AgentState) -> Dict:
    """Hand off from Master/Sales to Eligibility Agent."""
    updates: Dict = {}

    text = (
        "Perfect! Now let me check your eligibility for a Tata Capital personal loan.\n\n"
        "I'll ask you a few quick questions - this should take less than 2 minutes."
    )
    updates |= _append_assistant(state, text)
    updates["current_agent"] = "eligibility"
    updates["previous_agent"] = state.get("current_agent", "master")
    updates["agent_handoff_reason"] = "Requirements gathered, starting eligibility check"

    return updates


def master_handoff_to_document_verification(state: AgentState) -> Dict:
    """Hand off from Eligibility to Document Verification Agent after user qualifies."""
    updates: Dict = {}

    if not state.get("is_eligible"):
        return {}

    # Build customer info table
    age = state.get("age_years", "N/A")
    employment_type = state.get("employment_type", "N/A")
    if employment_type:
        employment_type = employment_type.replace("_", " ").title()
    
    monthly_income = state.get("monthly_income", 0)
    existing_emi = state.get("total_existing_emi", 0)
    loan_amount = state.get("requested_loan_amount", 0)
    tenure = state.get("requested_tenure_months", 0)
    foir = state.get("foir", 0)
    
    # Format numbers with commas
    income_str = f"Rs {monthly_income:,}" if monthly_income else "N/A"
    emi_str = f"Rs {existing_emi:,}" if existing_emi else "Rs 0"
    loan_str = f"Rs {loan_amount:,}" if loan_amount else "N/A"
    tenure_str = f"{tenure} months" if tenure else "N/A"
    foir_str = f"{foir:.0%}" if foir else "N/A"

    customer_table = (
        "| Field | Value |\n"
        "|-------|-------|\n"
        f"| Age | {age} years |\n"
        f"| Employment Type | {employment_type} |\n"
        f"| Monthly Income | {income_str} |\n"
        f"| Existing EMI | {emi_str} |\n"
        f"| Loan Amount | {loan_str} |\n"
        f"| Tenure | {tenure_str} |\n"
        f"| FOIR | {foir_str} |\n"
    )

    text = (
        "**Congratulations! You are eligible for a Tata Capital Personal Loan.**\n\n"
        "**Please verify your details:**\n\n"
        f"{customer_table}\n"
        "To complete your application, we need to verify your identity. "
        "This is a quick 3-step process:\n\n"
        "1. Live Selfie - Take a photo of yourself\n"
        "2. Aadhaar Front - Capture front of your Aadhaar card\n"
        "3. Aadhaar Back - Capture back of your Aadhaar card\n\n"
        "Let us start with your live selfie. Please look at the camera and click the capture button when ready."
    )
    updates |= _append_assistant(state, text)
    updates["current_agent"] = "document_verification"
    updates["previous_agent"] = "eligibility"
    updates["doc_verification_started"] = True
    updates["doc_verification_stage"] = "awaiting_selfie"
    updates["agent_handoff_reason"] = "User eligible, starting document verification"

    return updates


def master_end_conversation(state: AgentState) -> Dict:
    """End the conversation gracefully."""
    updates: Dict = {}

    if state.get("doc_verification_complete"):
        text = (
            "**Your application is complete!**\n\n"
            "We've successfully verified your documents. Our team will review your application "
            "and get back to you within 24-48 hours with the final decision.\n\n"
            "You'll receive updates via SMS and email.\n\n"
            "Thank you for choosing Tata Capital! If you have any questions, feel free to reach out."
        )
    elif state.get("is_eligible") is False:
        text = (
            "Thank you for your interest in Tata Capital Personal Loans.\n\n"
            "Unfortunately, you don't currently meet our eligibility criteria. "
            "However, if your circumstances change (income increase, EMIs close, etc.), "
            "please feel free to try again.\n\n"
            "Is there anything else I can help you with?"
        )
    else:
        text = (
            "Thank you for visiting Tata Capital!\n\n"
            "If you'd like to continue your application later, just come back and we can pick up where we left off."
        )

    updates |= _append_assistant(state, text)
    updates["conversation_ended"] = True
    updates["current_agent"] = "master"

    return updates

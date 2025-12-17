import json
from typing import Dict, List
from anthropic import Anthropic

from ..config import settings
from ..state import EligibilityState

client = Anthropic(api_key=settings.anthropic_api_key)

EXTRACTION_SYSTEM_PROMPT = """
You are an information extraction engine for a bank's personal loan eligibility assistant.

Given the conversation, extract ONLY the following fields and return a SINGLE JSON object, no explanation, no markdown:

{
  "age_years": int | null,
  "dob_raw": str | null,

  "employment_type": "salaried" | "self_employed" | null,
  "job_title": str | null,
  "business_type": str | null,

  "monthly_income": int | null,
  "annual_income": int | null,

  "total_experience_months": int | null,
  "current_job_months": int | null,
  "business_vintage_months": int | null,

  "has_existing_loans": bool | null,
  "total_existing_emi": int | null,

  "requested_loan_amount": int | null,
  "requested_tenure_months": int | null
}

Rules:
- If user says "teacher in government school" treat as salaried, job_title="government school teacher".
- Normalise Indian amounts like "1 lakh", "10L", "1,00,000" into integers in rupees.
- "3 years" -> 36 months, "18 months" -> 18, etc.
- If something is not mentioned, use null.
- Do not include any other keys.
- Do not include comments or extra text. Only JSON.
""".strip()


def _conversation_text(state: EligibilityState) -> str:
    msgs: List[Dict[str, str]] = state.get("messages", [])
    lines = []
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def extract_and_merge_fields(state: EligibilityState) -> Dict:
    user_msg = state.get("user_message")
    if not user_msg:
        return {}

    convo = _conversation_text(state)
    prompt = f"{convo}\n\nUSER: {user_msg}\n\nExtract the latest known values and return JSON only."

    # Bug 6 Fix: Add error handling for LLM failures
    try:
        resp = client.messages.create(
            model=settings.model_name,
            max_tokens=512,
            system=EXTRACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"[LLM Extraction Error] {e}")
        return {}

    text = ""
    for block in resp.content:
        if hasattr(block, "text"):
            text += block.text

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}

    json_str = text[start : end + 1]
    try:
        data = json.loads(json_str)
    except Exception:
        return {}

    allowed = {
        "age_years",
        "dob_raw",
        "employment_type",
        "job_title",
        "business_type",
        "monthly_income",
        "annual_income",
        "total_experience_months",
        "current_job_months",
        "business_vintage_months",
        "has_existing_loans",
        "total_existing_emi",
        "requested_loan_amount",
        "requested_tenure_months",
    }

    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    return updates

from typing import Dict
from ..state import EligibilityState


def ingest_user_message(state: EligibilityState) -> Dict:
    updates: Dict = {}
    user_msg = state.get("user_message")
    if not user_msg:
        return {}

    messages = list(state.get("messages", []))
    messages.append({"role": "user", "content": user_msg})
    updates["messages"] = messages
    return updates

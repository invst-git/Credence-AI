"""
Multi-Agent Loan Eligibility Graph

This graph orchestrates multiple agents:
- Master Agent: Orchestrates flow, greetings, intent detection
- Sales Agent: Customer engagement, requirement gathering
- Eligibility Agent: Hard eligibility checks
- Document Verification Agent: Selfie + Aadhaar capture

Flow:
1. User message -> Ingest
2. Extract fields (LLM)
3. Normalize values
4. Route to appropriate agent based on state
5. Agent processes and responds
6. Loop back for next user message
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver

from .state import AgentState
from .nodes.ingest import ingest_user_message
from .nodes.extraction import extract_and_merge_fields
from .nodes.normalize import normalize_and_compute_derived
from .nodes.rules import apply_hard_rules
from .nodes.questions import decide_next_question
from .nodes.final import final_response
from .nodes.sales import sales_offers
from .nodes.master_agent import (
    master_greeting,
    master_router,
    master_handoff_to_document_verification,
)
from .nodes.sales_agent import sales_conversation
from .nodes.document_verification_agent import doc_verification_router


def create_graph():
    """Create and compile the multi-agent conversation graph."""
    workflow = StateGraph(AgentState)

    # ========== Core Processing Nodes ==========
    workflow.add_node("ingest_user_message", ingest_user_message)
    workflow.add_node("extract_and_merge_fields", extract_and_merge_fields)
    workflow.add_node("normalize_and_compute_derived", normalize_and_compute_derived)
    
    # ========== Master Agent Nodes ==========
    workflow.add_node("master_greeting", master_greeting)
    workflow.add_node("master_router", master_router)
    
    # ========== Sales Agent Nodes ==========
    workflow.add_node("sales_conversation", sales_conversation)
    workflow.add_node("sales_offers_step", sales_offers)  # Legacy sales offers for FOIR negotiation
    
    # ========== Eligibility Agent Nodes ==========
    workflow.add_node("apply_hard_rules", apply_hard_rules)
    workflow.add_node("decide_next_question", decide_next_question)
    workflow.add_node("final_response", final_response)
    
    # ========== Document Verification Agent Nodes ==========
    workflow.add_node("doc_verification_router", doc_verification_router)
    workflow.add_node("handoff_to_doc_verification", master_handoff_to_document_verification)

    # ========== Entry Point ==========
    workflow.set_entry_point("ingest_user_message")
    
    # ========== Core Processing Flow ==========
    workflow.add_edge("ingest_user_message", "extract_and_merge_fields")
    workflow.add_edge("extract_and_merge_fields", "normalize_and_compute_derived")
    
    # ========== Main Router After Normalization ==========
    def route_after_normalize(state: AgentState) -> str:
        """Route to appropriate agent based on current state."""
        
        # Check if conversation hasn't started
        if not state.get("conversation_started"):
            return "master_greeting"
        
        current_agent = state.get("current_agent")
        
        # Document Verification Agent
        if current_agent == "document_verification":
            return "doc_verification_router"
        
        # Sales Agent (active conversation)
        if current_agent == "sales" and state.get("sales_conversation_active"):
            # Check if requirements gathered - handed off to eligibility
            if state.get("customer_requirements_gathered"):
                return "apply_hard_rules"
            return "sales_conversation"
        
        # Eligibility Agent
        if current_agent == "eligibility":
            return "apply_hard_rules"
        
        # Sales mode (FOIR exceeded, offering alternatives)
        if state.get("sales_mode"):
            return "sales_offers_step"
        
        # Default to master router
        return "master_router"
    
    workflow.add_conditional_edges(
        "normalize_and_compute_derived",
        route_after_normalize,
        {
            "master_greeting": "master_greeting",
            "master_router": "master_router",
            "sales_conversation": "sales_conversation",
            "apply_hard_rules": "apply_hard_rules",
            "sales_offers_step": "sales_offers_step",
            "doc_verification_router": "doc_verification_router",
        },
    )
    
    # ========== Master Agent Edges ==========
    workflow.add_edge("master_greeting", END)
    
    def route_after_master(state: AgentState) -> str:
        """Route based on master agent decision."""
        if state.get("conversation_ended"):
            return END
        current_agent = state.get("current_agent")
        if current_agent == "sales":
            return "sales_conversation"
        if current_agent == "eligibility":
            return "apply_hard_rules"
        if current_agent == "document_verification":
            return "doc_verification_router"
        return END
    
    workflow.add_conditional_edges(
        "master_router",
        route_after_master,
        {
            "sales_conversation": "sales_conversation",
            "apply_hard_rules": "apply_hard_rules",
            "doc_verification_router": "doc_verification_router",
            END: END,
        },
    )
    
    # ========== Sales Agent Edges ==========
    def route_after_sales_conversation(state: AgentState) -> str:
        """Route after sales conversation."""
        if state.get("customer_requirements_gathered"):
            return "apply_hard_rules"
        return END
    
    workflow.add_conditional_edges(
        "sales_conversation",
        route_after_sales_conversation,
        {
            "apply_hard_rules": "apply_hard_rules",
            END: END,
        },
    )
    
    # ========== Eligibility Agent Edges ==========
    def route_after_rules(state: AgentState) -> str:
        """Route after applying eligibility rules."""
        if state.get("sales_mode"):
            return "sales_offers_step"
        if state.get("done"):
            if state.get("is_eligible"):
                return "handoff_to_doc_verification"
            return "final_response"
        return "decide_next_question"

    workflow.add_conditional_edges(
        "apply_hard_rules",
        route_after_rules,
        {
            "sales_offers_step": "sales_offers_step",
            "handoff_to_doc_verification": "handoff_to_doc_verification",
            "final_response": "final_response",
            "decide_next_question": "decide_next_question",
        },
    )

    workflow.add_edge("final_response", END)
    workflow.add_edge("decide_next_question", END)
    workflow.add_edge("sales_offers_step", END)
    
    # ========== Document Verification Edges ==========
    workflow.add_edge("handoff_to_doc_verification", END)
    workflow.add_edge("doc_verification_router", END)

    # ========== Compile with Checkpointer ==========
    checkpointer = InMemorySaver()
    app = workflow.compile(checkpointer=checkpointer)
    return app


graph = create_graph()

from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict, total=False):
    """
    Unified state for the multi-agent loan eligibility system.
    Supports Master Agent, Sales Agent, Eligibility Agent, and Document Verification Agent.
    """
    
    # ========== Conversation ==========
    messages: List[Dict[str, str]]
    user_message: Optional[str]
    
    # ========== Multi-Agent Orchestration ==========
    current_agent: Optional[str]       # "master" | "eligibility" | "sales" | "document_verification"
    previous_agent: Optional[str]
    agent_handoff_reason: Optional[str]
    conversation_started: Optional[bool]
    conversation_ended: Optional[bool]
    
    # ========== Customer Intent ==========
    customer_intent: Optional[str]     # "apply_loan" | "check_eligibility" | "inquiry" | "other"
    
    # ========== Core Extracted Fields (Eligibility) ==========
    age_years: Optional[int]
    dob_raw: Optional[str]
    
    employment_type: Optional[str]     # "salaried" or "self_employed"
    job_title: Optional[str]
    business_type: Optional[str]
    
    monthly_income: Optional[int]      # Rs per month
    annual_income: Optional[int]       # Rs per year
    
    total_experience_months: Optional[int]
    current_job_months: Optional[int]
    business_vintage_months: Optional[int]
    
    has_existing_loans: Optional[bool]
    total_existing_emi: Optional[int]  # Rs per month
    
    requested_loan_amount: Optional[int]     # Rs
    requested_tenure_months: Optional[int]   # months
    
    approx_new_emi: Optional[int]
    foir: Optional[float]
    
    is_eligible: Optional[bool]
    ineligibility_reason: Optional[str]
    
    stage: Optional[str]
    done: Optional[bool]
    
    # ========== Sales Agent State ==========
    sales_mode: Optional[bool]
    sales_stage: Optional[str]         # e.g. "awaiting_choice"
    sales_offers: Optional[List[Dict[str, Any]]]
    sales_conversation_active: Optional[bool]
    customer_requirements_gathered: Optional[bool]
    sales_negotiation_round: Optional[int]
    
    # ========== Document Verification Agent State ==========
    doc_verification_started: Optional[bool]
    doc_verification_stage: Optional[str]  # "awaiting_selfie" | "awaiting_aadhaar_front" | "awaiting_aadhaar_back" | "complete"
    selfie_captured: Optional[bool]
    selfie_verified: Optional[bool]
    aadhaar_front_captured: Optional[bool]
    aadhaar_back_captured: Optional[bool]
    aadhaar_verified: Optional[bool]
    doc_verification_complete: Optional[bool]
    
    # ========== Document Data (extracted from Aadhaar via OCR) ==========
    aadhaar_name: Optional[str]
    aadhaar_number: Optional[str]
    aadhaar_dob: Optional[str]
    aadhaar_gender: Optional[str]
    aadhaar_address: Optional[str]
    
    # ========== LandingAI OCR Raw Data (for later stages) ==========
    # Structure: {
    #   "front": {"raw_parse": {...}, "raw_extract": {...}, "full_name": ..., ...},
    #   "back": {"raw_parse": {...}, "raw_extract": {...}, "address": ..., ...}
    # }
    # raw_parse contains: markdown, metadata from LandingAI Parse API
    # raw_extract contains: extraction, metadata from LandingAI Extract API
    aadhaar_ocr_raw: Optional[Dict[str, Any]]
    aadhaar_front_markdown: Optional[str]  # Parsed markdown from front side
    aadhaar_back_markdown: Optional[str]   # Parsed markdown from back side
    
    # ========== Captured Images (base64) ==========
    selfie_image: Optional[str]
    aadhaar_front_image: Optional[str]
    aadhaar_back_image: Optional[str]
    captured_image: Optional[str]  # Temp storage for current capture
    captured_image_type: Optional[str]  # "selfie" | "aadhaar_front" | "aadhaar_back"
    
    # ========== Citizen Verification (DB Match) ==========
    citizen_verified: Optional[bool]
    citizen_found: Optional[bool]
    verification_attempts: Optional[int]  # Max 2 attempts allowed
    verification_mismatch_reason: Optional[str]
    
    # ========== OTP Verification ==========
    otp_phone_number: Optional[str]     # Masked phone from DB lookup
    otp_phone_full: Optional[str]       # Full phone for sending OTP (not exposed to frontend)
    otp_verified: Optional[bool]
    otp_attempts: Optional[int]
    otp_sent_at: Optional[float]        # Unix timestamp when OTP was sent
    
    # ========== Document Upload ==========
    customer_uuid: Optional[str]        # Unique ID for customer folder
    uploaded_documents: Optional[Dict[str, bool]]  # {"pan_card": True, ...}
    document_ocr_results: Optional[Dict[str, Any]]  # OCR results per document
    
    # ========== PAN Verification ==========
    pan_number: Optional[str]
    pan_name: Optional[str]
    pan_dob: Optional[str]
    cibil_score: Optional[int]
    pan_verified: Optional[bool]
    pan_aadhaar_match: Optional[bool]
    pan_verification_attempts: Optional[int]  # Max 2
    pan_rejection_reason: Optional[str]
    
    # ========== Employment Certificate Verification ==========
    employment_verified: Optional[bool]
    employment_employer_name: Optional[str]
    employment_total_exp_months: Optional[int]
    employment_current_job_months: Optional[int]
    employment_verification_attempts: Optional[int]
    employment_rejection_reason: Optional[str]
    
    # ========== Salary Slip Verification ==========
    salary_verified: Optional[bool]
    salary_average_gross: Optional[int]
    salary_employer_warning_given: Optional[bool]
    salary_verification_attempts: Optional[int]
    salary_rejection_reason: Optional[str]
    
    # ========== Bank Statement Verification ==========
    bank_verified: Optional[bool]
    bank_detected_emi: Optional[int]
    bank_closing_balance: Optional[int]
    bank_verification_attempts: Optional[int]
    bank_rejection_reason: Optional[str]
    
    # ========== Address Proof Verification ==========
    address_verified: Optional[bool]
    address_verification_attempts: Optional[int]
    address_rejection_reason: Optional[str]
    
    # ========== Document Retry Tracking ==========
    failed_documents: Optional[List[str]]  # Documents that need retry
    
    # ========== Underwriting ==========
    underwriting_score: Optional[int]
    underwriting_decision: Optional[str]  # "approved", "conditional", "rejected"
    underwriting_conditions: Optional[List[str]]
    underwriting_rejection_reasons: Optional[List[str]]
    underwriting_result: Optional[Dict[str, Any]]  # Full result object for frontend UI


# Alias for backward compatibility
EligibilityState = AgentState

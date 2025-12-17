"""
Multi-Agent Loan Eligibility API

Endpoints:
- POST /eligibility/chat - Main chat endpoint for conversation
- POST /eligibility/upload-document - Document upload endpoint
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import uuid

from .graph import graph
from .services.document_upload_service import (
    process_document_upload,
    get_required_documents,
    get_upload_status,
    all_documents_uploaded,
    SALARIED_DOCUMENTS,
    SELF_EMPLOYED_DOCUMENTS
)


class ChatRequest(BaseModel):
    thread_id: str | None = None
    user_message: str | None = None
    image_data: str | None = None  # Base64 encoded image
    image_type: str | None = None  # "selfie" | "aadhaar_front" | "aadhaar_back"


class ChatResponse(BaseModel):
    assistant_message: str
    current_agent: str | None = None
    is_eligible: bool | None = None
    doc_verification_stage: str | None = None
    otp_notification: str | None = None
    # Document upload fields
    customer_uuid: str | None = None
    employment_type: str | None = None
    uploaded_documents: Dict[str, bool] | None = None
    required_documents: List[Dict] | None = None
    # Underwriting result for loan approval UI
    underwriting_result: Dict | None = None


class DocumentUploadRequest(BaseModel):
    thread_id: str
    customer_uuid: str
    doc_type: str
    pdf_base64: str


class DocumentUploadResponse(BaseModel):
    success: bool
    message: str
    doc_type: str
    uploaded_documents: Dict[str, bool] | None = None
    all_complete: bool = False


app = FastAPI(
    title="Credence - Tata Capital Loan Assistant",
    description="Multi-agent loan eligibility and application system",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Credence Loan Eligibility",
        "version": "2.0.0",
        "agents": ["master", "sales", "eligibility", "document_verification"],
    }


@app.post("/eligibility/chat", response_model=ChatResponse)
async def eligibility_chat(req: ChatRequest):
    """
    Main chat endpoint for multi-agent conversation.
    
    Args:
        req: ChatRequest with thread_id and user_message
        
    Returns:
        ChatResponse with assistant message and current agent state
    """
    thread_id = req.thread_id or f"thread_{uuid.uuid4().hex}"
    user_message = req.user_message or ""

    if not user_message.strip():
        return ChatResponse(assistant_message="Could you share your message so I can help?")

    # Build input state with image if provided
    input_state = {"user_message": user_message}
    if req.image_data:
        input_state["captured_image"] = req.image_data
        input_state["captured_image_type"] = req.image_type
    
    final_state = graph.invoke(
        input_state,
        config={"configurable": {"thread_id": thread_id}},
    )

    # Extract the last assistant message
    messages = final_state.get("messages", [])
    assistant_msg = ""
    for m in reversed(messages):
        if m.get("role") == "assistant":
            assistant_msg = m.get("content", "")
            break
    if not assistant_msg and messages:
        assistant_msg = messages[-1].get("content", "")

    # Get document upload data if in upload stage
    doc_stage = final_state.get("doc_verification_stage")
    required_docs = None
    if doc_stage == "document_upload":
        emp_type = final_state.get("employment_type", "salaried")
        required_docs = get_required_documents(emp_type)

    return ChatResponse(
        assistant_message=assistant_msg,
        current_agent=final_state.get("current_agent"),
        is_eligible=final_state.get("is_eligible"),
        doc_verification_stage=doc_stage,
        otp_notification=None,
        customer_uuid=final_state.get("customer_uuid"),
        employment_type=final_state.get("employment_type"),
        uploaded_documents=final_state.get("uploaded_documents"),
        required_documents=required_docs,
        underwriting_result=final_state.get("underwriting_result"),
    )


@app.post("/eligibility/upload-document", response_model=DocumentUploadResponse)
async def upload_document(req: DocumentUploadRequest):
    """
    Upload a document for processing.
    
    Args:
        req: DocumentUploadRequest with customer_uuid, doc_type, and pdf_base64
        
    Returns:
        DocumentUploadResponse with upload status
    """
    if not req.customer_uuid:
        raise HTTPException(status_code=400, detail="customer_uuid is required")
    
    if not req.doc_type:
        raise HTTPException(status_code=400, detail="doc_type is required")
    
    if not req.pdf_base64:
        raise HTTPException(status_code=400, detail="pdf_base64 is required")
    
    # Process the upload
    result = process_document_upload(req.customer_uuid, req.doc_type, req.pdf_base64)
    
    # Get updated status - need to get employment type from thread state
    # For now, check both salaried and self-employed
    try:
        final_state = graph.invoke(
            {"user_message": ""},
            config={"configurable": {"thread_id": req.thread_id}},
        )
        emp_type = final_state.get("employment_type", "salaried")
        
        # Update the uploaded_documents in state
        uploaded_docs = final_state.get("uploaded_documents", {})
        if result.success:
            uploaded_docs[req.doc_type] = True
        
        # Check if all complete
        all_complete = all_documents_uploaded(req.customer_uuid, emp_type)
        
    except Exception as e:
        print(f"[Upload] Error getting state: {e}")
        uploaded_docs = {req.doc_type: result.success}
        all_complete = False
    
    return DocumentUploadResponse(
        success=result.success,
        message=result.message,
        doc_type=req.doc_type,
        uploaded_documents=uploaded_docs,
        all_complete=all_complete,
    )


@app.post("/reset-thread/{thread_id}")
async def reset_thread(thread_id: str):
    """
    Reset a conversation thread (for testing).
    Note: With InMemorySaver, this is a no-op as state is already ephemeral.
    """
    return {"status": "ok", "thread_id": thread_id, "message": "Thread reset"}


# ========== Loan Decision Endpoints ==========

from fastapi.responses import Response
from .services.sanction_letter_service import (
    generate_sanction_letter_pdf,
    SanctionLetterData,
    generate_reference_number
)
from datetime import datetime
import base64


class LoanDecisionRequest(BaseModel):
    thread_id: str
    decision: str  # "accept" or "decline"
    email: str | None = None  # Optional email for sending sanction letter


class LoanDecisionResponse(BaseModel):
    success: bool
    message: str
    pdf_base64: str | None = None
    pdf_filename: str | None = None
    reference_number: str | None = None


@app.post("/eligibility/loan-decision", response_model=LoanDecisionResponse)
async def handle_loan_decision(req: LoanDecisionRequest):
    """
    Handle user's accept/decline decision on loan offer.
    
    If accepted, generates sanction letter PDF.
    If declined, just acknowledges the decision.
    """
    # Get current state
    try:
        final_state = graph.invoke(
            {"user_message": ""},
            config={"configurable": {"thread_id": req.thread_id}},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get state: {e}")
    
    if req.decision == "decline":
        return LoanDecisionResponse(
            success=True,
            message="You chose to decline the loan offer. Thank you for considering Tata Capital."
        )
    
    elif req.decision == "accept":
        # Generate sanction letter
        aadhaar_name = final_state.get("aadhaar_name", "Customer")
        aadhaar_number = final_state.get("aadhaar_number", "")
        pan_number = final_state.get("pan_number", "")
        address = final_state.get("aadhaar_address", "")
        phone = final_state.get("citizen_phone", "")
        
        loan_amount = final_state.get("requested_loan_amount", 0)
        interest_rate = 16.0
        tenure = final_state.get("requested_tenure_months", 36)
        
        # Calculate EMI
        monthly_rate = interest_rate / 100 / 12
        if monthly_rate > 0 and tenure > 0:
            emi = int(loan_amount * monthly_rate * ((1 + monthly_rate) ** tenure) / (((1 + monthly_rate) ** tenure) - 1))
        else:
            emi = int(loan_amount / tenure) if tenure > 0 else 0
        
        processing_fee = int(loan_amount * 0.015)  # 1.5%
        total_interest = (emi * tenure) - loan_amount
        total_payable = loan_amount + total_interest + processing_fee
        
        cibil = final_state.get("cibil_score", 0)
        
        ref_num = generate_reference_number()
        
        letter_data = SanctionLetterData(
            customer_name=aadhaar_name,
            aadhaar_number=aadhaar_number,
            pan_number=pan_number,
            address=address,
            phone_number=phone,
            loan_amount=loan_amount,
            interest_rate=interest_rate,
            tenure_months=tenure,
            emi_amount=emi,
            processing_fee=processing_fee,
            total_interest=total_interest,
            total_payable=total_payable,
            cibil_score=cibil,
            reference_number=ref_num
        )
        
        # Generate PDF
        pdf_bytes = generate_sanction_letter_pdf(letter_data)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        
        # Generate filename
        clean_name = aadhaar_name.replace(" ", "_")
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{clean_name}_Sanction_Letter_{date_str}.pdf"
        
        # Mock email sending
        email_msg = ""
        if req.email:
            email_msg = f" A copy has been sent to {req.email}."
        
        return LoanDecisionResponse(
            success=True,
            message=f"Congratulations! Your loan has been sanctioned.{email_msg}",
            pdf_base64=pdf_base64,
            pdf_filename=filename,
            reference_number=ref_num
        )
    
    else:
        raise HTTPException(status_code=400, detail="Invalid decision. Use 'accept' or 'decline'.")

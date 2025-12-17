"""
Document Verification Agent - Handles identity verification through selfie and Aadhaar capture.

Responsibilities:
- Guide user through live selfie capture
- Guide user through Aadhaar card front capture
- Guide user through Aadhaar card back capture
- Extract Aadhaar data via LandingAI OCR
- Verify extracted data against citizen database
- Send OTP to registered phone and verify
- Display extracted details for confirmation
- Track verification status
- Provide clear instructions at each step
- Handle retakes and errors gracefully
"""

import time
from typing import Dict, Any
from ..state import AgentState
from ..services.landing_ai_service import (
    process_aadhaar_front,
    process_aadhaar_back,
    format_aadhaar_for_display,
    mask_aadhaar_number
)
from ..services.citizen_service import (
    verify_citizen,
    mask_phone_number
)
from ..services.otp_service import (
    send_otp,
    verify_otp,
    extract_otp_from_message,
    mask_phone_for_display,
    MAX_OTP_ATTEMPTS
)
from ..services.document_upload_service import (
    generate_customer_uuid,
    get_required_documents,
    create_customer_folder,
    all_documents_uploaded,
    get_upload_status
)
from ..services.pan_verification_service import (
    verify_pan,
    extract_pan_from_ocr,
    MIN_CREDIT_SCORE
)
from ..services.employment_verification_service import (
    verify_employment_certificate
)
from ..services.salary_verification_service import (
    verify_salary_slips
)
from ..services.bank_verification_service import (
    verify_bank_statement
)
from ..services.address_verification_service import (
    verify_address_proof
)
from ..services.underwriting_service import (
    perform_underwriting,
    format_loan_details_table,
    format_score_breakdown
)


def _append_assistant(state: AgentState, text: str) -> Dict:
    """Helper to append assistant message to conversation."""
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": text})
    return {"messages": messages}


def doc_verification_router(state: AgentState) -> Dict:
    """
    Route based on current verification stage.
    Called when document_verification is the current agent.
    """
    # Only run if doc verification agent is active
    if state.get("current_agent") != "document_verification":
        return {}
    
    stage = state.get("doc_verification_stage")
    user_message = state.get("user_message", "").lower().strip()
    
    # Handle user responses at each stage
    if stage == "awaiting_selfie":
        return handle_selfie_stage(state, user_message)
    elif stage == "awaiting_aadhaar_front":
        return handle_aadhaar_front_stage(state, user_message)
    elif stage == "awaiting_aadhaar_back":
        return handle_aadhaar_back_stage(state, user_message)
    elif stage == "extracting_aadhaar":
        return process_ocr_extraction(state)
    elif stage == "awaiting_retry":
        return handle_retry_stage(state, user_message)
    elif stage == "awaiting_otp":
        return handle_otp_stage(state, user_message)
    elif stage == "otp_verified":
        return proceed_to_document_upload(state)
    elif stage == "verification_failed":
        return handle_verification_failed(state, user_message)
    elif stage == "document_upload":
        return handle_document_upload_stage(state, user_message)
    elif stage == "verifying_pan":
        return handle_pan_verification(state)
    elif stage == "pan_retry":
        return handle_pan_retry_stage(state, user_message)
    elif stage == "pan_rejected":
        return handle_pan_rejected(state, user_message)
    elif stage == "verifying_employment":
        return handle_employment_verification(state)
    elif stage == "employment_retry":
        return handle_doc_retry_stage(state, user_message, "employment_certificate")
    elif stage == "verifying_salary":
        return handle_salary_verification(state)
    elif stage == "salary_retry":
        return handle_doc_retry_stage(state, user_message, "salary_slips")
    elif stage == "verifying_bank":
        return handle_bank_verification(state)
    elif stage == "bank_retry":
        return handle_doc_retry_stage(state, user_message, "bank_statements")
    elif stage == "verifying_address":
        return handle_address_verification(state)
    elif stage == "address_retry":
        return handle_doc_retry_stage(state, user_message, "address_proof")
    elif stage == "verification_rejected":
        return handle_final_rejection(state, user_message)
    elif stage == "underwriting":
        return handle_underwriting(state)
    elif stage == "complete":
        return verification_complete(state)
    else:
        # Initialize - start with selfie request
        return request_selfie(state)


def request_selfie(state: AgentState) -> Dict:
    """Ask user to capture a live selfie."""
    updates: Dict = {}
    
    text = (
        "**Step 1 of 3: Live Selfie**\n\n"
        "Please take a clear photo of your face. Ensure the following:\n\n"
        "- Good lighting on your face\n"
        "- Face the camera directly\n"
        "- Remove glasses or hats\n"
        "- Keep a neutral expression\n\n"
        "**Click the camera button below to capture your selfie.**"
    )
    
    updates |= _append_assistant(state, text)
    updates["doc_verification_stage"] = "awaiting_selfie"
    
    return updates


def handle_selfie_stage(state: AgentState, user_message: str) -> Dict:
    """Handle user response during selfie capture stage."""
    updates: Dict = {}
    
    # Check for capture confirmation
    if any(word in user_message for word in ["captured", "done", "taken", "ok", "yes", "next", "ready"]):
        # Store selfie image if provided
        captured_image = state.get("captured_image")
        if captured_image and state.get("captured_image_type") == "selfie":
            updates["selfie_image"] = captured_image
        
        updates["selfie_captured"] = True
        updates["selfie_verified"] = True  # Face matching skipped for MVP
        
        # Request next step
        next_step = request_aadhaar_front(state)
        updates.update(next_step)
        return updates
    
    # Check for help request
    if "help" in user_message or "issue" in user_message or "problem" in user_message:
        text = (
            "**Selfie Capture Help**\n\n"
            "Having trouble? Here are some tips:\n\n"
            "1. Make sure you're in a well-lit area\n"
            "2. Hold your phone at eye level\n"
            "3. Check that your full face is visible\n"
            "4. Avoid backlight (do not stand in front of windows)\n\n"
            "If the camera is not working, try refreshing the page."
        )
        updates |= _append_assistant(state, text)
        return updates
    
    # Check for skip/retry
    if "retake" in user_message or "again" in user_message:
        return request_selfie(state)
    
    # Default - remind them what to do
    text = (
        "We are waiting for your selfie.\n\n"
        "Please capture your photo using the camera button."
    )
    updates |= _append_assistant(state, text)
    return updates


def request_aadhaar_front(state: AgentState) -> Dict:
    """Ask user to capture the front of their Aadhaar card."""
    updates: Dict = {}
    
    text = (
        "Selfie captured successfully.\n\n"
        "**Step 2 of 3: Aadhaar Card (Front)**\n\n"
        "Now, please capture the **front side** of your Aadhaar card. Ensure the following:\n\n"
        "- The entire card is visible\n"
        "- Text and photo are clearly readable\n"
        "- No glare or shadows on the card\n"
        "- Card is placed on a flat, contrasting surface\n\n"
        "**Click the camera button to capture the front of your Aadhaar.**"
    )
    
    updates |= _append_assistant(state, text)
    updates["doc_verification_stage"] = "awaiting_aadhaar_front"
    
    return updates


def handle_aadhaar_front_stage(state: AgentState, user_message: str) -> Dict:
    """Handle user response during Aadhaar front capture stage."""
    updates: Dict = {}
    
    # Check for capture confirmation
    if any(word in user_message for word in ["captured", "done", "taken", "ok", "yes", "next", "ready"]):
        # Store front image if provided
        captured_image = state.get("captured_image")
        if captured_image and state.get("captured_image_type") == "aadhaar_front":
            updates["aadhaar_front_image"] = captured_image
        
        updates["aadhaar_front_captured"] = True
        
        # Request next step
        next_step = request_aadhaar_back(state)
        updates.update(next_step)
        return updates
    
    # Check for help request
    if "help" in user_message or "issue" in user_message or "problem" in user_message:
        text = (
            "**Aadhaar Front Capture Help**\n\n"
            "Tips for a clear capture:\n\n"
            "1. Place the card on a dark, solid surface\n"
            "2. Make sure all 4 corners are visible\n"
            "3. Avoid capturing at an angle\n"
            "4. Turn off flash if there is glare\n"
            "5. Hold the camera steady"
        )
        updates |= _append_assistant(state, text)
        return updates
    
    # Check for retake
    if "retake" in user_message or "again" in user_message:
        return request_aadhaar_front(state)
    
    # Default reminder
    text = (
        "We are waiting for the front of your Aadhaar card.\n\n"
        "Please capture it using the camera button."
    )
    updates |= _append_assistant(state, text)
    return updates


def request_aadhaar_back(state: AgentState) -> Dict:
    """Ask user to capture the back of their Aadhaar card."""
    updates: Dict = {}
    
    text = (
        "Aadhaar front captured.\n\n"
        "**Step 3 of 3: Aadhaar Card (Back)**\n\n"
        "Almost done. Please capture the **back side** of your Aadhaar card.\n\n"
        "Make sure the address and QR code are clearly visible.\n\n"
        "**Click the camera button to capture the back of your Aadhaar.**"
    )
    
    updates |= _append_assistant(state, text)
    updates["doc_verification_stage"] = "awaiting_aadhaar_back"
    
    return updates


def handle_aadhaar_back_stage(state: AgentState, user_message: str) -> Dict:
    """Handle user response during Aadhaar back capture stage."""
    updates: Dict = {}
    
    # Check for capture confirmation
    if any(word in user_message for word in ["captured", "done", "taken", "ok", "yes", "next", "ready"]):
        # Store back image if provided
        captured_image = state.get("captured_image")
        if captured_image and state.get("captured_image_type") == "aadhaar_back":
            updates["aadhaar_back_image"] = captured_image
        
        updates["aadhaar_back_captured"] = True
        updates["doc_verification_stage"] = "extracting_aadhaar"
        
        # Show processing message
        text = (
            "**Processing your documents...**\n\n"
            "Please wait while we extract and verify your Aadhaar details.\n"
            "This may take a few seconds."
        )
        updates |= _append_assistant(state, text)
        
        # Trigger OCR extraction
        ocr_result = process_ocr_extraction_sync(state, updates)
        updates.update(ocr_result)
        
        return updates
    
    # Check for help request
    if "help" in user_message or "issue" in user_message:
        text = (
            "**Aadhaar Back Capture Help**\n\n"
            "Same tips as before:\n\n"
            "1. Flip the card to show the back\n"
            "2. Make sure address text is readable\n"
            "3. QR code should be clearly visible\n"
            "4. Keep the camera steady"
        )
        updates |= _append_assistant(state, text)
        return updates
    
    # Check for retake
    if "retake" in user_message or "again" in user_message:
        return request_aadhaar_back(state)
    
    # Default reminder
    text = (
        "We are waiting for the back of your Aadhaar card.\n\n"
        "Please capture it using the camera button."
    )
    updates |= _append_assistant(state, text)
    return updates


def handle_retry_stage(state: AgentState, user_message: str) -> Dict:
    """Handle user response when awaiting retry decision."""
    updates: Dict = {}
    
    if any(word in user_message for word in ["retry", "yes", "try", "again", "continue"]):
        # Clear previous images and restart from Aadhaar front
        updates["aadhaar_front_image"] = None
        updates["aadhaar_back_image"] = None
        updates["aadhaar_front_captured"] = False
        updates["aadhaar_back_captured"] = False
        
        text = (
            "**Let us try again.**\n\n"
            "Please capture the **front side** of your Aadhaar card.\n"
            "Make sure the image is clear and well-lit."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "awaiting_aadhaar_front"
        return updates
    
    if any(word in user_message for word in ["cancel", "no", "exit", "stop", "quit"]):
        text = (
            "**Verification Cancelled**\n\n"
            "Your loan application cannot proceed without identity verification.\n"
            "Please contact our support team if you need assistance."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verification_failed"
        updates["done"] = True
        updates["current_agent"] = "master"
        return updates
    
    # Default - remind them of options
    text = (
        "Please type 'retry' to try capturing your Aadhaar again, "
        "or 'cancel' to exit verification."
    )
    updates |= _append_assistant(state, text)
    return updates


def handle_verification_failed(state: AgentState, user_message: str) -> Dict:
    """Handle user input after verification has failed."""
    updates: Dict = {}
    
    # Just acknowledge and keep them at failed state
    text = (
        "Your verification has ended. Please contact our support team for assistance.\n\n"
        "You can reach us at:\n"
        "Phone: 1800-XXX-XXXX (Toll Free)\n"
        "Email: support@tatacapital.com"
    )
    updates |= _append_assistant(state, text)
    return updates


def process_ocr_extraction(state: AgentState) -> Dict:
    """Process OCR extraction from captured images."""
    return process_ocr_extraction_sync(state, {})


def process_ocr_extraction_sync(state: AgentState, updates: Dict) -> Dict:
    """
    Process OCR extraction from captured Aadhaar images.
    Extracts data from both front and back images using LandingAI.
    """
    front_image = state.get("aadhaar_front_image") or updates.get("aadhaar_front_image")
    back_image = state.get("aadhaar_back_image") or updates.get("aadhaar_back_image")
    
    # If no images, show error
    if not front_image or not back_image:
        text = (
            "**Image Processing Error**\n\n"
            "We could not process your Aadhaar images. Please try capturing them again.\n\n"
            "Reason: One or more images were not received properly."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "awaiting_aadhaar_front"
        return updates
    
    try:
        # Call synchronous OCR functions directly
        front_result = process_aadhaar_front(front_image)
        back_result = process_aadhaar_back(back_image)
        
        # Check for errors
        if "error" in front_result or "error" in back_result:
            error_msg = front_result.get("error") or back_result.get("error")
            text = (
                "**OCR Extraction Failed**\n\n"
                f"We encountered an issue processing your Aadhaar: {error_msg}\n\n"
                "Please try capturing clearer images of your Aadhaar card."
            )
            updates |= _append_assistant(state, text)
            updates["doc_verification_stage"] = "awaiting_aadhaar_front"
            return updates
        
        # Store extracted data
        aadhaar_name = front_result.get("full_name")
        aadhaar_dob = front_result.get("date_of_birth")
        aadhaar_number = front_result.get("aadhaar_number")
        aadhaar_gender = front_result.get("gender")
        aadhaar_address = back_result.get("address")
        
        # Validate Aadhaar number
        if not aadhaar_number or len(aadhaar_number.replace(" ", "")) != 12:
            text = (
                "**Aadhaar Validation Failed**\n\n"
                "We could not extract a valid 12-digit Aadhaar number from your image.\n\n"
                "Please ensure:\n"
                "- The Aadhaar card is clearly visible\n"
                "- The number is not obscured or blurry\n"
                "- You are using a valid Aadhaar card\n\n"
                "Try capturing the front side again."
            )
            updates |= _append_assistant(state, text)
            updates["doc_verification_stage"] = "awaiting_aadhaar_front"
            return updates
        
        # Store in state
        updates["aadhaar_name"] = aadhaar_name
        updates["aadhaar_dob"] = aadhaar_dob
        updates["aadhaar_number"] = aadhaar_number
        updates["aadhaar_gender"] = aadhaar_gender
        updates["aadhaar_address"] = aadhaar_address
        
        # Store full OCR data from LandingAI (parse + extract JSONs)
        updates["aadhaar_ocr_raw"] = {
            "front": front_result,
            "back": back_result
        }
        
        # Store parsed markdown separately for easy access
        front_markdown = front_result.get("raw_parse", {}).get("markdown", "")
        back_markdown = back_result.get("raw_parse", {}).get("markdown", "")
        updates["aadhaar_front_markdown"] = front_markdown
        updates["aadhaar_back_markdown"] = back_markdown
        
        # Display extracted details
        formatted_aadhaar = format_aadhaar_for_display(aadhaar_number)
        
        text = (
            "**Aadhaar Details Extracted:**\n\n"
            f"**Name:** {aadhaar_name or 'Not extracted'}\n"
            f"**Date of Birth:** {aadhaar_dob or 'Not extracted'}\n"
            f"**Aadhaar Number:** {formatted_aadhaar}\n"
        )
        
        if aadhaar_gender:
            text += f"**Gender:** {aadhaar_gender}\n"
        
        if aadhaar_address:
            addr_display = aadhaar_address[:100] + "..." if len(aadhaar_address) > 100 else aadhaar_address
            text += f"**Address:** {addr_display}\n"
        
        text += "\n**Verifying against our records...**"
        updates |= _append_assistant(state, text)
        
        # ========== CITIZEN VERIFICATION ==========
        current_attempts = state.get("verification_attempts", 0) + 1
        updates["verification_attempts"] = current_attempts
        
        try:
            verification_result = verify_citizen(
                aadhaar_number=aadhaar_number,
                extracted_name=aadhaar_name,
                extracted_dob=aadhaar_dob,
                extracted_address=aadhaar_address
            )
        except Exception as ve:
            text = (
                "\n\n**Database Connection Error**\n\n"
                f"Could not connect to verification database: {str(ve)}\n\n"
                "Please try again later."
            )
            updates |= _append_assistant(state, text)
            updates["doc_verification_stage"] = "awaiting_aadhaar_front"
            return updates
        
        updates["citizen_found"] = verification_result.citizen_found
        updates["citizen_verified"] = verification_result.is_verified
        
        if verification_result.is_verified:
            # SUCCESS - Citizen verified! Now send OTP
            phone_number = verification_result.phone_number or ""
            masked_phone = mask_phone_number(phone_number)
            updates["otp_phone_number"] = masked_phone
            updates["otp_phone_full"] = phone_number
            updates["aadhaar_verified"] = True
            updates["otp_attempts"] = 0
            updates["otp_sent_at"] = time.time()
            
            # Send OTP via Supabase Auth
            otp_result = send_otp(phone_number)
            
            if otp_result.success:
                updates["doc_verification_stage"] = "awaiting_otp"
                
                text = (
                    "**Identity Verified Successfully**\n\n"
                    "Your Aadhaar details match our records.\n\n"
                    f"**Phone Number on File:** {masked_phone}\n\n"
                    "**OTP Verification**\n\n"
                    f"We have sent a 6-digit OTP to {masked_phone}. "
                    "Please enter the OTP below to complete verification."
                )
                updates |= _append_assistant(state, text)
            else:
                # OTP sending failed - still allow proceeding for now
                updates["doc_verification_stage"] = "awaiting_otp"
                
                text = (
                    "**Identity Verified Successfully**\n\n"
                    "Your Aadhaar details match our records.\n\n"
                    f"**Phone Number on File:** {masked_phone}\n\n"
                    "**OTP Verification**\n\n"
                    f"Enter the 6-digit OTP sent to {masked_phone}."
                )
                updates |= _append_assistant(state, text)
            
        elif not verification_result.citizen_found:
            # HARD REJECT - Aadhaar not in database
            updates["verification_mismatch_reason"] = verification_result.mismatch_details
            updates["doc_verification_stage"] = "verification_failed"
            
            text = (
                "\n\n**Verification Failed**\n\n"
                "**Reason:** Your Aadhaar number was not found in our customer database.\n\n"
                "This could mean:\n"
                "- You do not have an existing account with us\n"
                "- The Aadhaar number was not captured correctly\n\n"
                "Please contact our support team for assistance or try again with a clearer image."
            )
            updates |= _append_assistant(state, text)
            
            if current_attempts < 2:
                text = (
                    f"\n\n**You have {2 - current_attempts} attempt(s) remaining.**\n"
                    "Would you like to try capturing your Aadhaar card again?\n\n"
                    "_Type 'retry' to try again or 'cancel' to exit._"
                )
                updates |= _append_assistant(state, text)
                updates["doc_verification_stage"] = "awaiting_retry"
            else:
                updates["done"] = True
                updates["current_agent"] = "master"
            
        else:
            # MISMATCH - Details don't match
            updates["verification_mismatch_reason"] = verification_result.mismatch_details
            
            text = (
                "\n\n**Verification Mismatch**\n\n"
                "The details extracted from your Aadhaar do not match our records:\n\n"
                f"```\n{verification_result.mismatch_details}\n```\n\n"
            )
            
            if current_attempts < 2:
                text += (
                    f"**You have {2 - current_attempts} attempt(s) remaining.**\n\n"
                    "This could be due to:\n"
                    "- Poor image quality causing OCR errors\n"
                    "- Outdated information in your Aadhaar\n\n"
                    "Please try capturing clearer images of your Aadhaar card.\n"
                    "_Type 'retry' to try again or 'cancel' to exit._"
                )
                updates |= _append_assistant(state, text)
                updates["doc_verification_stage"] = "awaiting_retry"
            else:
                text += (
                    "**Maximum attempts reached.**\n\n"
                    "Unfortunately, we could not verify your identity. "
                    "Please contact our support team for assistance.\n\n"
                    "Your application cannot proceed without identity verification."
                )
                updates |= _append_assistant(state, text)
                updates["doc_verification_stage"] = "verification_failed"
                updates["done"] = True
                updates["current_agent"] = "master"
        
        return updates
        
    except Exception as e:
        text = (
            "**Processing Error**\n\n"
            f"An unexpected error occurred: {str(e)}\n\n"
            "Please try again or contact support if the issue persists."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "awaiting_aadhaar_front"
        return updates


def _finalize_verification(state: AgentState, current_updates: Dict) -> Dict:
    """Finalize verification after successful OCR extraction."""
    updates: Dict = {}
    
    loan_amount = state.get("requested_loan_amount", 0)
    tenure = state.get("requested_tenure_months", 0)
    emi = state.get("approx_new_emi", 0)
    
    # Get extracted name for personalization
    aadhaar_name = current_updates.get("aadhaar_name") or state.get("aadhaar_name")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    
    text = (
        f"\n\n**Congratulations, {first_name}.**\n\n"
        "Your identity has been verified and your loan application is being processed.\n\n"
        f"**Application Summary**\n"
        f"- Loan Amount: **Rs {loan_amount:,}**\n"
        f"- Tenure: **{tenure} months**\n"
    )
    
    if emi:
        text += f"- Estimated EMI: **Rs {emi:,}**/month\n"
    
    text += (
        "\n**What Happens Next?**\n"
        "1. Our team will review your application\n"
        "2. You will receive an update within 24-48 hours\n"
        "3. Once approved, funds will be disbursed to your account\n\n"
        "You will receive notifications via SMS and email.\n\n"
        "Thank you for choosing Tata Capital."
    )
    
    updates |= _append_assistant(state, text)
    updates["doc_verification_complete"] = True
    updates["done"] = True
    updates["current_agent"] = "master"  # Return to master for any follow-up
    
    return updates


def verification_complete(state: AgentState) -> Dict:
    """Handle successful completion of all document verification."""
    updates: Dict = {}
    
    # Check if already marked complete
    if state.get("doc_verification_complete"):
        return {}
    
    return _finalize_verification(state, {})


def doc_verification_handle_skip(state: AgentState) -> Dict:
    """Handle if user wants to skip or do later."""
    updates: Dict = {}
    
    text = (
        "We understand you may not be ready to complete verification right now.\n\n"
        "Your eligibility result has been saved. You can return anytime to complete "
        "the document verification and proceed with your loan application.\n\n"
        "Simply come back and say 'continue verification' to pick up where you left off."
    )
    
    updates |= _append_assistant(state, text)
    updates["current_agent"] = "master"
    
    return updates


def handle_otp_stage(state: AgentState, user_message: str) -> Dict:
    """
    Handle user input during OTP verification stage.
    
    Validates 6-digit OTP, tracks attempts, and handles resend requests.
    """
    updates: Dict = {}
    
    masked_phone = state.get("otp_phone_number", "")
    full_phone = state.get("otp_phone_full", "")
    current_attempts = state.get("otp_attempts", 0)
    
    # Check for resend request
    if "resend" in user_message or "send again" in user_message or "new otp" in user_message:
        return resend_otp(state)
    
    # Extract OTP from message
    otp_code = extract_otp_from_message(user_message)
    
    if not otp_code:
        # Could not parse OTP from message
        text = "Please enter the 6-digit OTP sent to your phone."
        updates |= _append_assistant(state, text)
        return updates
    
    # Verify OTP via Supabase Auth
    result = verify_otp(full_phone, otp_code, current_attempts)
    updates["otp_attempts"] = current_attempts + 1
    
    if result.success:
        # OTP verified successfully!
        updates["otp_verified"] = True
        updates["doc_verification_stage"] = "otp_verified"
        
        text = (
            "**OTP Verified Successfully**\n\n"
            "Your phone number has been confirmed.\n\n"
            "---\n\n"
            "**Next Step: Document Upload**\n\n"
            "Please proceed to upload your required documents."
        )
        updates |= _append_assistant(state, text)
        
        # Proceed to document upload
        upload_updates = proceed_to_document_upload(state)
        updates.update(upload_updates)
        
    else:
        # OTP verification failed
        attempts_remaining = result.attempts_remaining or (MAX_OTP_ATTEMPTS - current_attempts - 1)
        
        if attempts_remaining <= 0:
            # Max attempts reached
            updates["doc_verification_stage"] = "verification_failed"
            text = (
                "**OTP Verification Failed**\n\n"
                "Maximum attempts exceeded. Your verification session has ended.\n\n"
                "Please contact our support team for assistance:\n"
                "Phone: 1800-XXX-XXXX (Toll Free)\n"
                "Email: support@tatacapital.com"
            )
            updates |= _append_assistant(state, text)
            updates["done"] = True
            updates["current_agent"] = "master"
        else:
            # Still have attempts - this is the retry path
            updates["doc_verification_stage"] = "awaiting_otp"  # Stay in OTP stage for retry
            if result.error == "OTP_EXPIRED":
                text = (
                    "**OTP Expired**\n\n"
                    "Your OTP has expired. Click 'Resend OTP' to get a new one."
                )
            else:
                text = (
                    f"**Invalid OTP**\n\n"
                    f"The OTP you entered is incorrect.\n"
                    f"You have **{attempts_remaining}** attempt(s) remaining.\n\n"
                    "Please try again."
                )
            updates |= _append_assistant(state, text)
    
    return updates


def resend_otp(state: AgentState) -> Dict:
    """Resend OTP to the registered phone number."""
    updates: Dict = {}
    
    full_phone = state.get("otp_phone_full", "")
    masked_phone = state.get("otp_phone_number", "")
    
    if not full_phone:
        text = (
            "**Error**\n\n"
            "Could not find phone number. Please restart the verification process."
        )
        updates |= _append_assistant(state, text)
        return updates
    
    # Reset attempts and send new OTP
    updates["otp_attempts"] = 0
    updates["otp_sent_at"] = time.time()
    
    result = send_otp(full_phone)
    
    if result.success:
        text = (
            f"**New OTP Sent**\n\n"
            f"A new 6-digit OTP has been sent to {masked_phone}.\n\n"
            "_The OTP is valid for 5 minutes._"
        )
    else:
        text = (
            f"**OTP Resend Requested**\n\n"
            f"Please enter the OTP sent to {masked_phone}.\n\n"
            "_The OTP is valid for 5 minutes._"
        )
    
    updates |= _append_assistant(state, text)
    return updates


def proceed_to_document_upload(state: AgentState) -> Dict:
    """
    Proceed to document upload phase after OTP verification.
    
    Shows document upload UI based on employment type (salaried/self-employed).
    """
    updates: Dict = {}
    
    aadhaar_name = state.get("aadhaar_name", "")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    employment_type = state.get("employment_type", "salaried")
    
    # Generate customer UUID if not already created
    customer_uuid = state.get("customer_uuid")
    if not customer_uuid:
        customer_uuid = generate_customer_uuid()
        updates["customer_uuid"] = customer_uuid
        create_customer_folder(customer_uuid)
    
    # Get required documents for employment type
    required_docs = get_required_documents(employment_type)
    
    # Initialize upload status
    uploaded_documents = {doc["id"]: False for doc in required_docs}
    updates["uploaded_documents"] = uploaded_documents
    
    # Pass required docs to frontend so it can render the Upload UI
    updates["required_documents"] = required_docs
    
    # Build document list for display (as backup/context)
    doc_list = "\n".join([f"- {doc['name']}" for doc in required_docs])
    
    text = (
        f"**Excellent, {first_name}!**\n\n"
        "Your identity has been verified successfully.\n\n"
        "**Document Upload**\n\n"
        "Please upload the required documents using the buttons below."
    )
    
    updates |= _append_assistant(state, text)
    updates["otp_verified"] = True
    updates["doc_verification_stage"] = "document_upload"
    
    print(f"[Document Upload] Proceeding to upload stage for customer {customer_uuid}")
    
    return updates


def handle_document_upload_stage(state: AgentState, user_message: str) -> Dict:
    """
    Handle document upload stage.
    
    Documents are uploaded via separate API endpoint, so this mainly handles
    status checks and the 'proceed' command.
    """
    updates: Dict = {}
    
    customer_uuid = state.get("customer_uuid", "")
    employment_type = state.get("employment_type", "salaried")
    
    # Check if user clicked "Proceed" after all uploads complete
    if user_message == "proceed" or user_message == "all_documents_uploaded":
        # Check file system for actual upload status (not stale state dict)
        if customer_uuid and all_documents_uploaded(customer_uuid, employment_type):
            return handle_all_documents_complete(state)
        else:
            # Some documents still pending - get actual status from file system
            if customer_uuid:
                upload_status = get_upload_status(customer_uuid, employment_type)
                pending = [k for k, v in upload_status.items() if not v]
            else:
                pending = ["Unable to determine - customer UUID missing"]
            
            text = (
                "**Documents Still Required**\n\n"
                f"Please upload the following documents before proceeding:\n"
                f"- {', '.join(pending)}"
            )
            updates |= _append_assistant(state, text)
            return updates
    
    # Default response - remind about uploads
    text = "Please upload all required documents using the Upload buttons above."
    updates |= _append_assistant(state, text)
    return updates


def handle_all_documents_complete(state: AgentState) -> Dict:
    """
    Handle when all documents have been uploaded and processed.
    """
    updates: Dict = {}
    
    customer_uuid = state.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    
    # Log for future agent integration
    print(f"[Document Upload] All documents uploaded for customer {customer_uuid}")
    print("[Document Upload] Starting PAN verification...")
    
    # Trigger PAN verification instead of completing
    updates["doc_verification_stage"] = "verifying_pan"
    
    # Process PAN verification immediately
    pan_result = handle_pan_verification_internal(state, updates)
    updates.update(pan_result)
    
    return updates


def handle_pan_verification_internal(state: AgentState, current_updates: Dict) -> Dict:
    """
    Internal function to verify PAN after upload.
    Called from handle_all_documents_complete.
    """
    import os
    import json
    
    updates: Dict = {}
    
    customer_uuid = state.get("customer_uuid") or current_updates.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    aadhaar_dob = state.get("aadhaar_dob", "")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    
    # Get current attempt count
    pan_attempts = state.get("pan_verification_attempts", 0)
    
    # Read PAN OCR result from file
    pan_ocr_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "customer_data", 
        customer_uuid, "pan_card_ocr.json"
    )
    
    pan_ocr_result = None
    print(f"[PAN Verification] Looking for OCR file at: {pan_ocr_path}")
    if os.path.exists(pan_ocr_path):
        try:
            with open(pan_ocr_path, "r", encoding="utf-8") as f:
                pan_ocr_result = json.load(f)
            print(f"[PAN Verification] Successfully loaded OCR file with keys: {list(pan_ocr_result.keys()) if pan_ocr_result else 'None'}")
        except Exception as e:
            print(f"[PAN Verification] Error reading OCR file: {e}")
    
    if not pan_ocr_result:
        text = (
            "**PAN Processing Error**\n\n"
            "We could not read your PAN card details. Please try uploading again."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "pan_retry"
        updates["pan_verification_attempts"] = pan_attempts + 1
        return updates
    
    # Extract PAN fields from OCR
    pan_data = extract_pan_from_ocr(pan_ocr_result)
    pan_number = pan_data.get("pan_number")
    pan_name = pan_data.get("full_name")
    pan_dob = pan_data.get("date_of_birth")
    
    # Store extracted data
    updates["pan_number"] = pan_number
    updates["pan_name"] = pan_name
    updates["pan_dob"] = pan_dob
    
    if not pan_number:
        text = (
            "**PAN Number Not Found**\n\n"
            "We could not extract a valid PAN number from your uploaded document.\n"
            "Please ensure you uploaded a clear image of your PAN card."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "pan_retry"
        updates["pan_verification_attempts"] = pan_attempts + 1
        return updates
    
    # Verify PAN against CIBIL and cross-validate with Aadhaar
    print(f"[PAN Verification] Comparing PAN with Aadhaar:")
    print(f"  - PAN Name:     '{pan_name}'")
    print(f"  - Aadhaar Name: '{aadhaar_name}'")
    print(f"  - PAN DOB:      '{pan_dob}'")
    print(f"  - Aadhaar DOB:  '{aadhaar_dob}'")
    
    result = verify_pan(
        pan_number=pan_number,
        pan_name=pan_name or "",
        pan_dob=pan_dob or "",
        aadhaar_name=aadhaar_name,
        aadhaar_dob=aadhaar_dob
    )
    
    updates["pan_verification_attempts"] = pan_attempts + 1
    
    # Case 1: PAN not found in CIBIL database
    if not result.pan_found:
        text = (
            "**PAN Verification Failed**\n\n"
            f"{result.rejection_reason}"
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "pan_rejected"
        updates["pan_rejection_reason"] = result.rejection_reason
        updates["pan_verified"] = False
        return updates
    
    # Store credit score
    updates["cibil_score"] = result.credit_score
    
    # Case 2: Credit score too low
    if not result.credit_approved:
        text = (
            f"**Credit Score: {result.credit_score}**\n\n"
            f"{result.rejection_reason}"
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "pan_rejected"
        updates["pan_rejection_reason"] = result.rejection_reason
        updates["pan_verified"] = False
        return updates
    
    # Case 3: Name/DOB mismatch with Aadhaar
    if not result.is_verified:
        updates["pan_aadhaar_match"] = False
        
        if pan_attempts < 1:  # First attempt failed, allow retry
            text = (
                f"**Credit Score: {result.credit_score}** ✓\n\n"
                "**Document Mismatch Detected**\n\n"
                f"{result.mismatch_details}\n\n"
                "Your PAN details do not match your Aadhaar. "
                "Please re-upload a clearer image of your PAN card."
            )
            updates |= _append_assistant(state, text)
            updates["doc_verification_stage"] = "pan_retry"
        else:
            # Second attempt also failed - reject
            text = (
                f"**Credit Score: {result.credit_score}** ✓\n\n"
                "**Verification Failed**\n\n"
                f"{result.mismatch_details}\n\n"
                "We are unable to verify your identity as the details on your "
                "PAN card do not match your Aadhaar. Your application cannot proceed.\n\n"
                "Please contact our support team for assistance."
            )
            updates |= _append_assistant(state, text)
            updates["doc_verification_stage"] = "pan_rejected"
            updates["pan_rejection_reason"] = "PAN and Aadhaar details mismatch after 2 attempts"
            updates["pan_verified"] = False
        
        return updates
    
    # Case 4: All verified!
    updates["pan_verified"] = True
    updates["pan_aadhaar_match"] = True
    
    text = (
        f"**PAN Verified Successfully!**\n\n"
        f"**Credit Score: {result.credit_score}** ✓\n\n"
        f"Excellent, {first_name}! Your PAN has been verified and your credit score "
        f"meets our requirements.\n\n"
        "Verifying Employment Certificate..."
    )
    updates |= _append_assistant(state, text)
    updates["doc_verification_stage"] = "verifying_employment"
    
    # Chain directly to employment verification (merge updates)
    merged_state = {**state, **updates}
    emp_updates = handle_employment_verification(merged_state)
    updates.update(emp_updates)
    
    return updates


def handle_pan_verification(state: AgentState) -> Dict:
    """
    Handle pan verification stage (called from router).
    """
    return handle_pan_verification_internal(state, {})


def handle_pan_retry_stage(state: AgentState, user_message: str) -> Dict:
    """
    Handle PAN retry stage - user needs to re-upload PAN only.
    """
    updates: Dict = {}
    
    # Check if PAN was re-uploaded (triggered by upload API)
    if user_message == "pan_reuploaded" or user_message == "proceed":
        # Re-verify PAN
        return handle_pan_verification_internal(state, {})
    
    # Default - remind about PAN re-upload
    text = (
        "Please re-upload your PAN card using the button above.\n"
        "Ensure the image is clear and all details are visible."
    )
    updates |= _append_assistant(state, text)
    return updates


def handle_pan_rejected(state: AgentState, user_message: str) -> Dict:
    """
    Handle pan rejected stage - application cannot proceed.
    """
    updates: Dict = {}
    
    rejection_reason = state.get("pan_rejection_reason", "Verification failed")
    
    text = (
        "Your loan application has been declined.\n\n"
        f"**Reason:** {rejection_reason}\n\n"
        "If you believe this is an error, please contact our support team:\n"
        "Phone: 1800-XXX-XXXX (Toll Free)\n"
        "Email: support@tatacapital.com"
    )
    updates |= _append_assistant(state, text)
    updates["done"] = True
    updates["current_agent"] = "master"
    
    return updates


# ========== Employment Certificate Verification ==========

def handle_employment_verification(state: AgentState) -> Dict:
    """Verify employment certificate."""
    import os
    import json
    
    updates: Dict = {}
    customer_uuid = state.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    attempts = state.get("employment_verification_attempts", 0)
    
    # Read OCR result
    ocr_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "customer_data",
        customer_uuid, "employment_certificate_ocr.json"
    )
    
    markdown = ""
    if os.path.exists(ocr_path):
        try:
            with open(ocr_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                markdown = ocr_data.get("data", {}).get("markdown", "")
        except Exception as e:
            print(f"[Employment Verification] Error reading OCR: {e}")
    
    if not markdown:
        text = "**Employment Certificate Error**\n\nCould not read your document. Please re-upload."
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "employment_retry"
        updates["employment_verification_attempts"] = attempts + 1
        updates["failed_documents"] = ["employment_certificate"]
        return updates
    
    # Verify
    result = verify_employment_certificate(markdown, aadhaar_name)
    updates["employment_verification_attempts"] = attempts + 1
    
    if result.is_verified:
        updates["employment_verified"] = True
        updates["employment_employer_name"] = result.employer_name
        updates["employment_total_exp_months"] = result.total_experience_months
        updates["employment_current_job_months"] = result.current_job_months
        
        text = (
            f"**Employment Certificate Verified** ✓\n\n"
            f"Employer: {result.employer_name}\n"
            f"Experience: {result.total_experience_months or 'N/A'} months\n\n"
            "Verifying Salary Slips..."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verifying_salary"
        
        # Chain directly to salary verification
        merged_state = {**state, **updates}
        salary_updates = handle_salary_verification(merged_state)
        updates.update(salary_updates)
    elif result.requires_retry and attempts < 1:
        text = (
            f"**Employment Certificate Issue**\n\n"
            f"{result.failure_reason}\n\n"
            "Please re-upload your Employment Certificate."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "employment_retry"
        updates["failed_documents"] = ["employment_certificate"]
    else:
        updates["employment_verified"] = False
        updates["employment_rejection_reason"] = result.failure_reason
        text = (
            f"**Employment Verification Failed**\n\n"
            f"{result.failure_reason}"
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verification_rejected"
    
    return updates


# ========== Salary Slip Verification ==========

def handle_salary_verification(state: AgentState) -> Dict:
    """Verify salary slips."""
    import os
    import json
    
    updates: Dict = {}
    customer_uuid = state.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    declared_income = state.get("monthly_income", 0)
    employer_name = state.get("employment_employer_name", "")
    employer_warning = state.get("salary_employer_warning_given", False)
    attempts = state.get("salary_verification_attempts", 0)
    
    # Read OCR
    ocr_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "customer_data",
        customer_uuid, "salary_slips_ocr.json"
    )
    
    markdown = ""
    if os.path.exists(ocr_path):
        try:
            with open(ocr_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                markdown = ocr_data.get("data", {}).get("markdown", "")
        except Exception as e:
            print(f"[Salary Verification] Error reading OCR: {e}")
    
    if not markdown:
        text = "**Salary Slip Error**\n\nCould not read your document. Please re-upload."
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "salary_retry"
        updates["salary_verification_attempts"] = attempts + 1
        updates["failed_documents"] = ["salary_slips"]
        return updates
    
    # Verify
    result = verify_salary_slips(markdown, aadhaar_name, declared_income, employer_name, employer_warning)
    updates["salary_verification_attempts"] = attempts + 1
    
    if result.is_verified:
        updates["salary_verified"] = True
        updates["salary_average_gross"] = result.average_gross_salary
        
        text = (
            f"**Salary Slips Verified** ✓\n\n"
            f"Average Gross Salary: ₹{result.average_gross_salary:,}/month\n\n"
            "Verifying Bank Statements..."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verifying_bank"
        
        # Chain directly to bank verification
        merged_state = {**state, **updates}
        bank_updates = handle_bank_verification(merged_state)
        updates.update(bank_updates)
    elif result.employer_warning:
        updates["salary_employer_warning_given"] = True
        text = (
            f"**Employer Mismatch Warning**\n\n"
            f"{result.failure_reason}\n\n"
            "Please re-upload correct salary slips."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "salary_retry"
        updates["failed_documents"] = ["salary_slips"]
    elif result.requires_retry and attempts < 1:
        text = (
            f"**Salary Slip Issue**\n\n"
            f"{result.failure_reason}\n\n"
            "Please re-upload correct salary slips."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "salary_retry"
        updates["failed_documents"] = ["salary_slips"]
    else:
        updates["salary_verified"] = False
        updates["salary_rejection_reason"] = result.failure_reason
        text = f"**Salary Verification Failed**\n\n{result.failure_reason}"
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verification_rejected"
    
    return updates


# ========== Bank Statement Verification ==========

def handle_bank_verification(state: AgentState) -> Dict:
    """Verify bank statements."""
    import os
    import json
    
    updates: Dict = {}
    customer_uuid = state.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    employer_name = state.get("employment_employer_name", "")
    expected_salary = state.get("salary_average_gross") or state.get("monthly_income", 0)
    declared_emi = state.get("total_existing_emi", 0)
    has_loans = state.get("has_existing_loans", False)
    attempts = state.get("bank_verification_attempts", 0)
    
    # Read OCR
    ocr_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "customer_data",
        customer_uuid, "bank_statements_ocr.json"
    )
    
    markdown = ""
    if os.path.exists(ocr_path):
        try:
            with open(ocr_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                markdown = ocr_data.get("data", {}).get("markdown", "")
        except Exception as e:
            print(f"[Bank Verification] Error reading OCR: {e}")
    
    if not markdown:
        text = "**Bank Statement Error**\n\nCould not read your document. Please re-upload."
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "bank_retry"
        updates["bank_verification_attempts"] = attempts + 1
        updates["failed_documents"] = ["bank_statements"]
        return updates
    
    # Verify
    result = verify_bank_statement(markdown, aadhaar_name, employer_name, expected_salary, declared_emi, has_loans)
    updates["bank_verification_attempts"] = attempts + 1
    
    if result.is_verified:
        updates["bank_verified"] = True
        updates["bank_detected_emi"] = result.total_detected_emi
        # Save closing balance from extracted data for underwriting
        updates["bank_closing_balance"] = result.extracted_data.get("closing_balance", 0) if result.extracted_data else 0
        
        text = (
            f"**Bank Statements Verified** ✓\n\n"
            f"Salary Credits: Verified\n"
            f"EMI Detected: ₹{result.total_detected_emi:,}/month\n\n"
            "Verifying Address Proof..."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verifying_address"
        
        # Chain directly to address verification
        merged_state = {**state, **updates}
        address_updates = handle_address_verification(merged_state)
        updates.update(address_updates)
    elif result.requires_retry and attempts < 1:
        text = (
            f"**Bank Statement Issue**\n\n"
            f"{result.failure_reason}\n\n"
            "Please re-upload your bank statements."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "bank_retry"
        updates["failed_documents"] = ["bank_statements"]
    else:
        updates["bank_verified"] = False
        updates["bank_rejection_reason"] = result.failure_reason
        text = f"**Bank Statement Verification Failed**\n\n{result.failure_reason}"
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verification_rejected"
    
    return updates


# ========== Address Proof Verification ==========

def handle_address_verification(state: AgentState) -> Dict:
    """Verify address proof."""
    import os
    import json
    
    updates: Dict = {}
    customer_uuid = state.get("customer_uuid", "")
    aadhaar_name = state.get("aadhaar_name", "")
    aadhaar_address = state.get("aadhaar_address", "")
    attempts = state.get("address_verification_attempts", 0)
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    
    # Read OCR
    ocr_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "customer_data",
        customer_uuid, "address_proof_ocr.json"
    )
    
    markdown = ""
    if os.path.exists(ocr_path):
        try:
            with open(ocr_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
                markdown = ocr_data.get("data", {}).get("markdown", "")
        except Exception as e:
            print(f"[Address Verification] Error reading OCR: {e}")
    
    if not markdown:
        text = "**Address Proof Error**\n\nCould not read your document. Please re-upload."
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "address_retry"
        updates["address_verification_attempts"] = attempts + 1
        updates["failed_documents"] = ["address_proof"]
        return updates
    
    # Verify
    result = verify_address_proof(markdown, aadhaar_name, aadhaar_address)
    updates["address_verification_attempts"] = attempts + 1
    
    if result.is_verified:
        updates["address_verified"] = True
        
        text = (
            f"**Address Proof Verified** ✓\n\n"
            f"All documents verified, {first_name}!\n\n"
            "Now performing final underwriting assessment..."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "underwriting"
        
        # Chain directly to underwriting
        merged_state = {**state, **updates}
        uw_updates = handle_underwriting(merged_state)
        updates.update(uw_updates)
    elif result.requires_retry and attempts < 1:
        text = (
            f"**Address Proof Issue**\n\n"
            f"{result.failure_reason}\n\n"
            "Please re-upload a valid address proof."
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "address_retry"
        updates["failed_documents"] = ["address_proof"]
    else:
        updates["address_verified"] = False
        updates["address_rejection_reason"] = result.failure_reason
        text = f"**Address Verification Failed**\n\n{result.failure_reason}"
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "verification_rejected"
    
    return updates


# ========== Generic Document Retry Handler ==========

def handle_doc_retry_stage(state: AgentState, user_message: str, doc_type: str) -> Dict:
    """Handle document retry stage for any document type."""
    updates: Dict = {}
    
    if user_message == "doc_reuploaded" or user_message == "proceed":
        # Route to appropriate verification
        if doc_type == "employment_certificate":
            return handle_employment_verification(state)
        elif doc_type == "salary_slips":
            return handle_salary_verification(state)
        elif doc_type == "bank_statements":
            return handle_bank_verification(state)
        elif doc_type == "address_proof":
            return handle_address_verification(state)
    
    # Default reminder
    doc_names = {
        "employment_certificate": "Employment Certificate",
        "salary_slips": "Salary Slips",
        "bank_statements": "Bank Statements",
        "address_proof": "Address Proof"
    }
    text = f"Please re-upload your {doc_names.get(doc_type, 'document')} using the button above."
    updates |= _append_assistant(state, text)
    return updates


# ========== Final Rejection Handler ==========

def handle_final_rejection(state: AgentState, user_message: str) -> Dict:
    """Handle final rejection when verification fails."""
    updates: Dict = {}
    
    # Collect all rejection reasons
    reasons = []
    if state.get("employment_rejection_reason"):
        reasons.append(f"Employment: {state['employment_rejection_reason']}")
    if state.get("salary_rejection_reason"):
        reasons.append(f"Salary: {state['salary_rejection_reason']}")
    if state.get("bank_rejection_reason"):
        reasons.append(f"Bank: {state['bank_rejection_reason']}")
    if state.get("address_rejection_reason"):
        reasons.append(f"Address: {state['address_rejection_reason']}")
    
    reason_text = "\n- ".join(reasons) if reasons else "Verification failed"
    
    text = (
        "**Loan Application Declined**\n\n"
        f"We are unable to proceed with your application.\n\n"
        f"**Reasons:**\n- {reason_text}\n\n"
        "If you believe this is an error, please contact our support team:\n"
        "Phone: 1800-XXX-XXXX (Toll Free)\n"
        "Email: support@tatacapital.com"
    )
    updates |= _append_assistant(state, text)
    updates["done"] = True
    updates["current_agent"] = "master"
    
    return updates


# ========== Underwriting ==========

def handle_underwriting(state: AgentState) -> Dict:
    """
    Perform final underwriting assessment and make loan decision.
    """
    updates: Dict = {}
    
    aadhaar_name = state.get("aadhaar_name", "")
    first_name = aadhaar_name.split()[0] if aadhaar_name else "there"
    
    # Gather all data needed for underwriting
    cibil_score = state.get("cibil_score", 0)
    
    # Calculate FOIR (already calculated during eligibility)
    monthly_income = state.get("monthly_income", 0)
    total_emi = state.get("total_existing_emi", 0)
    loan_emi = state.get("approx_new_emi", 0)  # EMI for requested loan
    new_total_emi = total_emi + loan_emi
    foir_percentage = (new_total_emi / monthly_income * 100) if monthly_income > 0 else 100
    
    # Employment stability - prefer verified from employment cert, fallback to eligibility
    current_job_months = state.get("employment_current_job_months") or state.get("current_job_months", 12)
    
    # Income verification
    declared_income = state.get("monthly_income", 0)
    verified_income = state.get("salary_average_gross", 0) or declared_income
    
    # Bank balance
    closing_balance = state.get("bank_closing_balance", 0)
    
    # Loan details - use correct state field names
    loan_amount = state.get("requested_loan_amount", 0)
    interest_rate = 16.0  # Standard rate
    tenure_months = state.get("requested_tenure_months", 36)
    
    # Perform underwriting
    result = perform_underwriting(
        cibil_score=cibil_score,
        foir_percentage=foir_percentage,
        current_job_months=current_job_months,
        declared_income=declared_income,
        verified_income=verified_income,
        closing_balance=closing_balance,
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        tenure_months=tenure_months
    )
    
    # Store results
    updates["underwriting_score"] = result.total_score
    updates["underwriting_decision"] = result.decision
    
    # Format score breakdown
    score_text = format_score_breakdown(result)
    
    if result.decision == "approved":
        # Full approval
        loan_details = format_loan_details_table(result)
        
        # Set approval stage for frontend to render Accept/Decline UI
        updates |= _append_assistant(state, "__LOAN_APPROVED__")  # Special marker
        updates["doc_verification_stage"] = "loan_approved"
        
        # Extract individual scores from breakdown list
        score_map = {item.factor: item.score for item in result.breakdown}
        
        updates["underwriting_result"] = {
            "decision": "approved",
            "score": result.total_score,
            "score_breakdown": {
                "cibil": score_map.get("CIBIL Score", 0),
                "foir": score_map.get("FOIR", 0),
                "employment": score_map.get("Employment Stability", 0),
                "income": score_map.get("Income Verification", 0),
                "bank": score_map.get("Bank Balance", 0)
            },
            "loan_amount": loan_amount,
            "interest_rate": interest_rate,
            "tenure_months": tenure_months,
            "emi": result.emi,
            "processing_fee": int(loan_amount * 0.015),
            "total_interest": result.total_interest,
            "total_payable": result.total_payable,
            "customer_name": first_name
        }
        updates["doc_verification_complete"] = True
        
    elif result.decision == "conditional":
        # Conditional approval
        updates["underwriting_conditions"] = result.conditions
        
        conditions_text = "\n".join([f"- {c}" for c in result.conditions]) if result.conditions else "- Add a co-applicant"
        
        suggested_text = ""
        if result.suggested_amount and result.suggested_tenure:
            suggested_emi = result.emi * 10 // 12  # Rough estimate for lower amount
            suggested_text = (
                f"\n\n**Alternative Offer:**\n"
                f"- Loan Amount: ₹{result.suggested_amount:,}\n"
                f"- Tenure: {result.suggested_tenure} months\n"
            )
        
        text = (
            f"**Conditional Approval, {first_name}**\n\n"
            f"Your application has been reviewed and requires additional steps.\n\n"
            f"**Underwriting Score: {result.total_score}/100**\n\n"
            f"{score_text}\n\n"
            f"---\n\n"
            f"## Required Conditions\n\n"
            f"{conditions_text}"
            f"{suggested_text}\n\n"
            f"---\n\n"
            "Please contact our team to discuss options:\n"
            "Phone: 1800-XXX-XXXX (Toll Free)\n"
            "Email: support@tatacapital.com"
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "complete"
        updates["done"] = True
        updates["current_agent"] = "master"
        
    else:
        # Rejected
        updates["underwriting_rejection_reasons"] = result.rejection_reasons
        
        rejection_text = "\n".join([f"- {r}" for r in result.rejection_reasons]) if result.rejection_reasons else "- Score below minimum threshold"
        
        text = (
            f"**Application Declined, {first_name}**\n\n"
            f"We regret to inform you that your loan application could not be approved at this time.\n\n"
            f"**Underwriting Score: {result.total_score}/100** (Minimum required: 50)\n\n"
            f"{score_text}\n\n"
            f"---\n\n"
            f"## Reasons for Decline\n\n"
            f"{rejection_text}\n\n"
            f"---\n\n"
            "**Suggestions:**\n"
            "- Improve your credit score\n"
            "- Reduce existing EMI obligations\n"
            "- Apply with a co-applicant\n\n"
            "You may re-apply after 6 months. Contact our team for guidance:\n"
            "Phone: 1800-XXX-XXXX (Toll Free)\n"
            "Email: support@tatacapital.com"
        )
        updates |= _append_assistant(state, text)
        updates["doc_verification_stage"] = "complete"
        updates["done"] = True
        updates["current_agent"] = "master"
    
    return updates

"""
OTP Service - Handles OTP generation and verification via Supabase Auth.

Uses Supabase Phone Auth to:
1. Send OTP to phone number
2. Verify OTP entered by user
3. Track verification attempts

For testing, uses Supabase's test phone number configuration.
"""

import httpx
import time
from typing import Optional
from dataclasses import dataclass

from ..config import settings


# OTP Configuration
OTP_EXPIRY_SECONDS = 300  # 5 minutes
MAX_OTP_ATTEMPTS = 3


@dataclass
class OTPResult:
    """Result of OTP operation"""
    success: bool
    message: str
    error: Optional[str] = None
    attempts_remaining: Optional[int] = None


def send_otp(phone_number: str) -> OTPResult:
    """
    Send OTP to the given phone number via Supabase Auth.
    
    For test phone numbers configured in Supabase, no actual SMS is sent.
    The predefined test OTP can be used.
    
    Args:
        phone_number: Phone number to send OTP to (without country code, we'll add +91)
    
    Returns:
        OTPResult with success status
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        return OTPResult(
            success=False,
            message="Supabase not configured",
            error="SUPABASE_URL or SUPABASE_ANON_KEY not set"
        )
    
    # Format phone number with country code (India +91)
    formatted_phone = format_phone_number(phone_number)
    
    try:
        # Call Supabase Auth signInWithOtp endpoint
        url = f"{settings.supabase_url}/auth/v1/otp"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json"
        }
        payload = {
            "phone": formatted_phone
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            return OTPResult(
                success=True,
                message=f"OTP sent to {mask_phone_for_display(phone_number)}"
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error_description") or error_data.get("msg") or f"HTTP {response.status_code}"
            return OTPResult(
                success=False,
                message="Failed to send OTP",
                error=error_msg
            )
            
    except httpx.TimeoutException:
        return OTPResult(
            success=False,
            message="Request timed out",
            error="Supabase Auth request timed out"
        )
    except Exception as e:
        return OTPResult(
            success=False,
            message="Failed to send OTP",
            error=str(e)
        )


def verify_otp(phone_number: str, otp_code: str, current_attempts: int = 0) -> OTPResult:
    """
    Verify the OTP entered by user via Supabase Auth.
    
    For testing, accepts the mock OTP '441623' without API call.
    
    Args:
        phone_number: Phone number the OTP was sent to
        otp_code: 6-digit OTP entered by user
        current_attempts: Number of attempts already made
    
    Returns:
        OTPResult with verification status
    """
    # Check attempts
    if current_attempts >= MAX_OTP_ATTEMPTS:
        return OTPResult(
            success=False,
            message="Maximum OTP attempts exceeded",
            error="MAX_ATTEMPTS_EXCEEDED",
            attempts_remaining=0
        )
    
    # Validate OTP format
    if not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
        return OTPResult(
            success=False,
            message="Invalid OTP format. Please enter a 6-digit code.",
            error="INVALID_FORMAT",
            attempts_remaining=MAX_OTP_ATTEMPTS - current_attempts
        )
    
    # ========== MOCK MODE for Testing ==========
    # Accept test OTP '441623' without calling Supabase API
    MOCK_OTP = "441623"
    if otp_code == MOCK_OTP:
        print(f"[OTP Mock] Accepted mock OTP: {MOCK_OTP}")
        return OTPResult(
            success=True,
            message="OTP verified successfully!",
            attempts_remaining=MAX_OTP_ATTEMPTS - current_attempts - 1
        )
    
    # If Supabase not configured, only accept mock OTP
    if not settings.supabase_url or not settings.supabase_anon_key:
        return OTPResult(
            success=False,
            message=f"Invalid OTP. {MAX_OTP_ATTEMPTS - current_attempts - 1} attempt(s) remaining.",
            error="INVALID_OTP",
            attempts_remaining=MAX_OTP_ATTEMPTS - current_attempts - 1
        )
    
    # Format phone number with country code
    formatted_phone = format_phone_number(phone_number)
    try:
        # Call Supabase Auth verify endpoint
        url = f"{settings.supabase_url}/auth/v1/verify"
        headers = {
            "apikey": settings.supabase_anon_key,
            "Content-Type": "application/json"
        }
        payload = {
            "phone": formatted_phone,
            "token": otp_code,
            "type": "sms"
        }
        
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload, headers=headers)
        
        attempts_remaining = MAX_OTP_ATTEMPTS - current_attempts - 1
        
        if response.status_code == 200:
            return OTPResult(
                success=True,
                message="OTP verified successfully!",
                attempts_remaining=attempts_remaining
            )
        else:
            error_data = response.json() if response.content else {}
            error_msg = error_data.get("error_description") or error_data.get("msg") or "Invalid OTP"
            
            # Check for specific error types
            if "expired" in error_msg.lower():
                return OTPResult(
                    success=False,
                    message="OTP has expired. Please request a new one.",
                    error="OTP_EXPIRED",
                    attempts_remaining=attempts_remaining
                )
            
            return OTPResult(
                success=False,
                message=f"Invalid OTP. {attempts_remaining} attempt(s) remaining.",
                error="INVALID_OTP",
                attempts_remaining=attempts_remaining
            )
            
    except httpx.TimeoutException:
        return OTPResult(
            success=False,
            message="Request timed out. Please try again.",
            error="TIMEOUT",
            attempts_remaining=MAX_OTP_ATTEMPTS - current_attempts
        )
    except Exception as e:
        return OTPResult(
            success=False,
            message="Verification failed. Please try again.",
            error=str(e),
            attempts_remaining=MAX_OTP_ATTEMPTS - current_attempts
        )


def format_phone_number(phone: str) -> str:
    """
    Format phone number with India country code (+91).
    
    Args:
        phone: Phone number (10 digits)
    
    Returns:
        Formatted phone number with +91 prefix
    """
    # Remove any existing prefix, spaces, or dashes
    clean = phone.replace(" ", "").replace("-", "").replace("+", "")
    
    # Remove 91 prefix if present
    if clean.startswith("91") and len(clean) > 10:
        clean = clean[2:]
    
    # Add +91 prefix
    return f"+91{clean}"


def mask_phone_for_display(phone: str) -> str:
    """
    Mask phone number for display.
    
    Args:
        phone: Full phone number
    
    Returns:
        Masked format: ******1234
    """
    clean = phone.replace(" ", "").replace("-", "").replace("+", "")
    if clean.startswith("91") and len(clean) > 10:
        clean = clean[2:]
    
    if len(clean) < 4:
        return "**********"
    
    last_four = clean[-4:]
    return f"******{last_four}"


def extract_otp_from_message(message: str) -> Optional[str]:
    """
    Extract 6-digit OTP from user message.
    
    Args:
        message: User's message
    
    Returns:
        6-digit OTP if found, None otherwise
    """
    # Remove spaces and find 6-digit sequences
    clean = message.replace(" ", "").replace("-", "")
    
    # Look for exactly 6 consecutive digits
    import re
    match = re.search(r'\b(\d{6})\b', clean)
    if match:
        return match.group(1)
    
    # Check if entire message is 6 digits
    if len(clean) == 6 and clean.isdigit():
        return clean
    
    return None

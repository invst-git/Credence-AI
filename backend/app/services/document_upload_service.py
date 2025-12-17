"""
Document Upload Service

Handles document uploads and async OCR processing using LandingAI Parse Jobs API.
Creates per-customer folders to store PDFs and OCR results.
"""

import os
import json
import base64
import httpx
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from ..config import settings


# LandingAI Parse Jobs API
LANDINGAI_PARSE_JOBS_URL = "https://api.va.landing.ai/v1/ade/parse/jobs"
LANDINGAI_EXTRACT_URL = "https://api.va.landing.ai/v1/ade/extract"
LANDINGAI_MODEL = "dpt-2-latest"

# Customer data directory
CUSTOMER_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "customer_data")

# Document types for each employment category
SALARIED_DOCUMENTS = [
    {"id": "pan_card", "name": "PAN Card", "description": "Permanent Account Number card"},
    {"id": "address_proof", "name": "Address Proof", "description": "Utility bill, passport, or voter ID"},
    {"id": "salary_slips", "name": "Salary Slips", "description": "Last 2 months salary slips"},
    {"id": "bank_statements", "name": "Bank Statements", "description": "Latest 3 months statements"},
    {"id": "employment_certificate", "name": "Employment Certificate", "description": "From current employer"},
]

SELF_EMPLOYED_DOCUMENTS = [
    {"id": "pan_card", "name": "PAN Card", "description": "Permanent Account Number card"},
    {"id": "address_proof", "name": "Address Proof", "description": "Utility bill, passport, or voter ID"},
    {"id": "bank_statements", "name": "Bank Statements", "description": "Past 12 months (savings and current)"},
    {"id": "itr", "name": "Income Tax Returns", "description": "ITR for the preceding year"},
]


@dataclass
class UploadResult:
    """Result of document upload operation"""
    success: bool
    message: str
    doc_type: str
    error: Optional[str] = None
    ocr_job_id: Optional[str] = None


@dataclass
class OCRResult:
    """Result of OCR processing"""
    success: bool
    message: str
    doc_type: str
    markdown: Optional[str] = None
    extraction: Optional[Dict] = None
    error: Optional[str] = None


def get_required_documents(employment_type: str) -> List[Dict]:
    """Get list of required documents based on employment type."""
    if employment_type == "salaried":
        return SALARIED_DOCUMENTS
    elif employment_type == "self_employed":
        return SELF_EMPLOYED_DOCUMENTS
    return SALARIED_DOCUMENTS  # Default to salaried


def create_customer_folder(customer_uuid: str) -> str:
    """
    Create a folder for storing customer documents.
    
    Args:
        customer_uuid: Unique identifier for the customer
        
    Returns:
        Path to the customer folder
    """
    customer_folder = os.path.join(CUSTOMER_DATA_DIR, customer_uuid)
    os.makedirs(customer_folder, exist_ok=True)
    print(f"[Document Upload] Created/verified customer folder: {customer_folder}")
    return customer_folder


def generate_customer_uuid() -> str:
    """Generate a new UUID for a customer."""
    return str(uuid.uuid4())


def save_pdf_document(customer_uuid: str, doc_type: str, pdf_base64: str) -> str:
    """
    Save uploaded PDF to customer folder.
    
    Args:
        customer_uuid: Customer's unique ID
        doc_type: Type of document (e.g., 'pan_card')
        pdf_base64: Base64 encoded PDF content
        
    Returns:
        Path to saved PDF file
    """
    customer_folder = create_customer_folder(customer_uuid)
    
    # Decode base64
    if "," in pdf_base64:
        pdf_base64 = pdf_base64.split(",")[1]
    
    pdf_bytes = base64.b64decode(pdf_base64)
    
    # Save PDF
    pdf_path = os.path.join(customer_folder, f"{doc_type}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"[Document Upload] Saved PDF: {pdf_path}")
    return pdf_path


def _get_headers() -> Dict[str, str]:
    """Get authorization headers for LandingAI API."""
    return {
        "Authorization": f"Bearer {settings.landingai_api_key}"
    }


def create_parse_job(pdf_path: str) -> Dict[str, Any]:
    """
    Create an async parse job using LandingAI Parse Jobs API.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        Response with job_id
    """
    if not settings.landingai_api_key:
        return {"error": "LANDINGAI_API_KEY not configured"}
    
    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        with httpx.Client(timeout=60.0) as client:
            files = {
                "document": (os.path.basename(pdf_path), pdf_bytes, "application/pdf")
            }
            data = {
                "model": LANDINGAI_MODEL
            }
            
            response = client.post(
                LANDINGAI_PARSE_JOBS_URL,
                files=files,
                data=data,
                headers=_get_headers()
            )
            
            if response.status_code in [200, 201, 202]:
                result = response.json()
                print(f"[Document Upload] Parse job created: {result}")
                return result
            else:
                return {
                    "error": f"Parse Jobs API error: {response.status_code}",
                    "detail": response.text
                }
                
    except Exception as e:
        print(f"[Document Upload] Error creating parse job: {e}")
        return {"error": f"Parse job creation failed: {str(e)}"}


def poll_job_status(job_id: str, max_attempts: int = 30, poll_interval: float = 2.0) -> Dict[str, Any]:
    """
    Poll the job status until completion.
    
    Args:
        job_id: The parse job ID
        max_attempts: Maximum polling attempts
        poll_interval: Seconds between polls
        
    Returns:
        Final job result with markdown
    """
    if not settings.landingai_api_key:
        return {"error": "LANDINGAI_API_KEY not configured"}
    
    url = f"{LANDINGAI_PARSE_JOBS_URL}/{job_id}"
    
    for attempt in range(max_attempts):
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=_get_headers())
                
                if response.status_code == 200:
                    result = response.json()
                    status = result.get("status")
                    
                    print(f"[Document Upload] Job {job_id} status: {status} (attempt {attempt + 1})")
                    
                    if status == "completed":
                        return result
                    elif status == "failed":
                        return {"error": "Parse job failed", "detail": result}
                    
                    # Still processing, wait and retry
                    time.sleep(poll_interval)
                else:
                    return {
                        "error": f"Job status API error: {response.status_code}",
                        "detail": response.text
                    }
                    
        except Exception as e:
            print(f"[Document Upload] Error polling job: {e}")
            return {"error": f"Polling failed: {str(e)}"}
    
    return {"error": "Job timed out after max attempts"}


def save_ocr_result(customer_uuid: str, doc_type: str, result: Dict[str, Any]) -> str:
    """
    Save OCR result to customer folder.
    
    Args:
        customer_uuid: Customer's unique ID
        doc_type: Type of document
        result: OCR result dictionary
        
    Returns:
        Path to saved JSON file
    """
    customer_folder = create_customer_folder(customer_uuid)
    
    json_path = os.path.join(customer_folder, f"{doc_type}_ocr.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"[Document Upload] Saved OCR result: {json_path}")
    return json_path


def process_document_upload(customer_uuid: str, doc_type: str, pdf_base64: str) -> UploadResult:
    """
    Process a document upload: save PDF and start async OCR.
    
    Args:
        customer_uuid: Customer's unique ID
        doc_type: Type of document
        pdf_base64: Base64 encoded PDF
        
    Returns:
        UploadResult with status
    """
    try:
        # Save PDF
        pdf_path = save_pdf_document(customer_uuid, doc_type, pdf_base64)
        
        # Create parse job
        job_result = create_parse_job(pdf_path)
        
        if "error" in job_result:
            return UploadResult(
                success=False,
                message=f"Failed to start OCR: {job_result['error']}",
                doc_type=doc_type,
                error=job_result["error"]
            )
        
        job_id = job_result.get("job_id")
        
        # Poll for completion
        final_result = poll_job_status(job_id)
        
        if "error" in final_result:
            return UploadResult(
                success=False,
                message=f"OCR processing failed: {final_result['error']}",
                doc_type=doc_type,
                error=final_result["error"]
            )
        
        # Save OCR result
        save_ocr_result(customer_uuid, doc_type, final_result)
        
        return UploadResult(
            success=True,
            message=f"Document uploaded and processed successfully",
            doc_type=doc_type,
            ocr_job_id=job_id
        )
        
    except Exception as e:
        print(f"[Document Upload] Error processing upload: {e}")
        return UploadResult(
            success=False,
            message=f"Upload failed: {str(e)}",
            doc_type=doc_type,
            error=str(e)
        )


def get_upload_status(customer_uuid: str, employment_type: str) -> Dict[str, bool]:
    """
    Get upload status for all required documents.
    
    Args:
        customer_uuid: Customer's unique ID
        employment_type: 'salaried' or 'self_employed'
        
    Returns:
        Dict with document types and their upload status
    """
    customer_folder = os.path.join(CUSTOMER_DATA_DIR, customer_uuid)
    required_docs = get_required_documents(employment_type)
    
    status = {}
    for doc in required_docs:
        doc_id = doc["id"]
        pdf_path = os.path.join(customer_folder, f"{doc_id}.pdf")
        ocr_path = os.path.join(customer_folder, f"{doc_id}_ocr.json")
        
        # Document is complete if both PDF and OCR exist
        status[doc_id] = os.path.exists(pdf_path) and os.path.exists(ocr_path)
    
    return status


def all_documents_uploaded(customer_uuid: str, employment_type: str) -> bool:
    """Check if all required documents have been uploaded and processed."""
    status = get_upload_status(customer_uuid, employment_type)
    return all(status.values())

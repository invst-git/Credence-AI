"""
LLM Extraction Service - Uses Claude for intelligent field extraction from OCR text.

Handles complex cases like:
- "Since June 12, 2023" -> date parsing
- "5 years 3 months experience" -> duration parsing
- Extracting structured data from unstructured OCR markdown
"""

import anthropic
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import json
import re

from ..config import settings


def get_anthropic_client() -> anthropic.Anthropic:
    """Get Anthropic client."""
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def extract_employment_details(ocr_markdown: str) -> Dict[str, Any]:
    """
    Extract employment details from Employment Certificate OCR.
    
    Returns:
        {
            "employee_name": str,
            "employer_name": str,
            "designation": str,
            "joining_date": str (YYYY-MM-DD),
            "total_experience_months": int,
            "issue_date": str (YYYY-MM-DD),
            "raw_experience": str (original text)
        }
    """
    client = get_anthropic_client()
    
    prompt = f"""Extract the following fields from this Employment Certificate OCR text. 
If a field is not found, return null for that field.

OCR Text:
{ocr_markdown}

Return a JSON object with these fields:
- employee_name: The employee's full name
- employer_name: The company/organization name
- designation: Job title/position
- joining_date: Date of joining in YYYY-MM-DD format (convert from any format)
- total_experience_text: Raw text describing experience (e.g., "5 years", "since 2020")
- issue_date: Date the certificate was issued in YYYY-MM-DD format

Important: 
- For dates, convert any format to YYYY-MM-DD
- If only month/year given, use 01 for day
- For "since [date]", treat that as joining_date

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=settings.model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            
            # Calculate experience in months if joining_date is available
            if result.get("joining_date"):
                try:
                    join_date = datetime.strptime(result["joining_date"], "%Y-%m-%d").date()
                    today = date.today()
                    diff = relativedelta(today, join_date)
                    result["total_experience_months"] = diff.years * 12 + diff.months
                except:
                    result["total_experience_months"] = None
            else:
                result["total_experience_months"] = None
                
            print(f"[LLM Extraction] Employment details: {result}")
            return result
            
    except Exception as e:
        print(f"[LLM Extraction] Error extracting employment details: {e}")
    
    return {
        "employee_name": None,
        "employer_name": None,
        "designation": None,
        "joining_date": None,
        "total_experience_months": None,
        "issue_date": None
    }


def extract_salary_slip_details(ocr_markdown: str) -> Dict[str, Any]:
    """
    Extract salary slip details from OCR.
    Can handle multiple slips in one PDF.
    
    Returns:
        {
            "employee_name": str,
            "employer_name": str,
            "slips": [
                {"month": "October 2024", "gross_salary": 50000, "net_salary": 45000},
                ...
            ]
        }
    """
    client = get_anthropic_client()
    
    prompt = f"""Extract salary slip information from this OCR text.
This may contain multiple salary slips (month-wise) in a single document.

OCR Text:
{ocr_markdown}

Return a JSON object with:
- employee_name: The employee's full name
- employer_name: The company name
- slips: An array of objects, each containing:
  - month: The pay period (e.g., "October 2024", "Nov 2024")
  - year: The year as integer (e.g., 2024)
  - month_number: Month as integer (1-12)
  - gross_salary: Gross salary amount as integer
  - net_salary: Net/take-home salary as integer

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=settings.model_name,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print(f"[LLM Extraction] Salary slip details: {result}")
            return result
            
    except Exception as e:
        print(f"[LLM Extraction] Error extracting salary details: {e}")
    
    return {"employee_name": None, "employer_name": None, "slips": []}


def extract_bank_statement_details(ocr_markdown: str) -> Dict[str, Any]:
    """
    Extract bank statement details including transactions and closing balance.
    
    Returns:
        {
            "account_holder_name": str,
            "bank_name": str,
            "statement_period": {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"},
            "closing_balance": int,
            "transactions": [
                {"date": "YYYY-MM-DD", "description": str, "credit": int, "debit": int},
                ...
            ]
        }
    """
    client = get_anthropic_client()
    
    prompt = f"""Extract bank statement information from this OCR text.
Focus on extracting all transactions with dates, descriptions, and amounts.
Also extract the closing balance.

OCR Text:
{ocr_markdown}

Return a JSON object with:
- account_holder_name: The account holder's name
- bank_name: The bank name
- statement_period: An object with "from" and "to" dates in YYYY-MM-DD format
- closing_balance: The closing/ending balance as integer
- transactions: An array of transaction objects, each containing:
  - date: Transaction date in YYYY-MM-DD format
  - description: Transaction description/narration
  - credit: Credit amount as integer (0 if debit)
  - debit: Debit amount as integer (0 if credit)

Include ALL transactions you can find.
Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=settings.model_name,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print(f"[LLM Extraction] Bank statement: {len(result.get('transactions', []))} transactions, closing balance: {result.get('closing_balance')}")
            return result
            
    except Exception as e:
        print(f"[LLM Extraction] Error extracting bank statement: {e}")
    
    return {"account_holder_name": None, "bank_name": None, "statement_period": None, "closing_balance": 0, "transactions": []}


def extract_address_proof_details(ocr_markdown: str) -> Dict[str, Any]:
    """
    Extract address proof details.
    
    Returns:
        {
            "name": str,
            "address": str,
            "document_type": str (utility_bill, passport, voter_id),
            "bill_date": str (YYYY-MM-DD)
        }
    """
    client = get_anthropic_client()
    
    prompt = f"""Extract address proof information from this OCR text.
This could be a utility bill, passport, or voter ID.

OCR Text:
{ocr_markdown}

Return a JSON object with:
- name: The person's full name
- address: The full address
- document_type: One of "utility_bill", "passport", or "voter_id"
- bill_date: The date on the document (bill date, issue date) in YYYY-MM-DD format

Return ONLY valid JSON, no other text."""

    try:
        response = client.messages.create(
            model=settings.model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            print(f"[LLM Extraction] Address proof details: {result}")
            return result
            
    except Exception as e:
        print(f"[LLM Extraction] Error extracting address proof: {e}")
    
    return {"name": None, "address": None, "document_type": None, "bill_date": None}

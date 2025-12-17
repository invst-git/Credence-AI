"""
Sanction Letter PDF Generation Service

Generates a professional PDF sanction letter for approved loans.
Branded with Credence AI | Tata Capital
"""

import os
import io
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# Constants
BRAND_COLOR = colors.HexColor("#1e3a5f")  # Dark blue
ACCENT_COLOR = colors.HexColor("#2563eb")  # Blue
SUCCESS_COLOR = colors.HexColor("#10b981")  # Green
TEXT_COLOR = colors.HexColor("#1f2937")
LIGHT_GRAY = colors.HexColor("#f3f4f6")

# Contact Info
CONTACT_EMAIL = "customercare@tatacapital.com"
CONTACT_PHONE = "1800-209-4444"
WEBSITE = "www.tatacapital.com"


@dataclass
class SanctionLetterData:
    """Data required for sanction letter generation"""
    # Borrower Details
    customer_name: str
    aadhaar_number: str  # Will be masked
    pan_number: str
    address: str
    phone_number: str  # Will be masked
    
    # Loan Details
    loan_amount: int
    interest_rate: float
    tenure_months: int
    emi_amount: int
    processing_fee: int
    total_interest: int
    total_payable: int
    
    # Credit Info
    cibil_score: int
    
    # Reference
    reference_number: Optional[str] = None
    issue_date: Optional[str] = None


def mask_aadhaar(aadhaar: str) -> str:
    """Mask Aadhaar number: XXXX XXXX 1234"""
    if not aadhaar or len(aadhaar) < 4:
        return "XXXX XXXX XXXX"
    clean = aadhaar.replace(" ", "").replace("-", "")
    return f"XXXX XXXX {clean[-4:]}"


def mask_phone(phone: str) -> str:
    """Mask phone number: ******1234"""
    if not phone or len(phone) < 4:
        return "**********"
    return f"******{phone[-4:]}"


def generate_reference_number() -> str:
    """Generate unique reference number: TCL/PL/YYYY/NNNNN"""
    now = datetime.now()
    # Use timestamp for uniqueness
    unique_id = int(now.timestamp()) % 100000
    return f"TCL/PL/{now.year}/{unique_id:05d}"


def format_currency(amount: int) -> str:
    """Format amount in Indian currency style: Rs. 5,00,000"""
    s = str(amount)
    if len(s) <= 3:
        return f"Rs. {s}"
    
    # Split into groups (last 3, then 2s)
    result = s[-3:]
    s = s[:-3]
    while s:
        result = s[-2:] + "," + result
        s = s[:-2]
    return f"Rs. {result}"


def create_styles() -> Dict[str, ParagraphStyle]:
    """Create custom paragraph styles"""
    base = getSampleStyleSheet()
    
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Heading1"],
            fontSize=18,
            textColor=BRAND_COLOR,
            alignment=TA_CENTER,
            spaceAfter=20,
            fontName="Helvetica-Bold"
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.gray,
            alignment=TA_CENTER,
            spaceAfter=10
        ),
        "section_header": ParagraphStyle(
            "SectionHeader",
            parent=base["Heading2"],
            fontSize=12,
            textColor=BRAND_COLOR,
            spaceBefore=15,
            spaceAfter=8,
            fontName="Helvetica-Bold"
        ),
        "normal": ParagraphStyle(
            "Normal",
            parent=base["Normal"],
            fontSize=10,
            textColor=TEXT_COLOR,
            leading=14
        ),
        "bold": ParagraphStyle(
            "Bold",
            parent=base["Normal"],
            fontSize=10,
            textColor=TEXT_COLOR,
            fontName="Helvetica-Bold"
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            textColor=colors.gray,
            alignment=TA_CENTER
        ),
        "congrats": ParagraphStyle(
            "Congrats",
            parent=base["Heading1"],
            fontSize=14,
            textColor=SUCCESS_COLOR,
            alignment=TA_CENTER,
            spaceAfter=10,
            fontName="Helvetica-Bold"
        )
    }


def generate_sanction_letter_pdf(data: SanctionLetterData) -> bytes:
    """
    Generate a PDF sanction letter.
    
    Args:
        data: SanctionLetterData with all required information
        
    Returns:
        PDF as bytes
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=40,
        bottomMargin=40
    )
    
    styles = create_styles()
    story = []
    
    # Reference number and date
    ref_num = data.reference_number or generate_reference_number()
    issue_date = data.issue_date or datetime.now().strftime("%d %B %Y")
    validity_date = (datetime.now() + timedelta(days=30)).strftime("%d %B %Y")
    
    # Header with branding
    header_data = [
        [
            Paragraph("<b>Credence AI</b> | Tata Capital", styles["bold"]),
            Paragraph(f"<b>Ref:</b> {ref_num}", styles["normal"])
        ],
        [
            Paragraph("Personal Loan Division", styles["normal"]),
            Paragraph(f"<b>Date:</b> {issue_date}", styles["normal"])
        ]
    ]
    header_table = Table(header_data, colWidths=[300, 200])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))
    
    # Title
    story.append(Paragraph("PERSONAL LOAN SANCTION LETTER", styles["title"]))
    story.append(Paragraph(f"Valid until: {validity_date}", styles["subtitle"]))
    
    # Horizontal line
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=15))
    
    # Congratulations message
    story.append(Paragraph(f"Congratulations, {data.customer_name.split()[0]}!", styles["congrats"]))
    story.append(Paragraph(
        "Your personal loan application has been <b>APPROVED</b>. "
        "Please review the details below.",
        styles["normal"]
    ))
    story.append(Spacer(1, 10))
    
    # Borrower Details Section
    story.append(Paragraph("BORROWER DETAILS", styles["section_header"]))
    
    borrower_data = [
        ["Name", data.customer_name],
        ["Aadhaar Number", mask_aadhaar(data.aadhaar_number)],
        ["PAN Number", data.pan_number],
        ["Address", data.address[:80] + "..." if len(data.address) > 80 else data.address],
        ["Mobile", mask_phone(data.phone_number)]
    ]
    
    borrower_table = Table(borrower_data, colWidths=[150, 350])
    borrower_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_COLOR),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story.append(borrower_table)
    story.append(Spacer(1, 10))
    
    # Loan Details Section
    story.append(Paragraph("LOAN DETAILS", styles["section_header"]))
    
    loan_data = [
        ["Loan Amount Sanctioned", format_currency(data.loan_amount)],
        ["Interest Rate", f"{data.interest_rate:.2f}% p.a. (Fixed)"],
        ["Loan Tenure", f"{data.tenure_months} months"],
        ["EMI Amount", format_currency(data.emi_amount)],
        ["Processing Fee (1.5%)", format_currency(data.processing_fee)],
        ["Total Interest Payable", format_currency(data.total_interest)],
        ["Total Amount Payable", format_currency(data.total_payable)],
        ["CIBIL Score", str(data.cibil_score)],
    ]
    
    loan_table = Table(loan_data, colWidths=[250, 250])
    loan_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e0f2fe")),  # Highlight last row
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_COLOR),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    story.append(loan_table)
    story.append(Spacer(1, 12))
    
    # Terms & Conditions
    story.append(Paragraph("TERMS & CONDITIONS", styles["section_header"]))
    
    terms = [
        "This is a provisional sanction letter subject to successful completion of documentation.",
        "This sanction is valid for 30 days from the date of issue.",
        "EMI will be deducted via NACH mandate on the same date each month.",
        "Prepayment is allowed after 6 EMIs without any prepayment charges.",
        "Late payment fee of Rs. 500 will be charged per instance of delayed payment.",
        "Final loan agreement must be signed before disbursement of funds."
    ]
    
    for i, term in enumerate(terms, 1):
        story.append(Paragraph(f"{i}. {term}", styles["normal"]))
        story.append(Spacer(1, 5))
    
    story.append(Spacer(1, 20))
    
    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceBefore=10))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "This is a system-generated letter and does not require a physical signature.",
        styles["footer"]
    ))
    story.append(Paragraph(
        f"For queries, contact: {CONTACT_EMAIL} | {CONTACT_PHONE}",
        styles["footer"]
    ))
    story.append(Paragraph(
        f"Visit us at: {WEBSITE}",
        styles["footer"]
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "<b>Powered by Credence AI</b>",
        styles["footer"]
    ))
    
    # Build PDF
    doc.build(story)
    
    buffer.seek(0)
    return buffer.getvalue()


def save_sanction_letter(
    data: SanctionLetterData,
    output_dir: str,
    filename: Optional[str] = None
) -> str:
    """
    Generate and save sanction letter PDF to disk.
    
    Args:
        data: SanctionLetterData
        output_dir: Directory to save the PDF
        filename: Optional filename (without extension)
        
    Returns:
        Full path to saved PDF
    """
    pdf_bytes = generate_sanction_letter_pdf(data)
    
    if not filename:
        # Generate filename: CustomerName_Sanction_Letter_YYYY-MM-DD.pdf
        clean_name = data.customer_name.replace(" ", "_")
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{clean_name}_Sanction_Letter_{date_str}"
    
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{filename}.pdf")
    
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    
    return filepath


# Testing
if __name__ == "__main__":
    test_data = SanctionLetterData(
        customer_name="Dandu Venkata Nitish Chandra Teja",
        aadhaar_number="1234 5678 9012",
        pan_number="CLMPV6609K",
        address="123 Test Street, Hyderabad, Telangana 500001",
        phone_number="9876543210",
        loan_amount=500000,
        interest_rate=16.0,
        tenure_months=36,
        emi_amount=17578,
        processing_fee=7500,
        total_interest=132808,
        total_payable=640308,
        cibil_score=900
    )
    
    pdf_path = save_sanction_letter(test_data, "./test_output")
    print(f"PDF saved to: {pdf_path}")

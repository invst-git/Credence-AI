# Credence - AI-Powered Personal Loan Platform

Credence is an intelligent, multi-agent loan origination system built with LangGraph. It provides an end-to-end digital lending experience from eligibility assessment through document verification to loan sanctioning, all through a conversational chat interface.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Multi-Agent System](#multi-agent-system)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Document Verification Flow](#document-verification-flow)
- [Underwriting Engine](#underwriting-engine)
- [Security Considerations](#security-considerations)

---

## Overview

Credence automates the personal loan application process using a sophisticated multi-agent architecture. The system guides applicants through:

1. **Eligibility Assessment** - Real-time evaluation against lending criteria
2. **Identity Verification** - Selfie capture and Aadhaar OCR with face matching
3. **Document Collection** - Automated upload and verification of financial documents
4. **Credit Underwriting** - Scoring-based loan decisioning
5. **Sanction Letter Generation** - Instant PDF generation post approval

---

## Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Chat Interface (Vanilla JS)                                     │   │
│  │  - Message bubbles with markdown rendering                       │   │
│  │  - Camera capture modal (Selfie, Aadhaar)                        │   │
│  │  - OTP input with 6-digit verification                           │   │
│  │  - Document upload with progress tracking                        │   │
│  │  - Loan approval UI with Accept/Decline                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ HTTP/REST
┌─────────────────────────────────────────────────────────────────────────┐
│                           FASTAPI BACKEND                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  API Layer (api.py)                                              │   │
│  │  - POST /eligibility/chat                                        │   │
│  │  - POST /eligibility/upload-document                             │   │
│  │  - POST /eligibility/loan-decision                               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  LANGGRAPH MULTI-AGENT ORCHESTRATION (graph.py)                  │   │
│  │                                                                   │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │   │
│  │  │ Master Agent │───▶│ Sales Agent  │───▶│ Eligibility Agent│   │   │
│  │  └──────────────┘    └──────────────┘    └──────────────────┘   │   │
│  │         │                                         │               │   │
│  │         │                                         ▼               │   │
│  │         │                              ┌────────────────────┐    │   │
│  │         └─────────────────────────────▶│  Document          │    │   │
│  │                                        │  Verification Agent│    │   │
│  │                                        └────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  SERVICES LAYER                                                  │   │
│  │  - OCR Service (Document parsing)                                │   │
│  │  - Citizen Verification (Database matching)                      │   │
│  │  - OTP Service (Phone verification via Supabase)                 │   │
│  │  - PAN Verification (CIBIL integration)                          │   │
│  │  - Employment/Salary/Bank Statement Verification                 │   │
│  │  - Underwriting Engine (Credit scoring)                          │   │
│  │  - Sanction Letter Generator (PDF creation)                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                                │
│  - Supabase (Database + OTP Authentication)                             │
│  - Claude (LLM for field extraction and NLU)                            │
│  - Custom Fine-tuned Qwen 2.5VL (Document OCR)                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### LangGraph Workflow

```
┌─────────────────┐
│  User Message   │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Ingest Message  │
└────────┬────────┘
         ▼
┌─────────────────┐
│ Extract Fields  │  (LLM-based extraction)
└────────┬────────┘
         ▼
┌─────────────────┐
│ Normalize Data  │  (Compute FOIR, EMI, etc.)
└────────┬────────┘
         ▼
┌─────────────────┐
│  Route to Agent │
└────────┬────────┘
         │
    ┌────┴────┬───────────┬────────────┐
    ▼         ▼           ▼            ▼
┌───────┐ ┌───────┐ ┌───────────┐ ┌─────────────┐
│Master │ │ Sales │ │Eligibility│ │Doc Verify   │
│Agent  │ │ Agent │ │  Agent    │ │   Agent     │
└───────┘ └───────┘ └───────────┘ └─────────────┘
```

---

## Technology Stack

### Frontend
| Technology | Purpose |
|------------|---------|
| HTML5 | Structure and semantic markup |
| CSS3 | Styling with CSS variables, gradients, animations |
| Vanilla JavaScript | Logic, DOM manipulation, API calls |
| MediaDevices API | Camera access for selfie and document capture |

### Backend
| Technology | Purpose |
|------------|---------|
| Python 3.12+ | Core runtime |
| FastAPI | REST API framework |
| LangGraph | Multi-agent orchestration |
| LangChain | LLM integration utilities |
| ReportLab | PDF generation |
| Pydantic | Data validation |

### External Services
| Service | Purpose |
|---------|---------|
| Claude (Anthropic) | LLM for natural language understanding and field extraction |
| Supabase | PostgreSQL database and OTP authentication |
| Custom Fine-tuned Qwen 2.5VL | Vision-language model for document OCR and text extraction |

---

## Project Structure

```
Credence-LangGraph/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api.py                    # FastAPI endpoints
│   │   ├── config.py                 # Environment configuration
│   │   ├── graph.py                  # LangGraph workflow definition
│   │   ├── state.py                  # AgentState TypedDict schema
│   │   │
│   │   ├── nodes/                    # LangGraph node implementations
│   │   │   ├── master_agent.py       # Orchestration and routing
│   │   │   ├── sales_agent.py        # Customer engagement
│   │   │   ├── document_verification_agent.py  # KYC and doc processing
│   │   │   ├── extraction.py         # LLM field extraction
│   │   │   ├── normalize.py          # Data normalization
│   │   │   ├── rules.py              # Eligibility hard rules
│   │   │   ├── questions.py          # Dynamic question generation
│   │   │   └── final.py              # Response formatting
│   │   │
│   │   └── services/                 # Business logic services
│   │       ├── citizen_service.py            # Aadhaar DB verification
│   │       ├── otp_service.py                # Supabase OTP
│   │       ├── document_upload_service.py    # File handling + OCR
│   │       ├── pan_verification_service.py   # PAN + CIBIL check
│   │       ├── employment_verification_service.py
│   │       ├── salary_verification_service.py
│   │       ├── bank_verification_service.py
│   │       ├── address_verification_service.py
│   │       ├── underwriting_service.py       # Credit scoring
│   │       ├── sanction_letter_service.py    # PDF generation
│   │       └── llm_extraction_service.py     # Gemini integration
│   │
│   ├── customer_data/                # Uploaded documents (gitignored)
│   └── data/                         # Mock citizen database
│
├── frontend/
│   ├── index.html                    # Main HTML structure
│   ├── styles.css                    # Complete stylesheet
│   ├── main.js                       # Application logic
│   └── config.js                     # API configuration
│
├── .env                              # Environment variables (gitignored)
├── .gitignore
└── README.md
```

---

## Multi-Agent System

### Agent Responsibilities

| Agent | Role | Key Functions |
|-------|------|---------------|
| **Master Agent** | Orchestration | Greeting, intent detection, routing to specialized agents, conversation management |
| **Sales Agent** | Engagement | Requirement gathering, loan product recommendations, FOIR-based alternative offers |
| **Eligibility Agent** | Assessment | Hard rule evaluation (age, income, employment), eligibility decisioning |
| **Document Verification Agent** | KYC | Selfie capture, Aadhaar OCR, face matching, OTP verification, document upload and verification, underwriting |
| **Sanction Letter Agent** | Disbursement | Loan approval confirmation, PDF sanction letter generation, email delivery |

### Agent Handoff Flow

1. **User initiates** -> Master Agent greets and detects intent
2. **"Apply for loan"** -> Sales Agent gathers requirements
3. **Requirements complete** -> Eligibility Agent runs hard rules
4. **Eligible** -> Document Verification Agent begins KYC
5. **KYC complete** -> Underwriting engine scores and decides
6. **Approved** -> Sanction Letter Agent generates PDF and delivery options

---

## Features

### Eligibility Assessment
- Age validation (21-60 years)
- Employment type classification (Salaried/Self-employed)
- Income threshold checks
- Experience/vintage requirements
- FOIR (Fixed Obligation to Income Ratio) calculation
- Real-time eligibility feedback

### Identity Verification
- Live selfie capture with camera preview
- Aadhaar card OCR (front and back)
- Face matching between selfie and Aadhaar photo
- Field extraction: Name, DOB, Aadhaar number, Address
- Database verification against citizen records
- Forgery detection for tampered documents

### OTP Verification
- Phone number extraction from verified records
- 6-digit OTP via Supabase Auth
- 3 retry attempts with expiry handling
- Auto-focus digit navigation

### Document Upload and Verification
- Supported documents:
  - PAN Card
  - Employment Certificate
  - Salary Slips (Last 2 months)
  - Bank Statements (Last 3 months)
  - Address Proof
- OCR-based data extraction
- Cross-validation with declared information
- Smart retry flow for failed documents

### Underwriting Engine
- 100-point credit scoring model:
  - CIBIL Score (40 points)
  - FOIR Ratio (30 points)
  - Employment Stability (15 points)
  - Income Verification (10 points)
  - Bank Balance (5 points)
- Decision outcomes: Approved, Conditional, Rejected
- EMI calculation with configurable interest rates

### Sanction Letter Generation
- Professional PDF output
- Masked sensitive data (Aadhaar, Phone)
- Loan terms and conditions
- Download and email options

---

## Installation

### Prerequisites
- Python 3.12+
- Node.js (optional, for serving frontend)
- Git

### Backend Setup

```bash
# Clone repository
git clone https://github.com/your-org/credence-langgraph.git
cd credence-langgraph

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install fastapi uvicorn langgraph langchain-google-genai python-dotenv reportlab supabase pydantic
```

### Frontend Setup

No build step required - vanilla JavaScript frontend.

---

## Configuration

### Environment Variables (.env)

Create a `.env` file in the `backend/` directory:

```env
# LLM
ANTHROPIC_API_KEY=your_anthropic_api_key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key

# Qwen 2.5VL OCR (if using hosted endpoint)
QWEN_OCR_ENDPOINT=your_qwen_endpoint
```

### Frontend Configuration (config.js)

```javascript
const CONFIG = {
    // For localhost development
    API_BASE_URL: "http://127.0.0.1:8000",
    
    // For mobile testing on same network
    // API_BASE_URL: "http://YOUR_LOCAL_IP:8000",
};
```

---

## Running the Application

### Start Backend Server

```bash
cd backend
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

### Access Frontend

Option 1: Open directly in browser
```
file:///path/to/frontend/index.html
```

Option 2: Serve with HTTP server
```bash
cd frontend
npx serve . -l 3000
```

### Mobile Testing

1. Find your computer's IP: `ipconfig` (Windows) or `ifconfig` (Mac/Linux)
2. Update `frontend/config.js` with your IP
3. Start backend with `--host 0.0.0.0`
4. Access from mobile: `http://YOUR_IP:3000`

---

## API Reference

### POST /eligibility/chat

Main conversation endpoint.

**Request:**
```json
{
    "thread_id": "sample_thread",
    "user_message": "I want to apply for a personal loan",
    "image_data": "base64_encoded_image",
    "image_type": "selfie"
}
```

**Response:**
```json
{
    "assistant_message": "Welcome! Let me help you...",
    "current_agent": "sales",
    "doc_verification_stage": "awaiting_selfie",
    "customer_uuid": "uuid-1234",
    "underwriting_result": { ... }
}
```

### POST /eligibility/upload-document

Document upload endpoint.

**Request:**
```json
{
    "thread_id": "thread_abc123",
    "customer_uuid": "uuid-1234",
    "doc_type": "pan_card",
    "pdf_base64": "base64_encoded_pdf"
}
```

### POST /eligibility/loan-decision

Accept or decline loan offer.

**Request:**
```json
{
    "thread_id": "thread_abc123",
    "decision": "accept"
}
```

**Response:**
```json
{
    "success": true,
    "pdf_base64": "base64_encoded_sanction_letter",
    "pdf_filename": "John_Doe_Sanction_Letter_2024-01-15.pdf",
    "reference_number": "TCL/PL/2024/12345"
}
```

---

## Document Verification Flow

```
1. SELFIE CAPTURE
   - Open camera (front-facing)
   - Capture photo
   - Store for face matching

2. AADHAAR FRONT
   - Open camera (rear-facing)
   - Capture front of Aadhaar
   - OCR extraction: Name, DOB, Aadhaar Number, Photo

3. AADHAAR BACK
   - Capture back of Aadhaar
   - OCR extraction: Address

4. FACE MATCHING
   - Compare selfie with Aadhaar photo
   - 70% similarity threshold

5. DATABASE VERIFICATION
   - Match against citizen records
   - Retrieve phone number for OTP

6. OTP VERIFICATION
   - Send 6-digit OTP to registered phone
   - 3 attempts allowed

7. DOCUMENT UPLOAD
   - PAN Card -> CIBIL score fetch
   - Employment Certificate -> Employer verification
   - Salary Slips -> Income verification
   - Bank Statements -> EMI detection
   - Address Proof -> Address verification

8. UNDERWRITING
   - Calculate credit score
   - Generate loan decision
   - Create sanction letter (if approved)
```

---

## Underwriting Engine

### Scoring Model (100 points total)

| Factor | Weight | Scoring Criteria |
|--------|--------|------------------|
| CIBIL Score | 40 | 800+: 40, 750-799: 32, 700-749: 24, 650-699: 16, <650: 8 |
| FOIR | 30 | <30%: 30, 30-40%: 24, 40-50%: 18, 50-60%: 12, >60%: 6 |
| Employment | 15 | 24+ months: 15, 12-23 months: 10, 6-11 months: 5, <6 months: 2 |
| Income Match | 10 | Match within 10%: 10, within 20%: 7, within 30%: 4, else: 2 |
| Bank Balance | 5 | 3x EMI: 5, 2x EMI: 3, 1x EMI: 2, else: 1 |

### Decision Thresholds

| Score Range | Decision |
|-------------|----------|
| 70-100 | Approved |
| 50-69 | Conditional (requires co-applicant or reduced amount) |
| 0-49 | Rejected |

---

## Security Considerations

### Data Protection
- Aadhaar numbers are masked in all UI displays (XXXX XXXX 1234)
- Phone numbers are partially hidden (******1234)
- Captured images stored temporarily, cleared after verification
- Customer documents stored in UUID-based folders

### API Security
- CORS configuration for controlled origins
- Input validation via Pydantic models
- No sensitive data in API responses

### Environment Security
- API keys stored in `.env` (gitignored)
- No hardcoded credentials in source code

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Submit a Pull Request

---

## License

Proprietary - All rights reserved.

---

## Support

For technical support or inquiries:
- Email: support@credence.ai
- Documentation: docs.credence.ai

# Personal Finance Autopilot Agent

A multi-agent personal finance system that parses bank statements (PDF/CSV), categorises transactions, and provides month-over-month spending analysis with actionable insights.

## Architecture

```
                          ┌──────────────┐
                          │   Streamlit   │
                          │   Frontend    │
                          │  (port 8501)  │
                          └──────┬───────┘
                                 │ HTTP
                          ┌──────▼───────┐
                          │   FastAPI     │
                          │   Backend     │
                          │  (port 8000)  │
                          └──────┬───────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
     ┌────────▼──────┐  ┌───────▼───────┐  ┌──────▼───────┐
     │  Orchestrator  │  │    SQLite     │  │  Gemini API  │
     │    Agent       │  │   Database    │  │  (LLM)       │
     └───────┬────────┘  └──────────────┘  └──────────────┘
             │
    ┌────────┼────────────┬──────────────┬──────────────┐
    │        │            │              │              │
┌───▼──┐ ┌──▼───┐  ┌─────▼────┐  ┌─────▼─────┐  ┌────▼────┐
│Parser│ │Categ-│  │ Analysis │  │Comparison │  │Insights │
│Agent │ │oriser│  │  Agent   │  │  Agent    │  │ Agent   │
└──────┘ └──────┘  └──────────┘  └───────────┘  └─────────┘
```

**Pipeline flow:** Upload → Parse (PDF/CSV) → Categorise (rules + LLM) → Detect Subscriptions → Calculate Summary (Pandas) → Compare Months → Generate Insights (Gemini) → Store in SQLite

## Quick Start

### Option 1: Docker (Recommended)

```bash
# 1. Clone and configure
cd finance-agent
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 2. Build and run
docker-compose up --build

# 3. Open browser
# Frontend: http://localhost:8501
# API docs: http://localhost:8000/docs
```

### Option 2: Local Development

```bash
# 1. Create virtual environment
cd finance-agent
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 4. Start backend
uvicorn backend.main:app --reload --port 8000

# 5. Start frontend (in another terminal)
streamlit run frontend/app.py
```

## Getting a Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com)
2. Sign in with your Google account
3. Click "Get API Key" → "Create API Key"
4. Copy the key into your `.env` file

The free tier provides generous limits for personal use.

## Supported Banks & Formats

### PDF Statements
Any bank statement PDF. Gemini Vision extracts transactions from the page images. Works best with:
- **HDFC Bank** — Monthly account statements
- **SBI** — Savings account statements
- **ICICI Bank** — Account statements
- **Axis Bank** — Transaction statements
- **Kotak Mahindra** — Account statements

### CSV Exports
Auto-detects column mappings for most banks. Handles:
- Single amount column with Dr/Cr indicator
- Separate debit and credit columns
- Various date formats
- Currency symbols (₹, Rs, INR)

## Two-Layer Categorisation

### Layer 1: Rule-Based (200+ Indian merchants)
Instant matching against a curated dictionary of Indian merchants including Swiggy, Zomato, Amazon, Flipkart, Netflix, Ola, Uber, and many more. Returns confidence 1.0.

### Layer 2: Gemini AI Fallback
Transactions not matched by rules are sent to Gemini for intelligent categorisation. Returns confidence 0.0–1.0 with transactions below 0.7 flagged for manual review.

## Features

- **Upload & Parse** — PDF (Gemini Vision + pdfplumber fallback) and CSV with auto column detection
- **Smart Categorisation** — 200+ merchant rules + Gemini AI fallback
- **Subscription Detection** — Finds recurring charges using interval analysis
- **Monthly Dashboard** — Income, expenses, savings, health score, category breakdown
- **Month-over-Month Comparison** — Trend analysis, category spikes, savings trajectory
- **AI Insights** — Specific, actionable advice with exact figures (not generic tips)
- **Transaction Management** — Browse, filter, search, and manually correct categories
- **Data Export** — Download transactions as CSV

## Data Privacy

- All data is stored **locally** in a SQLite database file
- The SQLite DB persists across Docker container restarts via a Docker volume
- **What is sent to Gemini API:** Transaction descriptions (for categorisation of unmatched transactions) and pre-computed summary statistics (for insights generation)
- **What is NOT sent:** Account numbers, balances, or personal identification details
- No data is stored on external servers beyond the Gemini API call processing

## Known Limitations

- **PDF parsing accuracy** depends on statement layout. Scanned/image PDFs work via Gemini Vision. Very unusual layouts may need CSV conversion.
- **Subscription detection** requires at least 2 months of data with the same merchant to identify patterns.
- **Gemini API rate limits** may cause delays during heavy usage. The system retries with exponential backoff.
- **Category matching** is optimised for Indian merchants. International transactions may fall through to the Gemini layer.
- **SQLite** is suitable for single-user/personal use. For multi-user production deployment, migrate to PostgreSQL.

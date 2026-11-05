# Corporate Intelligence Dashboard

Three-page Streamlit application for company financials, annual-report technology evidence, news intelligence, and AI-assisted Q&A.

## Pages
1. **Company Intelligence** (`app.py`) — sector leader overview at the top, then choose any company in the selected sector to see that company's financial data, technology evidence, and news. The old sector comparison section has been removed from this page.
2. **Sector Comparison** (`pages/1_Comparison.py`) — choose a sector and a company; compare its 15 technology parameters and available financial parameters against the sector leader. CSV download buttons are provided for both tables.
3. **AI Company Assistant** (`pages/2_Chatbot.py`) — ask about company financials, technology, news, or comparisons. Technology/vendor searches without a named company return a concise, AI-written list of matching companies and relevant context.

## Data sources (authoritative local files)
- Financial data: `data/company_master.csv`
- Technology evidence: `data/tech_matrix*.xlsx` workbooks with `Tech Matrix` and `Evidence` sheets. The legacy `evidence_summary*.xlsx` plus `technology_extraction*.xlsx` format is also supported.
- News: `data/news_analysis.xlsx`

The dashboard does not fabricate missing values. Missing financial values are shown as unavailable, and missing technology evidence is explicitly labelled. For technology/vendor questions without a named company (for example, "Which companies mention SAP or CRM?"), the assistant uses the Groq LLM to summarize a concise list of companies whose technology evidence explicitly matches the requested terms. Chat answers do not display citations, source panels, page numbers, or source filenames. A missing match means the term was not found in the available evidence; it does not prove that a company does not use the technology.

## Setup (Windows PowerShell)
1. Install Python 3.10+.
2. Extract the ZIP and open a terminal in the project folder.
3. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
4. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env` and add the API key required by your existing chatbot configuration. Do not share `.env` or commit API keys.
6. Start the app:
   ```powershell
   streamlit run app.py
   ```

## Notes
- The project ZIP intentionally excludes `.venv`, `.git`, Python cache files, and `.env` secrets. Reinstall dependencies locally.
- All company lists and values are read from the supplied files in `data/`. If a company is absent from the corresponding source workbook, the app says so instead of inventing information.

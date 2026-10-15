from pathlib import Path
from datetime import datetime
import time
import re

import pandas as pd
import yfinance as yf


# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "companies_list.csv"

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "company_final_financial.csv"


# ============================================================
# 2. SETTINGS
# ============================================================

# True = fetch Yahoo data again for every company
# False = reuse successfully completed companies from old output
FORCE_REFRESH = False

REQUEST_DELAY = 2
MAX_RETRIES = 3


# ============================================================
# 3. FINAL OUTPUT COLUMNS
# ============================================================

FINAL_COLUMNS = [
    "Sector Group",
    "Company",
    "Ticker",
    "LTP",
    "Revenue (Billion)",
    "Revenue Growth",
    "Net Revenue (Billion)",
    "EBITDA",
    "EBITDA Margin",
    "EPS",
    "PAT",
    "EPS (FY-26)",
    "PAT (FY-26)",
    "ROE",
    "ROCE",
    "Debt (Billion)",
    "Cash (Billion)",
    "Debt Equity Ratio",
    "Financial Year",
    "Updated At",
    "Sector",
    "Industry",
    "Market Cap Currency",
    "Market Cap",
    "Sector Rank",
    "Sector Leader",
    "Sector Company Count",
]


# ============================================================
# 4. HELPER FUNCTIONS
# ============================================================

def clean_text(value):
    """Convert any value to a clean string."""
    if pd.isna(value):
        return ""

    value = str(value).strip()

    if value.lower() in ["nan", "none", "null"]:
        return ""

    return value


def clean_ticker(ticker):
    """Clean ticker symbol."""

    ticker = clean_text(ticker)

    if not ticker:
        return ""

    ticker = ticker.upper().strip()

    # Remove spaces
    ticker = ticker.replace(" ", "")

    return ticker


def to_number(value):
    """Safely convert value to float."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except:
        pass

    try:
        return float(value)
    except:
        return None


def billion(value):
    """Convert raw rupee value into billions."""

    value = to_number(value)

    if value is None:
        return None

    return value / 1_000_000_000


def percentage(value):
    """Convert decimal percentage into percentage."""

    value = to_number(value)

    if value is None:
        return None

    # Yahoo often gives ROE as decimal, e.g. 0.18
    if abs(value) <= 1:
        return value * 100

    return value


def safe_get(dictionary, key):
    """Safely get a value from dictionary."""

    try:
        value = dictionary.get(key)

        if value is None:
            return None

        return value

    except:
        return None


# ============================================================
# 5. DETERMINE YAHOO TICKER
# ============================================================

def get_yahoo_ticker(company, ticker, exchange):

    ticker = clean_ticker(ticker)
    exchange = clean_text(exchange).upper()

    # --------------------------------------------------------
    # Already Yahoo format
    # --------------------------------------------------------

    if ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker

    # --------------------------------------------------------
    # NSE
    # --------------------------------------------------------

    if "NSE" in exchange or "NATIONAL STOCK" in exchange:

        if ticker:
            return ticker + ".NS"

    # --------------------------------------------------------
    # BSE
    # --------------------------------------------------------

    if "BSE" in exchange or "BOMBAY" in exchange:

        if ticker:
            return ticker + ".BO"

    # --------------------------------------------------------
    # If exchange is missing, try NSE first
    # --------------------------------------------------------

    if ticker:
        return ticker + ".NS"

    # --------------------------------------------------------
    # No ticker available
    # Search Yahoo Finance
    # --------------------------------------------------------

    try:

        url = "https://query1.finance.yahoo.com/v1/finance/search"

        response = yf.utils.get_json(
            url,
            params={
                "q": company,
                "quotesCount": 10,
                "newsCount": 0,
            }
        )

        quotes = response.get("quotes", [])

        for quote in quotes:

            symbol = quote.get("symbol", "")

            if symbol.endswith(".NS"):
                return symbol

            if symbol.endswith(".BO"):
                return symbol

    except Exception:
        pass

    return ""


# ============================================================
# 6. FETCH ONE COMPANY
# ============================================================

def fetch_company_data(company, ticker, exchange):

    yahoo_ticker = get_yahoo_ticker(
        company,
        ticker,
        exchange
    )

    if not yahoo_ticker:

        return {
            "Ticker": ticker,
            "Company": company,
            "Updated At": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Financial Year": "",
        }

    print(f"   Yahoo ticker: {yahoo_ticker}")

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            stock = yf.Ticker(yahoo_ticker)

            # ------------------------------------------------
            # BASIC INFORMATION
            # ------------------------------------------------

            info = {}

            try:
                info = stock.info
            except Exception:
                info = {}

            # ------------------------------------------------
            # COMPANY NAME
            # ------------------------------------------------

            yahoo_company = (
                safe_get(info, "longName")
                or safe_get(info, "shortName")
                or company
            )

            # ------------------------------------------------
            # SECTOR
            # ------------------------------------------------

            sector = (
                safe_get(info, "sector")
                or ""
            )

            industry = (
                safe_get(info, "industry")
                or ""
            )

            # ------------------------------------------------
            # MARKET CAP
            # ------------------------------------------------

            market_cap = safe_get(
                info,
                "marketCap"
            )

            market_cap_currency = (
                safe_get(info, "currency")
                or "INR"
            )

            # ------------------------------------------------
            # LTP
            # ------------------------------------------------

            ltp = (
                safe_get(info, "currentPrice")
                or safe_get(info, "regularMarketPrice")
            )

            # ------------------------------------------------
            # EPS
            # ------------------------------------------------

            eps = (
                safe_get(info, "trailingEps")
            )

            # ------------------------------------------------
            # ROE
            # ------------------------------------------------

            roe = percentage(
                safe_get(info, "returnOnEquity")
            )

            # ------------------------------------------------
            # ROCE
            # ------------------------------------------------
            #
            # Yahoo sometimes provides this.
            # If not available, calculate it from statements.
            # ------------------------------------------------

            roce = percentage(
                safe_get(
                    info,
                    "returnOnCapitalEmployed"
                )
            )

            # ------------------------------------------------
            # DEBT EQUITY RATIO
            # ------------------------------------------------

            debt_equity_ratio = safe_get(
                info,
                "debtToEquity"
            )

            # Yahoo debtToEquity can be expressed as
            # percentage (e.g. 25.5 = 0.255 ratio)
            # We keep Yahoo's reported value here.

            # ------------------------------------------------
            # REVENUE
            # ------------------------------------------------

            revenue = None
            revenue_growth = None
            net_revenue = None
            ebitda = None
            ebitda_margin = None
            pat = None
            debt = None
            cash = None
            financial_year = ""

            # ------------------------------------------------
            # INCOME STATEMENT
            # ------------------------------------------------

            try:

                income_stmt = stock.income_stmt

                if income_stmt is not None and not income_stmt.empty:

                    # ----------------------------------------
                    # Most recent financial year
                    # ----------------------------------------

                    columns = list(income_stmt.columns)

                    if columns:

                        latest_column = columns[0]

                        financial_year = str(
                            latest_column.date()
                            if hasattr(latest_column, "date")
                            else latest_column
                        )

                    # ----------------------------------------
                    # Revenue
                    # ----------------------------------------

                    if "Total Revenue" in income_stmt.index:

                        revenue_raw = income_stmt.loc[
                            "Total Revenue"
                        ].iloc[0]

                        revenue = billion(
                            revenue_raw
                        )

                    # ----------------------------------------
                    # Net Income / PAT
                    # ----------------------------------------

                    if "Net Income" in income_stmt.index:

                        pat_raw = income_stmt.loc[
                            "Net Income"
                        ].iloc[0]

                        pat = billion(
                            pat_raw
                        )

                    # ----------------------------------------
                    # EBITDA
                    # ----------------------------------------

                    if "EBITDA" in income_stmt.index:

                        ebitda_raw = income_stmt.loc[
                            "EBITDA"
                        ].iloc[0]

                        ebitda = billion(
                            ebitda_raw
                        )

                    # ----------------------------------------
                    # EBITDA calculation if Yahoo doesn't
                    # provide EBITDA
                    # ----------------------------------------

                    if ebitda is None:

                        operating_income = None
                        depreciation = None

                        if "Operating Income" in income_stmt.index:

                            operating_income = to_number(
                                income_stmt.loc[
                                    "Operating Income"
                                ].iloc[0]
                            )

                        if "Depreciation And Amortization" in income_stmt.index:

                            depreciation = to_number(
                                income_stmt.loc[
                                    "Depreciation And Amortization"
                                ].iloc[0]
                            )

                        if (
                            operating_income is not None
                            and depreciation is not None
                        ):

                            ebitda = (
                                operating_income
                                + depreciation
                            ) / 1_000_000_000

            except Exception as e:

                print(
                    f"   Income statement warning: {e}"
                )

            # ------------------------------------------------
            # REVENUE GROWTH
            # ------------------------------------------------

            try:

                if (
                    income_stmt is not None
                    and not income_stmt.empty
                    and "Total Revenue" in income_stmt.index
                    and len(income_stmt.columns) >= 2
                ):

                    current_revenue = to_number(
                        income_stmt.loc[
                            "Total Revenue"
                        ].iloc[0]
                    )

                    previous_revenue = to_number(
                        income_stmt.loc[
                            "Total Revenue"
                        ].iloc[1]
                    )

                    if (
                        current_revenue is not None
                        and previous_revenue not in [None, 0]
                    ):

                        revenue_growth = (
                            (
                                current_revenue
                                - previous_revenue
                            )
                            / previous_revenue
                        ) * 100

            except Exception:
                pass

            # ------------------------------------------------
            # EBITDA MARGIN
            # ------------------------------------------------

            if (
                ebitda is not None
                and revenue not in [None, 0]
            ):

                ebitda_margin = (
                    ebitda / revenue
                ) * 100

            # ------------------------------------------------
            # BALANCE SHEET
            # ------------------------------------------------

            try:

                balance_sheet = stock.balance_sheet

                if (
                    balance_sheet is not None
                    and not balance_sheet.empty
                ):

                    # ----------------------------------------
                    # Debt
                    # ----------------------------------------

                    debt_raw = None

                    if "Total Debt" in balance_sheet.index:

                        debt_raw = balance_sheet.loc[
                            "Total Debt"
                        ].iloc[0]

                    elif "Long Term Debt" in balance_sheet.index:

                        debt_raw = balance_sheet.loc[
                            "Long Term Debt"
                        ].iloc[0]

                    if debt_raw is not None:

                        debt = billion(
                            debt_raw
                        )

                    # ----------------------------------------
                    # Cash
                    # ----------------------------------------

                    cash_raw = None

                    if "Cash Cash Equivalents And Short Term Investments" in balance_sheet.index:

                        cash_raw = balance_sheet.loc[
                            "Cash Cash Equivalents And Short Term Investments"
                        ].iloc[0]

                    elif "Cash And Cash Equivalents" in balance_sheet.index:

                        cash_raw = balance_sheet.loc[
                            "Cash And Cash Equivalents"
                        ].iloc[0]

                    if cash_raw is not None:

                        cash = billion(
                            cash_raw
                        )

            except Exception as e:

                print(
                    f"   Balance sheet warning: {e}"
                )

            # ------------------------------------------------
            # FY-26 VALUES
            # ------------------------------------------------
            #
            # These are taken from the latest available
            # annual financial statement returned by Yahoo.
            # ------------------------------------------------

            eps_fy26 = eps
            pat_fy26 = pat

            # ------------------------------------------------
            # ROCE CALCULATION IF YAHOO DOES NOT PROVIDE IT
            # ------------------------------------------------

            if roce is None:

                try:

                    if (
                        income_stmt is not None
                        and balance_sheet is not None
                    ):

                        operating_income_raw = None

                        if "Operating Income" in income_stmt.index:

                            operating_income_raw = to_number(
                                income_stmt.loc[
                                    "Operating Income"
                                ].iloc[0]
                            )

                        total_assets = None
                        current_liabilities = None

                        if "Total Assets" in balance_sheet.index:

                            total_assets = to_number(
                                balance_sheet.loc[
                                    "Total Assets"
                                ].iloc[0]
                            )

                        if "Current Liabilities" in balance_sheet.index:

                            current_liabilities = to_number(
                                balance_sheet.loc[
                                    "Current Liabilities"
                                ].iloc[0]
                            )

                        if (
                            operating_income_raw is not None
                            and total_assets is not None
                            and current_liabilities is not None
                        ):

                            capital_employed = (
                                total_assets
                                - current_liabilities
                            )

                            if capital_employed != 0:

                                roce = (
                                    operating_income_raw
                                    / capital_employed
                                ) * 100

                except Exception:
                    pass

            # ------------------------------------------------
            # SECTOR GROUP
            # ------------------------------------------------

            sector_group = sector

            if not sector_group:

                sector_group = "Unknown"

            # ------------------------------------------------
            # RETURN RESULT
            # ------------------------------------------------

            return {

                "Sector Group": sector_group,

                "Company": company,

                "Ticker": yahoo_ticker,

                "LTP": ltp,

                "Revenue (Billion)": revenue,

                "Revenue Growth": revenue_growth,

                "Net Revenue (Billion)": revenue,

                "EBITDA": ebitda,

                "EBITDA Margin": ebitda_margin,

                "EPS": eps,

                "PAT": pat,

                "EPS (FY-26)": eps_fy26,

                "PAT (FY-26)": pat_fy26,

                "ROE": roe,

                "ROCE": roce,

                "Debt (Billion)": debt,

                "Cash (Billion)": cash,

                "Debt Equity Ratio": debt_equity_ratio,

                "Financial Year": financial_year,

                "Updated At": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

                "Sector": sector_group,

                "Industry": industry,

                "Market Cap Currency": market_cap_currency,

                "Market Cap": market_cap,
            }

        except Exception as e:

            print(
                f"   Attempt {attempt}/{MAX_RETRIES} failed: {e}"
            )

            if attempt < MAX_RETRIES:

                time.sleep(3)

    # ========================================================
    # FAILED COMPANY
    # ========================================================

    return {

        "Sector Group": "",

        "Company": company,

        "Ticker": ticker,

        "LTP": "",

        "Revenue (Billion)": "",

        "Revenue Growth": "",

        "Net Revenue (Billion)": "",

        "EBITDA": "",

        "EBITDA Margin": "",

        "EPS": "",

        "PAT": "",

        "EPS (FY-26)": "",

        "PAT (FY-26)": "",

        "ROE": "",

        "ROCE": "",

        "Debt (Billion)": "",

        "Cash (Billion)": "",

        "Debt Equity Ratio": "",

        "Financial Year": "",

        "Updated At": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "Sector": "",

        "Industry": "",

        "Market Cap Currency": "",

        "Market Cap": "",

    }


# ============================================================
# 7. LOAD INPUT
# ============================================================

print("=" * 70)
print("COMPANY FINANCIAL + SECTOR DATA PIPELINE")
print("=" * 70)

print(f"\nInput file:")
print(INPUT_FILE)

if not INPUT_FILE.exists():

    print("\nERROR: companies_list.csv not found.")
    print("Put companies_list.csv in:")
    print(BASE_DIR)

    raise SystemExit


df_input = pd.read_csv(
    INPUT_FILE,
    dtype=str
)

print(
    f"\nTotal companies in input: {len(df_input)}"
)

print(
    "\nInput columns:"
)

print(
    list(df_input.columns)
)


# ============================================================
# 8. FIND COMPANY COLUMN
# ============================================================

possible_company_columns = [
    "Company",
    "Company_Name",
    "Company Name",
]

company_column = None

for col in possible_company_columns:

    if col in df_input.columns:

        company_column = col
        break


if company_column is None:

    print(
        "\nERROR: Could not find Company column."
    )

    print(
        "Available columns:"
    )

    print(
        list(df_input.columns)
    )

    raise SystemExit


# ============================================================
# 9. FIND TICKER COLUMN
# ============================================================

possible_ticker_columns = [
    "Ticker",
    "NSE Symbol",
    "NSE_Symbol",
    "Symbol",
]

ticker_column = None

for col in possible_ticker_columns:

    if col in df_input.columns:

        ticker_column = col
        break


# ============================================================
# 10. FIND EXCHANGE COLUMN
# ============================================================

possible_exchange_columns = [
    "Exchange",
    "exchange",
]

exchange_column = None

for col in possible_exchange_columns:

    if col in df_input.columns:

        exchange_column = col
        break


# ============================================================
# 11. LOAD PREVIOUS OUTPUT FOR RESUME
# ============================================================

old_data = {}

if OUTPUT_FILE.exists() and not FORCE_REFRESH:

    print(
        "\nExisting output found."
    )

    try:

        old_df = pd.read_csv(
            OUTPUT_FILE,
            dtype=str
        )

        if "Company" in old_df.columns:

            for _, row in old_df.iterrows():

                name = clean_text(
                    row.get("Company", "")
                ).lower()

                if name:

                    old_data[name] = row.to_dict()

            print(
                f"Existing companies available for resume: "
                f"{len(old_data)}"
            )

    except Exception as e:

        print(
            f"Could not read previous output: {e}"
        )


# ============================================================
# 12. FETCH ALL COMPANIES
# ============================================================

results = []

total = len(df_input)

for index, row in df_input.iterrows():

    company = clean_text(
        row.get(company_column, "")
    )

    if not company:

        continue

    ticker = ""

    if ticker_column:

        ticker = clean_text(
            row.get(ticker_column, "")
        )

    exchange = ""

    if exchange_column:

        exchange = clean_text(
            row.get(exchange_column, "")
        )

    print(
        f"\n[{index + 1}/{total}] {company}"
    )

    # --------------------------------------------------------
    # RESUME
    # --------------------------------------------------------

    company_key = company.lower()

    if (
        not FORCE_REFRESH
        and company_key in old_data
    ):

        old_row = old_data[company_key]

        # Only reuse if it has some meaningful data
        old_ticker = clean_text(
            old_row.get("Ticker", "")
        )

        old_sector = clean_text(
            old_row.get("Sector", "")
        )

        old_market_cap = clean_text(
            old_row.get("Market Cap", "")
        )

        if (
            old_ticker
            or old_sector
            or old_market_cap
        ):

            print("   Using existing data.")

            results.append(
                old_row
            )

            continue

    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    result = fetch_company_data(
        company,
        ticker,
        exchange
    )

    results.append(
        result
    )

    time.sleep(
        REQUEST_DELAY
    )


# ============================================================
# 13. CREATE DATAFRAME
# ============================================================

df = pd.DataFrame(
    results
)


# ============================================================
# 14. MAKE SURE ALL REQUIRED COLUMNS EXIST
# ============================================================

for col in FINAL_COLUMNS:

    if col not in df.columns:

        df[col] = ""


# ============================================================
# 15. CLEAN MARKET CAP
# ============================================================

df["Market Cap Numeric"] = pd.to_numeric(
    df["Market Cap"],
    errors="coerce"
)


# ============================================================
# 16. CLEAN SECTOR
# ============================================================

df["Sector"] = (
    df["Sector"]
    .fillna("")
    .astype(str)
    .str.strip()
)

df["Sector"] = df["Sector"].replace(
    "",
    "Unknown"
)

df["Sector Group"] = df["Sector"]


# ============================================================
# 17. SORT BY SECTOR + MARKET CAP
# ============================================================

df = df.sort_values(
    by=[
        "Sector",
        "Market Cap Numeric"
    ],
    ascending=[
        True,
        False
    ],
    na_position="last"
).reset_index(
    drop=True
)


# ============================================================
# 18. SECTOR COMPANY COUNT
# ============================================================

df["Sector Company Count"] = (
    df.groupby("Sector")["Company"]
    .transform("count")
)


# ============================================================
# 19. SECTOR RANK
# ============================================================

df["Sector Rank"] = (
    df.groupby("Sector")["Market Cap Numeric"]
    .rank(
        method="first",
        ascending=False
    )
)


# Convert rank to integer where available
df["Sector Rank"] = df["Sector Rank"].apply(
    lambda x: int(x)
    if pd.notna(x)
    else ""
)


# ============================================================
# 20. FIND SECTOR LEADER
# ============================================================

sector_leaders = {}

for sector, group in df.groupby("Sector"):

    valid_group = group[
        group["Market Cap Numeric"].notna()
    ]

    if len(valid_group) == 0:

        sector_leaders[sector] = ""

        continue

    leader_row = valid_group.iloc[0]

    sector_leaders[sector] = clean_text(
        leader_row["Company"]
    )


df["Sector Leader"] = df["Sector"].map(
    sector_leaders
)


# ============================================================
# 21. REMOVE TEMPORARY COLUMN
# ============================================================

df = df.drop(
    columns=[
        "Market Cap Numeric"
    ],
    errors="ignore"
)


# ============================================================
# 22. FINAL COLUMN ORDER
# ============================================================

df = df[
    FINAL_COLUMNS
]


# ============================================================
# 23. SAVE OUTPUT
# ============================================================

df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)


# ============================================================
# 24. SUMMARY
# ============================================================

print("\n")
print("=" * 70)
print("PIPELINE COMPLETED")
print("=" * 70)

print(
    f"\nCompanies processed: {len(df)}"
)

print(
    f"Columns generated: {len(df.columns)}"
)

print(
    f"\nOutput saved to:"
)

print(
    OUTPUT_FILE
)

print(
    "\nFinal columns:"
)

for i, col in enumerate(
    df.columns,
    start=1
):

    print(
        f"{i}. {col}"
    )

print("\n")
print(
    df.head(10).to_string(
        index=False
    )
)

print("\n")
print("=" * 70)
"""
Data loading and company detection utilities.
"""

from pathlib import Path
import re
from collections import Counter
from difflib import SequenceMatcher, get_close_matches

import pandas as pd
import streamlit as st

from utils.company_keys import (  # noqa: F401  (re-exported for the pages)
    COMPANY_SUFFIXES as _COMPANY_SUFFIXES,
    compute_company_key,
    normalize_text,
    strip_company_suffix,
)
from utils.tech_knowledge import build_knowledge_base


# =========================================================
# PATHS
#
# Everything lives under <project_root>/data/:
#   data/company_master.csv           financials (one row per company)
#   data/news_analysis.xlsx           news
#   data/evidence_summary.xlsx        technology facts, batch 1 (Financial Services)
#   data/technology_extraction1.xlsx  page-level citations for batch 1
#   data/evidence_summary2.xlsx       technology facts, batch 2 (Healthcare)
#   data/technology_extraction2.xlsx  page-level citations for batch 2
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

COMPANY_MASTER_FILE = DATA_DIR / "company_master.csv"

NEWS_FILE = DATA_DIR / "news_analysis.xlsx"

# The technology workbooks are discovered automatically in data/
# (evidence_summary*.xlsx paired with technology_extraction*.xlsx).
TECH_DIR = DATA_DIR


# =========================================================
# COMPANY MASTER
# =========================================================

@st.cache_data(show_spinner="Loading company financials...")
def load_company_master() -> pd.DataFrame:

    if not COMPANY_MASTER_FILE.exists():
        raise FileNotFoundError(
            "Company master file not found:\n"
            f"{COMPANY_MASTER_FILE}\n\n"
            "Copy companies_final_financial.csv into the data/ folder and "
            "rename it to company_master.csv."
        )

    df = pd.read_csv(COMPANY_MASTER_FILE, low_memory=False)

    if "Company" not in df.columns:
        raise ValueError("company_master.csv is missing a 'Company' column")

    # Your CSV uses "Ticker" as the header instead of "NSE Symbol" -
    # accept either so the rest of the app can keep using "NSE Symbol".
    if "NSE Symbol" not in df.columns:
        if "Ticker" in df.columns:
            df = df.rename(columns={"Ticker": "NSE Symbol"})
        else:
            raise ValueError(
                "company_master.csv needs an 'NSE Symbol' or 'Ticker' column"
            )

    # Company key
    if "Company_Key" in df.columns:
        df["Company_Key"] = df["Company_Key"].astype(str).str.lower().str.strip()
    else:
        df["Company_Key"] = df["Company"].astype(str).map(compute_company_key)

    # Internal normalized fields (used for search/matching)
    df["_Company_Normalized"] = df["Company"].astype(str).map(normalize_text)
    df["_Symbol_Normalized"] = df["NSE Symbol"].astype(str).map(normalize_text)

    return df


# =========================================================
# NEWS
# =========================================================

@st.cache_data(show_spinner="Loading news...")
def load_news() -> pd.DataFrame:

    if not NEWS_FILE.exists():
        raise FileNotFoundError(
            "News file not found:\n"
            f"{NEWS_FILE}\n\n"
            "Copy news_analysis.xlsx into the data/ folder."
        )

    if NEWS_FILE.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(NEWS_FILE)
    else:
        df = pd.read_csv(NEWS_FILE, low_memory=False)

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    # news_analysis.xlsx has a "Company" column but no Company_Key - build
    # one the same way load_company_master() does, so the two dataframes
    # can be joined/filtered on Company_Key consistently.
    if "Company_Key" in df.columns:
        df["Company_Key"] = df["Company_Key"].astype(str).str.lower().str.strip()
    elif "Company" in df.columns:
        df["Company_Key"] = df["Company"].astype(str).map(compute_company_key)
    else:
        df["Company_Key"] = ""

    return df


# =========================================================
# TECHNOLOGY
#
# Built from evidence_summary*.xlsx (the facts) and
# technology_extraction*.xlsx (the PDF / page / section citations).
# =========================================================

@st.cache_resource(show_spinner="Loading technology evidence...")
def load_tech_knowledge():
    """The full technology knowledge base (profiles + page-level evidence)."""

    kb = build_knowledge_base(TECH_DIR)

    if not kb.profiles:
        raise FileNotFoundError(
            "No technology evidence found.\n\n"
            f"Expected evidence_summary*.xlsx and technology_extraction*.xlsx in:\n{TECH_DIR}"
        )

    return kb


@st.cache_data(show_spinner=False)
def load_technology():
    """
    (summary_df, detail_df) view of the technology knowledge base.

    summary_df : one row per company (Company, Company_Key, 15 parameter columns)
    detail_df  : one row per evidence point (Company, Parameter, Point, Pages, Claim ID)
    """

    kb = load_tech_knowledge()
    return kb.summary_df(), kb.detail_df()


# =========================================================
# SECTORS
# =========================================================

def get_sectors(company_df: pd.DataFrame) -> list[str]:

    if "Sector" not in company_df.columns:
        return []

    values = company_df["Sector"].dropna().astype(str).str.strip()
    values = values[values != ""]

    return sorted(values.unique().tolist())


# =========================================================
# SECTOR COMPANIES
# =========================================================

def get_sector_companies(company_df: pd.DataFrame, sector: str) -> pd.DataFrame:

    if "Sector" not in company_df.columns:
        return company_df.iloc[0:0].copy()

    result = company_df[
        company_df["Sector"].astype(str).str.strip() == str(sector).strip()
    ].copy()

    if "Sector Rank" in result.columns:
        result = result.sort_values("Sector Rank", na_position="last")

    return result


# =========================================================
# SECTOR LEADER
# =========================================================

def get_sector_leader(company_df: pd.DataFrame, sector: str):

    result = get_sector_companies(company_df, sector)

    if result.empty:
        return None

    if "Sector Rank" in result.columns:
        ranks = pd.to_numeric(result["Sector Rank"], errors="coerce")
        leaders = result[ranks == 1]
        if not leaders.empty:
            return leaders.iloc[0]

    if "Market Cap" in result.columns:
        result["_market_cap"] = pd.to_numeric(result["Market Cap"], errors="coerce")
        result = result.sort_values("_market_cap", ascending=False, na_position="last")

    return result.iloc[0]


# =========================================================
# COMPANY SEARCH
# =========================================================

def find_company(company_df: pd.DataFrame, query: str) -> pd.DataFrame:

    normalized_query = normalize_text(query)

    if not normalized_query:
        return company_df.iloc[0:0].copy()

    result = company_df[
        company_df["_Company_Normalized"].str.contains(normalized_query, regex=False, na=False)
    ]
    if not result.empty:
        return result

    result = company_df[company_df["_Symbol_Normalized"] == normalized_query]
    if not result.empty:
        return result

    names = company_df["_Company_Normalized"].dropna().unique().tolist()
    close = get_close_matches(normalized_query, names, n=3, cutoff=0.70)

    if close:
        return company_df[company_df["_Company_Normalized"].isin(close)]

    return company_df.iloc[0:0].copy()


# =========================================================
# DETECT ALL COMPANIES
# =========================================================

def _phrase_spans(question: str, phrase: str):
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return [(m.start(), m.end()) for m in re.finditer(pattern, question)]


def detect_companies_in_text(company_df: pd.DataFrame, text: str) -> pd.DataFrame:
    """
    Detect ALL companies mentioned in a question.

        "Compare TCS and Infosys"        -> both companies
        "ICICI Bank cybersecurity"       -> ICICI Bank Ltd.   (no "Ltd." needed)
        "State Bank of India technology" -> State Bank of India only
                                            (not also "Bank of India")

    A company is recognised by any of:
      * its full name, or its name without Ltd/Limited/Pvt/etc.
      * its NSE symbol or Company_Key
      * a distinctive leading part of its name (one or more words, unique
        in the dataset), e.g. "ICICI" -> ICICI Bank Ltd. or
        "Max Healthcare" -> Max Healthcare Institute

    When one match sits inside a longer one, the longer match wins.
    """

    if company_df.empty or not text:
        return company_df.iloc[0:0].copy()

    question = normalize_text(text)

    if not question:
        return company_df.iloc[0:0].copy()

    # ---- name variants per company --------------------------------
    variants = {}
    name_count = Counter()
    leading_token_count = Counter()
    symbol_count = Counter()

    for index, row in company_df.iterrows():
        full = normalize_text(row.get("Company", ""))
        stripped = strip_company_suffix(full)
        variants[index] = (full, stripped)
        symbol_count[normalize_text(row.get("NSE Symbol", ""))] += 1

        tokens = stripped.split()
        name_count[stripped] += 1
        if tokens:
            leading_token_count[tokens[0]] += 1
        for k in range(2, len(tokens)):
            name_count[" ".join(tokens[:k])] += 1

    # ---- candidate matches -----------------------------------------
    candidates = []

    for index, row in company_df.iterrows():

        full, stripped = variants[index]
        symbol = normalize_text(row.get("NSE Symbol", ""))
        company_key = normalize_text(row.get("Company_Key", ""))

        phrases = set()

        # A symbol shared by several rows (data errors such as ITC Hotels
        # carrying "ITC") cannot identify a company, so it is ignored.
        if symbol_count[symbol] > 1:
            symbol = ""

        for value, min_len in ((full, 3), (stripped, 3), (symbol, 3), (company_key, 4)):
            if len(value) >= min_len:
                phrases.add(value)

        tokens = stripped.split()
        if (
            tokens
            and len(tokens[0]) >= 4
            and leading_token_count[tokens[0]] == 1
        ):
            phrases.add(tokens[0])

        for k in range(2, len(tokens)):
            prefix = " ".join(tokens[:k])
            if name_count[prefix] == 1:
                phrases.add(prefix)

        for phrase in phrases:
            for start, end in _phrase_spans(question, phrase):
                candidates.append((start, end, index))

    if candidates:

        # longest match first; a match inside a longer one is dropped
        candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))

        accepted = []
        for start, end, index in candidates:
            inside_longer = any(
                a_start <= start and end <= a_end
                and (a_end - a_start) > (end - start)
                and a_index != index
                for a_start, a_end, a_index in accepted
            )
            if not inside_longer:
                accepted.append((start, end, index))

        first_position = {}
        for start, _, index in accepted:
            if index not in first_position or start < first_position[index]:
                first_position[index] = start

        ordered = sorted(first_position, key=lambda i: first_position[i])

        # one row per Company_Key
        seen_keys, indices = set(), []
        for index in ordered:
            key = str(company_df.loc[index].get("Company_Key", index))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            indices.append(index)

        return company_df.loc[indices].copy()

    # ---- fuzzy fallback (typos) --------------------------------------
    words = question.split()
    fuzzy_matches = []
    max_ngram = min(4, len(words))

    for n in range(1, max_ngram + 1):
        for start in range(0, len(words) - n + 1):
            phrase = " ".join(words[start:start + n])
            if len(phrase) < 4:
                continue

            for index, (full, stripped) in variants.items():
                if len(stripped) < 5:
                    continue

                similarity = SequenceMatcher(None, phrase, stripped).ratio()
                if similarity >= 0.88:
                    fuzzy_matches.append((similarity, start, index))

    if fuzzy_matches:
        fuzzy_matches.sort(key=lambda x: (-x[0], x[1]))
        best_score = fuzzy_matches[0][0]

        indices = []
        for score, _, index in fuzzy_matches:
            if score < best_score - 0.02:
                continue
            if index not in indices:
                indices.append(index)
            if len(indices) >= 5:
                break

        return company_df.loc[indices].copy()

    return company_df.iloc[0:0].copy()


# =========================================================
# OLD SINGLE-COMPANY FUNCTION
# =========================================================

def detect_company_in_text(company_df: pd.DataFrame, text: str):

    result = detect_companies_in_text(company_df, text)

    if result.empty:
        return None

    return result.iloc[0]

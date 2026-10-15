import difflib
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Company Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# IMPORT PROJECT FUNCTIONS
# ============================================================

from utils.data_loader import (
    load_company_master,
    load_news,
    load_technology,
    load_tech_knowledge,
    detect_companies_in_text,
    compute_company_key,
    NEWS_FILE,
    DATA_DIR,
)

from utils.chatbot import (
    DailyTokenQuotaError,
    answer_question,
    get_api_key,
    get_model,
)


# ============================================================
# FILE LOCATIONS
# ============================================================

PDF_URL_FILES = [
    DATA_DIR / "nse_annual_report_urls.xlsx",
    BASE_DIR / "nse_annual_report_urls.xlsx",
]


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #ffffff;
        color: #17324d;
    }

    .block-container {
        max-width: 1400px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }

    [data-testid="stSidebar"] {
        background-color: #f7fbff;
        border-right: 1px solid #dce6f0;
    }

    h1, h2, h3 {
        color: #0f4c81 !important;
    }

    div[data-testid="stMetric"] {
        background-color: #ffffff;
        border: 1px solid #dce6f0;
        border-radius: 10px;
        padding: 12px 14px;
    }

    div[data-testid="stMetricLabel"] {
        color: #64748b;
    }

    div[data-testid="stMetricValue"] {
        color: #0f4c81;
    }

    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
    }

    .stChatMessage {
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# LOAD MAIN DATA
# ============================================================

try:
    company_df = load_company_master()
    news_df = load_news()
    tech_summary_df, tech_detail_df = load_technology()
    tech_kb = load_tech_knowledge()

except Exception as exc:
    st.error("Unable to load chatbot data.")
    st.exception(exc)
    st.stop()


# ============================================================
# NORMALIZE COMPANY NAME
# ============================================================

def normalize_company_name(name) -> str:

    if name is None:
        return ""

    try:
        if pd.isna(name):
            return ""
    except Exception:
        pass

    text = str(name).strip().lower()

    text = text.replace("&", " and ")

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    suffixes = [
        "private limited",
        "private ltd",
        "pvt limited",
        "pvt ltd",
        "limited",
        "ltd",
        "plc",
        "incorporated",
        "inc",
        "corporation",
        "corp",
        "llp",
    ]

    for suffix in suffixes:
        text = re.sub(
            rf"\b{re.escape(suffix)}\b",
            " ",
            text
        )

    return " ".join(text.split())


# ============================================================
# NORMALIZE SECTOR NAME
#
# NEW: same idea as normalize_company_name, but without the
# legal-suffix stripping (sectors don't have "Ltd"/"Inc" etc).
# Used to match sector names typed in a question ("RealEstate",
# "Utilies") against the sector values in company_df, and lets
# spacing/punctuation differences ("Real Estate" vs "RealEstate")
# resolve to the same key.
# ============================================================

def normalize_sector_name(name) -> str:

    if name is None:
        return ""

    try:
        if pd.isna(name):
            return ""
    except Exception:
        pass

    text = str(name).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)

    return " ".join(text.split())


# ============================================================
# FIND COLUMN
# ============================================================

def find_column(df, possible_names):

    if df is None or df.empty:
        return None

    normalized = {
        str(c).strip().lower().replace("_", " "): c
        for c in df.columns
    }

    for name in possible_names:

        key = (
            str(name)
            .strip()
            .lower()
            .replace("_", " ")
        )

        if key in normalized:
            return normalized[key]

    return None


# ============================================================
# SECTOR COLUMN LOOKUP
#
# NEW: candidate header names for the column that holds each
# company's sector (e.g. "Real Estate", "Utilities", "Healthcare").
# If your company_master.csv uses a different header than any of
# these, add it to this list.
# ============================================================

def get_sector_column(company_df):
    return find_column(
        company_df,
        [
            "Sector",
            "Sector Name",
            "Industry",
            "Industry Sector",
            "GICS Sector",
            "Category",
        ],
    )


# ============================================================
# DETECT SECTORS MENTIONED IN THE QUESTION
#
# NEW: handles questions like
#   "Compare technology parameters of RealEstate, Utilies,
#    Healthcare sector leader"
# which name SECTORS, not companies. detect_companies_in_text()
# can never find a company here because none is written - so this
# is a separate detection path that looks for sector names (with
# light fuzzy matching, to tolerate typos like "Utilies") instead.
# ============================================================

def detect_sectors_in_text(company_df, question):

    sector_col = get_sector_column(company_df)
    if not sector_col:
        return []

    unique_sectors = sorted(
        {
            str(v).strip()
            for v in company_df[sector_col].dropna().unique()
            if str(v).strip()
        }
    )

    if not unique_sectors:
        return []

    normalized_sectors = {
        normalize_sector_name(s): s for s in unique_sectors
    }

    q_norm = normalize_sector_name(question)
    raw_question = str(question or "").lower()
    technology_sector_mentioned = bool(
        re.search(
            r"\btechnology\s+(?:sector|industry)\b"
            r"|\b(?:sector|industry)\s+of\s+technology\b",
            raw_question,
        )
    )

    found = []
    found_keys = set()

    # --------------------------------------------------------
    # 1) Exact / substring match first (handles "RealEstate",
    #    "Healthcare" typed correctly, multi-word sectors, etc.)
    # --------------------------------------------------------

    for norm_key, original in normalized_sectors.items():
        if norm_key == "technology" and not technology_sector_mentioned:
            # "technology" is also a common topic word; do not mistake
            # technology questions for a request about the Technology sector.
            continue
        if norm_key and norm_key in q_norm and norm_key not in found_keys:
            found.append(original)
            found_keys.add(norm_key)

    # --------------------------------------------------------
    # 2) Fuzzy match remaining words/phrases against remaining
    #    sector keys, to catch typos like "Utilies" -> "Utilities".
    # --------------------------------------------------------

    remaining_keys = [
        k for k in normalized_sectors
        if k not in found_keys
        and (k != "technology" or technology_sector_mentioned)
    ]

    if remaining_keys:

        q_tokens = q_norm.split()

        candidates = set(q_tokens)
        for i in range(len(q_tokens) - 1):
            candidates.add(q_tokens[i] + " " + q_tokens[i + 1])

        for cand in candidates:
            if len(cand) < 4:
                continue

            matches = difflib.get_close_matches(
                cand, remaining_keys, n=1, cutoff=0.8
            )

            if matches:
                key = matches[0]
                if key not in found_keys:
                    found.append(normalized_sectors[key])
                    found_keys.add(key)
                    remaining_keys.remove(key)

    return found


# ============================================================
# GET SECTOR LEADER ROWS FOR A LIST OF SECTORS
#
# NEW: for each sector name detected in the question, find that
# sector's leader (via the "Sector Leader" column already used
# elsewhere in this file) and return the leader's own full row(s)
# from company_df, so they can be treated exactly like an
# explicitly-named company for context, captions, and Sources.
# ============================================================

def get_sector_leaders(company_df, sectors):

    if not sectors:
        return pd.DataFrame()

    sector_col = get_sector_column(company_df)

    if not sector_col or "Sector Leader" not in company_df.columns:
        return pd.DataFrame()

    leader_frames = []
    seen_keys = set()

    for sector in sectors:

        sector_key = normalize_sector_name(sector)

        rows = company_df[
            company_df[sector_col].apply(normalize_sector_name) == sector_key
        ]

        if rows.empty:
            continue

        leader_name = None
        for val in rows["Sector Leader"]:
            val = str(val).strip()
            if val and val.lower() not in {"nan", "none"}:
                leader_name = val
                break

        if not leader_name:
            continue

        leader_key = normalize_company_name(leader_name)

        if leader_key in seen_keys:
            continue

        leader_rows = company_df[
            company_df["Company"].apply(normalize_company_name) == leader_key
        ]

        if not leader_rows.empty:
            leader_frames.append(leader_rows)
            seen_keys.add(leader_key)

    if not leader_frames:
        return pd.DataFrame()

    return pd.concat(leader_frames).drop_duplicates(subset=["Company"])


# ============================================================
# SECTOR-LEADER AUGMENTATION (for an explicitly named company)
# ============================================================

def augment_with_sector_leader(
    company_df,
    matched_companies,
    question
):
    """
    Add each detected company's Sector Leader to the context
    passed to the chatbot.

    IMPORTANT:

    This function affects the chatbot context only.

    It does NOT decide which companies are shown in the
    "Companies checked" caption or Sources panel (that's
    handled by source_companies, built in the chat-input
    section below, using the return value of this function).

    FIX: matched_companies is not guaranteed to carry every
    column of company_df - it may only carry whatever columns
    the detection step chose to return. This re-looks-up full
    rows from company_df by normalized company name first, so
    "Sector Leader" (and every other column) is guaranteed to
    be available.
    """

    if (
        matched_companies is None
        or matched_companies.empty
    ):
        return matched_companies

    company_col = find_column(
        matched_companies,
        ["Company", "Company Name"]
    )

    if not company_col:
        return matched_companies

    detected_keys = set(
        matched_companies[company_col].apply(
            normalize_company_name
        )
    )

    full_rows = company_df[
        company_df["Company"].apply(
            normalize_company_name
        ).isin(detected_keys)
    ]

    if full_rows.empty or "Sector Leader" not in full_rows.columns:
        return matched_companies

    extra_frames = [matched_companies]
    existing_keys = set(detected_keys)

    for _, row in full_rows.iterrows():

        leader_name = str(
            row.get("Sector Leader", "")
        ).strip()

        if not leader_name:
            continue

        leader_key = normalize_company_name(
            leader_name
        )

        if leader_key in existing_keys:
            continue

        leader_rows = company_df[
            company_df["Company"].apply(
                normalize_company_name
            ) == leader_key
        ]

        if not leader_rows.empty:

            extra_frames.append(
                leader_rows
            )

            existing_keys.add(
                leader_key
            )

    if len(extra_frames) == 1:
        return matched_companies

    return pd.concat(
        extra_frames
    ).drop_duplicates(
        subset=["Company"]
    )
# ============================================================
# COMPARISON INTENT DETECTION
#
# NEW: augment_with_sector_leader was being called for every
# detected company regardless of what the question actually
# asked, so "Tell me about Brigade's technology" (a single-
# company question) was also pulling in Brigade's sector
# leader and showing its Technology sources. A company's own
# sector leader should only be added when the question signals
# an actual comparison/benchmark intent.
# ============================================================

def wants_leader_comparison(question):
    text = str(question or "").lower()

    comparison_words = [
        "leader",
        "compare",
        "comparison",
        "vs",
        "versus",
        "against",
        "benchmark",
        "how does it stack",
        "relative to",
    ]

    for word in comparison_words:
        if " " in word:
            if word in text:
                return True
        elif re.search(rf"\b{re.escape(word)}\b", text):
            return True

    return False

# ============================================================
# LOAD PDF URL FILE
# ============================================================

@st.cache_data
def load_pdf_url_file():

    for file_path in PDF_URL_FILES:

        if not file_path.exists():
            continue

        try:

            df = pd.read_excel(
                file_path,
                dtype=str
            ).fillna("")

            company_col = find_column(
                df,
                [
                    "Company Name",
                    "Company"
                ]
            )

            url_col = find_column(
                df,
                [
                    "Alternative pdf url",
                    "Alternative PDF URL",
                    "URL"
                ]
            )

            if company_col and url_col:
                return (
                    df,
                    company_col,
                    url_col
                )

        except Exception:
            continue

    return pd.DataFrame(), None, None


pdf_url_df, pdf_url_company_col, pdf_url_col = (
    load_pdf_url_file()
)


# ============================================================
# GET PDF URL FOR COMPANY
# ============================================================

def get_pdf_url_for_company(company_name):

    if (
        pdf_url_df.empty
        or not company_name
    ):
        return None

    target = normalize_company_name(
        company_name
    )

    for _, row in pdf_url_df.iterrows():

        if normalize_company_name(
            row.get(
                pdf_url_company_col,
                ""
            )
        ) == target:

            url = str(
                row.get(
                    pdf_url_col,
                    ""
                )
            ).strip()

            if (
                url
                and url.lower()
                not in {
                    "nan",
                    "none",
                    "not available",
                    "not found",
                }
            ):
                return url

    return None


# ============================================================
# TECHNOLOGY SOURCES
#
# Sources come from technology_extraction1.xlsx / technology_extraction2.xlsx:
# the annual-report PDF name, the PAGE NUMBER, the section heading and the
# page text that supports each statement the assistant made.
# ============================================================

def pdf_page_url(pdf_url, page):
    """Direct link to a page of the annual report (browsers honour #page=N)."""
    if not pdf_url:
        return None
    base = str(pdf_url).split("#", 1)[0]
    return f"{base}#page={int(page)}"


def display_technology_sources(tech_sources, sources_are_citations=True, max_per_company=15):

    if not tech_sources:
        return False

    if sources_are_citations:
        st.markdown("## \U0001F4DA Technology sources")
        st.caption(
            "Page numbers refer to the company's annual report, as recorded in "
            "technology_extraction1.xlsx / technology_extraction2.xlsx."
        )
    else:
        st.markdown("## \U0001F4DA Technology evidence reviewed")
        st.caption(
            "The answer did not cite specific points, so this is the annual-report "
            "evidence that was provided to the assistant."
        )

    by_company = {}
    for source in tech_sources:
        by_company.setdefault(source["company"], []).append(source)

    for company, sources in by_company.items():

        st.caption(f"**{company}**")

        pdf_url = get_pdf_url_for_company(company)

        if not pdf_url:
            st.caption(
                "\u26A0\uFE0F No annual-report link found for this company in "
                "nse_annual_report_urls.xlsx - showing the PDF name and page number only."
            )

        for i, source in enumerate(sources[:max_per_company], start=1):

            with st.container(border=True):

                pdf_text = source.get("pdf") or "Annual report"

                st.markdown(
                    f"**{i}. {source['parameter']}** \u2014 "
                    f"{pdf_text}, **Page {source['page']}**"
                )

                if source.get("section"):
                    st.caption(f"Section: {source['section']}")

                if source.get("excerpt"):
                    st.caption(source["excerpt"])

                link = pdf_page_url(pdf_url, source["page"])
                if link:
                    st.markdown(
                        f"[Open annual report \u2014 page {source['page']}]({link})"
                    )

        if len(sources) > max_per_company:
            st.caption(f"+ {len(sources) - max_per_company} more cited pages for {company}")

    return True


# ============================================================
# NEWS SOURCES
# ============================================================

def display_news_sources(
    companies,
    question
):

    if (
        news_df is None
        or news_df.empty
        or not companies
    ):
        return False

    if "Company" not in news_df.columns:
        return False

    q = str(question).lower()

    sentiment_filter = None

    if "positive" in q:
        sentiment_filter = "positive"

    elif "negative" in q:
        sentiment_filter = "negative"

    rows = []

    for company in companies:

        key = compute_company_key(
            company
        )

        matches = news_df[
            news_df["Company"].apply(
                compute_company_key
            ) == key
        ]

        if (
            sentiment_filter
            and "Sentiment" in matches.columns
        ):

            matches = matches[
                matches["Sentiment"]
                .astype(str)
                .str.lower()
                .str.contains(
                    sentiment_filter,
                    na=False
                )
            ]

        if "Date" in matches.columns:

            matches = matches.sort_values(
                "Date",
                ascending=False
            )

        rows.extend(
            matches.to_dict(
                "records"
            )
        )

    if not rows:
        return False

    st.markdown(
        "## 📚 News sources"
    )

    for i, row in enumerate(
        rows[:10],
        start=1
    ):

        with st.container(
            border=True
        ):

            headline = (
                row.get(
                    "Headline",
                    ""
                )
                or "News item"
            )

            source = (
                row.get(
                    "Source",
                    ""
                )
                or "n/a"
            )

            st.markdown(
                f"**{i}. {headline}**"
            )

            st.caption(
                f"Source: {source}"
            )

    return True


# ============================================================
# QUESTION TYPE HINT
# ============================================================

def guess_question_type(
    question,
    companies=None,
    answer=""
):
    """
    Determine whether the Sources panel should display
    technology or news sources.

    This checks the USER'S QUESTION rather than the generated
    answer, so words generated by the LLM cannot accidentally
    trigger the wrong Sources panel.
    """

    combined = str(
        question or ""
    ).lower()

    for name in (companies or []):

        name = str(
            name
        ).strip().lower()

        if name:

            combined = re.sub(
                re.escape(name),
                " ",
                combined
            )

    def has_word(
        text,
        tokens
    ):
        # Tokens like "gaps?" / "events?" are tiny regex patterns
        # (optional trailing "s"), not literal strings, so only
        # multi-word phrases are treated as literal substrings -
        # single-word tokens are used as-is so their regex syntax
        # works.
        for token in tokens:

            if " " in token:

                if token in text:
                    return True

            elif re.search(
                rf"\b{token}\b",
                text
            ):
                return True

        return False

    news_words = [
        "news",
        "headline",
        "announcement",
        "press release",
        "update",
        "events?",
    ]

    tech_words = [
        "technology",
        "tech",
        "digital",
        "cloud",
        "automation",
        "cybersecurity",
        "cyber security",
        "r and d",
        "r&d",
        "research",
        "innovation",
        "roadmap",
        "partnership",
        "adoption",
        "ai",
        "gaps?",
        "parameters?",
    ]

    news_hint = has_word(
        combined,
        news_words
    )

    tech_hint = has_word(
        combined,
        tech_words
    )

    if news_hint:
        tech_hint = False

    return (
        news_hint,
        tech_hint
    )


# ============================================================
# DISPLAY SOURCES
# ============================================================

def display_sources(
    companies,
    question,
    tech_sources=None,
    sources_are_citations=True,
):
    """
    Technology answers -> the exact annual-report pages the assistant cited
                          (from technology_extraction*.xlsx).
    News questions     -> News sources (unchanged).
    Financial/general  -> no Sources panel.
    """

    news_hint, _ = guess_question_type(question, companies)

    if tech_sources:
        display_technology_sources(tech_sources, sources_are_citations)

    if news_hint:
        display_news_sources(companies, question)


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.subheader(
        "AI Company Assistant"
    )

    st.caption(
        "Ask about company financials, "
        "technology, news, or compare companies."
    )

    st.divider()

    st.page_link("app.py", label="Company Intelligence")
    st.page_link("pages/1_Comparison.py", label="Sector Comparison")
    st.page_link("pages/2_Chatbot.py", label="AI Company Assistant")

    st.divider()

    st.subheader(
        "Data Coverage"
    )

    st.metric(
        "Companies",
        f"{len(company_df):,}"
    )

    st.metric(
        "News Records",
        f"{len(news_df):,}"
    )

    st.metric(
        "Technology Profiles",
        f"{int((tech_summary_df['Evidence_Points'] > 0).sum()):,}"
    )

    st.divider()

    st.subheader(
        "Source Files"
    )

    if tech_kb.files_loaded:

        st.success(
            "Technology evidence loaded"
        )

        for _file_name in tech_kb.files_loaded:
            st.caption(_file_name)

    else:

        st.warning(
            "Technology evidence "
            "(evidence_summary / technology_extraction) "
            "not found."
        )

    if (
        news_df is not None
        and not news_df.empty
    ):

        st.success(
            "News analysis file loaded"
        )

        st.caption(
            NEWS_FILE.name
        )

    else:

        st.warning(
            "news_analysis.xlsx not found "
            "or empty."
        )

    st.divider()

    st.subheader(
        "AI Configuration"
    )

    if get_api_key():

        st.success(
            "Groq API key detected"
        )

    else:

        st.error(
            "Groq API key not detected"
        )

    st.caption(
        f"Model: {get_model()}"
    )

    # --------------------------------------------------------
    # DEBUG: sector column detection
    #
    # NEW: helps confirm whether company_master.csv's sector
    # column was found under one of the expected header names.
    # If this shows "not found", add the actual header used in
    # your file to get_sector_column()'s candidate list above.
    # --------------------------------------------------------

    st.divider()
    st.subheader("Sector Detection")

    _sector_col = get_sector_column(company_df)

    if _sector_col:
        st.success(f"Sector column: {_sector_col}")
    else:
        st.warning(
            "No sector column found - sector-leader "
            "comparisons by sector name won't work until "
            "the correct column name is added."
        )

    st.divider()

    if st.button(
        "Clear Chat",
        use_container_width=True
    ):

        st.session_state.messages = []

        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.title(
    "🤖 AI Company Assistant"
)

st.caption(
    "Financial Intelligence  •  "
    "News Intelligence  •  "
    "Technology Intelligence"
)

st.divider()


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    role = message.get(
        "role",
        "assistant"
    )

    content = message.get(
        "content",
        ""
    )

    with st.chat_message(role):

        if role == "assistant":

            companies = message.get(
                "companies",
                []
            )

            source_companies = message.get(
                "source_companies",
                companies
            )

            original_question = message.get(
                "question",
                ""
            )

            if companies:

                st.caption(
                    "Companies checked: "
                    + "  •  ".join(
                        companies
                    )
                )

            st.markdown(
                content
            )

            if source_companies or message.get("tech_sources"):

                display_sources(
                    source_companies,
                    original_question,
                    message.get("tech_sources"),
                    message.get("sources_are_citations", True),
                )

        else:

            st.markdown(
                content
            )


# ============================================================
# CHAT INPUT
# ============================================================

question = st.chat_input(
    "Ask about a company, financials, "
    "news, technology, or compare companies..."
)


if question:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    with st.chat_message("user"):

        st.markdown(
            question
        )

    # ========================================================
    # DETECT EXPLICIT COMPANIES
    # ========================================================

    explicit_companies = (
        detect_companies_in_text(
            company_df,
            question
        )
    )

    # ========================================================
    # DETECT SECTORS AND RESOLVE THEIR LEADERS
    #
    # NEW: handles "Compare technology parameters of RealEstate,
    # Utilies, Healthcare sector leader" - no company name is
    # written at all, only sector names, so this resolves each
    # sector to its leader company from company_df.
    # ========================================================

    detected_sectors = detect_sectors_in_text(
        company_df,
        question
    )

    sector_leader_rows = get_sector_leaders(
        company_df,
        detected_sectors
    )

    # ========================================================
    # COMBINE EXPLICIT COMPANIES + SECTOR-LEADER COMPANIES
    #
    # A sector-leader mention names a company just as surely as
    # spelling the company out - the user just used the sector's
    # name instead of the leader's name. So both are treated the
    # same way from here on for "Companies checked" and Sources.
    # ========================================================

    frames_for_names = []

    if explicit_companies is not None and not explicit_companies.empty:
        frames_for_names.append(explicit_companies)

    if sector_leader_rows is not None and not sector_leader_rows.empty:
        frames_for_names.append(sector_leader_rows)

    if frames_for_names:
        all_detected_df = pd.concat(frames_for_names).drop_duplicates(
            subset=["Company"]
        )
    else:
        all_detected_df = explicit_companies

    # ========================================================
    # DETECTED NAMES
    # ========================================================

    detected_names = []

    if (
        all_detected_df is not None
        and not all_detected_df.empty
    ):

        company_column = find_column(
            all_detected_df,
            [
                "Company",
                "Company Name"
            ]
        )

        if company_column:

            detected_names = [
                str(
                    row.get(
                        company_column,
                        ""
                    )
                ).strip()

                for _, row
                in all_detected_df.iterrows()

                if str(
                    row.get(
                        company_column,
                        ""
                    )
                ).strip()
            ]

    detected_names = list(
        dict.fromkeys(
            detected_names
        )
    )

    # ========================================================
    # BUILD CHATBOT CONTEXT
    #
    # Also pulls in each detected company's OWN sector leader
    # (covers "Compare Brigade to its sector leader" phrasing,
    # in addition to the direct sector-name path above).
    # ========================================================

        # ========================================================
    # BUILD CHATBOT CONTEXT
    #
    # Only pull in a detected company's OWN sector leader when
    # the question actually asks for a comparison/benchmark
    # (e.g. "compare Brigade to its sector leader"). A plain
    # single-company question ("Brigade's technology gaps")
    # should stay scoped to just that company - it should NOT
    # also show the leader's sources.
    #
    # detected_sectors / sector_leader_rows (above) are a
    # separate path and are unaffected: naming a sector
    # ("Healthcare sector leader") is inherently a leader
    # request, regardless of comparison wording.
    # ========================================================

    if wants_leader_comparison(question):
        matched_companies = (
            augment_with_sector_leader(
                company_df,
                all_detected_df,
                question
            )
        )
    else:
        matched_companies = all_detected_df

    # Reflect the complete context scope in the "Companies checked" caption,
    # including a leader explicitly requested via comparison wording.
    if matched_companies is not None and not matched_companies.empty:
        matched_company_col = find_column(
            matched_companies,
            ["Company", "Company Name"],
        )
        if matched_company_col:
            detected_names = list(
                dict.fromkeys(
                    detected_names
                    + [
                        str(name).strip()
                        for name in matched_companies[matched_company_col]
                        if str(name).strip()
                    ]
                )
            )

    # ========================================================
    # COMPANIES FOR SOURCES PANEL
    # ========================================================

    source_companies = list(
        detected_names
    )

    if (
        matched_companies is not None
        and not matched_companies.empty
    ):

        mc_col = find_column(
            matched_companies,
            [
                "Company",
                "Company Name"
            ]
        )

        if mc_col:

            for _, row in matched_companies.iterrows():

                name = str(
                    row.get(
                        mc_col,
                        ""
                    )
                ).strip()

                if (
                    name
                    and normalize_company_name(name)
                    not in {
                        normalize_company_name(x)
                        for x in source_companies
                    }
                ):

                    source_companies.append(
                        name
                    )

    # ========================================================
    # HISTORY
    # ========================================================

    history = (
        st.session_state.messages[:-1]
    )

    # ========================================================
    # ASSISTANT
    # ========================================================

    with st.chat_message("assistant"):

        if detected_names:

            st.caption(
                "Companies checked: "
                + "  •  ".join(
                    detected_names
                )
            )

        else:

            st.warning(
                "No specific company was detected. "
                "I can search collected annual-report evidence for a "
                "technology/vendor; for a company-specific answer, mention "
                "a company name, NSE symbol, or sector "
                "(e.g. 'Healthcare sector leader')."
            )

        tech_sources = []
        sources_are_citations = True

        try:

            result = answer_question(
                question=question,
                company_df=company_df,
                news_df=news_df,
                kb=tech_kb,
                matched_companies=matched_companies,
                history=history,
            )

            answer = result.text
            tech_sources = result.tech_sources
            sources_are_citations = result.sources_are_citations

        except DailyTokenQuotaError as exc:
            answer = str(exc)

        except Exception as exc:

            answer = (
                "I could not complete the request."
            )

            st.error(
                "Request failed."
            )

            with st.expander(
                "Technical details"
            ):

                st.code(
                    str(exc)
                )

        st.markdown(
            answer
        )

        if source_companies or tech_sources:

            display_sources(
                source_companies,
                question,
                tech_sources,
                sources_are_citations,
            )

    # ========================================================
    # SAVE ASSISTANT MESSAGE
    # ========================================================

    st.session_state.messages.append(
        {
            "role": "assistant",

            "content": answer,

            "companies": detected_names,

            "source_companies": source_companies,

            "question": question,

            "tech_sources": tech_sources,

            "sources_are_citations": sources_are_citations,
        }
    )
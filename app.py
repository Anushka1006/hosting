
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="Corporate Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.data_loader import (
    load_company_master,
    load_news,
    load_technology,
    load_tech_knowledge,
    get_sectors,
    get_sector_leader,
    get_sector_companies,
)
from utils.tech_knowledge import TECHNOLOGY_PARAMETERS
from utils.company_keys import compute_company_key


# ---------------------------------------------------------
# PAGE STYLING
# ---------------------------------------------------------

st.markdown(
    """
    <style>
    .stApp {
        background: #ffffff;
        color: #17324d;
    }

    .block-container {
        max-width: 1450px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }

    [data-testid="stSidebar"] {
        background: #f7fbff;
        border-right: 1px solid #dce6f0;
    }

    h1, h2, h3 {
        color: #0f4c81 !important;
        font-weight: 700 !important;
    }

    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #dce6f0;
        border-radius: 10px;
        padding: 14px 16px;
        min-width: 0;
    }

    div[data-testid="stMetric"] label {
        color: #52677d;
    }

    div[data-testid="stMetricValue"] {
        font-size: clamp(1.1rem, 2vw, 1.8rem);
        overflow-wrap: anywhere;
        word-break: normal;
    }

    .tech-content {
        color: #334155;
        font-size: 14px;
        line-height: 1.6;
    }

    hr {
        border-color: #dce6f0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def num(value, decimals=0):
    """Format numeric values with commas."""
    try:
        if pd.isna(value) or str(value).strip() == "":
            return "N/A"

        return f"{float(value):,.{decimals}f}"

    except (ValueError, TypeError):
        return "N/A"


def pct(value):
    """Format decimal or percentage values."""
    try:
        if pd.isna(value) or str(value).strip() == "":
            return "N/A"

        number = float(value)

        return (
            f"{number * 100:.1f}%"
            if abs(number) <= 1
            else f"{number:.1f}%"
        )

    except (ValueError, TypeError):
        return "N/A"


def format_market_cap(value, unit="rupees"):
    """
    Format market capitalization in the Indian numbering system.

    unit:
        rupees  -> input is in INR
        crore   -> input is already in crore INR
        million -> input is in million INR

    IMPORTANT:
    Set unit to match the actual units in your source dataset.
    """
    try:
        if pd.isna(value) or str(value).strip() == "":
            return "N/A"

        # Handle strings such as "₹13,000,000,000"
        if isinstance(value, str):
            value = (
                value.strip()
                .replace("₹", "")
                .replace(",", "")
                .replace("INR", "")
                .strip()
            )

        amount = float(value)

        if amount < 0:
            return "N/A"

        unit = unit.lower().strip()

        if unit == "rupees":
            amount_in_rupees = amount
        elif unit == "crore":
            amount_in_rupees = amount * 1_00_00_000
        elif unit == "million":
            amount_in_rupees = amount * 10_00_000
        else:
            raise ValueError(
                "Unsupported market cap unit. "
                "Use 'rupees', 'crore', or 'million'."
            )

        lakh = 1_00_000
        crore = 1_00_00_000
        lakh_crore = 1_00_00_00_00_000

        if amount_in_rupees >= lakh_crore:
            return (
                f"₹{amount_in_rupees / lakh_crore:,.2f} "
                "lakh crore"
            )

        if amount_in_rupees >= crore:
            return (
                f"₹{amount_in_rupees / crore:,.2f} crore"
            )

        if amount_in_rupees >= lakh:
            return (
                f"₹{amount_in_rupees / lakh:,.2f} lakh"
            )

        return f"₹{amount_in_rupees:,.0f}"

    except (ValueError, TypeError):
        return "N/A"


def company_news(df, company_name):
    """Return news records matching the selected company."""
    if df.empty or "Company_Key" not in df.columns:
        return df.iloc[0:0].copy()

    key = compute_company_key(company_name)

    return df[
        df["Company_Key"].astype(str).eq(key)
    ].copy()


# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

try:
    financial = load_company_master()
    news = load_news()
    tech_summary, tech_detail = load_technology()
    kb = load_tech_knowledge()

except Exception as error:
    st.error(
        "Unable to load project data. "
        "Check the required Excel/CSV files in data/."
    )
    st.exception(error)
    st.stop()


# ---------------------------------------------------------
# PAGE TITLE
# ---------------------------------------------------------

st.title("Corporate Intelligence Dashboard")

st.caption(
    "NSE / BSE • Financial Intelligence • "
    "News Intelligence • Technology Intelligence"
)


# ---------------------------------------------------------
# SIDEBAR: NAVIGATION, SECTOR, COMPANY
# ---------------------------------------------------------

with st.sidebar:

    st.subheader("Navigation")

    st.page_link(
        "app.py",
        label="Company Intelligence",
    )

    st.page_link(
        "pages/1_Comparison.py",
        label="Sector Comparison",
    )

    st.page_link(
        "pages/2_Chatbot.py",
        label="AI Company Assistant",
    )

    st.divider()

    st.subheader("Company Selection")

    sectors = get_sectors(financial)

    sector = (
        st.selectbox(
            "Select Sector",
            sectors,
            key="selected_sector",
        )
        if sectors
        else None
    )

    selected_name = None

    if sector:

        sector_companies = get_sector_companies(
            financial,
            sector,
        )

        if (
            sector_companies is not None
            and not sector_companies.empty
            and "Company" in sector_companies.columns
        ):

            names = (
                sector_companies["Company"]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            leader = get_sector_leader(financial, sector)

            leader_name = None

            if leader is not None:
                leader_name = str(leader.get("Company", ""))

            default_index = (
                names.index(leader_name)
                if leader_name in names
                else 0
            )

            if names:
                selected_name = st.selectbox(
                    "Select Company",
                    names,
                    index=default_index,
                    key="company_detail_select",
                )
            else:
                st.warning(
                    "No companies are available in this sector."
                )

        else:
            st.warning(
                "No companies are available in this sector."
            )

    st.divider()

    st.subheader("Data Coverage")

    st.metric(
        "Companies",
        f"{len(financial):,}",
    )

    st.metric(
        "News Records",
        f"{len(news):,}",
    )

    st.metric(
        "Technology Profiles",
        f"{len(kb.profiles):,}",
    )


# ---------------------------------------------------------
# VALIDATE SELECTION
# ---------------------------------------------------------

if not sectors:
    st.warning(
        "No sectors are available in company_master.csv."
    )
    st.stop()

if not sector:
    st.warning("Please select a sector from the sidebar.")
    st.stop()

if not selected_name:
    st.info(
        "Please select a company from the left sidebar "
        "to view its intelligence."
    )
    st.stop()


# ---------------------------------------------------------
# COMPANY FINANCIAL INTELLIGENCE
# ---------------------------------------------------------

match = financial[
    financial["Company"].astype(str).eq(selected_name)
]

row = match.iloc[0] if not match.empty else None

st.header("Company Intelligence")
st.subheader(selected_name)

if row is not None:

    metric_cols = st.columns(4)

    # IMPORTANT:
    # This assumes Market Cap is stored in rupees.
    # If your CSV stores it in crore or million units,
    # change unit="rupees" to the appropriate unit.
    market_cap_display = format_market_cap(
        row.get("Market Cap"),
        unit="rupees",
    )

    metric_cols[0].metric(
        "Market Cap",
        market_cap_display,
    )

    metric_cols[1].metric(
        "Revenue (Billion)",
        num(row.get("Revenue (Billion)"), 2),
    )

    metric_cols[2].metric(
        "Revenue Growth",
        pct(row.get("Revenue Growth")),
    )

    metric_cols[3].metric(
        "EBITDA Margin",
        pct(row.get("EBITDA Margin")),
    )

    fin_cols = [
        column
        for column in [
            "Company",
            "NSE Symbol",
            "Sector",
            "Industry",
            "LTP",
            "Market Cap",
            "Revenue (Billion)",
            "Revenue Growth",
            "Net Revenue (Billion)",
            "EBITDA (Billion)",
            "EBITDA Margin",
            "EPS",
            "PAT (Billion)",
            "EPS (FY-26)",
            "PAT (FY-26)",
            "ROE",
            "ROCE",
            "Debt (Billion)",
            "Cash (Billion)",
            "Debt Equity Ratio",
            "Financial Year",
        ]
        if column in financial.columns
    ]

    with st.expander(
        "View All Available Financial Data",
        expanded=True,
    ):
        st.dataframe(
            pd.DataFrame([row[fin_cols]]),
            use_container_width=True,
            hide_index=True,
        )

else:
    st.warning(
        "Financial information for the selected company "
        "was not found in company_master.csv."
    )


# ---------------------------------------------------------
# TECHNOLOGY INTELLIGENCE
# ---------------------------------------------------------

st.divider()
st.header("Technology Intelligence")

profile = kb.get_profile(selected_name)

if profile is None or profile.total_points == 0:

    st.info(
        "No technology evidence for this company was found "
        "in the configured technology evidence workbooks. "
        "No values have been inferred."
    )

else:

    st.caption(
        "Evidence from the supplied technology workbooks."
    )

    for parameter in TECHNOLOGY_PARAMETERS:

        points = profile.points.get(parameter, [])

        with st.container(border=True):

            st.markdown(f"**{parameter}**")

            if not points:
                st.caption(
                    "No evidence in the supplied technology workbooks."
                )
                continue

            for point in points:

                pages = (
                    ", ".join(map(str, point.pages))
                    if point.pages
                    else "not specified"
                )

                st.markdown(
                    f"- {point.text} *(page {pages})*"
                )


# ---------------------------------------------------------
# NEWS INTELLIGENCE
# ---------------------------------------------------------

st.divider()
st.header("News Intelligence")

company_news_df = company_news(
    news,
    selected_name,
)

if company_news_df.empty:

    st.info(
        "No matching news rows were found for this company "
        "in news_analysis.xlsx."
    )

else:

    if "Date" in company_news_df.columns:
        company_news_df = company_news_df.sort_values(
            "Date",
            ascending=False,
            na_position="last",
        )

    display_cols = [
        column
        for column in [
            "Date",
            "Company",
            "Headline",
            "Summary",
            "Sentiment",
            "Source",
            "Reason",
        ]
        if column in company_news_df.columns
    ]

    st.caption(
        f"{len(company_news_df)} news records "
        "from the supplied workbook."
    )

    st.dataframe(
        company_news_df[display_cols],
        use_container_width=True,
        hide_index=True,
    )

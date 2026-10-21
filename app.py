from pathlib import Path
import os
import json
import re
import hashlib

import pandas as pd
import numpy as np
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
# GENERAL HELPER FUNCTIONS
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
    """Format decimal ratios or percentage values."""
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
    """Format market capitalization as lakh crore, crore, lakh, or rupees."""
    try:
        if pd.isna(value) or str(value).strip() == "":
            return "N/A"

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
            amount_in_rupees = amount * 10_000_000
        elif unit == "million":
            amount_in_rupees = amount * 1_000_000
        else:
            raise ValueError("Use 'rupees', 'crore', or 'million'.")

        lakh = 100_000
        crore = 10_000_000
        lakh_crore = 1_000_000_000_000

        if amount_in_rupees >= lakh_crore:
            return f"₹{amount_in_rupees / lakh_crore:,.2f} lakh crore"
        if amount_in_rupees >= crore:
            return f"₹{amount_in_rupees / crore:,.2f} crore"
        if amount_in_rupees >= lakh:
            return f"₹{amount_in_rupees / lakh:,.2f} lakh"
        return f"₹{amount_in_rupees:,.0f}"

    except (ValueError, TypeError):
        return "N/A"


# ---------------------------------------------------------
# FINANCIAL FILTER CONFIGURATION
# ---------------------------------------------------------

# Source units:
# Market Cap: rupees
# Revenue/PAT/EBITDA/Debt/Cash: ₹ billions
# Growth/margins/ROE/ROCE: decimal ratios
# EPS/LTP: rupees per share
#
# Values entered without a unit suffix use the display units below.
FINANCIAL_FILTER_METRICS = {
    "Market Capitalization": {
        "column": "Market Cap",
        "unit_label": "₹ lakh crore",
        "to_source_factor": 1_000_000_000_000,
        "default_threshold": 17.0,
    },
    "Revenue": {
        "column": "Revenue (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "Net Revenue": {
        "column": "Net Revenue (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "EBITDA": {
        "column": "EBITDA (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "Net Profit (PAT)": {
        "column": "PAT (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 10.0,
    },
    "Net Profit (FY-26)": {
        "column": "PAT (FY-26)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 10.0,
    },
    "EPS": {
        "column": "EPS",
        "unit_label": "₹ per share",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "EPS (FY-26)": {
        "column": "EPS (FY-26)",
        "unit_label": "₹ per share",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "Last Traded Price (LTP)": {
        "column": "LTP",
        "unit_label": "₹ per share",
        "to_source_factor": 1.0,
        "default_threshold": 1000.0,
    },
    "Revenue Growth": {
        "column": "Revenue Growth",
        "unit_label": "%",
        "to_source_factor": 0.01,
        "default_threshold": 10.0,
    },
    "EBITDA Margin": {
        "column": "EBITDA Margin",
        "unit_label": "%",
        "to_source_factor": 0.01,
        "default_threshold": 10.0,
    },
    "ROE": {
        "column": "ROE",
        "unit_label": "%",
        "to_source_factor": 0.01,
        "default_threshold": 10.0,
    },
    "ROCE": {
        "column": "ROCE",
        "unit_label": "%",
        "to_source_factor": 0.01,
        "default_threshold": 10.0,
    },
    "Debt": {
        "column": "Debt (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 100.0,
    },
    "Cash": {
        "column": "Cash (Billion)",
        "unit_label": "₹ billion",
        "to_source_factor": 1.0,
        "default_threshold": 10.0,
    },
    "Debt-to-Equity Ratio": {
        "column": "Debt Equity Ratio",
        "unit_label": "ratio",
        "to_source_factor": 1.0,
        "default_threshold": 1.0,
    },
}


def parse_financial_value(value, metric_label, config):

    if value is None:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    text = (
        text.replace(",", "")
        .replace("₹", "")
        .replace("inr", "")
        .replace("rs.", "")
        .replace("rs", "")
        .replace("%", "")
        .strip()
    )

    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*"
        r"(.*?)",
        text,
    )
    if not match:
        raise ValueError(
            f"Cannot understand '{value}'. Try '5k crore', "
            "'5000 crore', '5 lakh crore', or a plain number."
        )

    amount = float(match.group(1))
    suffix = re.sub(r"\s+", " ", match.group(2).strip())

    if not suffix:
        return amount

    # Normalize common spellings.
    suffix = suffix.replace("lacs", "lakh").replace("lac", "lakh")
    suffix = suffix.replace("cr.", "crore").replace("cr", "crore")
    suffix = re.sub(r"\s+", " ", suffix)

    # Optional numeric shorthand before a unit:
    # 5k crore = 5,000 crore; 2.5k crore = 2,500 crore.
    prefix_multiplier = 1.0
    prefix_match = re.fullmatch(
        r"(k|thousand|mn|million|bn|billion)\s*(.*)",
        suffix,
    )
    if prefix_match:
        prefix = prefix_match.group(1)
        suffix = prefix_match.group(2).strip()
        prefix_multiplier = {
            "k": 1_000,
            "thousand": 1_000,
            "mn": 1_000_000,
            "million": 1_000_000,
            "bn": 1_000_000_000,
            "billion": 1_000_000_000,
        }[prefix]

    # A suffix that is only a multiplier means an absolute number.
    if suffix in {"k", "thousand", "mn", "million", "bn", "billion"}:
        prefix_multiplier *= {
            "k": 1_000,
            "thousand": 1_000,
            "mn": 1_000_000,
            "million": 1_000_000,
            "bn": 1_000_000_000,
            "billion": 1_000_000_000,
        }[suffix]
        suffix = ""

    if suffix in {"lakh crore", "crore", "lakh"}:
        currency_multiplier = {
            "lakh": 100_000,
            "crore": 10_000_000,
            "lakh crore": 1_000_000_000_000,
        }[suffix]
        amount_in_rupees = amount * prefix_multiplier * currency_multiplier

        if config["column"] == "Market Cap":
            return amount_in_rupees / 1_000_000_000_000

        currency_columns = {
            "Revenue (Billion)",
            "Net Revenue (Billion)",
            "EBITDA (Billion)",
            "PAT (Billion)",
            "PAT (FY-26)",
            "Debt (Billion)",
            "Cash (Billion)",
        }
        if config["column"] in currency_columns:
            return amount_in_rupees / 1_000_000_000

        raise ValueError(
            f"Currency units such as crore cannot be used with {metric_label}. "
            f"Enter a number in {config['unit_label']} instead."
        )

    # Absolute values such as 5k, 100 million, or 2 billion.
    if suffix == "":
        absolute_amount = amount * prefix_multiplier
        if config["column"] == "Market Cap":
            return absolute_amount / 1_000_000_000_000

        currency_columns = {
            "Revenue (Billion)",
            "Net Revenue (Billion)",
            "EBITDA (Billion)",
            "PAT (Billion)",
            "PAT (FY-26)",
            "Debt (Billion)",
            "Cash (Billion)",
        }
        if config["column"] in currency_columns:
            return absolute_amount / 1_000_000_000
        if config["unit_label"] == "%":
            return absolute_amount
        return absolute_amount

    raise ValueError(
        f"Cannot understand unit '{suffix}' for {metric_label}. "
        "Try '5k crore', '5000 crore', '5 lakh crore', '100 billion', "
        "or a plain number in the displayed units."
    )


def financial_input_step(metric_label, current_value):
    """Return the increment used by plus/minus controls."""
    unit = FINANCIAL_FILTER_METRICS[metric_label]["unit_label"]

    if unit == "%":
        return 1.0
    if unit == "ratio":
        return 0.1
    if unit == "₹ per share":
        return 10.0
    if metric_label == "Market Capitalization":
        return max(abs(current_value) * 0.05, 0.01)
    return max(abs(current_value) * 0.05, 1.0)


def adjust_financial_value(key, direction, metric):
    """Callback used by plus/minus buttons."""
    config = FINANCIAL_FILTER_METRICS[metric]
    try:
        current = parse_financial_value(
            st.session_state.get(key, ""),
            metric,
            config,
        )
        if current is None:
            current = 0.0
    except (ValueError, TypeError):
        current = 0.0

    step = financial_input_step(metric, current)
    updated = current + direction * step

    if metric != "Revenue Growth":
        updated = max(0.0, updated)

    # Store a plain number in the display units so that the input remains valid.
    st.session_state[key] = f"{updated:.8g}"


def financial_results_table(company_df: pd.DataFrame) -> pd.DataFrame:
    """Create a readable table without changing the numeric source dataframe."""
    columns = [
        "Company",
        "Sector",
        "Industry",
        "Market Cap",
        "Revenue (Billion)",
        "Revenue Growth",
        "PAT (Billion)",
        "EBITDA Margin",
        "Sector Rank",
    ]
    visible = [column for column in columns if column in company_df.columns]
    result = company_df[visible].copy()

    if "Market Cap" in result.columns:
        result["Market Cap"] = result["Market Cap"].map(
            lambda value: format_market_cap(value, unit="rupees")
        )

    for column in ["Revenue (Billion)", "PAT (Billion)"]:
        if column in result.columns:
            result[column] = result[column].map(lambda value: num(value, 2))

    for column in ["Revenue Growth", "EBITDA Margin"]:
        if column in result.columns:
            result[column] = result[column].map(pct)

    if "Sector Rank" in result.columns:
        result["Sector Rank"] = result["Sector Rank"].map(
            lambda value: num(value, 0)
        )

    return result


def company_news(df, company_name):
    """Return news records matching the selected company."""
    if df.empty or "Company_Key" not in df.columns:
        return df.iloc[0:0].copy()

    key = compute_company_key(company_name)
    return df[df["Company_Key"].astype(str).eq(key)].copy()


# ---------------------------------------------------------
# SUMMARY-ONLY TECHNOLOGY DATA
# ---------------------------------------------------------

@st.cache_data(show_spinner="Loading summarized technology profiles...")
def load_summary_technology_points(data_dir: str) -> dict:
    """Load summary claims, not raw page-level extraction evidence."""
    data_path = Path(data_dir)
    result = {}

    for workbook in sorted(data_path.glob("evidence_summary*.xlsx")):
        try:
            points_df = pd.read_excel(
                workbook,
                sheet_name="Summary Points",
                dtype=str,
            ).fillna("")
        except Exception:
            continue

        required = {"Company", "Parameter", "Point"}
        if not required.issubset(points_df.columns):
            continue

        for _, record in points_df.iterrows():
            company = str(record.get("Company", "")).strip()
            parameter = str(record.get("Parameter", "")).strip()
            point_text = str(record.get("Point", "")).strip()

            if (
                not company
                or parameter not in TECHNOLOGY_PARAMETERS
                or not point_text
            ):
                continue

            point_text = re.sub(
                r"^\s*\d+\s*[.)]\s*",
                "",
                point_text,
            ).strip()

            if not point_text or point_text.lower().startswith(
                ("not available in collected data", "no evidence available")
            ):
                continue

            key = compute_company_key(company)
            company_entry = result.setdefault(
                key,
                {"company": company, "parameters": {}},
            )
            parameter_points = company_entry["parameters"].setdefault(
                parameter,
                [],
            )

            normalized = re.sub(r"\s+", " ", point_text).casefold()
            if not any(
                re.sub(r"\s+", " ", existing["text"]).casefold() == normalized
                for existing in parameter_points
            ):
                pages = str(record.get("Source Pages", "")).strip()
                page_numbers = re.findall(r"\d+", pages)
                parameter_points.append(
                    {"text": point_text, "pages": page_numbers}
                )

    return result


# ---------------------------------------------------------
# LOAD PROJECT DATA
# ---------------------------------------------------------

try:
    financial = load_company_master()
    news = load_news()
    tech_summary, tech_detail = load_technology()
    kb = load_tech_knowledge()
    summary_technology = load_summary_technology_points(
        str(BASE_DIR / "data")
    )
except Exception as error:
    st.error(
        "Unable to load project data. Check the required Excel/CSV files in data/."
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
# SIDEBAR
# ---------------------------------------------------------

with st.sidebar:
    st.subheader("Navigation")

    st.page_link("app.py", label="Company Intelligence")
    st.page_link("pages/1_Comparison.py", label="Sector Comparison")
    st.page_link("pages/2_Chatbot.py", label="AI Company Assistant")

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

    st.divider()
    st.subheader("Data Coverage")
    st.metric("Companies", f"{len(financial):,}")
    st.metric("News Records", f"{len(news):,}")
    st.metric("Technology Profiles", f"{len(kb.profiles):,}")


# ---------------------------------------------------------
# FINANCIAL FILTER BAR: TEXT BOXES + PLUS/MINUS
# ---------------------------------------------------------

if not sectors:
    st.warning("No sectors are available in company_master.csv.")
    st.stop()

if not sector:
    st.warning("Please select a sector from the sidebar.")
    st.stop()

sector_companies = get_sector_companies(financial, sector)

st.subheader("Find Companies by Financial Value")
st.caption(
    "Enter a minimum and maximum value. Supported examples include "
    "'5k crore', '5000 crore', '5 lakh crore', '10 lakh crore', "
    "'100 billion', and plain numbers. Use + and − to adjust values."
)

with st.container(border=True):
    available_metrics = {
        label: config
        for label, config in FINANCIAL_FILTER_METRICS.items()
        if config["column"] in sector_companies.columns
    }

    if not available_metrics:
        st.warning(
            "No supported financial metric columns were found in the company data."
        )
        filtered_companies = sector_companies.copy()

    else:
        metric_label = st.selectbox(
            "Financial metric",
            options=list(available_metrics.keys()),
            key="financial_filter_metric",
        )
        config = available_metrics[metric_label]
        source_column = config["column"]
        unit_label = config["unit_label"]
        factor = float(config["to_source_factor"])

        numeric_source = pd.to_numeric(
            sector_companies[source_column],
            errors="coerce",
        ).replace([np.inf, -np.inf], np.nan)
        valid_source = numeric_source.dropna()

        if valid_source.empty:
            st.warning(
                f"No numeric values are available for {metric_label} in this sector."
            )
            filtered_companies = sector_companies.iloc[0:0].copy()

        else:
            display_values = valid_source / factor
            data_min = float(display_values.min())
            data_max = float(display_values.max())

            lower_key = f"financial_lower_{metric_label}"
            upper_key = f"financial_upper_{metric_label}"
            previous_metric_key = "financial_previous_metric"

            if st.session_state.get(previous_metric_key) != metric_label:
                st.session_state[lower_key] = f"{data_min:.8g}"
                st.session_state[upper_key] = f"{data_max:.8g}"
                st.session_state[previous_metric_key] = metric_label

            if lower_key not in st.session_state:
                st.session_state[lower_key] = f"{data_min:.8g}"
            if upper_key not in st.session_state:
                st.session_state[upper_key] = f"{data_max:.8g}"

            st.caption(
                f"Available data range: {data_min:,.4f} to "
                f"{data_max:,.4f} {unit_label}"
            )

            lower_col, upper_col = st.columns(2)

            with lower_col:
                st.markdown("**Minimum value**")
                minus_col, input_col, plus_col = st.columns(
                    [1, 5, 1],
                    vertical_alignment="bottom",
                )

                with minus_col:
                    st.button(
                        "−",
                        key=f"lower_minus_{metric_label}",
                        help="Decrease minimum value",
                        on_click=adjust_financial_value,
                        args=(lower_key, -1, metric_label),
                        use_container_width=True,
                    )

                with input_col:
                    st.text_input(
                        f"Minimum ({unit_label})",
                        key=lower_key,
                        placeholder="e.g. 5k crore",
                        help=(
                            "Currency examples: 5k crore, 5000 crore, "
                            "5 lakh crore, 100 billion."
                        ),
                    )

                with plus_col:
                    st.button(
                        "+",
                        key=f"lower_plus_{metric_label}",
                        help="Increase minimum value",
                        on_click=adjust_financial_value,
                        args=(lower_key, 1, metric_label),
                        use_container_width=True,
                    )

            with upper_col:
                st.markdown("**Maximum value**")
                minus_col, input_col, plus_col = st.columns(
                    [1, 5, 1],
                    vertical_alignment="bottom",
                )

                with minus_col:
                    st.button(
                        "−",
                        key=f"upper_minus_{metric_label}",
                        help="Decrease maximum value",
                        on_click=adjust_financial_value,
                        args=(upper_key, -1, metric_label),
                        use_container_width=True,
                    )

                with input_col:
                    st.text_input(
                        f"Maximum ({unit_label})",
                        key=upper_key,
                        placeholder="e.g. 10 lakh crore",
                        help=(
                            "Currency examples: 10k crore, 10 lakh crore, "
                            "or a plain number in the displayed units."
                        ),
                    )

                with plus_col:
                    st.button(
                        "+",
                        key=f"upper_plus_{metric_label}",
                        help="Increase maximum value",
                        on_click=adjust_financial_value,
                        args=(upper_key, 1, metric_label),
                        use_container_width=True,
                    )

            st.caption(
                "Plain numbers use the displayed units: ₹ lakh crore for market "
                "capitalization, ₹ billion for revenue/EBITDA/PAT/debt/cash, "
                "percentage points for percentage metrics, and the named units "
                "for EPS, LTP, and debt-to-equity."
            )

            apply_col, reset_col = st.columns(2)

            with apply_col:
                apply_filter = st.button(
                    "Apply Filter",
                    key=f"apply_financial_filter_{metric_label}",
                    type="primary",
                    use_container_width=True,
                )

            with reset_col:
                reset_filter = st.button(
                    "Reset to Sector Range",
                    key=f"reset_financial_filter_{metric_label}",
                    use_container_width=True,
                )

            filter_state_key = f"applied_financial_filter_{metric_label}"

            if reset_filter:
                st.session_state[lower_key] = f"{data_min:.8g}"
                st.session_state[upper_key] = f"{data_max:.8g}"
                st.session_state[filter_state_key] = {
                    "lower": data_min,
                    "upper": data_max,
                }

            elif apply_filter:
                try:
                    lower_value = parse_financial_value(
                        st.session_state.get(lower_key, ""),
                        metric_label,
                        config,
                    )
                    upper_value = parse_financial_value(
                        st.session_state.get(upper_key, ""),
                        metric_label,
                        config,
                    )

                    if lower_value is None or upper_value is None:
                        raise ValueError(
                            "Enter both a minimum and maximum value."
                        )

                    if lower_value < 0 or upper_value < 0:
                        raise ValueError(
                            "Financial filter values cannot be negative."
                        )

                    if lower_value > upper_value:
                        raise ValueError(
                            "Minimum value cannot exceed maximum value."
                        )

                    st.session_state[filter_state_key] = {
                        "lower": lower_value,
                        "upper": upper_value,
                    }

                except (ValueError, TypeError) as error:
                    st.error(str(error))

            applied_range = st.session_state.get(
                filter_state_key,
                {"lower": data_min, "upper": data_max},
            )
            lower_value = float(applied_range["lower"])
            upper_value = float(applied_range["upper"])

            # Display inputs are converted back to source units before filtering.
            filtered_companies = sector_companies.loc[
                numeric_source.notna()
                & numeric_source.between(
                    lower_value * factor,
                    upper_value * factor,
                    inclusive="both",
                )
            ].copy()

            st.caption(
                f"Applied range: {lower_value:,.4f}–"
                f"{upper_value:,.4f} {unit_label}"
            )

    count_col, sector_count_col = st.columns(2)
    count_col.metric("Matching companies", f"{len(filtered_companies):,}")
    sector_count_col.metric(
        "Companies in selected sector",
        f"{len(sector_companies):,}",
    )

if filtered_companies.empty:
    st.warning(
        "No companies fall within this range. Adjust the values or reset the filter."
    )
    st.stop()

st.markdown("#### Matching Companies")
st.dataframe(
    financial_results_table(filtered_companies),
    use_container_width=True,
    hide_index=True,
)


# ---------------------------------------------------------
# COMPANY SELECTION
# ---------------------------------------------------------

filtered_names = (
    filtered_companies["Company"]
    .dropna()
    .astype(str)
    .drop_duplicates()
    .tolist()
)
previous_selection = st.session_state.get("company_detail_select")
selected_index = (
    filtered_names.index(previous_selection)
    if previous_selection in filtered_names
    else 0
)
selected_name = st.selectbox(
    "Select a company to view its full intelligence",
    options=filtered_names,
    index=selected_index,
    key="company_detail_select",
)

st.divider()

if not selected_name:
    st.info("Please select a company to view its intelligence.")
    st.stop()


# ---------------------------------------------------------
# COMPANY FINANCIAL INTELLIGENCE
# ---------------------------------------------------------

match = financial[financial["Company"].astype(str).eq(selected_name)]
row = match.iloc[0] if not match.empty else None

st.header("Company Intelligence")
st.subheader(selected_name)

if row is not None:
    metric_cols = st.columns(4)

    metric_cols[0].metric(
        "Market Cap",
        format_market_cap(row.get("Market Cap"), unit="rupees"),
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

    with st.expander("View All Available Financial Data", expanded=True):
        st.dataframe(
            pd.DataFrame([row[fin_cols]]),
            use_container_width=True,
            hide_index=True,
        )
else:
    st.warning(
        "Financial information for the selected company was not found "
        "in company_master.csv."
    )


# ---------------------------------------------------------
# GPT-OSS TECHNOLOGY SUMMARIZATION
# ---------------------------------------------------------

SUMMARY_CACHE_FILE = BASE_DIR / "output" / "technology_ui_summaries.json"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


def _get_secret_value(name: str, default: str = "") -> str:
    """Read settings from Streamlit secrets, then environment variables."""
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(secret_value or os.getenv(name, default) or "").strip()


def _load_summary_cache() -> dict:
    try:
        if SUMMARY_CACHE_FILE.exists():
            with SUMMARY_CACHE_FILE.open("r", encoding="utf-8") as file:
                value = json.load(file)
                return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_summary_cache(cache: dict) -> None:
    SUMMARY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = SUMMARY_CACHE_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(cache, file, ensure_ascii=False, indent=2)
    temporary_file.replace(SUMMARY_CACHE_FILE)


def _source_fingerprint(profile: dict) -> str:
    """Invalidate saved summaries when source Summary Points change."""
    stable_payload = json.dumps(
        profile.get("parameters", {}),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(stable_payload.encode("utf-8")).hexdigest()


def _build_summary_prompt(profile: dict) -> tuple[str, dict]:
    """Build bounded evidence input and keep source pages outside the LLM."""
    source_parameters = {}
    page_map = {}

    for parameter in TECHNOLOGY_PARAMETERS:
        points = profile.get("parameters", {}).get(parameter, [])
        if not points:
            continue

        selected_points = []
        pages_for_parameter = []

        for point in points[:10]:
            text = str(point.get("text", "")).strip()
            if not text:
                continue

            pages = [
                str(page).strip()
                for page in point.get("pages", [])
                if str(page).strip()
            ]
            selected_points.append({"text": text[:900], "pages": pages})
            pages_for_parameter.extend(pages)

        if selected_points:
            source_parameters[parameter] = selected_points
            page_map[parameter] = sorted(
                set(pages_for_parameter),
                key=lambda x: (
                    not x.isdigit(),
                    int(x) if x.isdigit() else x,
                ),
            )

    payload = json.dumps(source_parameters, ensure_ascii=False)
    if len(payload) > 24000:
        source_parameters = {
            parameter: points[:5]
            for parameter, points in source_parameters.items()
        }
        payload = json.dumps(source_parameters, ensure_ascii=False)

    prompt = f"""You are a careful corporate technology analyst. Summarize the supplied annual-report technology evidence for one company.

Rules:
- Use ONLY facts in the supplied evidence. Do not add outside knowledge, assumptions, rankings, or invented numbers.
- Produce one concise summary per supplied technology parameter, ideally 1-2 sentences and no more than 55 words per parameter.
- Combine related points and remove repetition while retaining important company-specific actions, systems, initiatives, risks, investments, partnerships, and measurable facts.
- Do not turn a missing value into zero. If a supplied point says a value is not reported, preserve that distinction.
- Do not include page numbers in summary text; the application attaches source pages from the original evidence.
- Return ONLY valid JSON: an object whose keys are the exact parameter names supplied and whose values are plain-string summaries. Do not include markdown fences or extra keys.

Evidence by parameter:
{payload}
"""
    return prompt, page_map


def generate_gpt_oss_technology_summary(profile: dict) -> dict:
    """Generate and return a cached GPT-OSS summary per available parameter."""
    api_key = _get_secret_value("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to your .env file or Streamlit secrets."
        )

    from groq import Groq

    model = _get_secret_value("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    effort = _get_secret_value("GROQ_REASONING_EFFORT", "low").lower()
    if effort not in {"low", "medium", "high"}:
        effort = "low"

    prompt, page_map = _build_summary_prompt(profile)
    if not page_map:
        return {
            "model": model,
            "parameters": {},
            "source_fingerprint": _source_fingerprint(profile),
        }

    client = Groq(api_key=api_key)
    kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write grounded, concise corporate technology summaries "
                    "and follow JSON-only output instructions."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_completion_tokens": 4500,
        "extra_body": {"reasoning_effort": effort},
    }

    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if (
            "reasoning_effort" in str(exc).lower()
            or "extra_body" in str(exc).lower()
        ):
            kwargs.pop("extra_body", None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise

    content = (response.choices[0].message.content or "").strip()
    content = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        content,
        flags=re.IGNORECASE,
    ).strip()

    try:
        summaries = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GPT-OSS returned invalid JSON. Please try regenerating the summary."
        ) from exc

    if not isinstance(summaries, dict):
        raise RuntimeError("GPT-OSS returned an unexpected summary format.")

    parameter_results = {}
    for parameter, pages in page_map.items():
        summary_text = summaries.get(parameter, "")
        if isinstance(summary_text, list):
            summary_text = " ".join(str(item) for item in summary_text)

        summary_text = re.sub(r"\s+", " ", str(summary_text)).strip()
        if summary_text:
            parameter_results[parameter] = {
                "summary": summary_text,
                "pages": pages,
            }

    return {
        "model": model,
        "parameters": parameter_results,
        "source_fingerprint": _source_fingerprint(profile),
    }


# ---------------------------------------------------------
# TECHNOLOGY INTELLIGENCE
# ---------------------------------------------------------

st.divider()
st.header("Technology Intelligence")

summary_key = compute_company_key(selected_name)
summary_profile = summary_technology.get(summary_key)

if not summary_profile or not summary_profile.get("parameters"):
    st.info(
        "No summarized technology source points are available for this company. "
        "Raw extracted evidence is intentionally not displayed here. Check the "
        "Summary Points sheet in data/evidence_summary*.xlsx."
    )
else:
    cache = _load_summary_cache()
    source_fingerprint = _source_fingerprint(summary_profile)
    cached_entry = cache.get(summary_key, {})

    cache_is_current = (
        isinstance(cached_entry, dict)
        and cached_entry.get("source_fingerprint") == source_fingerprint
        and isinstance(cached_entry.get("parameters"), dict)
        and bool(cached_entry.get("parameters"))
    )

    if not cache_is_current:
        try:
            with st.spinner("Preparing technology insights…"):
                generated_entry = generate_gpt_oss_technology_summary(
                    summary_profile
                )

            cache[summary_key] = {
                "company": summary_profile.get("company", selected_name),
                **generated_entry,
            }
            _save_summary_cache(cache)
            cached_entry = cache[summary_key]

        except Exception as error:
            st.error(f"Unable to generate the AI technology summary: {error}")
            st.warning(
                "No raw-evidence fallback is shown. Check GROQ_API_KEY, your "
                "network connection, model availability, and Groq usage limits."
            )
            cached_entry = {}

    ai_parameters = (
        cached_entry.get("parameters", {})
        if isinstance(cached_entry, dict)
        else {}
    )

    if not ai_parameters:
        st.info("No AI summaries are available for the selected company yet.")
    else:
        available_parameters = [
            parameter
            for parameter in TECHNOLOGY_PARAMETERS
            if parameter in ai_parameters
        ]

        tech_cols = st.columns(3)
        for index, parameter in enumerate(available_parameters):
            item = ai_parameters[parameter]
            with tech_cols[index % 3]:
                with st.container(border=True):
                    st.markdown(f"**{parameter}**")
                    st.markdown(item.get("summary", "Summary unavailable."))
                    pages = item.get("pages", [])
                    if pages:
                        st.caption(
                            "Source page(s): " + ", ".join(str(page) for page in pages)
                        )

        missing_parameters = [
            parameter
            for parameter in TECHNOLOGY_PARAMETERS
            if parameter not in ai_parameters
        ]
        if missing_parameters:
            with st.expander(
                f"Parameters without source summary points ({len(missing_parameters)})"
            ):
                st.write(", ".join(missing_parameters))


# ---------------------------------------------------------
# NEWS INTELLIGENCE
# ---------------------------------------------------------

st.divider()
st.header("News Intelligence")

company_news_df = company_news(news, selected_name)

if company_news_df.empty:
    st.info(
        "No matching news rows were found for this company in news_analysis.xlsx."
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
        f"{len(company_news_df)} news records from the supplied workbook."
    )
    st.dataframe(
        company_news_df[display_cols],
        use_container_width=True,
        hide_index=True,
    )

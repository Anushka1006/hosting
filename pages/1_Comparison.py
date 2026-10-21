from pathlib import Path
import os
import re

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from groq import Groq


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="Sector Comparison",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.data_loader import (
    load_company_master,
    load_tech_knowledge,
    get_sectors,
    get_sector_leader,
    get_sector_companies,
)

from utils.tech_knowledge import TECHNOLOGY_PARAMETERS


DEFAULT_MODEL = "openai/gpt-oss-20b"


# ============================================================
# PAGE STYLING
# ============================================================

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
    }

    hr {
        border-color: #dce6f0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# GROQ CONFIGURATION
# Reuses the same environment variables as the chatbot.
# ============================================================

def _get_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""

    return str(value or os.getenv(name, default) or "").strip()


def get_api_key() -> str:
    return _get_secret("GROQ_API_KEY")


def get_model() -> str:
    return _get_secret("GROQ_MODEL", DEFAULT_MODEL)


def get_reasoning_effort() -> str:
    value = _get_secret(
        "GROQ_REASONING_EFFORT",
        "low",
    ).lower()

    return value if value in {"low", "medium", "high"} else "low"


def get_groq_client() -> Groq:
    api_key = get_api_key()

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to your existing .env file "
            "or Streamlit Cloud Secrets."
        )

    return Groq(api_key=api_key)


def call_comparison_llm(prompt: str) -> str:
    """Call the same Groq model configured for the chatbot."""

    client = get_groq_client()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a corporate intelligence analyst. "
                "Compare companies using only the supplied company data "
                "and annual-report technology evidence. "
                "Be balanced, precise, and transparent about missing data. "
                "Never invent figures, technology adoption, vendors, "
                "investments, achievements, citations, or page numbers."
            ),
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]

    kwargs = {
        "model": get_model(),
        "messages": messages,
        "max_completion_tokens": 3000,
        "temperature": 0.3,
    }

    effort = get_reasoning_effort()

    if effort:
        kwargs["extra_body"] = {
            "reasoning_effort": effort,
        }

    try:
        response = client.chat.completions.create(**kwargs)

    except Exception as exc:
        # Match the chatbot's fallback for unsupported reasoning options.
        if (
            "reasoning_effort" in str(exc).lower()
            and "extra_body" in kwargs
        ):
            kwargs.pop("extra_body", None)
            response = client.chat.completions.create(**kwargs)
        else:
            raise

    answer = (
        response.choices[0].message.content or ""
    ).strip()

    if not answer:
        raise RuntimeError(
            "The LLM returned an empty comparison. Please try again."
        )

    return answer


# ============================================================
# DISPLAY HELPERS
# ============================================================

def display_value(value):
    if value is None:
        return "Not available in supplied data"

    try:
        if pd.isna(value) or str(value).strip() == "":
            return "Not available in supplied data"
    except Exception:
        pass

    return str(value)


def points_text(profile, parameter):
    if profile is None:
        return "No evidence in supplied technology workbooks"

    points = profile.points.get(parameter, [])

    if not points:
        return "No evidence in supplied technology workbooks"

    return "\n".join(
        f"• {point.text} "
        f"(page {', '.join(map(str, point.pages)) or 'not specified'})"
        for point in points
    )


def compact_evidence(profile, max_points_per_parameter=3):
    """Build bounded, page-labelled evidence for the LLM prompt."""

    if profile is None or profile.total_points == 0:
        return "No extracted technology evidence is available."

    sections = []

    for parameter in TECHNOLOGY_PARAMETERS:
        points = profile.points.get(parameter, [])

        if not points:
            continue

        lines = []

        for point in points[:max_points_per_parameter]:
            text = " ".join(str(point.text).split())

            # Limit the size of an individual evidence point.
            if len(text) > 650:
                text = text[:647].rsplit(" ", 1)[0] + "..."

            pages = (
                ", ".join(map(str, point.pages))
                if point.pages
                else "not specified"
            )

            lines.append(
                f"- {text} [Annual report page: {pages}]"
            )

        sections.append(
            f"{parameter}:\n" + "\n".join(lines)
        )

    if not sections:
        return "No extracted technology evidence is available."

    return "\n\n".join(sections)


# ============================================================
# BUILD LLM COMPARISON PROMPT
# ============================================================

def build_comparison_prompt(
    selected_name,
    leader_name,
    company_row,
    leader_row,
    company_profile,
    leader_profile,
):
    financial_params = [
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
        "Sector Rank",
    ]

    def financial_context(name, row):
        lines = [f"Company: {name}"]

        for parameter in financial_params:
            if parameter in row.index:
                lines.append(
                    f"{parameter}: {display_value(row.get(parameter))}"
                )

        return "\n".join(lines)

    selected_evidence = compact_evidence(company_profile)
    leader_evidence = compact_evidence(leader_profile)

    same_company = selected_name == leader_name

    return f"""
Compare the following selected company with its sector leader.

SELECTED COMPANY
{financial_context(selected_name, company_row)}

SECTOR LEADER
{financial_context(leader_name, leader_row)}

SELECTED COMPANY — EXTRACTED ANNUAL-REPORT TECHNOLOGY EVIDENCE
{selected_evidence}

SECTOR LEADER — EXTRACTED ANNUAL-REPORT TECHNOLOGY EVIDENCE
{leader_evidence}

ANALYSIS REQUIREMENTS

1. Write an informative comparison using the supplied facts only.

2. Use these sections:
   - Executive Summary
   - Financial Comparison
   - Technology Comparison
   - Relative Strengths
   - Technology Gaps and Data Limitations
   - Overall Assessment

3. In the financial section, compare the available values and explain
   meaningful differences. Do not assume that a larger value always
   means better performance. Do not invent missing figures or
   calculate ratios when the underlying data is unavailable.

4. In the technology section, compare corresponding parameters such as
   Current Technology Adoption, Digital Transformation, R&D, Emerging
   Technologies, Cloud Adoption, Automation, Cybersecurity, AI,
   Technology Investments, Platforms & Systems, Tech Risk, and
   Talent & Skills, wherever evidence is available.

5. Identify actual similarities and differences. Explain the significance
   of a disclosed initiative only when the supplied evidence supports
   that interpretation.

6. Cite technology statements using the supplied annual-report page
   numbers, for example: (annual report, p. 125).
   Use only page numbers explicitly supplied with the evidence.
   Never fabricate citations.

7. If no evidence is supplied for a parameter, say:
   "No evidence found in the supplied technology workbooks."
   This does not establish that the company does not use the technology.

8. Distinguish missing evidence from a demonstrated weakness.
   Do not call a company technologically weak merely because its
   evidence collection is incomplete.

9. If evidence coverage differs between the companies, mention that
   limitation and avoid declaring a definitive technology winner.

10. If the selected company and sector leader are the same company,
    explain that a separate company-versus-leader comparison is not
    meaningful. Do not manufacture differences.

11. Do not repeat the full evidence excerpts. Explain the evidence
    in clear, natural language.

12. Keep the analysis detailed enough to be useful, with clear headings
    and concise paragraphs or bullets.
"""


# ============================================================
# LOAD DATA
# ============================================================

try:
    financial = load_company_master()
    kb = load_tech_knowledge()

except Exception as exc:
    st.error(
        "Unable to load the supplied financial or technology data."
    )
    st.exception(exc)
    st.stop()


# ============================================================
# PAGE TITLE AND NAVIGATION
# ============================================================

st.title("Sector Comparison")

st.caption(
    "Compare any company with its sector leader using the supplied "
    "financial data and annual-report technology evidence."
)

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

    sectors = get_sectors(financial)

    sector = (
        st.selectbox(
            "Select Sector",
            sectors,
            key="comparison_sector",
        )
        if sectors
        else None
    )

    companies = (
        get_sector_companies(financial, sector)
        if sector
        else financial.iloc[0:0]
    )

    company_names = (
        companies["Company"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
        if "Company" in companies.columns
        else []
    )

    leader = (
        get_sector_leader(financial, sector)
        if sector
        else None
    )

    default_name = next(
        (
            name
            for name in company_names
            if leader is not None
            and name != str(leader.get("Company"))
        ),
        company_names[0] if company_names else None,
    )

    selected = (
        st.selectbox(
            "Select Company",
            company_names,
            index=(
                company_names.index(default_name)
                if default_name in company_names
                else 0
            ),
            key="comparison_company",
        )
        if company_names
        else None
    )


# ============================================================
# VALIDATE SELECTION
# ============================================================

if not sector or leader is None or not selected:
    st.info("Select a sector and company to start comparison.")
    st.stop()

leader_name = str(leader["Company"])

chosen = companies[
    companies["Company"].astype(str).eq(selected)
]

if chosen.empty:
    st.warning(
        "Selected company was not found in the financial workbook."
    )
    st.stop()

company = chosen.iloc[0]

st.subheader(f"{selected} vs {leader_name}")

if selected == leader_name:
    st.info(
        "The selected company is the sector leader, so both sides "
        "represent the same company."
    )

# st.caption(
#     "Financial data: data/company_master.csv • "
#     "Technology evidence: configured technology evidence workbooks"
# )


# ============================================================
# TECHNOLOGY PARAMETERS COMPARISON — EXISTING TABLE
# ============================================================

st.header("Technology Parameters Comparison")

leader_profile = kb.get_profile(leader_name)
company_profile = kb.get_profile(selected)

tech_rows = []

for parameter in TECHNOLOGY_PARAMETERS:
    tech_rows.append(
        {
            "Technology Parameter": parameter,
            selected: points_text(company_profile, parameter),
            f"Sector Leader — {leader_name}": points_text(
                leader_profile,
                parameter,
            ),
        }
    )

tech_compare = pd.DataFrame(tech_rows)

st.dataframe(
    tech_compare,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download technology comparison CSV",
    tech_compare.to_csv(index=False).encode("utf-8-sig"),
    file_name="technology_comparison.csv",
    mime="text/csv",
)


# ============================================================
# FINANCIAL PARAMETERS COMPARISON — EXISTING TABLE
# ============================================================

st.header("Financial Parameters Comparison")

financial_params = [
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
    "Sector Rank",
]

rows = []

for parameter in financial_params:
    if parameter in financial.columns:
        rows.append(
            {
                "Financial Parameter": parameter,
                selected: display_value(company.get(parameter)),
                f"Sector Leader — {leader_name}": display_value(
                    leader.get(parameter)
                ),
            }
        )

fin_compare = pd.DataFrame(rows)

st.dataframe(
    fin_compare,
    use_container_width=True,
    hide_index=True,
)


# ============================================================
# EXISTING FINANCIAL CHART
# ============================================================

numeric_metrics = [
    parameter
    for parameter in [
        "Market Cap",
        "Revenue (Billion)",
        "EBITDA (Billion)",
        "PAT (Billion)",
    ]
    if parameter in financial.columns
]

if numeric_metrics:
    chart_rows = []

    for parameter in numeric_metrics:
        for name, row in [
            (selected, company),
            (leader_name, leader),
        ]:
            try:
                value = pd.to_numeric(
                    row.get(parameter),
                    errors="coerce",
                )
            except Exception:
                value = float("nan")

            if pd.notna(value):
                chart_rows.append(
                    {
                        "Parameter": parameter,
                        "Company": name,
                        "Value": float(value),
                    }
                )

    # ============================================================
# INTERACTIVE SECTOR FINANCIAL COMPARISON
# ============================================================

st.header("Sector Financial Benchmarking")

st.caption(
    "Compare the selected company against the top 10 companies "
    "in the selected sector."
)

# Interactive controls
control1, control2 = st.columns(2)

with control1:
    metric_label = st.radio(
        "Choose financial parameter",
        ["Market Cap", "Revenue"],
        horizontal=True,
        key="benchmark_metric",
    )

with control2:
    chart_type = st.radio(
        "Chart type",
        ["Bar chart", "Line chart"],
        horizontal=True,
        key="benchmark_chart_type",
    )

# Map displayed labels to CSV columns
metric_columns = {
    "Market Cap": "Market Cap",
    "Revenue": "Revenue (Billion)",
}
metric_column = metric_columns[metric_label]

# Get the companies in the selected sector
benchmark_df = companies.copy()

benchmark_df["Company"] = benchmark_df["Company"].astype(str).str.strip()
benchmark_df = benchmark_df.drop_duplicates(subset=["Company"])

# Numeric sorting columns
benchmark_df["_rank"] = (
    pd.to_numeric(benchmark_df["Sector Rank"], errors="coerce")
    if "Sector Rank" in benchmark_df.columns
    else float("nan")
)

benchmark_df["_cap"] = (
    pd.to_numeric(benchmark_df["Market Cap"], errors="coerce")
    if "Market Cap" in benchmark_df.columns
    else float("nan")
)

# Rank companies by sector rank, falling back to market cap
if benchmark_df["_rank"].notna().any():
    benchmark_df = benchmark_df.sort_values(
        ["_rank", "_cap"],
        ascending=[True, False],
        na_position="last",
    )
else:
    benchmark_df = benchmark_df.sort_values(
        "_cap", ascending=False, na_position="last"
    )

# Select top 10 companies
benchmark_df = benchmark_df.head(10).copy()

# Always include the selected company
selected_rows = companies[
    companies["Company"].astype(str).str.strip().str.casefold()
    == str(selected).strip().casefold()
]

if not selected_rows.empty:
    already_included = benchmark_df["Company"].str.casefold().eq(
        str(selected).strip().casefold()
    ).any()

    if not already_included:
        benchmark_df = pd.concat(
            [benchmark_df, selected_rows.head(1)],
            ignore_index=True,
        )

# Check metric availability
if metric_column not in benchmark_df.columns:
    st.warning(f"The selected financial metric '{metric_label}' is unavailable.")
else:
    plot_df = benchmark_df[["Company", metric_column]].copy()
    plot_df[metric_column] = pd.to_numeric(
        plot_df[metric_column], errors="coerce"
    )

    # Convert decimal margins (e.g. 0.15) into percentages.
    # if metric_column == "EBITDA Margin":
    #     plot_df[metric_column] = plot_df[metric_column].apply(
    #         lambda value: value * 100
    #         if pd.notna(value) and abs(value) <= 1
    #         else value
    #     )

    plot_df = plot_df.dropna(subset=[metric_column])

    # Mark the selected company in the chart
    plot_df["Company"] = plot_df["Company"].apply(
        lambda name: (
            f"{name} (Selected)"
            if name.strip().casefold() == str(selected).strip().casefold()
            else name
        )
    )

    plot_df = plot_df.set_index("Company")

    if plot_df.empty:
        st.info(f"No numeric values are available for {metric_label}.")
    else:
        if chart_type == "Bar chart":
            st.bar_chart(
                plot_df,
                horizontal=False,
                height=420,
            )
        else:
            st.line_chart(
                plot_df,
                height=420,
            )

        # if metric_label == "Market Cap":
        #     st.caption("Market capitalization — as stored in the supplied CSV.")
        # elif metric_label == "Revenue":
        #     st.caption("Revenue in billions — as stored in the supplied CSV.")
        # else:
        #     st.caption("EBITDA margin shown as a percentage.")

# Display the companies included in the comparison
# with st.expander("View benchmark companies"):
#     st.dataframe(
#         benchmark_df[["Company"]].drop_duplicates(),
#         use_container_width=True,
#         hide_index=True,
#     )



st.download_button(
    "Download financial comparison CSV",
    fin_compare.to_csv(index=False).encode("utf-8-sig"),
    file_name="financial_comparison.csv",
    mime="text/csv",
)

# st.caption(
#     "Missing values are shown as unavailable; the dashboard does not "
#     "invent evidence or fill gaps with generated facts."
# )


# ============================================================
# NEW: LLM-GENERATED COMPARISON ANALYSIS
# ============================================================

st.divider()
st.header("LLM Comparison Analysis")

st.write(
    "Generate an explanation of the financial and technology differences "
    "between the selected company and its sector leader."
)

st.caption(
    "The existing comparison tables above remain the source-data view. "
    "The LLM explanation is an additional interpretation of that data."
)

# A changed selection should not display an old company's explanation.
comparison_key = (
    str(sector),
    str(selected),
    str(leader_name),
)

if (
    st.session_state.get("llm_comparison_key")
    != comparison_key
):
    st.session_state.pop("llm_comparison_result", None)
    st.session_state["llm_comparison_key"] = comparison_key


if st.button(
    "Generate LLM Comparison",
    type="primary",
    key="generate_llm_comparison",
):

    if selected == leader_name:
        st.session_state["llm_comparison_result"] = (
            "### Comparison unavailable\n\n"
            "The selected company is also the sector leader. "
            "Select a different company to generate a meaningful "
            "company-versus-leader comparison."
        )

    else:
        try:
            prompt = build_comparison_prompt(
                selected_name=selected,
                leader_name=leader_name,
                company_row=company,
                leader_row=leader,
                company_profile=company_profile,
                leader_profile=leader_profile,
            )

            with st.spinner(
                "Analysing the financial data and technology evidence..."
            ):
                result = call_comparison_llm(prompt)

            st.session_state["llm_comparison_result"] = result

        except Exception as exc:
            error_text = str(exc)

            if (
                "tokens per day" in error_text.lower()
                or "tpd" in error_text.lower()
            ):
                st.error(
                    "The configured Groq daily token quota has been "
                    "reached. Please try again after the quota resets."
                )

            elif (
                "413" in error_text
                or "rate_limit" in error_text.lower()
                or "rate limit" in error_text.lower()
            ):
                st.error(
                    "The Groq request exceeded a model or rate limit. "
                    "Try again later or review the model quota."
                )

            else:
                st.error(
                    "Unable to generate the LLM comparison. "
                    "Check the existing Groq configuration and try again."
                )

                with st.expander("Technical details"):
                    st.code(error_text)


# Show the result below the tables and chart.
llm_result = st.session_state.get(
    "llm_comparison_result"
)

if llm_result:
    st.markdown("---")
    st.subheader(
        f"Analysis: {selected} vs {leader_name}"
    )
    st.markdown(llm_result)

    st.download_button(
        "Download LLM comparison as Markdown",
        data=llm_result.encode("utf-8"),
        file_name="llm_comparison.md",
        mime="text/markdown",
    )
else:
    st.info(
        "Click **Generate LLM Comparison** to create an explanation "
        "based on the currently selected companies and the supplied data."
    )

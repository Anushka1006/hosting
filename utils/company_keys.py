"""
Company-name normalisation shared by every module.

Lives in its own file (no Streamlit import) so that both
utils/data_loader.py and utils/tech_knowledge.py can use the exact same
Company_Key definition without importing each other.
"""

import re

import pandas as pd


def normalize_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Corporate suffixes that appear inconsistently across the source files
# (company_master.csv spells every company "... Ltd.", while the technology
# workbooks and news file often drop it).
COMPANY_SUFFIXES = [
    "private limited", "pvt limited", "pvt ltd", "private ltd",
    "limited", "ltd", "plc", "incorporated", "inc",
    "corporation", "corp", "llp",
]


def strip_company_suffix(normalized_text: str) -> str:
    text = normalized_text
    for suffix in COMPANY_SUFFIXES:
        text = re.sub(rf"\b{re.escape(suffix)}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compute_company_key(name) -> str:
    """
    The single definition of Company_Key: normalise, strip corporate
    suffixes, remove all spaces.  Every dataframe / workbook must build its
    key with this function or joins silently miss.
    """
    return strip_company_suffix(normalize_text(name)).replace(" ", "")


def short_company_name(name) -> str:
    """'ICICI Bank Ltd.' -> 'ICICI Bank' (for compact inline citations)."""
    text = str(name or "").strip()
    text = re.sub(
        r"\s+(private limited|pvt\.? ltd\.?|limited|ltd\.?|plc|inc\.?)\s*$",
        "", text, flags=re.I,
    )
    return text.strip() or str(name or "").strip()

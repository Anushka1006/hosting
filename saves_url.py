# ============================================================
# NSE ANNUAL REPORT 2025-26 URL COLLECTOR
# ============================================================
#
# INPUT:
#   companies_list.csv
#
# Input CSV must contain ONLY:
#
#   Company Name
#
#
# OUTPUT:
#   output/nse_annual_report_urls.xlsx
#   output/nse_annual_report_urls.csv
#
#
# OUTPUT COLUMNS:
#
#   Company Name
#   Alternative pdf url
#
#
# The script:
#
#   1. Reads company names from CSV
#   2. Downloads official NSE equity company list
#   3. Finds NSE symbol for each company
#   4. Opens direct NSE Annual Reports page
#   5. Searches ONLY for:
#          FROM YEAR = 2025
#          TO YEAR   = 2026
#   6. Extracts the actual NSE PDF URL
#   7. Saves progress after every company
#
# ============================================================


import os
import re
import time
from io import StringIO
from urllib.parse import quote

import pandas as pd

from playwright.sync_api import (
    sync_playwright
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = r"D:\GENXAI\NSE BSE\A_NEW"


# ------------------------------------------------------------
# INPUT
# ------------------------------------------------------------

INPUT_FILE = os.path.join(
    BASE_DIR,
    "companynames.csv"
)


# ------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------

OUTPUT_DIR = os.path.join(
    BASE_DIR,
    "output"
)


OUTPUT_XLSX = os.path.join(
    OUTPUT_DIR,
    "nse_annual_report_urls.xlsx"
)


OUTPUT_CSV = os.path.join(
    OUTPUT_DIR,
    "nse_annual_report_urls.csv"
)


# ============================================================
# NSE URLS
# ============================================================

NSE_HOME = (
    "https://www.nseindia.com"
)


NSE_ANNUAL_REPORT_URL = (
    "https://www.nseindia.com/"
    "companies-listing/corporate-filings-annual-reports"
)


# Official NSE equity security list
NSE_EQUITY_CSV = (
    "https://nsearchives.nseindia.com/"
    "content/equities/EQUITY_L.csv"
)


# ============================================================
# TARGET YEAR
# ============================================================

TARGET_FROM_YEAR = "2025"
TARGET_TO_YEAR = "2026"


# ============================================================
# PROCESSING SETTINGS
# ============================================================

# First test:
#
# False = browser window visible
#
# Once everything is working you can change to:
#
# HEADLESS = True
#

HEADLESS = False


# ------------------------------------------------------------
# Process entire input file
# ------------------------------------------------------------

START_ROW = 1
END_ROW = None


# ------------------------------------------------------------
# Delay between companies
# ------------------------------------------------------------

WAIT_AFTER_COMPANY = 2


# ------------------------------------------------------------
# NSE timeout
# ------------------------------------------------------------

TIMEOUT = 30000


# ------------------------------------------------------------
# Retry count
# ------------------------------------------------------------

MAX_RETRIES = 3


# ============================================================
# NORMALIZE COMPANY NAME
# ============================================================

def normalize_company_name(name):

    if pd.isna(name):
        return ""

    name = str(name).strip().lower()

    # Replace punctuation
    name = re.sub(
        r"[^a-z0-9]+",
        " ",
        name
    )

    # Common company suffixes
    suffixes = [
        "private limited",
        "private ltd",
        "pvt limited",
        "pvt ltd",
        "limited",
        "ltd",
        "incorporated",
        "inc",
        "corporation",
        "corp",
        "company",
        "co"
    ]

    for suffix in suffixes:

        name = re.sub(
            rf"\b{re.escape(suffix)}\b",
            " ",
            name
        )

    # Remove extra spaces
    name = re.sub(
        r"\s+",
        " ",
        name
    ).strip()

    return name


# ============================================================
# LOAD INPUT CSV
# ============================================================

def load_input_file():

    print()
    print("=" * 70)
    print("LOADING INPUT FILE")
    print("=" * 70)

    if not os.path.exists(INPUT_FILE):

        raise FileNotFoundError(
            f"""
Input file not found:

{INPUT_FILE}

Please put your CSV file here:

{BASE_DIR}

The file name must be:

companies_list.csv
"""
        )


    print()
    print(
        f"Input file:"
    )

    print(
        INPUT_FILE
    )


    # --------------------------------------------------------
    # Read CSV
    # --------------------------------------------------------

    df = pd.read_csv(
        INPUT_FILE,
        dtype=str
    ).fillna("")


    print()
    print(
        "Columns found:"
    )

    print(
        list(df.columns)
    )


    # --------------------------------------------------------
    # Find Company Name column
    # --------------------------------------------------------

    company_column = None

    possible_columns = [
        "Company Name",
        "Company_Name",
        "Company",
        "company_name",
        "company"
    ]


    for column in possible_columns:

        if column in df.columns:

            company_column = column

            break


    if company_column is None:

        raise ValueError(
            """
Could not find the company name column.

Your CSV must contain:

Company Name

Example:

Company Name
Indian Hotels Company
3M India Limited
ABB India Limited
ACC Limited
"""
        )


    # --------------------------------------------------------
    # Create NEW dataframe
    #
    # This ensures output has exactly two columns.
    # --------------------------------------------------------

    result = pd.DataFrame()

    result["Company Name"] = (
        df[company_column]
        .astype(str)
        .str.strip()
    )

    result["Alternative pdf url"] = ""


    # --------------------------------------------------------
    # Remove completely empty company rows
    # --------------------------------------------------------

    result = result[
        result["Company Name"].str.strip() != ""
    ].reset_index(drop=True)


    print()
    print(
        f"Total companies found: {len(result)}"
    )


    return result


# ============================================================
# LOAD EXISTING OUTPUT FOR RESUME
# ============================================================

def load_existing_output():

    if not os.path.exists(
        OUTPUT_XLSX
    ):

        return None


    print()
    print(
        "Existing output file found."
    )

    print(
        "Loading previous progress..."
    )


    try:

        old_df = pd.read_excel(
            OUTPUT_XLSX,
            dtype=str
        ).fillna("")


        if (
            "Company Name" not in old_df.columns
            or
            "Alternative pdf url" not in old_df.columns
        ):

            return None


        return old_df[
            [
                "Company Name",
                "Alternative pdf url"
            ]
        ].copy()


    except Exception as e:

        print(
            f"Could not load previous output: {e}"
        )

        return None


# ============================================================
# MERGE PREVIOUS PROGRESS
# ============================================================

def merge_previous_progress(
    current_df,
    old_df
):

    if old_df is None:

        return current_df


    previous_results = {}


    for _, row in old_df.iterrows():

        company = str(
            row["Company Name"]
        ).strip()


        value = str(
            row["Alternative pdf url"]
        ).strip()


        if not company:
            continue


        key = normalize_company_name(
            company
        )


        previous_results[key] = value


    # --------------------------------------------------------
    # Put old results into current dataframe
    # --------------------------------------------------------

    for index in range(
        len(current_df)
    ):

        company = str(
            current_df.at[
                index,
                "Company Name"
            ]
        ).strip()


        key = normalize_company_name(
            company
        )


        if key in previous_results:

            current_df.at[
                index,
                "Alternative pdf url"
            ] = previous_results[key]


    return current_df


# ============================================================
# CHECK EXISTING VALID RESULT
# ============================================================

def has_valid_existing_result(value):

    if pd.isna(value):

        return False


    value = str(
        value
    ).strip()


    if not value:

        return False


    if value.lower() in [
        "nan",
        "none",
        "null"
    ]:

        return False


    # --------------------------------------------------------
    # "Not for this year" is a valid completed result.
    # --------------------------------------------------------

    if value.lower() == "not for this year":

        return True


    # --------------------------------------------------------
    # Any actual URL is completed.
    # --------------------------------------------------------

    if value.startswith(
        "http"
    ):

        return True


    return False


# ============================================================
# DOWNLOAD NSE EQUITY LIST
# ============================================================

def download_nse_equity_list(
    context
):

    print()
    print("=" * 70)
    print("DOWNLOADING OFFICIAL NSE COMPANY LIST")
    print("=" * 70)


    try:

        response = context.request.get(
            NSE_EQUITY_CSV,
            timeout=60000,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/153.0.0.0 "
                    "Safari/537.36"
                ),

                "Accept": (
                    "text/csv,"
                    "application/csv,"
                    "text/plain,"
                    "*/*"
                ),

                "Referer": NSE_HOME
            }
        )


        print(
            f"NSE response status: "
            f"{response.status}"
        )


        if not response.ok:

            print(
                "Could not download NSE company list."
            )

            return None


        text = response.body().decode(
            "utf-8",
            errors="replace"
        )


        nse_df = pd.read_csv(
            StringIO(text)
        )


        print(
            f"NSE records downloaded: "
            f"{len(nse_df)}"
        )


        print()
        print(
            "NSE columns:"
        )

        print(
            list(nse_df.columns)
        )


        return nse_df


    except Exception as e:

        print()
        print(
            f"Error downloading NSE list:"
        )

        print(
            e
        )

        return None


# ============================================================
# FIND NSE COLUMNS
# ============================================================

def find_nse_columns(
    nse_df
):

    symbol_column = None
    company_column = None


    # --------------------------------------------------------
    # SYMBOL
    # --------------------------------------------------------

    for column in nse_df.columns:

        normalized = (
            str(column)
            .strip()
            .upper()
        )


        if normalized == "SYMBOL":

            symbol_column = column

            break


    # --------------------------------------------------------
    # COMPANY NAME
    # --------------------------------------------------------

    possible_company_columns = [
        "NAME OF COMPANY",
        "COMPANY NAME",
        "NAME_OF_COMPANY"
    ]


    for column in nse_df.columns:

        normalized = (
            str(column)
            .strip()
            .upper()
        )


        if normalized in possible_company_columns:

            company_column = column

            break


    return (
        symbol_column,
        company_column
    )


# ============================================================
# BUILD NSE SYMBOL LOOKUP
# ============================================================

def build_symbol_lookup(
    nse_df
):

    symbol_column, company_column = (
        find_nse_columns(
            nse_df
        )
    )


    if symbol_column is None:

        raise ValueError(
            "SYMBOL column not found in NSE list."
        )


    if company_column is None:

        raise ValueError(
            "Company name column not found in NSE list."
        )


    print()
    print(
        f"NSE Symbol column:"
    )

    print(
        symbol_column
    )


    print(
        f"NSE Company column:"
    )

    print(
        company_column
    )


    lookup = {}


    for _, row in nse_df.iterrows():

        symbol = str(
            row[symbol_column]
        ).strip().upper()


        company = str(
            row[company_column]
        ).strip()


        if not symbol:
            continue


        if not company:
            continue


        normalized = normalize_company_name(
            company
        )


        if normalized:

            lookup[normalized] = symbol


    print()
    print(
        f"Company-symbol mappings:"
        f" {len(lookup)}"
    )


    return lookup


# ============================================================
# FIND NSE SYMBOL
# ============================================================

def find_nse_symbol(
    company_name,
    symbol_lookup,
    nse_df
):

    target = normalize_company_name(
        company_name
    )


    if not target:

        return None


    # --------------------------------------------------------
    # 1. Exact match
    # --------------------------------------------------------

    if target in symbol_lookup:

        return symbol_lookup[target]


    # --------------------------------------------------------
    # 2. Token matching
    # --------------------------------------------------------

    symbol_column, company_column = (
        find_nse_columns(
            nse_df
        )
    )


    if (
        symbol_column is None
        or
        company_column is None
    ):

        return None


    target_tokens = set(
        target.split()
    )


    best_symbol = None
    best_score = 0


    for _, row in nse_df.iterrows():

        candidate = str(
            row[company_column]
        ).strip()


        if not candidate:

            continue


        candidate_normalized = (
            normalize_company_name(
                candidate
            )
        )


        candidate_tokens = set(
            candidate_normalized.split()
        )


        if not candidate_tokens:

            continue


        # ----------------------------------------------------
        # Token similarity
        # ----------------------------------------------------

        intersection = (
            target_tokens
            &
            candidate_tokens
        )


        union = (
            target_tokens
            |
            candidate_tokens
        )


        if not union:

            continue


        score = (
            len(intersection)
            /
            len(union)
        )


        # ----------------------------------------------------
        # Containment bonus
        # ----------------------------------------------------

        if (
            target in candidate_normalized
            or
            candidate_normalized in target
        ):

            score += 0.30


        if score > best_score:

            best_score = score

            best_symbol = str(
                row[symbol_column]
            ).strip().upper()


    # --------------------------------------------------------
    # Accept strong matches only
    # --------------------------------------------------------

    if best_score >= 0.60:

        return best_symbol


    return None


# ============================================================
# OPEN NSE ANNUAL REPORT PAGE
# ============================================================

def open_annual_report_page(
    page,
    symbol
):

    url = (
        NSE_ANNUAL_REPORT_URL
        +
        "?symbol="
        +
        quote(symbol)
        +
        "&tabIndex=equity"
    )


    print()
    print(
        f"Opening NSE page for symbol: "
        f"{symbol}"
    )


    print(
        url
    )


    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=TIMEOUT
    )


    # Give NSE JavaScript time to load
    page.wait_for_timeout(
        4000
    )


    return url


# ============================================================
# CHECK 2025-26 ROW
# ============================================================

def is_target_year_row(
    text
):

    if not text:

        return False


    text = str(
        text
    )


    # Normalize dash characters
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )


    # --------------------------------------------------------
    # Must contain BOTH 2025 and 2026
    # --------------------------------------------------------

    has_2025 = bool(
        re.search(
            r"\b2025\b",
            text
        )
    )


    has_2026 = bool(
        re.search(
            r"\b2026\b",
            text
        )
    )


    return (
        has_2025
        and
        has_2026
    )


# ============================================================
# CLEAN URL
# ============================================================

def clean_url(
    url
):

    if not url:

        return ""


    url = str(
        url
    ).strip()


    url = url.replace(
        "&amp;",
        "&"
    )


    # Remove surrounding characters
    url = url.strip(
        "\"'()[]{}"
    )


    return url


# ============================================================
# EXTRACT PDF URL FROM ELEMENT
# ============================================================

def extract_pdf_url_from_element(
    element,
    page
):

    # --------------------------------------------------------
    # HREF
    # --------------------------------------------------------

    try:

        href = element.get_attribute(
            "href"
        )


        if href:

            href = clean_url(
                href
            )


            if (
                ".pdf" in href.lower()
                or
                "nsearchives.nseindia.com"
                in href.lower()
            ):

                if href.startswith(
                    "http"
                ):

                    return href


                if href.startswith(
                    "/"
                ):

                    return (
                        "https://www.nseindia.com"
                        +
                        href
                    )

    except Exception:

        pass


    # --------------------------------------------------------
    # ONCLICK
    # --------------------------------------------------------

    try:

        onclick = (
            element.get_attribute(
                "onclick"
            )
            or
            ""
        )


        if onclick:

            # Absolute URL
            matches = re.findall(
                r"""https?://[^"'()\s]+""",
                onclick,
                re.IGNORECASE
            )


            for url in matches:

                url = clean_url(
                    url
                )


                if (
                    ".pdf" in url.lower()
                    or
                    "nsearchives.nseindia.com"
                    in url.lower()
                ):

                    return url


            # Relative PDF
            matches = re.findall(
                r"""['"]([^'"]+\.pdf[^'"]*)['"]""",
                onclick,
                re.IGNORECASE
            )


            for value in matches:

                return (
                    "https://nsearchives.nseindia.com/"
                    +
                    value.lstrip("/")
                )

    except Exception:

        pass


    # --------------------------------------------------------
    # DATA ATTRIBUTES
    # --------------------------------------------------------

    attributes = [
        "data-url",
        "data-href",
        "data-link",
        "data-pdf",
        "data-pdf-url",
        "data-download"
    ]


    for attribute in attributes:

        try:

            value = element.get_attribute(
                attribute
            )


            if not value:

                continue


            value = clean_url(
                value
            )


            if (
                ".pdf" not in value.lower()
                and
                "nsearchives.nseindia.com"
                not in value.lower()
            ):

                continue


            if value.startswith(
                "http"
            ):

                return value


            if value.startswith(
                "/"
            ):

                return (
                    "https://www.nseindia.com"
                    +
                    value
                )


            return (
                "https://nsearchives.nseindia.com/"
                +
                value.lstrip("/")
            )

        except Exception:

            continue


    return None


# ============================================================
# EXTRACT URL FROM ROW
# ============================================================

def extract_url_from_row(
    row,
    page
):

    # --------------------------------------------------------
    # 1. Search all links
    # --------------------------------------------------------

    try:

        links = row.locator(
            "a"
        )


        count = links.count()


        for i in range(
            count
        ):

            link = links.nth(i)


            url = extract_pdf_url_from_element(
                link,
                page
            )


            if url:

                return url

    except Exception:

        pass


    # --------------------------------------------------------
    # 2. Search buttons
    # --------------------------------------------------------

    try:

        buttons = row.locator(
            "button"
        )


        count = buttons.count()


        for i in range(
            count
        ):

            button = buttons.nth(i)


            url = extract_pdf_url_from_element(
                button,
                page
            )


            if url:

                return url

    except Exception:

        pass


    # --------------------------------------------------------
    # 3. Search every element
    # --------------------------------------------------------

    try:

        elements = row.locator(
            "*"
        )


        count = elements.count()


        for i in range(
            min(count, 300)
        ):

            element = elements.nth(i)


            url = extract_pdf_url_from_element(
                element,
                page
            )


            if url:

                return url

    except Exception:

        pass


    # --------------------------------------------------------
    # 4. Search entire HTML
    # --------------------------------------------------------

    try:

        html = row.evaluate(
            "(el) => el.outerHTML"
        )


        # Absolute PDF
        matches = re.findall(
            r"""https?://[^"'<> ]+\.pdf[^"'<> ]*""",
            html,
            re.IGNORECASE
        )


        for url in matches:

            return clean_url(
                url
            )


        # Relative PDF
        matches = re.findall(
            r"""['"]([^'"]+\.pdf[^'"]*)['"]""",
            html,
            re.IGNORECASE
        )


        for value in matches:

            return (
                "https://nsearchives.nseindia.com/"
                +
                value.lstrip("/")
            )

    except Exception:

        pass


    return ""


# ============================================================
# FIND 2025-26 REPORT
# ============================================================

def find_2025_2026_report(
    page
):

    print()
    print(
        f"Looking ONLY for "
        f"{TARGET_FROM_YEAR}-{TARGET_TO_YEAR}"
    )


    # --------------------------------------------------------
    # Wait for dynamic table
    # --------------------------------------------------------

    page.wait_for_timeout(
        3000
    )


    # --------------------------------------------------------
    # Get table rows
    # --------------------------------------------------------

    rows = page.locator(
        "table tbody tr"
    )


    try:

        row_count = rows.count()

    except Exception:

        row_count = 0


    print()
    print(
        f"NSE table rows found: "
        f"{row_count}"
    )


    target_row = None


    # ========================================================
    # SEARCH ROWS
    # ========================================================

    for i in range(
        row_count
    ):

        row = rows.nth(i)


        try:

            if not row.is_visible():

                continue


            text = row.inner_text().strip()


            if not text:

                continue


            normalized_text = (
                " ".join(
                    text.split()
                )
            )


            # ------------------------------------------------
            # STRICT YEAR CHECK
            # ------------------------------------------------

            if not is_target_year_row(
                normalized_text
            ):

                continue


            print()
            print(
                "Candidate 2025-26 row:"
            )


            print(
                normalized_text[:500]
            )


            target_row = row

            break


        except Exception:

            continue


    # ========================================================
    # NO REPORT
    # ========================================================

    if target_row is None:

        print()
        print(
            "No 2025-26 annual report found."
        )

        return None


    # ========================================================
    # EXTRACT PDF
    # ========================================================

    pdf_url = extract_url_from_row(
        target_row,
        page
    )


    if pdf_url:

        print()
        print(
            "=" * 60
        )

        print(
            "2025-26 REPORT FOUND"
        )

        print(
            pdf_url
        )

        print(
            "=" * 60
        )


        return pdf_url


    # --------------------------------------------------------
    # 2025-26 row exists but URL wasn't extracted
    # --------------------------------------------------------

    print()
    print(
        "2025-26 row was found,"
    )

    print(
        "but PDF URL could not be extracted."
    )


    try:

        html = target_row.evaluate(
            "(el) => el.outerHTML"
        )


        print()
        print(
            "ROW HTML:"
        )

        print(
            html[:5000]
        )

    except Exception:

        pass


    # IMPORTANT:
    # Do NOT call this "Not for this year".
    #
    # The report exists, but URL extraction failed.
    #
    # Return empty so it can be retried.
    #

    return ""


# ============================================================
# PROCESS ONE COMPANY
# ============================================================

def process_company(
    page,
    company_name,
    symbol
):

    print()
    print("=" * 75)

    print(
        f"COMPANY: {company_name}"
    )

    print(
        f"NSE SYMBOL: {symbol}"
    )

    print("=" * 75)


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print()
        print(
            f"Attempt {attempt}/"
            f"{MAX_RETRIES}"
        )


        try:

            # ------------------------------------------------
            # Open direct annual report page
            # ------------------------------------------------

            open_annual_report_page(
                page,
                symbol
            )


            # ------------------------------------------------
            # Find report
            # ------------------------------------------------

            result = find_2025_2026_report(
                page
            )


            # ------------------------------------------------
            # PDF found
            # ------------------------------------------------

            if result:

                return result


            # ------------------------------------------------
            # Empty string means:
            #
            # Page loaded but PDF URL extraction failed.
            #
            # Retry.
            # ------------------------------------------------

            if result == "":

                print()
                print(
                    "PDF extraction failed."
                )


                if attempt < MAX_RETRIES:

                    print(
                        "Retrying..."
                    )

                    time.sleep(3)

                    continue


                # Do NOT falsely say "Not for this year"
                return ""


            # ------------------------------------------------
            # No report
            # ------------------------------------------------

            return "Not for this year"


        except Exception as e:

            print()
            print(
                "NSE error:"
            )

            print(
                e
            )


            if attempt < MAX_RETRIES:

                print(
                    "Retrying..."
                )

                time.sleep(3)

            else:

                print(
                    "All retries failed."
                )


    return ""


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_files(
    df
):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    # --------------------------------------------------------
    # IMPORTANT:
    # Force exactly two columns.
    # --------------------------------------------------------

    final_df = df[
        [
            "Company Name",
            "Alternative pdf url"
        ]
    ].copy()


    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    final_df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )


    # --------------------------------------------------------
    # Save Excel
    # --------------------------------------------------------

    final_df.to_excel(
        OUTPUT_XLSX,
        index=False,
        sheet_name="NSE Annual Reports"
    )


    print()
    print(
        "Progress saved:"
    )

    print(
        f"Excel: {OUTPUT_XLSX}"
    )

    print(
        f"CSV  : {OUTPUT_CSV}"
    )


# ============================================================
# SHOW PROGRESS
# ============================================================

def show_progress(
    df
):

    total = len(df)

    completed = 0
    remaining = 0


    for value in df[
        "Alternative pdf url"
    ]:

        if has_valid_existing_result(
            value
        ):

            completed += 1

        else:

            remaining += 1


    print()
    print("-" * 70)

    print(
        f"TOTAL     : {total}"
    )

    print(
        f"COMPLETED : {completed}"
    )

    print(
        f"REMAINING : {remaining}"
    )

    print("-" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 75)

    print(
        "NSE 2025-26 ANNUAL REPORT URL COLLECTOR"
    )

    print("=" * 75)


    # ========================================================
    # LOAD INPUT
    # ========================================================

    df = load_input_file()


    print()

    show_progress(
        df
    )


    # ========================================================
    # LOAD PREVIOUS OUTPUT
    # ========================================================

    old_df = load_existing_output()


    if old_df is not None:

        df = merge_previous_progress(
            df,
            old_df
        )


        print()
        print(
            "Previous progress loaded."
        )


        show_progress(
            df
        )


    # ========================================================
    # PROCESSING RANGE
    # ========================================================

    start_index = max(
        0,
        START_ROW - 1
    )


    if END_ROW is None:

        end_index = len(df)

    else:

        end_index = min(
            END_ROW,
            len(df)
        )


    print()
    print(
        f"Processing rows "
        f"{start_index + 1} "
        f"to "
        f"{end_index}"
    )


    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    with sync_playwright() as p:

        print()
        print(
            "Starting Chromium..."
        )


        browser = p.chromium.launch(
            headless=HEADLESS
        )


        context = browser.new_context(

            accept_downloads=False,

            viewport={
                "width": 1440,
                "height": 1000
            },

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),

            locale="en-IN"
        )


        page = context.new_page()


        page.set_default_timeout(
            TIMEOUT
        )


        # ====================================================
        # OPEN NSE
        # ====================================================

        print()
        print(
            "Opening NSE..."
        )


        try:

            page.goto(
                NSE_HOME,
                wait_until="domcontentloaded",
                timeout=TIMEOUT
            )


            page.wait_for_timeout(
                3000
            )


        except Exception as e:

            print()
            print(
                "Could not open NSE."
            )

            print(
                e
            )


            browser.close()

            return


        # ====================================================
        # DOWNLOAD NSE COMPANY MASTER
        # ====================================================

        nse_df = download_nse_equity_list(
            context
        )


        if nse_df is None:

            print()
            print(
                "Could not get NSE company list."
            )


            browser.close()

            return


        # ====================================================
        # BUILD SYMBOL LOOKUP
        # ====================================================

        try:

            symbol_lookup = build_symbol_lookup(
                nse_df
            )

        except Exception as e:

            print()
            print(
                "Could not build NSE symbol lookup:"
            )

            print(
                e
            )


            browser.close()

            return


        # ====================================================
        # PROCESS EACH COMPANY
        # ====================================================

        for index in range(
            start_index,
            end_index
        ):

            company_name = str(
                df.at[
                    index,
                    "Company Name"
                ]
            ).strip()


            # ------------------------------------------------
            # Empty company
            # ------------------------------------------------

            if not company_name:

                continue


            # ------------------------------------------------
            # Existing result
            # ------------------------------------------------

            existing_value = str(
                df.at[
                    index,
                    "Alternative pdf url"
                ]
            ).strip()


            # ------------------------------------------------
            # Skip completed
            # ------------------------------------------------

            if has_valid_existing_result(
                existing_value
            ):

                print()
                print(
                    "-" * 75
                )


                print(
                    f"[{index + 1}/{len(df)}] "
                    f"{company_name}"
                )


                print(
                    "Already completed:"
                )


                print(
                    existing_value
                )


                print(
                    "Skipping."
                )


                continue


            # =================================================
            # COMPANY
            # =================================================

            print()
            print(
                "#" * 75
            )


            print(
                f"[{index + 1}/{len(df)}]"
            )


            print(
                company_name
            )


            print(
                "#" * 75
            )


            # =================================================
            # FIND NSE SYMBOL
            # =================================================

            symbol = find_nse_symbol(
                company_name,
                symbol_lookup,
                nse_df
            )


            if not symbol:

                print()
                print(
                    "NSE symbol could not be matched."
                )


                # ------------------------------------------------
                # Important:
                # We leave blank instead of falsely saying
                # "Not for this year".
                #
                # This allows the next run to retry.
                # ------------------------------------------------

                df.at[
                    index,
                    "Alternative pdf url"
                ] = ""


                save_files(
                    df
                )


                continue


            print()
            print(
                f"Matched NSE symbol: "
                f"{symbol}"
            )


            # =================================================
            # FIND 2025-26 REPORT
            # =================================================

            result = process_company(
                page,
                company_name,
                symbol
            )


            # =================================================
            # SAVE RESULT
            # =================================================

            df.at[
                index,
                "Alternative pdf url"
            ] = result


            # ------------------------------------------------
            # Save immediately
            # ------------------------------------------------

            save_files(
                df
            )


            print()
            print(
                "RESULT:"
            )


            if result:

                print(
                    result
                )

            else:

                print(
                    "Blank - will retry on next run."
                )


            # ------------------------------------------------
            # Delay
            # ------------------------------------------------

            time.sleep(
                WAIT_AFTER_COMPANY
            )


        # ====================================================
        # CLOSE BROWSER
        # ====================================================

        browser.close()


    # ========================================================
    # FINAL SAVE
    # ========================================================

    save_files(
        df
    )


    # ========================================================
    # FINAL STATUS
    # ========================================================

    print()
    print("=" * 75)

    print(
        "PROCESS COMPLETED"
    )

    print("=" * 75)


    show_progress(
        df
    )


    print()
    print(
        "FINAL OUTPUT:"
    )


    print(
        OUTPUT_XLSX
    )


    print(
        OUTPUT_CSV
    )


    print()
    print(
        "Output columns:"
    )

    print(
        "1. Company Name"
    )

    print(
        "2. Alternative pdf url"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
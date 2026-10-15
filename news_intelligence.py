import os
import re
import json
import time
import hashlib
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests
import pandas as pd

from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side

from dotenv import load_dotenv


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

if not SERPER_API_KEY:
    raise ValueError(
        "\nSERPER_API_KEY is missing.\n"
        "Add it to your .env file:\n\n"
        "SERPER_API_KEY=your_serper_api_key\n"
    )


# ============================================================
# FILE CONFIGURATION
# ============================================================

INPUT_FILE = "companies_list_tech.csv"

OUTPUT_DIR = "output"

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "news_analysis.xlsx"
)

PROGRESS_FILE = os.path.join(
    OUTPUT_DIR,
    "news_progress.json"
)


# ============================================================
# COMPANY RANGE
# ============================================================

# TEST FIRST:
#
# START_COMPANY = 1
# END_COMPANY = 1
#
# THEN:
#
# START_COMPANY = 1
# END_COMPANY = 439

START_COMPANY = 181
END_COMPANY = 300

RESUME = True


RESULTS_PER_SEARCH = 10

MAX_CANDIDATES_PER_COMPANY = 30

MAX_EVENTS_PER_COMPANY = 12

REQUEST_TIMEOUT = 20

REQUEST_DELAY_SECONDS = 1.0

MAX_RETRIES = 3

SEARCH_QUERY_TEMPLATES = [

    # General current news
    '"{company}" latest news',

    # Positive / business developments
    '"{company}" order OR contract OR expansion OR acquisition OR partnership OR investment OR launch OR approval OR growth',

    # Negative / risk developments
    '"{company}" lawsuit OR investigation OR penalty OR fine OR fraud OR cyberattack OR "data breach" OR recall OR controversy OR disruption OR default OR violation',
]


OUTPUT_COLUMNS = [
    "Company",
    "Date",
    "Headline",
    "Summary",
    "Sentiment",
    "Source",
    "Reason",
]


POSITIVE_TERMS = {

    "growth",
    "grew",
    "increase",
    "increased",
    "rise",
    "rose",
    "profit",
    "profits",
    "revenue growth",

    "order",
    "orders",
    "contract",
    "contracts",
    "secured",
    "wins",
    "won",
    "award",
    "awarded",

    "expansion",
    "capacity expansion",
    "new facility",
    "new plant",

    "investment",
    "invest",
    "invests",
    "invested",

    "acquisition",
    "acquires",
    "acquired",

    "partnership",
    "collaboration",
    "strategic alliance",

    "launch",
    "launched",

    "approval",
    "approved",

    "funding",
    "funded",

    "recovery",
    "recovered",

    "new project",
    "new business",
    "business expansion",

    "record revenue",
    "record profit",

    "production increase",
    "capacity increase",
}


# ============================================================
# NEGATIVE TERMS
# ============================================================

NEGATIVE_TERMS = {

    "lawsuit",
    "lawsuits",

    "investigation",
    "investigated",
    "investigating",

    "probe",
    "probed",

    "penalty",
    "penalties",

    "fine",
    "fined",

    "fraud",
    "fraudulent",

    "cyberattack",
    "cyber attack",
    "cybersecurity incident",

    "data breach",
    "data breach",
    "data leak",

    "hacked",
    "hack",

    "recall",
    "recalled",

    "warning",
    "warned",

    "default",
    "defaulted",

    "violation",
    "violations",

    "controversy",
    "controversial",

    "suspended",
    "suspension",

    "shutdown",
    "shut down",

    "disruption",
    "disrupted",

    "decline",
    "declined",

    "loss",
    "losses",

    "fall",
    "fell",
    "fallen",

    "drop",
    "dropped",

    "decrease",
    "decreased",

    "regulatory action",
    "regulatory notice",

    "show cause notice",

    "adverse",

    "rejected",
    "rejection",

    "denied",
    "denial",

    "delay",
    "delayed",

    "resignation",
    "resigned",

    "breach",

    "risk",
    "risks",
}


# ============================================================
# STRONG NEGATIVE TERMS
# ============================================================

STRONG_NEGATIVE_TERMS = {

    "fraud",
    "cyberattack",
    "cyber attack",
    "data breach",
    "data leak",
    "investigation",
    "probe",
    "lawsuit",
    "penalty",
    "fine",
    "default",
    "recall",
    "suspended",
    "suspension",
    "shutdown",
    "regulatory action",
    "show cause notice",
}


# ============================================================
# STRONG NEWS SOURCES
# ============================================================

SOURCE_PRIORITY = {

    "Reuters": 10,

    "SEBI": 10,

    "NSE": 10,

    "BSE": 10,

    "RBI": 10,

    "Government": 10,

    "Company Official": 10,

    "Economic Times": 9,

    "Business Standard": 9,

    "Mint": 9,

    "Financial Express": 8,

    "CNBC-TV18": 8,

    "The Hindu BusinessLine": 8,

    "The Hindu": 8,

    "Indian Express": 8,

    "NDTV Profit": 8,

    "Times of India": 7,

    "Moneycontrol": 7,

    "Other": 3,
}


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_url(url):

    if not url:
        return ""

    url = str(url).strip()

    # Remove tracking parameters
    url = url.split("?")[0]

    url = url.split("#")[0]

    return url.rstrip("/").lower()


def normalize_for_search(text):

    text = clean_text(text).lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# JUNK RESULT FILTER
# ============================================================

def is_junk_result(title, url):

    title = clean_text(title).lower()

    url = normalize_url(url)


    # --------------------------------------------------------
    # Stock / quote / profile pages
    # --------------------------------------------------------

    junk_title_terms = [

        "share price",

        "stock price",

        "live share price",

        "get quote",

        "52 week high",

        "52-week high",

        "52 week low",

        "52-week low",

        "shareholding pattern",

        "dividend history",

        "historical share price",

        "technical analysis",

        "stock forecast",

        "share forecast",

        "price target",

        "target price",

        "stock recommendation",

        "company profile",

        "stock analysis",

        "fundamental analysis",

        "peer comparison",

        "financial ratios",

        "investor relations",

        "investor presentation",

        "earnings presentation",
    ]


    for term in junk_title_terms:

        if term in title:

            return True


    # --------------------------------------------------------
    # Junk domains
    # --------------------------------------------------------

    junk_domains = [

        "screener.in",

        "trendlyne.com",

        "marketsmojo.com",

        "goodreturns.in",

        "ticker.finology.in",

        "moneycontrol.com/india/stockpricequote",
    ]


    for domain in junk_domains:

        if domain in url:

            return True


    # --------------------------------------------------------
    # Wikipedia
    # --------------------------------------------------------

    if "wikipedia.org" in url:

        return True


    # --------------------------------------------------------
    # Generic corporate documents
    # --------------------------------------------------------

    document_terms = [

        "annual report",

        "annual-report",

        "sustainability report",

        "integrated report",

        "investor presentation",

        "investor relations",

        "shareholding",

        "financial results",

        "results presentation",

        "notice to shareholders",

        "credit rating",

        "rating rationale",

        "care ratings",

        "icra ratings",

        "crisil ratings",

        "parts catalogue",

        "parts catalog",

        "apprentice",

        "tender document",

        "privacy policy",

        "terms of use",

        "cookie policy",
    ]


    for term in document_terms:

        if term in title:

            return True


    # --------------------------------------------------------
    # PDF filtering
    # --------------------------------------------------------
    #
    # We don't reject every PDF.
    # Regulatory PDFs can contain important events.
    #
    # --------------------------------------------------------

    if url.endswith(".pdf"):

        pdf_terms = [

            "annual",

            "investor",

            "presentation",

            "policy",

            "brochure",

            "catalogue",

            "catalog",

            "apprentice",

            "tender",

            "rating",

            "financial",
        ]


        for term in pdf_terms:

            if term in title:

                return True


    return False


# ============================================================
# COMPANY RELEVANCE
# ============================================================

def is_company_relevant(
    company,
    title,
    snippet
):

    company_clean = normalize_for_search(
        company
    )

    title_clean = normalize_for_search(
        title
    )

    snippet_clean = normalize_for_search(
        snippet
    )


    text = (
        title_clean
        + " "
        + snippet_clean
    )


    # --------------------------------------------------------
    # Exact company name
    # --------------------------------------------------------

    if company_clean in text:

        return True


    # --------------------------------------------------------
    # Individual company words
    # --------------------------------------------------------

    company_words = [

        word
        for word
        in company_clean.split()
        if len(word) >= 3
    ]


    if not company_words:

        return False


    matches = sum(

        1

        for word
        in company_words

        if word in text
    )


    # For multi-word companies require at least two words.
    if len(company_words) >= 2:

        return matches >= 2


    return matches >= 1


# ============================================================
# NEWS SCORE
# ============================================================

def calculate_news_score(
    company,
    title,
    snippet,
    url
):

    title_clean = clean_text(
        title
    )

    snippet_clean = clean_text(
        snippet
    )


    title_lower = title_clean.lower()

    snippet_lower = snippet_clean.lower()


    text = (
        title_lower
        + " "
        + snippet_lower
    )


    score = 0


    # --------------------------------------------------------
    # Exact company name
    # --------------------------------------------------------

    if company.lower() in text:

        score += 30


    # --------------------------------------------------------
    # Positive event terms
    # --------------------------------------------------------

    for term in POSITIVE_TERMS:

        if term in title_lower:

            score += 10

        elif term in snippet_lower:

            score += 4


    # --------------------------------------------------------
    # Negative event terms
    # --------------------------------------------------------

    for term in NEGATIVE_TERMS:

        if term in title_lower:

            score += 18

        elif term in snippet_lower:

            score += 7


    # --------------------------------------------------------
    # Strong negative terms
    # --------------------------------------------------------

    for term in STRONG_NEGATIVE_TERMS:

        if term in title_lower:

            score += 15


    # --------------------------------------------------------
    # Reputable news sources
    # --------------------------------------------------------

    source = detect_source(
        url,
        title
    )


    score += SOURCE_PRIORITY.get(
        source,
        3
    )


    return score


# ============================================================
# SOURCE DETECTION
# ============================================================

def detect_source(
    url,
    title=""
):

    url_lower = normalize_url(
        url
    )


    sources = [

        (
            "Reuters",
            [
                "reuters.com"
            ]
        ),

        (
            "Economic Times",
            [
                "economictimes.indiatimes.com",
                "economictimes.com"
            ]
        ),

        (
            "Business Standard",
            [
                "business-standard.com"
            ]
        ),

        (
            "Mint",
            [
                "livemint.com"
            ]
        ),

        (
            "Financial Express",
            [
                "financialexpress.com"
            ]
        ),

        (
            "CNBC-TV18",
            [
                "cnbctv18.com"
            ]
        ),

        (
            "The Hindu BusinessLine",
            [
                "thehindubusinessline.com"
            ]
        ),

        (
            "The Hindu",
            [
                "thehindu.com"
            ]
        ),

        (
            "Indian Express",
            [
                "indianexpress.com"
            ]
        ),

        (
            "NDTV Profit",
            [
                "ndtvprofit.com"
            ]
        ),

        (
            "Times of India",
            [
                "timesofindia.indiatimes.com"
            ]
        ),

        (
            "Moneycontrol",
            [
                "moneycontrol.com"
            ]
        ),

        (
            "SEBI",
            [
                "sebi.gov.in"
            ]
        ),

        (
            "NSE",
            [
                "nseindia.com"
            ]
        ),

        (
            "BSE",
            [
                "bseindia.com"
            ]
        ),

        (
            "RBI",
            [
                "rbi.org.in"
            ]
        ),

        (
            "Government",
            [
                "gov.in",
                "nic.in"
            ]
        ),
    ]


    for source, domains in sources:

        for domain in domains:

            if domain in url_lower:

                return source


    # --------------------------------------------------------
    # Detect likely company website
    # --------------------------------------------------------

    try:

        hostname = urlparse(
            url_lower
        ).netloc

        hostname = hostname.replace(
            "www.",
            ""
        )


        company_words = re.findall(
            r"[a-z0-9]+",
            title.lower()
        )


        # Do NOT call something "Company Official"
        # merely because it contains words such as
        # company/corporate/investor.
        #
        # That caused wrong source labels previously.

        if hostname.endswith(
            ".com"
        ):

            return hostname


    except Exception:

        pass


    return "Other"


# ============================================================
# DATE PARSING
# ============================================================

def parse_date_string(
    value
):

    if not value:

        return ""


    value = clean_text(
        value
    )


    # Remove common relative terms
    if value.lower() in [
        "today",
        "yesterday",
        "just now",
        "hours ago",
        "minutes ago",
    ]:

        return ""


    formats = [

        "%Y-%m-%d",

        "%Y-%m-%dT%H:%M:%S",

        "%Y-%m-%dT%H:%M:%SZ",

        "%d-%m-%Y",

        "%d/%m/%Y",

        "%Y/%m/%d",

        "%d %B %Y",

        "%d %b %Y",

        "%B %d, %Y",

        "%b %d, %Y",

        "%d %B, %Y",

        "%d %b, %Y",
    ]


    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt
            )

            return dt.strftime(
                "%Y-%m-%d"
            )

        except ValueError:

            continue


    # --------------------------------------------------------
    # Search date inside text
    # --------------------------------------------------------

    patterns = [

        r"\b\d{4}-\d{1,2}-\d{1,2}\b",

        r"\b\d{1,2}/\d{1,2}/\d{4}\b",

        r"\b\d{1,2}-\d{1,2}-\d{4}\b",

        r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b",

        r"\b[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}\b",
    ]


    for pattern in patterns:

        match = re.search(
            pattern,
            value
        )


        if not match:

            continue


        date_text = match.group(0)


        for fmt in formats:

            try:

                dt = datetime.strptime(
                    date_text,
                    fmt
                )

                return dt.strftime(
                    "%Y-%m-%d"
                )

            except ValueError:

                continue


    return ""


# ============================================================
# DATE EXTRACTION FROM SERPER RESULT
# ============================================================

def extract_result_date(
    result
):

    # --------------------------------------------------------
    # Serper / Google fields
    # --------------------------------------------------------

    fields = [

        "date",

        "publishedDate",

        "published_date",

        "publicationDate",

        "timestamp",
    ]


    for field in fields:

        value = result.get(
            field
        )


        if value:

            parsed = parse_date_string(
                value
            )

            if parsed:

                return parsed


    # --------------------------------------------------------
    # Snippet
    # --------------------------------------------------------

    snippet = clean_text(
        result.get(
            "snippet",
            ""
        )
    )


    parsed = parse_date_string(
        snippet
    )


    if parsed:

        return parsed


    return ""


# ============================================================
# SENTIMENT
# ============================================================

def detect_sentiment(
    headline,
    summary
):

    headline = clean_text(
        headline
    )

    summary = clean_text(
        summary
    )


    headline_lower = headline.lower()

    summary_lower = summary.lower()


    positive_score = 0

    negative_score = 0


    # --------------------------------------------------------
    # Positive score
    # --------------------------------------------------------

    for term in POSITIVE_TERMS:

        if term in headline_lower:

            positive_score += 3

        elif term in summary_lower:

            positive_score += 1


    # --------------------------------------------------------
    # Negative score
    # --------------------------------------------------------

    for term in NEGATIVE_TERMS:

        if term in headline_lower:

            negative_score += 4

        elif term in summary_lower:

            negative_score += 2


    # --------------------------------------------------------
    # Strong negative
    # --------------------------------------------------------

    for term in STRONG_NEGATIVE_TERMS:

        if term in headline_lower:

            negative_score += 8


    # --------------------------------------------------------
    # Negative wins ties
    #
    # Important for risk intelligence.
    # --------------------------------------------------------

    if negative_score > positive_score:

        return "Negative"


    if positive_score > negative_score:

        return "Positive"


    # --------------------------------------------------------
    # No clear sentiment
    # --------------------------------------------------------

    return "Skip"


# ============================================================
# REASON
# ============================================================

def generate_reason(
    sentiment,
    headline,
    summary
):

    text = (
        clean_text(headline)
        + " "
        + clean_text(summary)
    ).lower()


    if sentiment == "Negative":

        if (
            "fraud" in text
            or
            "scam" in text
        ):

            return (
                "Fraud or misconduct was reported."
            )


        if (
            "cyberattack" in text
            or
            "cyber attack" in text
            or
            "data breach" in text
            or
            "data leak" in text
            or
            "hacked" in text
        ):

            return (
                "A cybersecurity or data-security "
                "incident was reported."
            )


        if (
            "lawsuit" in text
            or
            "legal case" in text
        ):

            return (
                "A legal case or lawsuit was reported."
            )


        if (
            "investigation" in text
            or
            "probe" in text
            or
            "investigated" in text
        ):

            return (
                "A regulatory or investigative "
                "action was reported."
            )


        if (
            "penalty" in text
            or
            "fine" in text
        ):

            return (
                "A regulatory penalty or fine "
                "was reported."
            )


        if "recall" in text:

            return (
                "A product or operational recall "
                "was reported."
            )


        if (
            "default" in text
        ):

            return (
                "A default or financial-risk "
                "event was reported."
            )


        if (
            "cyber" in text
        ):

            return (
                "A cybersecurity-related incident "
                "was reported."
            )


        if (
            "shutdown" in text
            or
            "shut down" in text
        ):

            return (
                "A shutdown or operational "
                "disruption was reported."
            )


        if "disruption" in text:

            return (
                "A business or operational "
                "disruption was reported."
            )


        if (
            "decline" in text
            or
            "declined" in text
            or
            "fall" in text
            or
            "fell" in text
            or
            "drop" in text
            or
            "dropped" in text
        ):

            return (
                "A decline in business or "
                "financial performance was reported."
            )


        if (
            "violation" in text
            or
            "regulatory action" in text
            or
            "show cause notice" in text
        ):

            return (
                "A regulatory or compliance "
                "issue was reported."
            )


        if "warning" in text:

            return (
                "A warning or adverse development "
                "was reported."
            )


        return (
            "A negative business, legal, "
            "regulatory, or operational "
            "development was reported."
        )


    if sentiment == "Positive":

        if (
            "order" in text
            or
            "contract" in text
            or
            "secured" in text
            or
            "wins" in text
            or
            "won" in text
        ):

            return (
                "A new order or contract win "
                "was reported."
            )


        if (
            "expansion" in text
            or
            "capacity expansion" in text
            or
            "new facility" in text
            or
            "new plant" in text
        ):

            return (
                "Business or production expansion "
                "was reported."
            )


        if (
            "investment" in text
            or
            "invests" in text
            or
            "invested" in text
        ):

            return (
                "A new business or technology "
                "investment was reported."
            )


        if (
            "acquisition" in text
            or
            "acquired" in text
        ):

            return (
                "An acquisition or business "
                "expansion was reported."
            )


        if (
            "partnership" in text
            or
            "collaboration" in text
            or
            "strategic alliance" in text
        ):

            return (
                "A strategic partnership or "
                "collaboration was reported."
            )


        if (
            "launch" in text
            or
            "launched" in text
        ):

            return (
                "A new product, service, or "
                "initiative was launched."
            )


        if (
            "approval" in text
            or
            "approved" in text
        ):

            return (
                "A regulatory or business "
                "approval was reported."
            )


        if (
            "profit" in text
            or
            "revenue growth" in text
            or
            "growth" in text
        ):

            return (
                "Positive business or financial "
                "growth was reported."
            )


        if (
            "award" in text
            or
            "awarded" in text
        ):

            return (
                "A new award or recognition "
                "was reported."
            )


        return (
            "A positive business development "
            "was reported."
        )


    return ""


# ============================================================
# SERPER SEARCH
# ============================================================

def serper_search(
    query
):

    endpoint = (
        "https://google.serper.dev/search"
    )


    headers = {

        "X-API-KEY": SERPER_API_KEY,

        "Content-Type": "application/json",
    }


    payload = {

        "q": query,

        "gl": "in",

        "hl": "en",

        "num": RESULTS_PER_SEARCH,
    }


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            response = requests.post(

                endpoint,

                headers=headers,

                json=payload,

                timeout=REQUEST_TIMEOUT
            )


            if response.status_code == 200:

                return response.json()


            print(
                f"    Serper HTTP "
                f"{response.status_code}"
            )

            print(
                response.text[:300]
            )


        except requests.RequestException as e:

            print(
                f"    Serper request failed: "
                f"{e}"
            )


        if attempt < MAX_RETRIES:

            time.sleep(
                attempt * 2
            )


    return {}


# ============================================================
# COLLECT CANDIDATES
# ============================================================

def collect_candidates(
    company
):

    candidates = []

    seen_urls = set()


    for template in SEARCH_QUERY_TEMPLATES:

        query = template.format(
            company=company
        )


        print(
            f"\n  Search: {query}"
        )


        data = serper_search(
            query
        )


        results = data.get(
            "organic",
            []
        )


        print(
            f"  Google results: "
            f"{len(results)}"
        )


        for result in results:

            title = clean_text(
                result.get(
                    "title",
                    ""
                )
            )


            snippet = clean_text(
                result.get(
                    "snippet",
                    ""
                )
            )


            url = normalize_url(
                result.get(
                    "link",
                    ""
                )
            )


            if not title or not url:

                continue


            # ------------------------------------------------
            # Duplicate URL
            # ------------------------------------------------

            if url in seen_urls:

                continue


            # ------------------------------------------------
            # Junk
            # ------------------------------------------------

            if is_junk_result(
                title,
                url
            ):

                print(
                    f"    SKIP JUNK: "
                    f"{title}"
                )

                continue


            # ------------------------------------------------
            # Company relevance
            # ------------------------------------------------

            if not is_company_relevant(
                company,
                title,
                snippet
            ):

                print(
                    f"    SKIP UNRELATED: "
                    f"{title}"
                )

                continue


            # ------------------------------------------------
            # News score
            # ------------------------------------------------

            score = calculate_news_score(
                company,
                title,
                snippet,
                url
            )


            # ------------------------------------------------
            # Date
            # ------------------------------------------------

            date = extract_result_date(
                result
            )


            # ------------------------------------------------
            # Source
            # ------------------------------------------------

            source = detect_source(
                url,
                title
            )


            candidate = {

                "company": company,

                "title": title,

                "snippet": snippet,

                "url": url,

                "date": date,

                "source": source,

                "score": score,
            }


            candidates.append(
                candidate
            )

            seen_urls.add(
                url
            )


        time.sleep(
            REQUEST_DELAY_SECONDS
        )


    # ========================================================
    # SORT
    # ========================================================

    candidates.sort(

        key=lambda x: (
            x["score"],
            x["date"]
        ),

        reverse=True
    )


    # ========================================================
    # LIMIT
    # ========================================================

    return candidates[
        :MAX_CANDIDATES_PER_COMPANY
    ]


# ============================================================
# EVENT ID
# ============================================================

def make_event_id(
    company,
    headline,
    url
):

    raw = (
        clean_text(company)
        + "|"
        + clean_text(headline)
        + "|"
        + normalize_url(url)
    ).lower()


    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


# ============================================================
# PROGRESS
# ============================================================

def load_progress():

    if not os.path.exists(
        PROGRESS_FILE
    ):

        return {
            "completed": []
        }


    try:

        with open(
            PROGRESS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(
                f
            )


        if not isinstance(
            data,
            dict
        ):

            return {
                "completed": []
            }


        if "completed" not in data:

            data["completed"] = []


        return data


    except Exception:

        return {
            "completed": []
        }


def save_progress(
    progress
):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    temp_file = (
        PROGRESS_FILE
        + ".tmp"
    )


    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            progress,
            f,
            indent=2,
            ensure_ascii=False
        )


    os.replace(
        temp_file,
        PROGRESS_FILE
    )


# ============================================================
# LOAD EXISTING EXCEL
# ============================================================

def load_existing_excel():

    if not os.path.exists(
        OUTPUT_FILE
    ):

        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
            + [
                "_EventID",
                "_URL"
            ]
        )


    try:

        df = pd.read_excel(
            OUTPUT_FILE
        )


    except Exception as e:

        print(
            f"Could not read Excel: {e}"
        )

        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
            + [
                "_EventID",
                "_URL"
            ]
        )


    # --------------------------------------------------------
    # Make sure required columns exist
    # --------------------------------------------------------

    for column in OUTPUT_COLUMNS:

        if column not in df.columns:

            df[column] = ""


    if "_EventID" not in df.columns:

        df["_EventID"] = ""


    if "_URL" not in df.columns:

        df["_URL"] = ""


    return df


# ============================================================
# SAVE EXCEL
# ============================================================

def save_excel(
    df
):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    output_df = df[
        OUTPUT_COLUMNS
    ].copy()


    temp_file = (
        OUTPUT_FILE
        + ".tmp.xlsx"
    )


    try:

        output_df.to_excel(
            temp_file,
            index=False
        )


        format_excel(
            temp_file
        )


        os.replace(
            temp_file,
            OUTPUT_FILE
        )


        return True


    except PermissionError:

        autosave_file = os.path.join(
            OUTPUT_DIR,
            "news_analysis_autosave.xlsx"
        )


        try:

            output_df.to_excel(
                autosave_file,
                index=False
            )


            format_excel(
                autosave_file
            )


            print(
                "\nWARNING:"
            )

            print(
                "news_analysis.xlsx "
                "is open/locked."
            )

            print(
                f"Autosave created: "
                f"{autosave_file}\n"
            )


            return False


        except Exception as e:

            print(
                f"Autosave failed: {e}"
            )

            return False


    except Exception as e:

        print(
            f"Excel save failed: {e}"
        )

        return False


# ============================================================
# EXCEL FORMATTING
# ============================================================

def format_excel(
    filename
):

    wb = load_workbook(
        filename
    )


    ws = wb.active


    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    for cell in ws[1]:

        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True
        )


    # --------------------------------------------------------
    # Borders
    # --------------------------------------------------------

    side = Side(
        style="thin"
    )


    border = Border(
        left=side,
        right=side,
        top=side,
        bottom=side
    )


    for row in ws.iter_rows():

        for cell in row:

            cell.border = border

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True
            )


    # --------------------------------------------------------
    # Widths
    # --------------------------------------------------------

    widths = {

        "A": 32,

        "B": 15,

        "C": 65,

        "D": 90,

        "E": 15,

        "F": 28,

        "G": 65,
    }


    for column, width in widths.items():

        ws.column_dimensions[
            column
        ].width = width


    # --------------------------------------------------------
    # Freeze
    # --------------------------------------------------------

    ws.freeze_panes = "A2"


    # --------------------------------------------------------
    # Filter
    # --------------------------------------------------------

    if ws.max_row >= 1:

        ws.auto_filter.ref = (
            ws.dimensions
        )


    ws.row_dimensions[1].height = 30


    wb.save(
        filename
    )


# ============================================================
# PROCESS COMPANY
# ============================================================

def process_company(
    company,
    df
):

    print("\n")
    print("=" * 75)
    print(
        f"PROCESSING: {company}"
    )
    print("=" * 75)


    # --------------------------------------------------------
    # Search
    # --------------------------------------------------------

    candidates = collect_candidates(
        company
    )


    print(
        f"\nCandidate results after filtering: "
        f"{len(candidates)}"
    )


    if not candidates:

        print(
            "No suitable news candidates found."
        )

        # Important:
        # We still consider the company processed
        # because Serper search itself succeeded.
        return df, True


    # --------------------------------------------------------
    # Existing IDs
    # --------------------------------------------------------

    existing_ids = set(

        str(x)

        for x in df[
            "_EventID"
        ].dropna()

        if str(x).strip()
    )


    # --------------------------------------------------------
    # Existing URLs
    # --------------------------------------------------------

    existing_urls = set(

        normalize_url(x)

        for x in df[
            "_URL"
        ].dropna()

        if str(x).strip()
    )


    new_rows = []

    company_events = 0


    # ========================================================
    # CANDIDATES
    # ========================================================

    for number, candidate in enumerate(
        candidates,
        start=1
    ):

        if company_events >= MAX_EVENTS_PER_COMPANY:

            break


        headline = candidate[
            "title"
        ]

        snippet = candidate[
            "snippet"
        ]

        url = candidate[
            "url"
        ]

        date = candidate[
            "date"
        ]

        source = candidate[
            "source"
        ]


        # ----------------------------------------------------
        # Duplicate URL
        # ----------------------------------------------------

        if url in existing_urls:

            continue


        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        sentiment = detect_sentiment(
            headline,
            snippet
        )


        if sentiment == "Skip":

            print(
                f"\n[{number}] SKIP - unclear sentiment"
            )

            print(
                f"    {headline}"
            )

            continue


        # ----------------------------------------------------
        # Reason
        # ----------------------------------------------------

        reason = generate_reason(
            sentiment,
            headline,
            snippet
        )


        # ----------------------------------------------------
        # Summary
        #
        # Serper Google snippet is used directly.
        # ----------------------------------------------------

        summary = snippet


        # ----------------------------------------------------
        # Event ID
        # ----------------------------------------------------

        event_id = make_event_id(
            company,
            headline,
            url
        )


        if event_id in existing_ids:

            continue


        # ----------------------------------------------------
        # Print event
        # ----------------------------------------------------

        print(
            f"\n[{number}] VALID EVENT"
        )

        print(
            f"    Date: "
            f"{date if date else 'Not available'}"
        )

        print(
            f"    Headline: "
            f"{headline}"
        )

        print(
            f"    Sentiment: "
            f"{sentiment}"
        )

        print(
            f"    Source: "
            f"{source}"
        )

        print(
            f"    Reason: "
            f"{reason}"
        )


        # ----------------------------------------------------
        # Store
        # ----------------------------------------------------

        new_rows.append({

            "Company": company,

            "Date": date,

            "Headline": headline,

            "Summary": summary,

            "Sentiment": sentiment,

            "Source": source,

            "Reason": reason,

            # Internal fields
            "_EventID": event_id,

            "_URL": url,
        })


        existing_ids.add(
            event_id
        )

        existing_urls.add(
            url
        )

        company_events += 1


    # ========================================================
    # ADD ROWS
    # ========================================================

    if new_rows:

        new_df = pd.DataFrame(
            new_rows
        )


        df = pd.concat(
            [
                df,
                new_df
            ],
            ignore_index=True
        )


    print(
        f"\nEvents added for "
        f"{company}: {len(new_rows)}"
    )


    return df, True


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 75)
    print("CORPORATE NEWS INTELLIGENCE")
    print("SERPER ONLY")
    print("=" * 75)


    # --------------------------------------------------------
    # Output directory
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True
    )


    # --------------------------------------------------------
    # Check input
    # --------------------------------------------------------

    if not os.path.exists(
        INPUT_FILE
    ):

        raise FileNotFoundError(
            f"\nInput file not found:\n"
            f"{INPUT_FILE}"
        )


    # --------------------------------------------------------
    # Read companies
    # --------------------------------------------------------

    companies_df = pd.read_csv(
        INPUT_FILE
    )


    # --------------------------------------------------------
    # Detect company column
    # --------------------------------------------------------

    possible_columns = [

        "Company Name",

        "Company",

        "company_name",

        "company",
    ]


    company_column = None


    for column in possible_columns:

        if column in companies_df.columns:

            company_column = column

            break


    if not company_column:

        raise ValueError(
            "\nCould not find company column.\n"
            "Expected:\n"
            "Company Name\n"
            "or\n"
            "Company"
        )


    companies = (

        companies_df[
            company_column
        ]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )


    total_companies = len(
        companies
    )


    print(
        f"\nCompanies in CSV: "
        f"{total_companies}"
    )


    # --------------------------------------------------------
    # Validate range
    # --------------------------------------------------------

    start = max(
        START_COMPANY - 1,
        0
    )


    end = min(
        END_COMPANY,
        total_companies
    )


    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    progress = load_progress()


    completed = set(

        str(x)

        for x
        in progress.get(
            "completed",
            []
        )
    )


    # --------------------------------------------------------
    # Excel
    # --------------------------------------------------------

    df = load_existing_excel()


    print(
        f"Existing events: "
        f"{len(df)}"
    )


    # ========================================================
    # COMPANY LOOP
    # ========================================================

    for index in range(
        start,
        end
    ):

        company_number = index + 1

        company = companies[
            index
        ]


        print("\n")
        print("#" * 75)

        print(
            f"COMPANY "
            f"{company_number} / "
            f"{total_companies}"
        )

        print(
            company
        )

        print(
            "#" * 75
        )


        # ----------------------------------------------------
        # Resume
        # ----------------------------------------------------

        if RESUME and company in completed:

            print(
                "Already completed. "
                "Skipping."
            )

            continue


        try:

            df, success = process_company(
                company,
                df
            )


            # ------------------------------------------------
            # SAVE AFTER EVERY COMPANY
            # ------------------------------------------------

            save_excel(
                df
            )


            # ------------------------------------------------
            # Mark complete
            # ------------------------------------------------

            if success:

                completed.add(
                    company
                )


                progress[
                    "completed"
                ] = sorted(
                    completed
                )


                save_progress(
                    progress
                )


                print(
                    f"\nCOMPLETED: "
                    f"{company}"
                )


        except KeyboardInterrupt:

            print("\n")
            print(
                "STOPPED BY USER."
            )

            print(
                "Existing Excel and "
                "progress are preserved."
            )

            break


        except Exception as e:

            print("\n")
            print(
                f"ERROR: {company}"
            )

            print(
                str(e)
            )

            print(
                "Company was NOT marked "
                "completed."
            )

            print(
                "It will be retried "
                "next time."
            )


        # ----------------------------------------------------
        # Small delay between companies
        # ----------------------------------------------------

        time.sleep(
            REQUEST_DELAY_SECONDS
        )


    # ========================================================
    # FINAL SAVE
    # ========================================================

    save_excel(
        df
    )


    print("\n")
    print("=" * 75)
    print("PIPELINE FINISHED")
    print("=" * 75)

    print(
        f"Total events: {len(df)}"
    )

    print(
        f"Completed companies: "
        f"{len(completed)}"
    )

    print(
        f"Excel file: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"Progress file: "
        f"{PROGRESS_FILE}"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()

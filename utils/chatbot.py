import os
import re
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from groq import Groq
from utils.company_keys import compute_company_key, short_company_name
from utils.tech_knowledge import TECHNOLOGY_PARAMETERS, Point, TechKnowledgeBase
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_MODEL = "openai/gpt-oss-20b"
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

    """gpt-oss models accept low | medium | high."""

    value = _get_secret("GROQ_REASONING_EFFORT", "low").lower()

    return value if value in {"low", "medium", "high"} else "low"

def get_tech_point_budget() -> int:

    """Max technology evidence points placed in front of the model per question."""

    try:

        return min(100, max(20, int(_get_secret("TECH_POINT_BUDGET", "200"))))

    except ValueError:

        return 200

def get_client() -> Groq:

    api_key = get_api_key()

    if not api_key:

        raise RuntimeError(

            "GROQ_API_KEY is missing. Add it to .env for local use, or "

            "Streamlit Cloud -> Settings -> Secrets."

        )

    return Groq(api_key=api_key)

def _is_empty(value) -> bool:

    if value is None:

        return True

    try:

        if pd.isna(value):

            return True

    except Exception:

        pass

    return str(value).strip() == ""

def _fmt(value, suffix: str = "") -> str:

    if _is_empty(value):

        return "n/a"

    try:

        if isinstance(value, float):

            return f"{value:,.2f}{suffix}"

    except Exception:

        pass

    return f"{value}{suffix}"

def _clean_text(value) -> str:

    if _is_empty(value):

        return ""

    return str(value).strip()


_TECH_INTENT = [

    r"technolog", r"\btech\b", r"digital", r"cloud", r"automat", r"cyber",

    r"security", r"\br ?(and|&) ?d\b", r"research", r"innovat", r"roadmap",

    r"partnership", r"adoption", r"\bai\b", r"gen ?ai", r"generative",

    r"machine learning", r"artificial intelligence", r"platform", r"software",

    r"\berp\b", r"blockchain", r"\biot\b", r"talent", r"skills", r"tech risk",

    r"pain area", r"\bgaps?\b", r"data protection", r"privacy",

]



_FIN_INTENT = [

    r"revenue", r"profit", r"\bpat\b", r"ebitda", r"margin", r"\broe\b",

    r"\broce\b", r"market cap", r"valuation", r"\bdebt", r"\bcash\b", r"\beps\b",

    r"\bprice\b", r"\bltp\b", r"financial", r"growth", r"\brank",

    r"balance sheet", r"earnings",

]



_NEWS_INTENT = [

    r"\bnews\b", r"headline", r"announcement", r"press release", r"\bupdates?\b",

    r"\bevents?\b", r"recent development", r"latest",

]


def _matches_any(text: str, patterns) -> bool:

    return any(re.search(p, text) for p in patterns)

def question_wants_technology(question: str) -> bool:

    q = str(question or "").lower()

    tech = _matches_any(q, _TECH_INTENT)

    fin = _matches_any(q, _FIN_INTENT)

    news = _matches_any(q, _NEWS_INTENT)



    if tech:

        return True

    return not fin and not news


def question_wants_financial(question: str) -> bool:

    return _matches_any(str(question or "").lower(), _FIN_INTENT)


def question_wants_news(question: str) -> bool:

    return _matches_any(str(question or "").lower(), _NEWS_INTENT)


def question_wants_broad_technology_detail(question: str) -> bool:

    q = str(question or "").lower()

    return bool(

        re.search(

            r"\btechnology\s+parameters?\b"

            r"|\btech(?:nology)?\s+(?:overview|landscape|profile)\b"

            r"|\ball\s+(?:the\s+)?(?:technology|tech)\b",

            q,

        )

    )

def question_wants_detailed_technology_evidence(question: str) -> bool:
    """Return True only when the user explicitly asks for raw/source evidence."""
    q = str(question or "").lower()
    evidence_patterns = [
        r"\boriginal\s+evidence\b",
        r"\braw\s+evidence\b",
        r"\bdetailed\s+evidence\b",
        r"\bannual[ -]?report\s+evidence\b",
        r"\bsource\s+(?:details|references?|documents?)\b",
        r"\bpage(?:\s*[- ]?wise)?\s+(?:numbers?|references?|evidence|details)\b",
        r"\bpage\s+numbers?\b",
        r"\bcitations?\b",
        r"\bshow\s+(?:me\s+)?(?:the\s+)?evidence\b",
        r"\bprovide\s+(?:me\s+)?(?:the\s+)?evidence\b",
        r"\bgive\s+(?:me\s+)?(?:the\s+)?evidence\b",
        r"\bextracts?\s+from\s+(?:the\s+)?annual[ -]?report\b",
        r"\bquote\s+(?:from\s+)?(?:the\s+)?annual[ -]?report\b",
    ]
    return any(re.search(pattern, q) for pattern in evidence_patterns)

def question_wants_technology_comparison(question: str) -> bool:

    if not question_wants_technology(question):

        return False

    q = str(question or "").lower()

    return bool(

        re.search(

            r"\bcompare\b|\bcomparison\b|\bvs\.?\b|\bversus\b|\bagainst\b"

            r"|\bbenchmark\b|\bsector leader\b|\brelative to\b",

            q,

        )

    )





def _has_technology_evidence_refusal(answer: str) -> bool:

    text = str(answer or "").lower()

    refusal_patterns = (

        r"\bonly covers\b",

        r"\bno (?:technology )?(?:evidence|data|information)\b.{0,120}\b(?:company|leader|comparison)\b",

        r"\bdoes not contain (?:any )?(?:technology )?(?:evidence|data)\b.{0,120}\b(?:company|leader)\b",

        r"\bcan(?:not|['’]t) make a comparison\b",

        r"\bunable to compare\b",

    )

    return _matches_any(text, refusal_patterns)


@dataclass

class SourceRegistry:

    entries: dict = field(default_factory=dict)     

    companies: list = field(default_factory=list)  

    def add(self, company_key: str, company_name: str, point: Point) -> int:

        sid = len(self.entries) + 1

        self.entries[sid] = {

            "company_key": company_key,

            "company": company_name,

            "point": point,

        }

        if company_name not in self.companies:

            self.companies.append(company_name)

        return sid

def _truncate(text: str, limit: int = 700) -> str:

    text = " ".join(str(text).split())

    if len(text) <= limit:

        return text

    return text[:limit].rsplit(" ", 1)[0] + " ..."

def _pages_text(point: Point) -> str:

    return ", ".join(str(p) for p in point.pages) if point.pages else "n/a"


def build_technology_section(

    company_name: str,

    kb: TechKnowledgeBase,

    question: str,

    registry: SourceRegistry,

    max_points: int,

) -> list[str]:



    profile = kb.get_profile(company_name) if kb is not None else None



    if profile is None or profile.total_points == 0:

        return [

            f"No technology evidence is on file for {company_name}. The annual-report "

            "technology extraction currently covers only some Financial Services "

            "and Healthcare companies."

        ]



    points = kb.select_points(profile.key, question, max_points=max_points)



    grouped: dict[str, list[Point]] = {}

    for point in points:

        grouped.setdefault(point.parameter, []).append(point)



    lines = []

    for parameter in TECHNOLOGY_PARAMETERS:

        pts = grouped.get(parameter)

        if not pts:

            continue

        lines.append(f"[{parameter}]")

        for point in pts:

            sid = registry.add(profile.key, company_name, point)

            lines.append(

                f"[S{sid}] {_truncate(point.text)} (annual report p. {_pages_text(point)})"

            )



    missing = profile.parameters_without_evidence()

    if missing:

        lines.append(

            "Parameters with NO evidence in the annual-report extraction: "

            + ", ".join(missing)

        )



    return lines





# ============================================================

# BUILD COMPANY CONTEXT (financials + news + technology evidence)

# ============================================================



def build_context(

    company_row: pd.Series,

    news_df: pd.DataFrame,

    kb: TechKnowledgeBase,

    question: str = "",

    registry: SourceRegistry | None = None,

    max_news: int = 12,

    max_tech_points: int = 40,

    include_technology: bool = True,

    include_financial: bool = True,

    include_news: bool = True,

) -> str:



    company_name = str(company_row.get("Company", "Unknown Company"))



    # Recompute the key fresh from the company name every time, rather

    # than trusting a stored Company_Key column (it can be stale or built

    # with a different rule) - a wrong key silently drops all news.

    company_key = compute_company_key(company_name)



    # --------------------------------------------------------

    # FINANCIALS

    # --------------------------------------------------------



    financials = [

        f"Company: {company_name}",

        f"NSE Symbol: {company_row.get('NSE Symbol', 'n/a')}",

        f"Sector: {company_row.get('Sector', 'n/a')}",

        f"Industry: {company_row.get('Industry', 'n/a')}",

        f"Sector Rank: {_fmt(company_row.get('Sector Rank'))} of {_fmt(company_row.get('Sector Company Count'))}",

        f"Sector Leader: {company_row.get('Sector Leader', 'n/a')}",

        f"Market Cap: Rs.{_fmt(company_row.get('Market Cap'))}",

        f"Revenue: Rs.{_fmt(company_row.get('Revenue (Billion)'))}B",

        f"Revenue Growth: {_fmt(company_row.get('Revenue Growth'))}",

        f"EBITDA Margin: {_fmt(company_row.get('EBITDA Margin'))}",

        f"PAT: Rs.{_fmt(company_row.get('PAT (Billion)'))}B",

        f"ROE: {_fmt(company_row.get('ROE'))}",

        f"ROCE: {_fmt(company_row.get('ROCE'))}",

        f"Debt/Equity: {_fmt(company_row.get('Debt Equity Ratio'))}",

        f"Cash: Rs.{_fmt(company_row.get('Cash (Billion)'))}B",

    ]



    # --------------------------------------------------------

    # NEWS - headline, date, sentiment, summary, source (unchanged)

    # --------------------------------------------------------



    news_lines = []



    if news_df is not None and not news_df.empty and "Company" in news_df.columns:



        company_news = news_df[

            news_df["Company"].apply(compute_company_key) == company_key

        ].copy()



        if "Date" in company_news.columns:

            company_news = company_news.sort_values("Date", ascending=False)



        company_news = company_news.head(max_news)



        for _, row in company_news.iterrows():



            date_value = row.get("Date")

            if pd.notna(date_value):

                try:

                    date_text = date_value.date()

                except Exception:

                    date_text = date_value

            else:

                date_text = "undated"



            sentiment = row.get("Sentiment", "")

            headline = row.get("Headline", "")

            summary = row.get("Summary", "")

            source = row.get("Source", "")



            if not _is_empty(headline):

                news_lines.append(

                    f"- [{date_text}] ({sentiment}) {headline} "

                    f"| Source: {source} | Summary: {summary}"

                )



    if not news_lines:

        news_lines = ["No recent news on file."]



    # --------------------------------------------------------

    # TECHNOLOGY - evidence points with [S#] ids and report pages

    # --------------------------------------------------------



    sections = []



    if include_financial:

        sections.append("=== COMPANY FINANCIAL DATA ===\n" + "\n".join(financials))



    if include_news:

        sections.append("=== RECENT NEWS DATA ===\n" + "\n".join(news_lines))



    if include_technology:

        if registry is None:

            registry = SourceRegistry()

        tech_lines = build_technology_section(

            company_name, kb, question, registry, max_tech_points

        )

        sections.append("=== TECHNOLOGY EVIDENCE (annual report) ===\n" + "\n".join(tech_lines))



    return "\n\n".join(sections)





# ============================================================

# MULTI COMPANY CONTEXT

# ============================================================



def build_multi_company_context(

    company_df: pd.DataFrame,

    matched_companies: pd.DataFrame,

    news_df: pd.DataFrame,

    kb: TechKnowledgeBase,

    question: str = "",

    registry: SourceRegistry | None = None,

    scale: float = 1.0,

    include_technology: bool = True,

    include_financial: bool = True,

    include_news: bool = True,

) -> str:



    if matched_companies is None or matched_companies.empty:

        return "No company was detected."



    n = len(matched_companies)

    budget = max(4 * n, int(get_tech_point_budget() * scale))

    per_company = max(4, min(100, budget // max(1, n)))

    max_news = max(6, int(14 * scale))



    sections = []

    for index, (_, company_row) in enumerate(matched_companies.iterrows(), start=1):

        context = build_context(

            company_row, news_df, kb,

            question=question,

            registry=registry,

            max_news=max_news,

            max_tech_points=per_company,

            include_technology=include_technology,

            include_financial=include_financial,

            include_news=include_news,

        )

        company_name = company_row.get("Company", "n/a")

        sections.append(f"=== MATCHED COMPANY {index}: {company_name} ===\n{context}")



    if include_financial:

        comparison_lines = []

        for _, row in matched_companies.iterrows():

            comparison_lines.append(

                f"{row.get('Company', 'n/a')} | Sector: {row.get('Sector', 'n/a')} | "

                f"Market Cap: Rs.{_fmt(row.get('Market Cap'))} | "

                f"Revenue Growth: {_fmt(row.get('Revenue Growth'))} | "

                f"EBITDA Margin: {_fmt(row.get('EBITDA Margin'))} | "

                f"ROE: {_fmt(row.get('ROE'))} | ROCE: {_fmt(row.get('ROCE'))}"

            )



        sections.append("=== MATCHED COMPANY COMPARISON DATA ===\n" + "\n".join(comparison_lines))



    return "\n\n".join(sections)





# ============================================================

# DATASET OVERVIEW (used when no specific company is detected)

# ============================================================



def build_dataset_overview_context(company_df: pd.DataFrame, kb: TechKnowledgeBase | None = None) -> str:



    if company_df is None or company_df.empty:

        return "No company dataset is available."



    lines = [f"Total companies in dataset: {len(company_df):,}"]



    if "Sector" in company_df.columns:

        lines.append(f"Total sectors: {company_df['Sector'].dropna().nunique():,}")



    if kb is not None and kb.profiles:

        covered = [p.company for p in kb.profiles.values() if p.total_points]

        lines.append(

            f"Technology evidence (from annual reports) is available for {len(covered)} companies "

            "in Financial Services and Healthcare. Ask about a named company to see it."

        )



    return "=== DATASET OVERVIEW ===\n" + "\n".join(lines)





# ============================================================

# SYSTEM PROMPT

# ============================================================



SYSTEM_PROMPT = """You are the Corporate Intelligence Assistant for an NSE/BSE

company research platform. You answer questions about company financials,

recent news, and technology adoption using ONLY the data supplied below.



How to behave:



1. Answer any question the user asks, however they phrase it - casual,

   technical, or indirect. Do not require exact keywords. "AI",

   "GenAI", "what tech do they use", "how digital are they", "how safe is

   their data" etc. should all be answered from the TECHNOLOGY EVIDENCE

   section using your own understanding of the text there.



   Give a detailed, substantive answer rather than a terse summary. When the

   user asks for more detail, provide richer context, deeper explanation, and

   fuller reasoning grounded in the supplied data. Prefer a structured answer

   with 2-5 paragraphs or clear bullet points when useful.

   Treat the user's request for more detail as a standing preference: do not

   imitate shorter answers from prior conversation history.



2. Treat the companies in the current MATCHED COMPANY sections as the exact

   scope of the request. Do not introduce, compare, or show sources for any

   other company based on prior chat history or assumptions. A sector leader

   belongs in scope only when the current question explicitly asks for one

   and that leader is listed in the supplied company context.



3. Ground every financial figure and every factual claim in the supplied

   data. Never invent numbers, technologies, vendors, dates, or news events

   that are not present in the data below.



4. You may reason over the supplied numbers freely - compute differences,

   ratios, rankings, or comparisons across the companies given to you.



5. If the answer is not in the supplied data, say so plainly and suggest

   what the user could ask instead. If a company has no technology evidence

   on file, say that - do not guess from general knowledge.



6. If multiple companies are supplied, address every one individually with

   comparable depth, then compare them directly when the user asks for a

   comparison. For technology comparisons, summarize the supplied evidence

   for each company in a concise side-by-side table. Do not let the first

   company crowd out the others.



7. Give detailed, substantive answers across financial, news, and technology

   questions; do not give a terse 1-2 sentence summary when the supplied data

   supports more. For a broad technology overview or a request for technology

   parameters, make a separate heading for EVERY parameter that has supplied

   evidence and explain the relevant points under it. Do not stop after the

   first few parameters; aim for at least 2 useful evidence-backed details per

   parameter when the supplied points support that, and cite each claim. A

   broad technology overview should normally be around 900-1,400 words when

   the supplied evidence supports it; avoid a short introduction and conclusion

   taking space away from the company-specific analysis. For a narrow technology

   question, focus on the relevant parameters and explain them in depth. For

   financial questions, cover all requested metrics,

   explain what they indicate, and include relevant comparisons or calculations

   from supplied figures. For news questions, describe each relevant event and

   its significance based only on the supplied headline and summary. Use

   headings, short paragraphs, or bullets for readability. For a direct

   technology comparison, use a concise side-by-side table of up to five

   relevant parameters instead of the full broad-overview treatment. Do not

   pad with repetition or disclaimers.



TECHNOLOGY EVIDENCE - how to use it:



8. The technology evidence is a list of extractive points copied from the

   company's annual report. They are often sentence fragments, repeat each

   other, or lack context. Do NOT paste them back. Explain them: rewrite in

   clear, natural language, group related points under a heading or theme,

   merge duplicates, and complete fragments only to the extent the evidence

   itself supports.

9. For broad technology requests such as "give me all technology parameters
   data", "explain the company's technology adoption", or "give me a
   technology overview", provide a moderately detailed, structured answer.

   Cover every technology parameter supported by the supplied evidence.
   For each parameter, explain:
   - What the company has adopted, implemented, developed, or planned.
   - The specific systems, technologies, initiatives, or activities
     mentioned in the evidence.
   - Why the activity matters for the company's operations or technology
     capabilities, where this can reasonably be explained.

   Aim for 2-4 meaningful sentences per parameter when the evidence
   supports that level of detail. Do not force additional sentences when
   the source contains very little information.

   Do not display raw annual-report excerpts, lengthy retrieved chunks,
   or a separate detailed evidence appendix in a normal overview response.

   Use the supplied evidence IDs for technology claims. If evidence for
   a parameter is unavailable, state "Not Available in collected data".
   Never fill gaps using assumptions or general industry knowledge.

   Show detailed annual-report evidence, page numbers, and source
   references when the user explicitly asks for original evidence,
   detailed evidence, page-wise evidence, or source details.



10. Reframe, never embellish. Do not add facts, numbers, product names,

   timelines or outcomes that the points do not state. Keep every number and

   unit exactly as given. Keep the strength of the claim: "plans to" must not

   become "has", "may" must not become "will", a risk is not an achievement.



11. A point is filed under a parameter (e.g. Cybersecurity, Cloud Adoption)

   but may be only loosely related. Use a point under a parameter only if it

   genuinely supports it. If a parameter has no evidence, say that the annual

   report evidence does not cover it - do not fill the gap.



12. CITATIONS: every technology claim must carry the id tag(s) of the

    evidence point(s) it is based on, written exactly like [S12] or

    [S12][S31], placed right after the sentence or bullet. Use only ids that

    appear in the data. Never write page numbers yourself and never put

    [S#] tags on financial or news statements - the app converts the tags

    into the annual-report page numbers.



13. For a technology comparison, use the supplied evidence for every matched

    company. Do not claim that a company's evidence is missing when its

    TECHNOLOGY EVIDENCE section contains cited points. Compare corresponding

    parameters where the evidence allows it.



14. For news questions, do not tell the user to "see the sources below" -

    actually describe what happened, using the headline and Summary text

    supplied in RECENT NEWS DATA. The Sources panel the app shows afterwards

    is only a citation list.

"""


def _looks_like_size_or_rate_error(exc: Exception) -> bool:

    text = str(exc).lower()

    return any(t in text for t in ("413", "rate_limit", "rate limit", "too large", "tokens per minute", "request too large"))





def _looks_like_daily_quota_error(exc: Exception) -> bool:

    text = str(exc).lower()

    return "tokens per day" in text or "tpd" in text





class DailyTokenQuotaError(RuntimeError):

    """Raised when Groq's organization-level daily token allowance is exhausted."""





def _daily_quota_message(exc: Exception) -> str:

    match = re.search(r"try again in\s+([0-9]+m[0-9]+(?:\.\d+)?s)", str(exc), re.I)

    wait = f" Try again in {match.group(1)}." if match else " Try again after the quota resets."

    return (

        "Groq's daily token quota for this organization has been reached."

        f"{wait} The app will not retry automatically because another request "

        "would fail until the quota resets. You can also ask your Groq "

        "organization administrator about a higher quota."

    )





def _call_groq(messages: list, effort: str | None, max_completion_tokens: int = 4500):

    client = get_client()



    kwargs = dict(

        model=get_model(),

        messages=messages,

        max_completion_tokens=max_completion_tokens,

        temperature=0.45,

    )

    if effort:

        kwargs["extra_body"] = {"reasoning_effort": effort}



    try:

        return client.chat.completions.create(**kwargs)

    except Exception as exc:

        # a model/SDK that does not accept reasoning_effort: retry without it

        if effort and "reasoning_effort" in str(exc).lower():

            kwargs.pop("extra_body", None)

            return client.chat.completions.create(**kwargs)

        raise





def ask(

    question: str,

    context: str,

    history=None,

    max_completion_tokens: int = 4500,

) -> str:



    if not question.strip():

        return "Please enter a question."



    format_instruction = ""

    if question_wants_technology_comparison(question):

        format_instruction = (

            "\n\nThis is a technology comparison. Summarize the evidence points "

            "supplied for each matched company; do not rely on just the first "

            "point in a parameter. Present a concise, balanced side-by-side "

            "table with up to seven relevant parameters. Combine related points "

            "into a short summary in each cell, cite every factual claim with "

            "the supplied evidence IDs, and do not add a long evidence appendix."

        )

    elif question_wants_broad_technology_detail(question):

        format_instruction = (

             "\n\nThe user wants a comprehensive overview of the company's "
            "technology parameters, not a one-line summary and not a raw "
            "evidence dump.\n"
            "Provide a moderately detailed, structured answer covering "
            "every technology parameter for which evidence is available.\n"
            "Use a Markdown table with these columns: Technology Parameter, "
            "What the company is doing, and Business/Technology Significance.\n"
            "For each available parameter, explain the actual activity, "
            "system, investment, initiative, or capability described in "
            "the supplied evidence. Give approximately 2-4 meaningful "
            "sentences per parameter where the evidence supports it.\n"
            "Explain significance in context, but clearly distinguish "
            "evidence-based facts from interpretation. Do not invent "
            "technologies, vendors, plans, or business outcomes.\n"
            "Include all relevant parameters, not just the first few. "
            "If evidence is unavailable for a parameter, write "
            "'Not Available in collected data'.\n"
            "Cite technology claims with the supplied evidence IDs, such "
            "as [S12]. Do not append a long raw-evidence table, repeat "
            "the same claim, or quote lengthy annual-report passages.\n"
            "Aim for useful detail and completeness rather than the "
            "shortest possible answer."
        )

    messages = [{

        "role": "system",

        "content": SYSTEM_PROMPT + format_instruction + "\n\n" + context,

    }]



    if history:

        for message in history[-2:]:

            role = message.get("role")

            content = message.get("content")

            if role in {"user", "assistant"} and content:

                limit = 800 if role == "assistant" else 300

                messages.append({"role": role, "content": str(content)[:limit]})



    messages.append({"role": "user", "content": question})



    response = _call_groq(messages, get_reasoning_effort(), max_completion_tokens)

    choice = response.choices[0]

    answer = (choice.message.content or "").strip()



    # the model spent its whole budget thinking -> try again with less thinking

    if not answer and getattr(choice, "finish_reason", "") == "length":

        response = _call_groq(messages, "low", max_completion_tokens)

        answer = (response.choices[0].message.content or "").strip()



    return answer or "No answer was returned."





# ============================================================

# CITATIONS: [S12] -> real annual-report page numbers + sources

# ============================================================



_CITE = re.compile(r"[\[\u3010(]\s*S\d+(?:\s*[,;]\s*S?\d+)*\s*[\]\u3011)]")





@dataclass

class ChatAnswer:

    text: str

    tech_sources: list = field(default_factory=list)

    technology_used: bool = False

    sources_are_citations: bool = True   # False -> "evidence reviewed" fallback





def _page_label(entries: list[dict], multi_company: bool) -> str:

    by_company: dict[str, list[int]] = {}

    for e in entries:

        pages = by_company.setdefault(e["company"], [])

        for page in e["point"].pages:

            if page not in pages:

                pages.append(page)



    parts = []

    for company, pages in by_company.items():

        pages_text = ", ".join(str(p) for p in sorted(pages))

        parts.append(

            f"{short_company_name(company)} p. {pages_text}" if multi_company else f"p. {pages_text}"

        )

    return "[" + "; ".join(parts) + "]"





def resolve_citations(

    answer: str,

    registry: SourceRegistry,

    kb: TechKnowledgeBase,

) -> tuple[str, list[dict]]:

    """

    Replace [S#] tags with page labels like [p. 161] and return the list of

    cited sources (PDF, page, section, excerpt) taken from technology_extraction.

    """



    multi_company = len(registry.companies) > 1

    cited_ids: list[int] = []



    def replace(match):

        ids = [int(x) for x in re.findall(r"\d+", match.group(0))]

        valid = [i for i in ids if i in registry.entries]

        if not valid:

            return ""                       # hallucinated id -> drop the tag

        for i in valid:

            if i not in cited_ids:

                cited_ids.append(i)

        return _page_label([registry.entries[i] for i in valid], multi_company)



    text = _CITE.sub(replace, answer)



    # tidy: "word ." from removed tags, and back-to-back identical labels

    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)

    text = re.sub(r"(\[[^\]]+\])(?:\s*\1)+", r"\1", text)



    sources = _sources_for_ids(cited_ids, registry, kb)

    return text, sources





def _sources_for_ids(ids: list[int], registry: SourceRegistry, kb: TechKnowledgeBase) -> list[dict]:

    sources, seen = [], set()



    for sid in ids:

        entry = registry.entries[sid]

        point: Point = entry["point"]



        for src in kb.sources_for_point(entry["company_key"], point):

            src = dict(src)

            src["company"] = entry["company"]

            key = (src["company_key"], src["page"], src["parameter"])

            if key in seen:

                continue

            seen.add(key)

            sources.append(src)



    return sources





def _append_detailed_technology_evidence(

    answer: str,

    matched_companies: pd.DataFrame,

    kb: TechKnowledgeBase,

    registry: SourceRegistry,

    coverage: float = 0.8,

) -> str:

    """Append a cited table covering 80% of distinct technology statements."""

    if matched_companies is None or matched_companies.empty:

        return answer



    company_col = next(

        (column for column in ("Company", "Company Name") if column in matched_companies.columns),

        None,

    )

    if company_col is None:

        return answer



    company_sections = []

    for company_name in matched_companies[company_col].dropna().astype(str):

        profile = kb.get_profile(company_name)

        if profile is None or profile.total_points == 0:

            continue



        unique_by_parameter: dict[str, list[Point]] = {}

        seen_text = set()

        for parameter in TECHNOLOGY_PARAMETERS:

            for point in profile.points.get(parameter, []):

                normalized = " ".join(point.text.lower().split())

                if normalized in seen_text:

                    continue

                seen_text.add(normalized)

                unique_by_parameter.setdefault(parameter, []).append(point)



        all_points = [

            (parameter, point)

            for parameter in TECHNOLOGY_PARAMETERS

            for point in unique_by_parameter.get(parameter, [])

        ]

        if not all_points:

            continue



        target_count = max(1, int(len(all_points) * coverage + 0.5))

        selected: list[tuple[str, Point]] = []

        per_parameter_index = {parameter: 0 for parameter in TECHNOLOGY_PARAMETERS}

        while len(selected) < target_count:

            added = False

            for parameter in TECHNOLOGY_PARAMETERS:

                points = unique_by_parameter.get(parameter, [])

                point_index = per_parameter_index[parameter]

                if point_index >= len(points):

                    continue

                selected.append((parameter, points[point_index]))

                per_parameter_index[parameter] += 1

                added = True

                if len(selected) >= target_count:

                    break

            if not added:

                break



        company_name = company_name.strip()

        lines = [

            f"#### {company_name}: annual-report evidence",

            (

                f"Coverage: {len(selected)} of {len(all_points)} distinct extracted "

                f"statements ({len(selected) / len(all_points):.0%}). Repeated "

                "statements are counted once; highlights are concise excerpts."

            ),

            "",

            "| Technology parameter | Evidence highlights |",

            "|---|---|",

        ]

        grouped: dict[str, list[Point]] = {}

        for parameter, point in selected:

            grouped.setdefault(parameter, []).append(point)



        for parameter in TECHNOLOGY_PARAMETERS:

            points = grouped.get(parameter)

            if not points:

                continue

            evidence = []

            for point in points:

                source_id = registry.add(profile.key, company_name, point)

                point_text = _truncate(point.text, limit=150).replace("|", r"\|")

                evidence.append(f"{point_text} [S{source_id}]")

            lines.append(

                f"| **{parameter}** | " + "\<br>".join(evidence) + " |"

            )



        company_sections.append("\n".join(lines))



    if not company_sections:

        return answer



    appendix = (

        "\n\n---\n\n### Detailed annual-report evidence\n\n"

        + "\n\n".join(company_sections)

    )

    return answer.rstrip() + appendix





def _build_concise_technology_comparison(
    matched_companies: pd.DataFrame,
    kb: TechKnowledgeBase,
    registry: SourceRegistry,
    question: str = "",
) -> str:
    """Build an evidence-grounded comparison even when one company has no profile."""
    company_col = next(
        (column for column in ("Company", "Company Name") if column in matched_companies.columns),
        None,
    )
    if company_col is None:
        return "A technology comparison could not be prepared because company names are unavailable."

    companies = []
    seen = set()
    for raw_name in matched_companies[company_col].dropna().astype(str):
        name = raw_name.strip()
        key = compute_company_key(name)
        if not name or key in seen:
            continue
        seen.add(key)
        profile = kb.get_profile(name) if kb is not None else None
        companies.append((name, profile))

    if len(companies) < 2:
        return "A technology comparison requires at least two matched companies."

    parameter_order = [
        "Current Technology Adoption", "Digital Transformation", "AI",
        "Emerging Technologies", "Automation", "Cybersecurity",
        "Platforms & Systems", "Cloud Adoption", "Technology Partnerships",
        "Technology Investments", "Future Technology Roadmaps",
        "Technology Pain Areas", "Tech Risk", "R&D", "Talent & Skills",
    ]

    # If the question names a parameter, put it first and return it even if it
    # would otherwise fall beyond the general comparison row limit.
    q = str(question or "").lower()
    parameter_patterns = {
        "R&D": r"\br\s*(?:&|and)\s*d\b|research(?: and| &) development|\brnd\b",
        "Technology Investments": r"investment|capex|capital expenditure|technology spend|technology budget",
        "Current Technology Adoption": r"technology adoption|tech stack|current technolog",
        "Digital Transformation": r"digital transformation|digitisation|digitization|digitalisation|digitalization",
        "Emerging Technologies": r"emerging technolog|blockchain|internet of things|\biot\b|5g",
        "Technology Partnerships": r"technology partnership|technology partner|collaboration|alliance",
        "Cloud Adoption": r"cloud adoption|cloud computing|cloud migration|\baws\b|\bazure\b",
        "Automation": r"automation|automated|\brpa\b|robotic process",
        "Cybersecurity": r"cybersecurity|cyber security|information security",
        "Future Technology Roadmaps": r"roadmap|future technology|technology plan",
        "Technology Pain Areas": r"technology pain|technology challenge|technology gap|technology issue",
        "AI": r"artificial intelligence|generative ai|\bai\b|machine learning",
        "Tech Risk": r"technology risk|tech risk|cyber risk",
        "Platforms & Systems": r"platforms? and systems?|core banking|\berp\b|\bsap\b",
        "Talent & Skills": r"technology talent|technology skills|tech skills",
    }
    requested = [p for p in parameter_order if re.search(parameter_patterns.get(p, r"(?!)"), q)]
    if requested:
        parameter_order = requested + [p for p in parameter_order if p not in requested]

    lines = [
        "### Technology comparison",
        "Evidence is compared only where the supplied annual-report data supports it. Missing evidence is not treated as zero.",
        "",
        "| Technology parameter | " + " | ".join(name for name, _ in companies) + " |",
        "|" + "|".join(["---"] * (len(companies) + 1)) + "|",
    ]

    included = 0
    # For a parameter-specific question, show that parameter first and then
    # up to six other available parameters for context. General comparisons get 7.
    limit = 7
    for parameter in parameter_order:
        points_by_company = []
        for name, profile in companies:
            points = profile.points.get(parameter, []) if profile else []
            points_by_company.append((name, profile, points))
        if not any(points for _, _, points in points_by_company):
            continue

        cells = [f"**{parameter}**"]
        for name, profile, points in points_by_company:
            if not points or profile is None:
                cells.append("No extracted evidence available")
                continue
            # Rank R&D points so reconstructed table rows and actual values are
            # shown before table titles, source-page labels, or generic headings.
            if parameter == "R&D":
                def rd_relevance(point):
                    text = point.text.lower()
                    score = 0
                    if "r&d" in text or "r and d" in text or "research and development" in text:
                        score += 5
                    if "capex" in text or "capital expenditure" in text:
                        score += 3
                    if re.search(r"\d+(?:\.\d+)?%", text) or re.search(r"\|\s*-\s*\|", text):
                        score += 8
                    if "table content reconstructed" in text or text.startswith("source page:"):
                        score -= 10
                    if len(text) < 35:
                        score -= 3
                    return score
                chosen = sorted(points, key=rd_relevance, reverse=True)[:3]
            else:
                chosen = points[:1]
            snippets = []
            for point in chosen:
                sid = registry.add(profile.key, name, point)
                excerpt = _truncate(point.text, limit=230).replace("\ufffd", "").replace("|", r"\|")
                page_text = ", ".join(str(p) for p in point.pages) if point.pages else "page unavailable"
                snippets.append(f"{excerpt} (p. {page_text}) [S{sid}]")
            cells.append("<br>".join(snippets))

        lines.append("| " + " | ".join(cells) + " |")
        included += 1
        if included >= limit and not requested:
            break
        # For a parameter-specific query, once the requested parameter has
        # been emitted, don't let unrelated rows displace it.
        if requested and included >= min(7, len(parameter_order)):
            break

    if included == 0:
        return "No extracted technology evidence was found for these companies in the loaded workbooks."
    return "\n".join(lines)


def _global_technology_search_terms(question: str) -> list[str]:
    """Keep this compatibility helper, but do not use individual words as searches."""
    # Deliberately return the complete question as one query unit. Splitting it
    # into words caused unrelated COMPARE / EXPAND / AI result sections.
    cleaned = " ".join(str(question or "").split())
    return [cleaned] if cleaned else []


def _search_technology_dataset(
    question: str,
    kb: TechKnowledgeBase,
) -> ChatAnswer:
    """Search all companies by the meaning of the complete question, not isolated words."""
    if kb is None or not kb.profiles:
        return ChatAnswer(
            text="No technology profiles are loaded. Check that the evidence_summary and technology_extraction workbooks are present and readable."
        )

    # A full-question semantic comparison is essential for action-oriented
    # questions such as 'which companies plan to expand AI'. Parameter labels
    # are included in each candidate so short labels such as AI remain useful.
    candidates = []
    documents = []
    for profile in kb.profiles.values():
        for parameter in TECHNOLOGY_PARAMETERS:
            for point in profile.points.get(parameter, []):
                candidates.append((profile, point))
                documents.append(
                    f"Company: {profile.company}. Technology parameter: {parameter}. "
                    f"Annual-report statement: {point.text}"
                )

    if not candidates:
        return ChatAnswer(text="No technology evidence points are loaded from the current workbooks.")

    try:
        scores = kb._ranker.scores(str(question or ""), documents)
        model_loaded = kb._ranker._load_model() is not None
    except Exception:
        scores = [0.0] * len(candidates)
        model_loaded = False

    ranked = sorted(
        zip(scores, candidates),
        key=lambda item: item[0],
        reverse=True,
    )

    # With embeddings, require a meaningful semantic match. If the embedding
    # model is unavailable, the ranker uses token overlap; use its positive
    # scores but never create separate result sections for individual words.
    best_score = ranked[0][0] if ranked else 0.0
    threshold = max(0.20, best_score * 0.62) if model_loaded else max(0.015, best_score * 0.45)
    ranked = [(score, item) for score, item in ranked if score >= threshold and score > 0]

    # De-duplicate repeated points and keep a small, balanced set per company.
    company_results: dict[str, dict] = {}
    for score, (profile, point) in ranked:
        key = profile.key
        bucket = company_results.setdefault(key, {"profile": profile, "points": [], "seen": set(), "score": score})
        normalized = " ".join(point.text.lower().split())
        if normalized in bucket["seen"]:
            continue
        if len(bucket["points"]) >= 3:
            continue
        bucket["seen"].add(normalized)
        bucket["points"].append((score, point))
        bucket["score"] = max(bucket["score"], score)

    results = sorted(company_results.values(), key=lambda x: x["score"], reverse=True)
    if not results:
        return ChatAnswer(
            text=(
                "I couldn't find annual-report statements that are sufficiently related to the complete question. "
                "Try naming the technology or company, or check whether the relevant annual-report evidence has been loaded. "
                "This does not prove that a company does not use or plan the technology."
            )
        )

    registry = SourceRegistry()
    lines = [
        "### Companies matching the technology question",
        "Results are ranked against the meaning of your complete question. Each row includes evidence from the company's loaded annual-report summaries; a missing match is not proof that the company does not use or plan the technology.",
        "",
        "| Company | Relevant technology evidence |",
        "|---|---|",
    ]

    for result in results:
        profile = result["profile"]
        excerpts = []
        for score, point in result["points"]:
            source_id = registry.add(profile.key, profile.company, point)
            parameter = point.parameter.replace("|", r"\|")
            excerpt = _truncate(point.text, limit=300).replace("|", r"\|")
            excerpts.append(f"**{parameter}:** {excerpt} [S{source_id}]")
        company_name = profile.company.replace("|", "\\|")
        lines.append(f"| {company_name} | " + "<br>".join(excerpts) + " |")

    answer, sources = resolve_citations("\n".join(lines), registry, kb)
    return ChatAnswer(text=answer, tech_sources=sources, technology_used=True)


# ============================================================
# MAIN ENTRY POINT USED BY THE CHAT PAGE
# ============================================================



def answer_question(

    question: str,

    company_df: pd.DataFrame,

    news_df: pd.DataFrame,

    kb: TechKnowledgeBase,

    matched_companies: pd.DataFrame,

    history=None,

) -> ChatAnswer:



    has_companies = matched_companies is not None and not matched_companies.empty
    explicit_technology = _matches_any(question.lower(), _TECH_INTENT)
    if (
        not has_companies
        and not question_wants_financial(question)
        and not question_wants_news(question)
        and (explicit_technology or _global_technology_search_terms(question))
    ):
        return _search_technology_dataset(question, kb)

    include_technology = has_companies and question_wants_technology(question)
    include_financial = question_wants_financial(question) or not (
        explicit_technology or question_wants_news(question)
    )

    include_news = question_wants_news(question) or not (

        explicit_technology or question_wants_financial(question)

    )



    def build(scale: float):

        registry = SourceRegistry()

        if has_companies:

            context = build_multi_company_context(

                company_df, matched_companies, news_df, kb,

                question=question,

                registry=registry,

                scale=scale,

                include_technology=include_technology,

                include_financial=include_financial,

                include_news=include_news,

            )

        else:

            context = build_dataset_overview_context(company_df, kb)

        return context, registry



    context, registry = build(1.0)



    try:

        raw_answer = ask(question, context, history=history)

    except Exception as exc:

        if _looks_like_daily_quota_error(exc):

            raise DailyTokenQuotaError(_daily_quota_message(exc)) from exc

        if not _looks_like_size_or_rate_error(exc):

            raise

        # Reduce both prompt evidence and reserved output tokens on a TPM retry.

        context, registry = build(0.4)

        try:

            raw_answer = ask(

                question,

                context,

                history=history,

                max_completion_tokens=3000,

            )

        except Exception as retry_exc:

            if _looks_like_daily_quota_error(retry_exc):

                raise DailyTokenQuotaError(_daily_quota_message(retry_exc)) from retry_exc

            if not _looks_like_size_or_rate_error(retry_exc):

                raise

            context, registry = build(0.2)

            try:

                raw_answer = ask(

                    question,

                    context,

                    history=None,

                    max_completion_tokens=1800,

                )

            except Exception as final_exc:

                if _looks_like_daily_quota_error(final_exc):

                    raise DailyTokenQuotaError(_daily_quota_message(final_exc)) from final_exc

                raise



    if not registry.entries:

        # strip any stray tags the model may have produced

        return ChatAnswer(text=_CITE.sub("", raw_answer).strip())



    if (
        include_technology
        and question_wants_technology_comparison(question)
        and len(matched_companies) > 1
    ):
        # Use a deterministic evidence-backed comparison instead of allowing
        # the LLM to reject a valid comparison when the leader lacks a profile.
        # This also ensures a requested parameter such as R&D is not omitted
        # because it appears late in the default parameter order.
        raw_answer = _build_concise_technology_comparison(
            matched_companies,
            kb,
            registry,
            question=question,
        )

    elif include_technology and question_wants_broad_technology_detail(question):

        company_col = next(

            (

                column for column in ("Company", "Company Name")

                if column in matched_companies.columns

            ),

            None,

        )

        profiles = (

            [

                kb.get_profile(name)

                for name in matched_companies[company_col].dropna().astype(str)

            ]

            if company_col else []

        )

        if (

            len(profiles) > 1

            and all(profile is not None and profile.total_points for profile in profiles)

            and _has_technology_evidence_refusal(raw_answer)

        ):

            company_names = [

                profile.company for profile in profiles

            ]

            raw_answer = (

                "### Technology comparison\n"

                "Annual-report technology evidence is available for "

                + " and ".join(company_names)

                + ". The cited parameter tables below provide the evidence "

                "for comparing their technology profiles."

            )



        # Keep broad technology summaries concise. Append the lengthy
        # annual-report evidence table only when the user explicitly asks for it.
        if question_wants_detailed_technology_evidence(question):
            raw_answer = _append_detailed_technology_evidence(
                raw_answer,
                matched_companies,
                kb,
                registry,
    )




    text, sources = resolve_citations(raw_answer, registry, kb)



    if sources:

        return ChatAnswer(text=text, tech_sources=sources, technology_used=True)



    # The model answered without citing: show what it was given instead.

    fallback_ids = []

    per_company: dict[str, int] = {}

    for sid, entry in registry.entries.items():

        count = per_company.get(entry["company_key"], 0)

        if count >= 6:

            continue

        per_company[entry["company_key"]] = count + 1

        fallback_ids.append(sid)



    return ChatAnswer(

        text=text,

        tech_sources=_sources_for_ids(fallback_ids, registry, kb),

        technology_used=True,

        sources_are_citations=False,

    )

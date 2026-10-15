"""
End-to-end smoke test of the Streamlit pages with the Groq network call stubbed.

Run from the project root:
    python tests/smoke_test.py

Everything except the HTTP call to Groq is real: data loading, company
detection, context building, citation resolution and page rendering.
"""

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GROQ_API_KEY", "test-key")

from streamlit.testing.v1 import AppTest  # noqa: E402

import utils.chatbot as cb  # noqa: E402
from utils.data_loader import (  # noqa: E402
    detect_companies_in_text,
    load_company_master,
    load_news,
    load_tech_knowledge,
)

CAPTURED = {}


def fake_groq(messages, effort, max_completion_tokens=4500):
    """Pretend to be the model: cite the first two evidence ids it was given."""
    system = messages[0]["content"]
    CAPTURED["system"] = system
    CAPTURED["effort"] = effort
    CAPTURED["max_completion_tokens"] = max_completion_tokens
    ids = re.findall(r"^\[S(\d+)\]", system, flags=re.M)
    if ids:
        body = (
            "The bank describes a layered approach. "
            f"First point [S{ids[0]}]. Second point [S{ids[1]}][S999]."
        )
    else:
        body = "Plain answer without technology evidence."
    msg = SimpleNamespace(content=body)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


cb._call_groq = fake_groq

# When a page is run standalone as the AppTest entrypoint, st.page_link("app.py")
# cannot resolve (it can in the real multipage app). Neutralise it for the test.
import streamlit as st  # noqa: E402
st.page_link = lambda *a, **k: None

failures = []


def check(label, condition, detail=""):
    print(("PASS  " if condition else "FAIL  ") + label + (f"   [{detail}]" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def page_text(at):
    parts = []
    for coll in (at.markdown, at.caption):
        parts += [e.value for e in coll]
    return "\n".join(parts)


# ---------------------------------------------------------------- dashboard
at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
check("dashboard loads without exception", not at.exception, at.exception)
for sector in ("Financial Services", "Healthcare", "Technology"):
    at.sidebar.selectbox[0].set_value(sector).run()
    check(f"dashboard renders sector {sector}", not at.exception, at.exception)
    txt = page_text(at)
    if sector == "Technology":
        check("uncovered sector leader shows 'no evidence' message",
              "No technology evidence is available" in "\n".join(i.value for i in at.info))
    else:
        check(f"{sector} leader shows technology points with page refs", "(p. " in txt)

# ------------------------------------------------------------------ chatbot
at = AppTest.from_file(str(ROOT / "pages" / "2_Chatbot.py"), default_timeout=180).run()
check("chat page loads without exception", not at.exception, at.exception)


def ask(q):
    at.chat_input[0].set_value(q).run()
    return page_text(at)


# 1. technology question -> cited pages from technology_extraction
txt = ask("What is ICICI Bank's cybersecurity approach?")
check("tech: no exception", not at.exception, at.exception)
check("tech: technology evidence was put in the prompt", "=== TECHNOLOGY EVIDENCE" in CAPTURED["system"])
check("tech: unrelated financial and news context is omitted",
      "=== COMPANY FINANCIAL DATA ===" not in CAPTURED["system"]
      and "=== RECENT NEWS DATA ===" not in CAPTURED["system"])
check("tech: [S#] tags became page labels", re.search(r"\[p\. \d+", txt) is not None, txt[-400:])
check("tech: hallucinated [S999] was dropped", "S999" not in txt)
check("tech: no raw [S#] tags left", re.search(r"\[S\d+\]", txt) is None)
check("tech: sources panel shows PDF name", "ICICI Bank Limited.pdf" in txt)
check("tech: sources panel shows a Page number", re.search(r"Page \d+", txt) is not None)
check("tech: sources panel shows Section", "Section:" in txt)
check("tech: reasoning effort passed", CAPTURED["effort"] in {"low", "medium", "high"}, CAPTURED["effort"])

# 2. financial question -> no technology evidence, no tech sources
CAPTURED.clear()
txt = ask("What is ICICI Bank's ROE and EBITDA margin?")
check("fin: technology evidence NOT in prompt", "=== TECHNOLOGY EVIDENCE" not in CAPTURED["system"])
check("fin: no technology sources panel", "Technology sources" not in txt.split("What is ICICI Bank's ROE")[-1])

# 2b. financial question with the word 'parameters' should still stay financial
company_df = load_company_master()
news_df = load_news()
kb = load_tech_knowledge()
matched = company_df[company_df["Company"].str.contains("ICICI", case=False, na=False)]
result = cb.answer_question("Financial Parameters of ICICI Bank", company_df, news_df, kb, matched, history=[])
check("fin-params: technology evidence NOT in prompt", result.technology_used is False)
check("fin-params: no technology sources panel", len(result.tech_sources) == 0)

# 3. news question -> news sources, no technology panel
CAPTURED.clear()
txt = ask("Latest news about Axis Bank")
check("news: technology evidence NOT in prompt", "=== TECHNOLOGY EVIDENCE" not in CAPTURED["system"])
check("news: news context present", "RECENT NEWS DATA" in CAPTURED["system"])

# 4. company without evidence -> told plainly
CAPTURED.clear()
txt = ask("Tell me about DLF technology")
check("no-evidence company: prompt says none on file", "No technology evidence is on file" in CAPTURED["system"])

# 4b. unscoped technology searches return only explicit evidence matches
empty_matches = company_df.iloc[0:0].copy()
original_ask = cb.ask

def unexpected_groq_call(*args, **kwargs):
    raise AssertionError("unscoped technology search must not call the model")

cb.ask = unexpected_groq_call
try:
    global_tech_result = cb.answer_question(
        "Which companies reported SAP and CRM in their annual reports?",
        company_df,
        news_df,
        kb,
        empty_matches,
        history=[],
    )
finally:
    cb.ask = original_ask

expected_global_matches = {}
for term in ("SAP", "CRM"):
    pattern = re.compile(
        r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        + (r"|customer\s+relationship\s+management" if term == "CRM" else ""),
        flags=re.I,
    )
    expected_global_matches[term] = {
        profile.company
        for profile in kb.profiles.values()
        if any(
            pattern.search(point.text)
            for points in profile.points.values()
            for point in points
        )
    }
check("global tech search: SAP and CRM have evidence-backed matches",
      all(expected_global_matches.values())
      and all(name in global_tech_result.text
              for names in expected_global_matches.values() for name in names))
check("global tech search: no unsupported company such as Adani Power is invented",
      "Adani Power" not in global_tech_result.text)
check("global tech search: all source companies match loaded evidence",
      {source["company"] for source in global_tech_result.tech_sources}
      == set().union(*expected_global_matches.values()))
check("global tech search: generated answer is not used",
      "Annual-report technology evidence search" in global_tech_result.text)

# 5. two companies (HDFC Bank is built from the extraction file)
CAPTURED.clear()
txt = ask("Compare technology of ICICI Bank and HDFC Bank")
check("compare: both companies in prompt",
      "ICICI Bank" in CAPTURED["system"] and "HDFC Bank" in CAPTURED["system"])
check("compare: company-labelled page refs", re.search(r"\[(ICICI|HDFC) Bank p\. \d+", txt) is not None, txt[-500:])

# 6. unique short company name resolves and adds its sector leader
CAPTURED.clear()
query = "Compare Technology Parameters of ICICI and its sector leader"
detected_icici = detect_companies_in_text(company_df, query)
check("icici: unique short name resolves to ICICI Bank Ltd.",
      detected_icici["Company"].tolist() == ["ICICI Bank Ltd."],
      str(detected_icici["Company"].tolist()))
txt = ask(query)
latest_company_caption = [
    item.value for item in at.caption
    if item.value.startswith("Companies checked:")
][-1]
check("icici: context includes ICICI Bank and HDFC Bank only",
      "ICICI Bank Ltd." in CAPTURED["system"]
      and "HDFC Bank Ltd." in CAPTURED["system"]
      and "Tata Consultancy Services Ltd." not in CAPTURED["system"])
check("icici: caption identifies both banks",
      "ICICI Bank Ltd." in latest_company_caption
      and "HDFC Bank Ltd." in latest_company_caption,
      latest_company_caption)

# 7. technology topic must not be mistaken for the Technology sector leader
CAPTURED.clear()
txt = ask("Compare technology parameters of Lenskart Solutions and its sector leader")
latest_company_caption = [
    item.value for item in at.caption
    if item.value.startswith("Companies checked:")
][-1]
check("scope: requested Lenskart and its Healthcare leader are included",
      "Lenskart Solutions Ltd." in latest_company_caption
      and "Divi's Laboratories Ltd." in latest_company_caption,
      latest_company_caption)
check("scope: unrelated Technology sector leader is excluded",
      "Tata Consultancy Services Ltd." not in latest_company_caption
      and "Tata Consultancy Services Ltd." not in CAPTURED["system"])
check("detail: prompt requires every requested company to get comparable depth",
      "comparable depth" in CAPTURED["system"])
check("comparison: prompt requests a concise side-by-side table",
      "Summarize the evidence points supplied for each matched company"
      in CAPTURED["system"])

# 7b. keep the model's comparison summary and resolve its evidence citations
angel_and_leader = (
    company_df.set_index("Company")
    .loc[["Angel One", "HDFC Bank Ltd."]]
    .reset_index()
)
original_ask = cb.ask

def groq_comparison_summary(question, context, history=None, max_completion_tokens=4500):
    CAPTURED["comparison_context"] = context
    sections = re.findall(
        r"=== MATCHED COMPANY \d+: (.*?) ===\n(.*?)(?=\n=== MATCHED COMPANY|\Z)",
        context,
        flags=re.S,
    )
    company_ids = {
        name: re.findall(r"^\[S(\d+)\]", section, flags=re.M)
        for name, section in sections
    }
    angel_id = company_ids["Angel One"][0]
    hdfc_id = company_ids["HDFC Bank Ltd."][0]
    return (
        "### Technology comparison\n"
        f"| Parameter | Angel One | HDFC Bank |\n"
        f"| Digital strategy | Angel One uses a digital-first model [S{angel_id}] "
        f"| HDFC focuses on digital innovation [S{hdfc_id}] |"
    )

cb.ask = groq_comparison_summary
try:
    summarized_comparison = cb.answer_question(
        "Compare technology parameters of Angel One and its sector leader",
        company_df,
        news_df,
        kb,
        angel_and_leader,
        history=[],
    )
finally:
    cb.ask = original_ask
check("comparison: model summary using multiple companies' evidence is preserved",
      "digital-first model" in summarized_comparison.text
      and "Digital strategy" in summarized_comparison.text
      and "Detailed annual-report evidence" not in summarized_comparison.text)
check("comparison: citations in the summary resolve to sources for both companies",
      re.search(r"\[Angel One p\. \d+\]", summarized_comparison.text) is not None
      and re.search(r"\[HDFC Bank p\. \d+\]", summarized_comparison.text) is not None
      and {source["company"] for source in summarized_comparison.tech_sources}
      == {"Angel One", "HDFC Bank Ltd."})

# 7c. a model refusal must not hide evidence for a detected sector leader
def groq_false_missing_evidence(question, context, history=None, max_completion_tokens=4500):
    return (
        "I’m sorry, but the information supplied only covers Angel One. "
        "No data for a sector-leader company is included, so I can’t make a comparison."
    )

cb.ask = groq_false_missing_evidence
try:
    comparison_result = cb.answer_question(
        "Compare technology parameters of Angel One and its sector leader",
        company_df,
        news_df,
        kb,
        angel_and_leader,
        history=[],
    )
finally:
    cb.ask = original_ask
comparison_rows = [
    line for line in comparison_result.text.splitlines()
    if line.startswith("| **")
]
check("comparison: false refusal is replaced with a short side-by-side table",
      "can’t make a comparison" not in comparison_result.text
      and "| Technology parameter | Angel One | HDFC Bank Ltd. |" in comparison_result.text
      and 6 <= len(comparison_rows) <= 7,
      comparison_result.text[:1000])
check("comparison: HDFC evidence is cited and detailed appendix is omitted",
      any(source["company"] == "HDFC Bank Ltd." for source in comparison_result.tech_sources)
      and "Detailed annual-report evidence" not in comparison_result.text
      and "Coverage:" not in comparison_result.text)
check("comparison: concise output stays under 3,000 characters",
      len(comparison_result.text) < 3000,
      f"{len(comparison_result.text)} characters")

# 8. broad technology overview sends a substantial cross-parameter evidence set
CAPTURED.clear()
txt = ask("Technology parameters of Lenskart")
evidence_ids = re.findall(r"^\[S(\d+)\]", CAPTURED["system"], flags=re.M)
check("detail: broad overview includes a bounded set of detailed evidence points",
      55 <= len(evidence_ids) <= 60, f"{len(evidence_ids)} points")
check("detail: broad overview prompt requires every evidenced parameter",
      "EVERY parameter that has supplied evidence"
      in " ".join(CAPTURED["system"].split()))
tech_section = CAPTURED["system"].split("=== TECHNOLOGY EVIDENCE (annual report) ===", 1)[-1]
parameter_sections = re.findall(r"^\[([^\]\n]+)\]$", tech_section, flags=re.M)
check("detail: evidence is distributed across the full company profile",
      len(parameter_sections) >= 10, f"{len(parameter_sections)} parameters")
check("detail: broad technology context excludes unrelated financial/news data",
      "=== COMPANY FINANCIAL DATA ===" not in CAPTURED["system"]
      and "=== RECENT NEWS DATA ===" not in CAPTURED["system"])
check("tpm: completion reservation leaves room under Groq's 8k limit",
      CAPTURED["max_completion_tokens"] == 4500)
profile = kb.get_profile("Lenskart Solutions Ltd.")
distinct_point_count = len({
    " ".join(point.text.lower().split())
    for points in profile.points.values()
    for point in points
})
expected_detail_count = max(1, int(distinct_point_count * 0.8 + 0.5))
check("detail: answer includes the requested locally rendered evidence coverage",
      f"Coverage: {expected_detail_count} of {distinct_point_count} distinct extracted statements"
      in txt)
check("detail: evidence is presented in a parameter table with page citations",
      "| Technology parameter | Evidence highlights |" in txt
      and re.search(r"\| \*\*.+\*\* \| .+\[p\. \d+", txt) is not None
      and re.search(r"\[S\d+\]", txt) is None)
evidence_excerpts = [
    re.sub(r"\[[^\]]+\]", "", excerpt).strip()
    for line in txt.splitlines()
    if line.startswith("| **")
    for excerpt in line.split("|", 3)[2].rsplit("|", 1)[0].split("<br>")
]
check("detail: evidence table keeps individual highlights concise",
      bool(evidence_excerpts) and max(map(len, evidence_excerpts)) <= 160,
      f"max excerpt length: {max(map(len, evidence_excerpts), default=0)}")
check("detail: local appendix is not added to the Groq prompt",
      "Detailed annual-report evidence" not in CAPTURED["system"])
check("detail: annual-report appendix is absent from financial answers",
      "Detailed annual-report evidence" not in result.text)

# 9. oversized TPM request retries with both a smaller prompt and output cap
original_groq = cb._call_groq
retry_tokens = []

def groq_413_once(messages, effort, max_completion_tokens=4500):
    retry_tokens.append(max_completion_tokens)
    if len(retry_tokens) == 1:
        raise RuntimeError("413 tokens per minute limit exceeded")
    return fake_groq(messages, effort, max_completion_tokens)

cb._call_groq = groq_413_once
lenskart = company_df[company_df["Company"].str.contains("Lenskart", case=False, na=False)]
try:
    retry_result = cb.answer_question(
        "Technology parameters of Lenskart",
        company_df,
        news_df,
        kb,
        lenskart,
        history=[],
    )
finally:
    cb._call_groq = original_groq
check("tpm: 413 retry reduces the output reservation",
      retry_tokens == [4500, 3000], str(retry_tokens))
check("tpm: retry still returns an answer",
      bool(retry_result.text))

# 10. daily quota errors should not trigger futile retries
daily_calls = []

def groq_daily_quota(messages, effort, max_completion_tokens=4500):
    daily_calls.append(max_completion_tokens)
    raise RuntimeError(
        "429 rate_limit_exceeded: tokens per day (TPD) limit reached; "
        "try again in 9m52.704s."
    )

cb._call_groq = groq_daily_quota
try:
    cb.answer_question(
        "Technology parameters of Lenskart",
        company_df,
        news_df,
        kb,
        lenskart,
        history=[],
    )
    daily_quota_handled = False
except cb.DailyTokenQuotaError as exc:
    daily_quota_handled = "9m52.704s" in str(exc)
finally:
    cb._call_groq = original_groq
check("quota: daily TPD limit is reported with reset guidance",
      daily_quota_handled)
check("quota: daily TPD limit does not trigger retries",
      len(daily_calls) == 1, str(daily_calls))

# 11. healthcare, batch 2
CAPTURED.clear()
txt = ask("Divi's Laboratories R&D and technology partnerships")
check("batch2: cites Divi's PDF", "Divi" in txt and "Page" in txt)

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)

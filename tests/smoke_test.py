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
    if "=== MATCHING COMPANIES AND EVIDENCE ===" in system:
        sections = re.findall(
            r"^([^|\n]+)\s+\|\s+(.+)$",
            system,
            flags=re.M,
        )
        lines = []
        for company, section in sections:
            terms = list(dict.fromkeys(re.findall(r"\b(SAP|CRM):", section)))
            label = ", ".join(terms) if terms else "technology"
            lines.append(
                f"- **{company}** — Mentions {label} in a described business activity."
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="\n".join(lines)),
                    finish_reason="stop",
                )
            ]
        )
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

# ------------------------------------------------------------------ chatbot
at = AppTest.from_file(str(ROOT / "pages" / "2_Chatbot.py"), default_timeout=180).run()
check("chat page loads without exception", not at.exception, at.exception)


def ask(q):
    at.chat_input[0].set_value(q).run()
    return page_text(at)


# 1. technology question -> answer only, without citations or source panels
txt = ask("What is ICICI Bank's cybersecurity approach?")
check("tech: no exception", not at.exception, at.exception)
check("tech: technology evidence was put in the prompt", "=== TECHNOLOGY EVIDENCE" in CAPTURED["system"])
check("tech: unrelated financial and news context is omitted",
      "=== COMPANY FINANCIAL DATA ===" not in CAPTURED["system"]
      and "=== RECENT NEWS DATA ===" not in CAPTURED["system"])
check("tech: citations and page references are hidden",
      re.search(r"\[(?:S\d+|[^\]]*\bp\.\s*\d+)[^\]]*\]", txt, re.I) is None
      and "Page " not in txt and "Section:" not in txt)
check("tech: source panels are hidden",
      "Technology sources" not in txt and "Companies checked:" not in txt
      and "tech_matrix" not in txt and ".xlsx" not in txt)
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
check("news: no source panel is rendered",
      "News sources" not in txt and "Sources:" not in txt)

# 4. company without evidence -> told plainly
CAPTURED.clear()
txt = ask("Tell me about DLF technology")
check("no-evidence company: answer is displayed without a source panel",
      "Technology sources" not in txt and "Page " not in txt)

# 4a. named vendor terms route company-specific questions to technology context
CAPTURED.clear()
ask("Does ICICI Bank use SAP?")
check("vendor: SAP query uses company technology evidence",
      "=== TECHNOLOGY EVIDENCE" in CAPTURED["system"]
      and "=== COMPANY FINANCIAL DATA ===" not in CAPTURED["system"]
      and "=== RECENT NEWS DATA ===" not in CAPTURED["system"])

# 4b. unscoped technology searches return only explicit evidence matches
empty_matches = company_df.iloc[0:0].copy()
CAPTURED.clear()
global_tech_result = cb.answer_question(
    "Which companies reported SAP and CRM in their annual reports?",
    company_df,
    news_df,
    kb,
    empty_matches,
    history=[],
)

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
check("global tech search: all source companies match loaded evidence",
      {source["company"] for source in global_tech_result.tech_sources}
      == set().union(*expected_global_matches.values()))
check("global tech search: LLM is used to write the concise answer",
      "MATCHING COMPANIES AND EVIDENCE" in CAPTURED["system"]
      and "900-1,400 words" not in CAPTURED["system"]
      and CAPTURED["max_completion_tokens"] < 3000)
check("global tech search: all companies are included without page citations",
      all(name in global_tech_result.text
          for names in expected_global_matches.values() for name in names)
      and re.search(r"\[(?:S\d+|[^\]]*\bp\.\s*\d+)[^\]]*\]", global_tech_result.text, re.I) is None)
check("global tech search: concise response avoids copied long excerpts",
      max((len(line) for line in global_tech_result.text.splitlines()), default=0) <= 260)

check("intent: personal statements are not technology searches",
      cb.question_wants_technology("I am a girl") is False)
check("intent: EPM is recognized as technology",
      cb.question_wants_technology("EPM") is True
      and any(
          term == "EPM"
          for term, _ in cb._explicit_technology_terms("Which companies use EPM?")
      ))

matching_companies = sorted(set().union(*expected_global_matches.values()))
classifier_calls = []
original_classifier_call = cb._call_groq

def groq_unsupported(messages, effort, max_completion_tokens=4500):
    classifier_calls.append(messages)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="UNSUPPORTED"),
                finish_reason="stop",
            )
        ]
    )

cb._call_groq = groq_unsupported
try:
    unsupported_result = cb.answer_question(
        "I am a girl",
        company_df,
        news_df,
        kb,
        empty_matches,
        history=[],
    )
finally:
    cb._call_groq = original_classifier_call
check("intent: unsupported questions receive the focused redirect",
      unsupported_result.text
      == "I can't answer that. Please ask me about technology, company news, or financial information."
      and not unsupported_result.tech_sources
      and len(classifier_calls) == 1)

original_ask = cb.ask
cb.ask = lambda *args, **kwargs: (
    f"- **{matching_companies[0]}** — Mentions SAP in a business activity."
)
try:
    global_comparison_result = cb._search_technology_dataset(
        "Compare SAP and CRM across companies",
        kb,
    )
finally:
    cb.ask = original_ask
check("global tech comparison: returns a side-by-side company table",
      global_comparison_result.text.startswith(
          "| Company | Matching evidence |"
      )
      and all(name in global_comparison_result.text for name in matching_companies)
      and "Technology sources" not in global_comparison_result.text
      and "Page " not in global_comparison_result.text)

cb.ask = lambda *args, **kwargs: (
    f"- **{matching_companies[0]}** — Mentions SAP in a business activity."
)
try:
    partial_global_result = cb._search_technology_dataset(
        "Which companies reported SAP and CRM?",
        kb,
    )
finally:
    cb.ask = original_ask
has_fallback_page_reference = re.search(
    r"\bPage\s+\d+",
    partial_global_result.text,
    re.I,
) is not None
check("global tech search: omitted LLM rows are restored from matching evidence",
      all(name in partial_global_result.text for name in matching_companies))
check("global tech search: fallback summaries remain concise and source-free",
      max((len(line) for line in partial_global_result.text.splitlines()), default=0) <= 280
      and not has_fallback_page_reference
      and "[S" not in partial_global_result.text,
      f"max line={max((len(line) for line in partial_global_result.text.splitlines()), default=0)}, "
      f"page-ref={has_fallback_page_reference}, "
      f"citation={'[S' in partial_global_result.text}")

original_call_groq = cb._call_groq
retry_requests = []

def groq_413_once(messages, effort, max_completion_tokens=4500):
    retry_requests.append((len(messages[0]["content"]), max_completion_tokens))
    if len(retry_requests) == 1:
        raise RuntimeError("413 tokens per minute limit exceeded")
    return fake_groq(messages, effort, max_completion_tokens)

cb._call_groq = groq_413_once
try:
    retried_global_result = cb._search_technology_dataset("Which companies mention SAP?", kb)
finally:
    cb._call_groq = original_call_groq
check("global tech search: 413 retries once with shorter prompt and output budget",
      len(retry_requests) == 2
      and retry_requests[1][0] < retry_requests[0][0]
      and retry_requests[1][1] < retry_requests[0][1],
      str(retry_requests))
check("global tech search: 413 retry retains all matched companies",
      all(name in retried_global_result.text
          for name in expected_global_matches["SAP"]))

# 5. two companies (HDFC Bank is built from the extraction file)
CAPTURED.clear()
txt = ask("Compare technology of ICICI Bank and HDFC Bank")
check("compare: both companies in prompt",
      "ICICI Bank" in CAPTURED["system"] and "HDFC Bank" in CAPTURED["system"])
check("compare: answer contains no page citations",
      re.search(r"\[[^\]]*\bp\.\s*\d+[^\]]*\]", txt, re.I) is None)

# 6. unique short company name resolves and adds its sector leader
CAPTURED.clear()
query = "Compare Technology Parameters of ICICI and its sector leader"
detected_icici = detect_companies_in_text(company_df, query)
check("icici: unique short name resolves to ICICI Bank Ltd.",
      detected_icici["Company"].tolist() == ["ICICI Bank Ltd."],
      str(detected_icici["Company"].tolist()))
txt = ask(query)
check("icici: context includes ICICI Bank and HDFC Bank only",
      "ICICI Bank Ltd." in CAPTURED["system"]
      and "HDFC Bank Ltd." in CAPTURED["system"]
      and "Tata Consultancy Services Ltd." not in CAPTURED["system"])
check("icici: answer has no company/source caption",
      "Companies checked:" not in txt and "Sources:" not in txt)

# 7. technology topic must not be mistaken for the Technology sector leader
CAPTURED.clear()
txt = ask("Compare technology parameters of Lenskart Solutions and its sector leader")
check("scope: requested Lenskart and its Healthcare leader are included",
      "Lenskart Solutions Ltd." in CAPTURED["system"]
      and "Divi's Laboratories Ltd." in CAPTURED["system"])
check("scope: unrelated Technology sector leader is excluded",
      "Tata Consultancy Services Ltd." not in CAPTURED["system"])
check("scope: answer is not accompanied by source details",
      "Technology sources" not in txt and "Page " not in txt)
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
      bool(summarized_comparison.text)
      and "Detailed annual-report evidence" not in summarized_comparison.text)
check("comparison: citations are hidden while evidence remains internally tracked",
      re.search(r"\[[^\]]*\bp\.\s*\d+[^\]]*\]", summarized_comparison.text, re.I) is None
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
check("comparison: concise output stays under 3,500 characters",
      len(comparison_result.text) < 3500,
      f"{len(comparison_result.text)} characters")

# 8. broad technology overview sends a substantial cross-parameter evidence set
CAPTURED.clear()
txt = ask("Technology parameters of Lenskart")
evidence_ids = re.findall(r"^\[S(\d+)\]", CAPTURED["system"], flags=re.M)
check("detail: broad overview includes a bounded set of detailed evidence points",
      55 <= len(evidence_ids) <= 110, f"{len(evidence_ids)} points")
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
check("detail: answer contains no citation or page references",
      re.search(r"\[(?:S\d+|[^\]]*\bp\.\s*\d+)[^\]]*\]", txt, re.I) is None
      and "Page " not in txt)
check("detail: no raw evidence appendix is appended to the answer",
      "Detailed annual-report evidence" not in txt
      and "Coverage:" not in txt)

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
check("batch2: answer does not expose a source panel",
      "Technology sources" not in txt and "Page " not in txt)

print()
print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
sys.exit(1 if failures else 0)

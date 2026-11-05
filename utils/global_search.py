"""
Global (no company named) question handling.

Used by the chat page when the question does not name a company.

What it does
------------
1. Off-topic questions ("I am a girl", "hello", "write a poem") get a polite
   "ask me about technology, news or financials" message instead of a junk
   keyword match.
2. Technology / vendor questions ("SAP", "CRM", "EPM", "which companies use
   Oracle", "SAP vs Oracle") are answered by EXACT term matching against the
   annual-report evidence (whole-word, so "girl" can never match "AI") and the
   answer is a direct list of companies.
3. Financial / news questions with no company get a short "name a company"
   message (the data needed to answer them is per company).

How the question is understood
------------------------------
* Rules first: a built-in vendor / technology lexicon plus any ALL-CAPS token
  (so unknown acronyms such as "EPM" or "WMS" work with no code change).
* For longer natural-language questions, or when no rule matches, a small LLM
  call (same Groq model as the chatbot) turns the question into search groups
  and decides whether it is on-topic at all. If the LLM is unavailable the
  rules are used on their own.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from utils.chatbot import (
    ChatAnswer,
    get_api_key,
    get_client,
    get_model,
    question_wants_financial,
    question_wants_news,
)
from utils.company_keys import compute_company_key, normalize_text, strip_company_suffix
from utils.tech_knowledge import TechKnowledgeBase

# ------------------------------------------------------------
# Messages
# ------------------------------------------------------------

OFF_TOPIC_MESSAGE = (
    "I can't help with that one. I can answer questions about **technology**, "
    "**news** and **financials** of the listed companies, for example:\n\n"
    "- *Which companies mention SAP?*\n"
    "- *Compare SAP and Oracle across companies*\n"
    "- *Latest news on Infosys*\n"
    "- *Compare TCS and Infosys revenue*"
)

NEED_COMPANY_MESSAGE = (
    "Financial and news answers are company-specific. Please mention a company "
    "name, NSE symbol or sector, for example *'Infosys revenue and EBITDA "
    "margin'* or *'Healthcare sector leader news'*.\n\n"
    "For technology you can ask without a company, e.g. *'Which companies "
    "mention SAP?'*"
)

NEED_TERM_MESSAGE = (
    "Please tell me which technology or vendor to look for (for example "
    "*SAP*, *CRM*, *cloud*, *cybersecurity*), or name a company, NSE symbol "
    "or sector."
)

TABLE_LIMIT = 40          # companies shown with evidence in the table
NAME_LIST_LIMIT = 150     # extra company names listed after the table
COMPARE_LIST_LIMIT = 40   # names shown per bucket in a comparison

# ------------------------------------------------------------
# Vendor / technology lexicon
#   (label, words a user may type, phrases searched in the evidence)
# ------------------------------------------------------------

_LEXICON: list[tuple[str, list[str], list[str]]] = [
    ("SAP", ["sap"], ["SAP", "S/4HANA", "S4HANA"]),
    ("Oracle", ["oracle"], ["Oracle"]),
    ("Salesforce", ["salesforce"], ["Salesforce"]),
    ("Microsoft", ["microsoft"], ["Microsoft"]),
    ("Azure", ["azure"], ["Azure"]),
    ("AWS", ["aws", "amazon web services"], ["AWS", "Amazon Web Services"]),
    ("Google Cloud", ["google cloud", "gcp"], ["Google Cloud", "GCP"]),
    ("Workday", ["workday"], ["Workday"]),
    ("ServiceNow", ["servicenow"], ["ServiceNow"]),
    ("Snowflake", ["snowflake"], ["Snowflake"]),
    ("Databricks", ["databricks"], ["Databricks"]),
    ("Power BI", ["power bi", "powerbi"], ["Power BI", "PowerBI"]),
    ("Tableau", ["tableau"], ["Tableau"]),
    ("Kubernetes", ["kubernetes"], ["Kubernetes"]),
    ("CRM", ["crm", "customer relationship management"],
     ["CRM", "customer relationship management"]),
    ("ERP", ["erp", "enterprise resource planning"],
     ["ERP", "enterprise resource planning"]),
    ("EPM", ["epm", "enterprise performance management",
             "corporate performance management"],
     ["EPM", "enterprise performance management",
      "corporate performance management", "Hyperion", "Anaplan", "OneStream"]),
    ("HRMS / HCM", ["hrms", "hcm", "human capital management"],
     ["HRMS", "HCM", "human capital management", "SuccessFactors"]),
    ("SCM", ["scm", "supply chain management"],
     ["SCM", "supply chain management"]),
    ("WMS", ["wms", "warehouse management"],
     ["WMS", "warehouse management"]),
    ("MES", ["mes", "manufacturing execution system"],
     ["MES", "manufacturing execution system"]),
    ("SCADA", ["scada"], ["SCADA"]),
    ("RPA", ["rpa", "robotic process automation"],
     ["RPA", "robotic process automation"]),
    ("IoT", ["iot", "internet of things"], ["IoT", "internet of things"]),
    ("Blockchain", ["blockchain"], ["blockchain"]),
    ("Generative AI", ["generative ai", "genai", "gen ai"],
     ["generative AI", "GenAI", "Gen AI", "LLM", "large language model"]),
    ("AI", ["ai", "artificial intelligence"],
     ["AI", "artificial intelligence"]),
    ("Machine learning", ["machine learning", "ml"],
     ["machine learning", "ML"]),
    ("Data analytics", ["data analytics", "analytics"],
     ["data analytics", "analytics"]),
    ("Cloud", ["cloud"], ["cloud"]),
    ("Cybersecurity", ["cybersecurity", "cyber security"],
     ["cybersecurity", "cyber security", "cyber-security", "SOC", "SIEM"]),
    ("Digital twin", ["digital twin"], ["digital twin"]),
    ("5G", ["5g"], ["5G"]),
    ("Automation", ["automation"], ["automation"]),
    ("Digital transformation", ["digital transformation"],
     ["digital transformation"]),
]

_ALLCAPS_STOP = {
    "I", "A", "OK", "US", "UK", "USA", "IT", "FY", "NSE", "BSE", "PM", "AM",
    "AND", "OR", "THE", "ALL", "HI", "YES", "NO", "FAQ", "PDF", "ROE",
    "ROCE", "EPS", "PAT", "LTP", "EBITDA", "VS",
}

_SMALLTALK = {
    "hi", "hello", "hey", "thanks", "thank", "you", "ok", "okay", "bye", "yes",
    "no", "help", "good", "morning", "evening", "afternoon", "who", "are",
    "what", "is", "your", "name", "how", "test", "testing",
}

_COMPARE_RX = re.compile(
    r"\bcompare\b|\bcomparison\b|\bvs\.?\b|\bversus\b|\bdifference between\b"
    r"|\bagainst\b", re.I)
_OR_RX = re.compile(r"\bor\b", re.I)
_LEADER_RX = re.compile(r"\bleaders?\b", re.I)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

_B = r"(?<![A-Za-z0-9])"
_E = r"(?![A-Za-z0-9])"


def _phrase_regex(phrase: str) -> re.Pattern:
    """Whole-word regex. Short ALL-CAPS tokens (SAP, CRM, AI) are case-sensitive."""
    p = phrase.strip()
    flags = 0 if (len(p) <= 4 and p.isupper()) else re.IGNORECASE
    return re.compile(_B + re.escape(p) + r"(?:s)?" + _E, flags)


class _Group:
    """One concept to look for: label + several exact phrases."""

    def __init__(self, label: str, phrases: list[str]):
        self.label = label
        self.phrases = [p for p in dict.fromkeys(phrases) if p and p.strip()]
        self._rx = [_phrase_regex(p) for p in self.phrases]

    def search(self, text: str):
        best = None
        for rx in self._rx:
            m = rx.search(text)
            if m and (best is None or m.start() < best.start()):
                best = m
        return best


def _extract_rule_groups(question: str) -> list[_Group]:
    """Find vendor / technology terms in the question using rules only."""
    work = question
    found: list[tuple[int, _Group]] = []

    triggers = []
    for label, words, phrases in _LEXICON:
        for w in words:
            triggers.append((w, label, phrases))
    triggers.sort(key=lambda t: len(t[0]), reverse=True)  # longest first

    taken_labels = set()
    for word, label, phrases in triggers:
        if label in taken_labels:
            continue
        rx = re.compile(_B + re.escape(word) + _E, re.I)
        m = rx.search(work)
        if not m:
            continue
        taken_labels.add(label)
        found.append((m.start(), _Group(label, phrases)))
        work = work[:m.start()] + " " * (m.end() - m.start()) + work[m.end():]

    # Unknown ALL-CAPS acronyms typed by the user (EPM, WMS, ...) - from the
    # original case of the question.
    for m in re.finditer(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9&/\-]{1,9}(?![A-Za-z0-9])", work):
        token = m.group(0)
        if token in _ALLCAPS_STOP or token.isdigit():
            continue
        found.append((m.start(), _Group(token, [token])))

    found.sort(key=lambda x: x[0])
    return [g for _, g in found]



def vendor_mention_only(question: str, explicit_companies: pd.DataFrame, detect_fn) -> bool:
    """
    True when the "company" the detector found is really just a vendor word.

    "compare SAP and Oracle" detects the listed company *Oracle Financial
    Services Software* only because of the word "Oracle". That should be a
    vendor search, not a company question. We treat it as a vendor mention
    when ALL of these hold:
      * a vendor / technology term is in the question,
      * the question is not a financial / news question (those need a company),
      * no detected company's full name is typed out in the question, and
      * nothing is still detected once the vendor words are removed.
    """
    if explicit_companies is None or explicit_companies.empty:
        return False
    q = " ".join(str(question or "").split())
    if not _extract_rule_groups(q):
        return False
    if question_wants_financial(q) or question_wants_news(q):
        return False

    nq = normalize_text(q)
    col = "Company" if "Company" in explicit_companies.columns else None
    if col:
        for name in explicit_companies[col].dropna():
            full = strip_company_suffix(normalize_text(name))
            if full and re.search(rf"(?<![a-z0-9]){re.escape(full)}(?![a-z0-9])", nq):
                return False

    stripped = q
    for _label, words, _phrases in _LEXICON:
        for w in words:
            stripped = re.sub(_B + re.escape(w) + _E, " ", stripped, flags=re.I)
    try:
        remaining = detect_fn(stripped)
    except Exception:
        return False
    return remaining is None or remaining.empty



def kb_only_company_rows(question: str, kb: TechKnowledgeBase, company_df: pd.DataFrame) -> pd.DataFrame:
    """
    Companies that have annual-report technology evidence but are NOT in
    company_master.csv (e.g. Infosys), found by their name in the question.

    The normal company detector only reads company_master.csv, so "AI plans of
    Infosys" would otherwise be treated as a company-less question. Rows are
    returned in company_df's column layout (financial columns empty), so the
    normal company answer path can use them; financial figures then show as
    unavailable instead of being invented.
    """
    empty = company_df.iloc[0:0].copy() if company_df is not None else pd.DataFrame()
    if kb is None or not kb.profiles or company_df is None:
        return empty
    master_keys = {compute_company_key(n) for n in company_df.get("Company", pd.Series(dtype=str)).dropna()}
    nq = f" {normalize_text(question)} "
    found = []
    for key, profile in kb.profiles.items():
        if key in master_keys:
            continue
        name = strip_company_suffix(normalize_text(profile.company))
        if len(name) >= 3 and f" {name} " in nq:
            found.append((name, profile))
    # keep the longest match when one name sits inside another
    found.sort(key=lambda x: len(x[0]), reverse=True)
    kept: list = []
    for name, profile in found:
        if any(name in k[0] for k in kept):
            continue
        kept.append((name, profile))
    if not kept:
        return empty
    rows = []
    for _name, profile in kept:
        row = {c: None for c in company_df.columns}
        row["Company"] = profile.company
        if "Company_Key" in row:
            row["Company_Key"] = profile.key
        rows.append(row)
    return pd.DataFrame(rows, columns=company_df.columns)


# ------------------------------------------------------------
# LLM router (understands meaning; used for natural-language questions)
# ------------------------------------------------------------

_ROUTER_PROMPT = """You route questions for a corporate-intelligence assistant
covering about 450 listed Indian companies. The assistant has three kinds of
data: annual-report TECHNOLOGY evidence, company FINANCIALS, and company NEWS.

Reply with ONE JSON object and nothing else:
{
 "intent": "technology_search" | "financial_or_news" | "off_topic",
 "mode": "all" | "any" | "compare",
 "sector": null or one of: __SECTORS__,
 "groups": [ {"label": "short name", "any_of": ["exact word or phrase", "..."]} ]
}

Definitions
- off_topic: greetings, personal statements ("I am a girl", "I am hungry"),
  chit-chat, general knowledge, coding help, anything that is not about
  companies' technology, news or financials. Words such as "girl" or "boy" in a
  personal statement are NOT technology topics.
- technology_search: asks which companies use / mention / plan / adopt /
  invest in a technology, vendor, product, system or capability.
- financial_or_news: asks about revenue, profit, ratios, rankings, news or
  announcements without naming a company.
Rules for "groups" (technology_search only)
- One group per concept the user wants. "any_of" lists the exact words,
  product names, abbreviations and synonyms that would literally appear in an
  annual report for that concept (max 8). Include the user's own words.
- mode "all": a company must match every group. mode "any": any group.
  mode "compare": the user compares the groups against each other.
- Use "sector" only if the user restricts to an industry (banks -> Financial
  Services, pharma -> Healthcare). Otherwise null.
- Max 4 groups. For off_topic or financial_or_news use "groups": [].
"""


def _llm_route(question: str, sectors: list[str]) -> dict | None:
    if not get_api_key():
        return None
    system = _ROUTER_PROMPT.replace(
        "__SECTORS__", json.dumps(sectors) if sectors else "[]"
    )
    kwargs = dict(
        model=get_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
        temperature=0,
        max_completion_tokens=900,
        extra_body={"reasoning_effort": "low"},
    )
    try:
        client = get_client()
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            if "reasoning_effort" in str(exc).lower():
                kwargs.pop("extra_body", None)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise
        raw = resp.choices[0].message.content or ""
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
    except Exception:
        return None

    intent = str(data.get("intent", "")).strip().lower()
    if intent not in {"technology_search", "financial_or_news", "off_topic"}:
        return None
    mode = str(data.get("mode", "all")).strip().lower()
    if mode not in {"all", "any", "compare"}:
        mode = "all"
    groups = []
    for g in (data.get("groups") or [])[:4]:
        if not isinstance(g, dict):
            continue
        phrases = [str(p).strip() for p in (g.get("any_of") or []) if str(p).strip()][:8]
        label = str(g.get("label") or (phrases[0] if phrases else "")).strip()
        phrases = [p for p in phrases if len(p) >= 2]
        if label and phrases:
            groups.append(_Group(label, phrases))
    sector = data.get("sector")
    sector = sector if isinstance(sector, str) and sector in sectors else None
    return {"intent": intent, "mode": mode, "groups": groups, "sector": sector}


# ------------------------------------------------------------
# Searching the evidence
# ------------------------------------------------------------

def _sector_keys(company_df: pd.DataFrame, sector_names: list[str]) -> set[str] | None:
    if not sector_names or company_df is None or company_df.empty:
        return None
    if "Sector" not in company_df.columns or "Company" not in company_df.columns:
        return None
    wanted = {s.strip().lower() for s in sector_names}
    mask = company_df["Sector"].astype(str).str.strip().str.lower().isin(wanted)
    # Recompute keys from the company name (same function the knowledge base
    # uses) so they always line up with the technology profiles.
    keys = {compute_company_key(n) for n in company_df.loc[mask, "Company"].dropna()}
    return keys or None


_PAGE_REF = re.compile(r"\s*\(\s*pp?\.\s*\d+[^)]*\)?")
_CANON_DROP = re.compile(
    r"\b(ltd|limited|co|company|corporation|corp|pvt|private|the|plc|inc)\b")


def _canon(name: str) -> str:
    """Merge the same company spelled two ways ('Indian Hotels Co. Ltd.' / 'Indian Hotels Company')."""
    n = str(name).lower().replace("&", " and ")
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = _CANON_DROP.sub(" ", n)
    return " ".join(n.split())


def _plural(n: int, word: str = "company", plural: str = "companies") -> str:
    return f"{n} {word if n == 1 else plural}"


def _scan(kb: TechKnowledgeBase, groups: list[_Group], allowed: set[str] | None):
    """hits[g][company_key] -> list of (point_text, match). Same company under two spellings is merged."""
    hits: list[dict[str, list]] = [dict() for _ in groups]
    canon_to_key: dict[str, str] = {}
    scope_keys: set[str] = set()
    for key, profile in kb.profiles.items():
        if allowed is not None and key not in allowed:
            continue
        canon = _canon(profile.company)
        rep = canon_to_key.setdefault(canon, key)
        scope_keys.add(rep)
        seen = set()
        for points in profile.points.values():
            for point in points:
                text = _PAGE_REF.sub("", point.text or "").strip()
                norm = " ".join(text.lower().split())
                if not text or norm in seen:
                    continue
                for gi, group in enumerate(groups):
                    m = group.search(text)
                    if m:
                        hits[gi].setdefault(rep, []).append((text, m))
                        seen.add(norm)
    return hits, len(scope_keys)


def _snippet(text: str, match: re.Match, before: int = 90, after: int = 150) -> str:
    text = " ".join(str(text).split())
    # the match positions refer to the original text; re-find in collapsed text
    m2 = re.search(re.escape(match.group(0)), text)
    if not m2:
        out = text[: before + after]
        return out + ("…" if len(text) > len(out) else "")
    s = max(0, m2.start() - before)
    e = min(len(text), m2.end() + after)
    chunk = text[s:m2.start()] + "**" + m2.group(0) + "**" + text[m2.end():e]
    chunk = chunk.replace("|", "\\|")
    return ("…" if s > 0 else "") + chunk + ("…" if e < len(text) else "")


def _best_evidence(entries: list) -> tuple[str, re.Match]:
    # prefer a readable mid-length statement that contains the term
    entries = sorted(entries, key=lambda e: (abs(len(e[0]) - 220)))
    return entries[0]


def _names(keys, kb: TechKnowledgeBase) -> list[str]:
    return sorted((kb.profiles[k].company for k in keys), key=str.lower)


def _fmt_names(names: list[str], limit: int) -> str:
    shown = ", ".join(names[:limit])
    extra = len(names) - limit
    return shown + (f" … and {extra} more" if extra > 0 else "")


def _scope_note(sector_names, scope) -> str:
    if sector_names:
        return f" in the **{', '.join(sector_names)}** sector ({scope} companies with evidence)"
    return f" (searched {scope} companies with annual-report evidence)"


def _no_match_text(groups: list[_Group], sector_names, scope: int) -> str:
    labels = ", ".join(f"**{g.label}**" for g in groups)
    checked = "; ".join(
        f"{g.label}: " + ", ".join(g.phrases) for g in groups if len(g.phrases) > 1
    )
    text = (
        f"I couldn't find {labels} in the collected annual-report evidence"
        f"{_scope_note(sector_names, scope)}. This doesn't prove that no company "
        "uses it. It only means the loaded summaries don't mention it."
    )
    if checked:
        text += f"\n\nTerms I searched: {checked}."
    return text


def _render_search(groups, mode, hits, scope, kb, sector_names) -> str:
    key_sets = [set(h) for h in hits]
    if mode == "any":
        keys = set().union(*key_sets)
    else:
        keys = set.intersection(*key_sets) if key_sets else set()

    if not keys:
        if len(groups) > 1 and mode == "all":
            parts = "; ".join(
                f"**{g.label}**: {_plural(len(ks))}" for g, ks in zip(groups, key_sets)
            )
            return (
                "No single company mentions all of "
                + " and ".join(f"**{g.label}**" for g in groups)
                + f" together in the loaded evidence{_scope_note(sector_names, scope)}. "
                f"Separately: {parts}. Ask for each one on its own to see the list."
            )
        return _no_match_text(groups, sector_names, scope)

    def score(k):
        return sum(len(h.get(k, [])) for h in hits)

    ordered = sorted(keys, key=lambda k: (-score(k), kb.profiles[k].company.lower()))
    label = (" and " if mode == "all" else " or ").join(f"**{g.label}**" for g in groups)
    verb = "mention" if len(groups) == 1 else ("mention both" if mode == "all" and len(groups) == 2 else "match")
    lines = [
        f"### Companies that {verb} {label}",
        f"**{_plural(len(ordered))}**{_scope_note(sector_names, scope)}. "
        "Ranked by how often the term appears in their annual-report evidence.",
    ]
    if len(groups) == 1:
        searched = ", ".join(groups[0].phrases) if len(groups[0].phrases) > 1 else ""
    else:
        searched = "; ".join(f"{g.label}: " + ", ".join(g.phrases) for g in groups if len(g.phrases) > 1)
    if searched:
        lines += ["", f"*Searched for: {searched}.*"]
    lines.append("")
    show_match_col = len(groups) > 1
    if show_match_col:
        lines += ["| Company | Matches | What the annual report says |", "|---|---|---|"]
    else:
        lines += ["| Company | What the annual report says |", "|---|---|"]

    for k in ordered[:TABLE_LIMIT]:
        entries = []
        matched = []
        for g, h in zip(groups, hits):
            if k in h:
                matched.append(g.label)
                entries.extend(h[k])
        text, m = _best_evidence(entries)
        name = kb.profiles[k].company.replace("|", "\\|")
        snip = _snippet(text, m)
        if show_match_col:
            lines.append(f"| {name} | {', '.join(matched)} | {snip} |")
        else:
            lines.append(f"| {name} | {snip} |")

    rest = ordered[TABLE_LIMIT:]
    if rest:
        lines += [
            "",
            f"**Also mentioned by ({len(rest)}):** "
            + _fmt_names(_names(rest, kb), NAME_LIST_LIMIT),
        ]
    lines += [
        "",
        "*A company missing from this list simply isn't mentioned in the loaded "
        "evidence; it doesn't prove the company doesn't use the technology.*",
    ]
    return "\n".join(lines)


def _render_compare(groups, hits, scope, kb, sector_names) -> str:
    key_sets = [set(h) for h in hits]
    both = set.intersection(*key_sets) if key_sets else set()
    title = " vs ".join(g.label for g in groups)
    lines = [
        f"### Comparison: {title}",
        f"Based on annual-report evidence{_scope_note(sector_names, scope)}.",
        "",
        "| Item | Companies mentioning it | Share of companies searched |",
        "|---|---|---|",
    ]
    for g, ks in zip(groups, key_sets):
        pct = f"{(100 * len(ks) / scope):.0f}%" if scope else "n/a"
        lines.append(f"| {g.label} | {len(ks)} | {pct} |")
    both_pct = f"{(100 * len(both) / scope):.0f}%" if scope else "n/a"
    lines.append(f"| Mention all of them | {len(both)} | {both_pct} |")
    lines.append("")

    if len(both):
        lines.append(
            f"**Companies mentioning all of {title.replace(' vs ', ', ')} "
            f"({len(both)}):** " + _fmt_names(_names(both, kb), COMPARE_LIST_LIMIT)
        )
        lines.append("")
    for g, ks in zip(groups, key_sets):
        # companies that mention this item but not (all of) the others
        others = set().union(*[s for s2, s in zip(groups, key_sets) if s2 is not g]) if len(groups) > 1 else set()
        exclusive = ks - others
        lines.append(
            f"**Only {g.label} ({len(exclusive)}):** "
            + (_fmt_names(_names(exclusive, kb), COMPARE_LIST_LIMIT) if exclusive else "none")
        )
        lines.append("")
    lines.append(
        "*Counts reflect what the loaded annual-report evidence mentions, not "
        "necessarily every system a company runs.*"
    )
    return "\n".join(lines)


def _run_search(groups, mode, kb, company_df, sector_names) -> ChatAnswer:
    allowed = _sector_keys(company_df, sector_names)
    hits, scope = _scan(kb, groups, allowed)
    if mode == "compare" and len(groups) >= 2:
        text = _render_compare(groups, hits, scope, kb, sector_names)
    else:
        text = _render_search(groups, "any" if mode == "any" else "all", hits, scope, kb, sector_names)
    return ChatAnswer(text=text, technology_used=True)


# ------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------

def answer_global_question(
    question: str,
    company_df: pd.DataFrame,
    kb: TechKnowledgeBase,
    sector_names: list[str] | None = None,
    use_llm: bool = True,
) -> ChatAnswer | None:
    """
    Answer a question that does not name a company.

    Returns a ChatAnswer, or None when the normal company/sector-leader flow
    should handle the question (e.g. "Healthcare sector leader technology").
    """
    q = " ".join(str(question or "").split())
    if not q:
        return ChatAnswer(text="Please enter a question.")
    if kb is None or not kb.profiles:
        return ChatAnswer(text="No technology evidence is loaded, so I can't search across companies.")

    sector_names = list(sector_names or [])
    if sector_names and _LEADER_RX.search(q):
        return None  # explicit sector-leader question -> existing flow

    sectors = []
    if company_df is not None and "Sector" in company_df.columns:
        sectors = sorted(company_df["Sector"].dropna().astype(str).unique())

    compare = bool(_COMPARE_RX.search(q))
    rule_groups = _extract_rule_groups(q)

    def mode_for(groups):
        if compare and len(groups) >= 2:
            return "compare"
        if len(groups) >= 2 and _OR_RX.search(q):
            return "any"
        return "all"

    # ---- 1. explicit vendor / technology words found by rules ------------
    if rule_groups:
        groups, mode, sector_scope = rule_groups, mode_for(rule_groups), sector_names
        # longer natural-language questions: let the LLM refine the groups
        if use_llm and len(q.split()) > 4:
            route = _llm_route(q, sectors)
            if route and route["intent"] == "technology_search" and route["groups"]:
                groups, mode = route["groups"], route["mode"]
                if route["sector"] and not sector_scope:
                    sector_scope = [route["sector"]]
        return _run_search(groups, mode, kb, company_df, sector_scope)

    # ---- 2. financial / news without any company --------------------------
    if question_wants_financial(q) or question_wants_news(q):
        if sector_names:
            return None
        return ChatAnswer(text=NEED_COMPANY_MESSAGE)

    # ---- 3. understand the question with the LLM --------------------------
    route = _llm_route(q, sectors) if use_llm else None
    if route:
        if route["intent"] == "off_topic":
            return ChatAnswer(text=OFF_TOPIC_MESSAGE)
        if route["intent"] == "financial_or_news":
            return None if sector_names else ChatAnswer(text=NEED_COMPANY_MESSAGE)
        if route["groups"]:
            sector_scope = sector_names or ([route["sector"]] if route["sector"] else [])
            return _run_search(route["groups"], route["mode"], kb, company_df, sector_scope)
        return ChatAnswer(text=NEED_TERM_MESSAGE)

    # ---- 4. LLM unavailable: conservative rule fallback -------------------
    if sector_names:
        return None
    words = re.findall(r"[A-Za-z][A-Za-z0-9+&/\-]*", q)
    if (
        1 <= len(words) <= 2
        and len(q.split()) <= 2
        and not any(w.lower() in _SMALLTALK for w in words)
    ):
        # a bare one/two-word term such as "Anaplan": look it up literally
        group = _Group(" ".join(words), [" ".join(words)])
        hits, _ = _scan(kb, [group], _sector_keys(company_df, sector_names))
        return _run_search([group], "all", kb, company_df, sector_names)
    if re.search(
        r"technolog|\btech\b|digital|software|platform|system|vendor|innovation|"
        r"\bcompanies\b|\bwhich\b",
        q, re.I,
    ):
        return ChatAnswer(text=NEED_TERM_MESSAGE)
    return ChatAnswer(text=OFF_TOPIC_MESSAGE)

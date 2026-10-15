
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from utils.company_keys import compute_company_key


# ============================================================
# PARAMETERS (the 15 columns of the new workbooks)
# ============================================================

TECHNOLOGY_PARAMETERS = [
    "Current Technology Adoption",
    "Digital Transformation",
    "R&D",
    "Emerging Technologies",
    "Technology Partnerships",
    "Technology Investments",
    "Cloud Adoption",
    "Automation",
    "Cybersecurity",
    "Future Technology Roadmaps",
    "Technology Pain Areas",
    "AI",
    "Tech Risk",
    "Platforms & Systems",
    "Talent & Skills",
]

# Words in a question that point at a parameter. Used ONLY to prioritise
# which evidence is placed in front of the model - never to refuse a question.
PARAMETER_HINTS = {
    "Current Technology Adoption": r"technology adoption|tech stack|current technolog|technolog(y|ies) (used|use|adopted)|what technolog|which technolog",
    "Digital Transformation": r"digital|digiti[sz]|transformation|online|mobile app|fintech",
    "R&D": r"\br ?(and|&) ?d\b|research|innovation|laborator|patent|pipeline|development",
    "Emerging Technologies": r"emerging|blockchain|\biot\b|internet of things|quantum|metaverse|5g|robotic|drone|new technolog",
    "Technology Partnerships": r"partner|collaborat|alliance|tie[- ]?up|joint venture|\bmou\b|vendor|ecosystem",
    "Technology Investments": r"invest|capex|capital expenditure|spend|budget|outlay",
    "Cloud Adoption": r"cloud|aws|azure|saas|data cent(er|re)|hosting",
    "Automation": r"automat|\brpa\b|robotic process|straight[- ]through|workflow",
    "Cybersecurity": r"cyber|security|breach|hack|phishing|ransomware|soc\b|data protection|privacy|infosec",
    "Future Technology Roadmaps": r"roadmap|future|plan|upcoming|strategy|outlook|next (year|phase)|going forward|vision",
    "Technology Pain Areas": r"pain|challenge|gap|weakness|issue|problem|bottleneck|legacy|limitation|concern|shortfall",
    "AI": r"\bai\b|artificial intelligence|gen ?ai|generative|machine learning|\bml\b|\bllm\b|chatbot|analytics|predictive",
    "Tech Risk": r"\brisk|outage|downtime|disruption|resilien|business continuity|third[- ]party|vendor risk|failure",
    "Platforms & Systems": r"platform|system|erp|\bsap\b|core banking|infrastructure|architecture|software|application|\bapi\b|\bit\b",
    "Talent & Skills": r"talent|skill|hiring|training|upskill|workforce|employee|learning|capabilit",
}

_STOPWORDS = set(
    "a an and are as at be by for from has have how in is it its of on or "
    "that the their this to was were what which who will with about tell me "
    "give show explain does do did company companies technology technologies "
    "tech please can you any all more most also than then into over under "
    "vs versus compare comparison between across both each".split()
)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class Block:
    """One page-level evidence block from a technology_extraction workbook."""
    pdf: str
    page: int
    section: str
    score: float | None
    text: str
    parameter: str
    extraction_file: str


@dataclass
class Point:
    """One summary point (a technology fact) with its report page numbers."""
    parameter: str
    text: str
    pages: list[int]
    claim_id: str = ""


@dataclass
class TechProfile:
    key: str
    company: str
    summary_file: str
    extraction_file: str
    derived: bool = False          # True -> built from extraction text, not from a summary file
    points: dict = field(default_factory=dict)   # parameter -> list[Point]

    @property
    def total_points(self) -> int:
        return sum(len(v) for v in self.points.values())

    def parameters_with_evidence(self) -> list[str]:
        return [p for p in TECHNOLOGY_PARAMETERS if self.points.get(p)]

    def parameters_without_evidence(self) -> list[str]:
        return [p for p in TECHNOLOGY_PARAMETERS if not self.points.get(p)]


# ============================================================
# PARSING HELPERS
# ============================================================

# A block header always looks like:   Source: x.pdf \n Page: 12 \n Section: y \n
# ("Source:" appearing inside running text is NOT followed by "Page: N", so it
# is never mistaken for a header.)
_HEADER = re.compile(
    r"Source:[ \t]*(?P<pdf>[^\n]+?)[ \t]*\n"
    r"Page:[ \t]*(?P<page>\d+)[ \t]*\n"
    r"Section:[ \t]*(?P<section>[^\n]*)\n"
)
_SCORE = re.compile(r"Combined Retrieval Score:\s*([0-9.]+)")
_NUMBERING = re.compile(r"^\s*\d+\s*[.)]\s*")

NOT_AVAILABLE_MARKERS = ("not available in collected data", "no evidence available")


def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_evidence_cell(cell, parameter: str, extraction_file: str) -> list[Block]:
    """Split one 'Technology Evidence' cell into its page-level blocks."""
    text = _clean(cell)
    if not text or text.lower().startswith(NOT_AVAILABLE_MARKERS):
        return []

    headers = list(_HEADER.finditer(text))
    blocks = []

    for i, m in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[m.end():end]

        score_match = _SCORE.search(body)
        score = float(score_match.group(1)) if score_match else None

        evidence = ""
        marker = "Original Evidence:"
        if marker in body:
            evidence = body.split(marker, 1)[1]
        evidence = _collapse(evidence)

        blocks.append(
            Block(
                pdf=m.group("pdf").strip(),
                page=int(m.group("page")),
                section=_collapse(m.group("section")),
                score=score,
                text=evidence,
                parameter=parameter,
                extraction_file=extraction_file,
            )
        )

    return blocks


def _split_sentences(text: str) -> list[str]:
    text = _collapse(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\u2022\"'(])", text)
    return [p.strip() for p in parts if p.strip()]


def _batch_id(path: Path) -> str:
    """evidence_summary.xlsx -> '1', evidence_summary2.xlsx -> '2'."""
    digits = re.findall(r"(\d+)\.xlsx$", path.name, flags=re.I)
    return digits[-1] if digits else "1"


def discover_file_pairs(data_dir: Path) -> list[tuple[Path, Path | None]]:
    """Pair each evidence_summary*.xlsx with its technology_extraction*.xlsx."""
    summaries = sorted(Path(data_dir).glob("evidence_summary*.xlsx"), key=_batch_id)
    extractions = {
        _batch_id(p): p for p in Path(data_dir).glob("technology_extraction*.xlsx")
    }
    return [(s, extractions.get(_batch_id(s))) for s in summaries]


# ============================================================
# KNOWLEDGE BASE
# ============================================================

class TechKnowledgeBase:

    def __init__(self):
        self.profiles: dict[str, TechProfile] = {}
        # company key -> page -> [Block]
        self.evidence: dict[str, dict[int, list[Block]]] = {}
        self.files_loaded: list[str] = []
        self.warnings: list[str] = []

    # --------------------------------------------------------
    # lookups
    # --------------------------------------------------------

    def get_profile(self, company_name) -> TechProfile | None:
        return self.profiles.get(compute_company_key(company_name))

    def has_profile(self, company_name) -> bool:
        profile = self.get_profile(company_name)
        return profile is not None and profile.total_points > 0

    def companies(self) -> list[str]:
        return sorted(p.company for p in self.profiles.values())

    # --------------------------------------------------------
    # sources (page-level citations from technology_extraction*.xlsx)
    # --------------------------------------------------------

    def blocks_for(self, key: str, page: int, parameter: str | None = None) -> list[Block]:
        blocks = self.evidence.get(key, {}).get(page, [])
        if parameter:
            same = [b for b in blocks if b.parameter == parameter]
            if same:
                return same
        return blocks

    def sources_for_point(self, key: str, point: Point, point_text: str = "") -> list[dict]:
        """Resolve a point's page numbers to PDF / page / section / excerpt."""
        profile = self.profiles.get(key)
        sources = []

        for page in point.pages:
            blocks = self.blocks_for(key, page, point.parameter)
            block = blocks[0] if blocks else None

            excerpt = ""
            if block and block.text:
                excerpt = _excerpt(block.text, point_text or point.text)

            sources.append(
                {
                    "company": profile.company if profile else "",
                    "company_key": key,
                    "parameter": point.parameter,
                    "pdf": block.pdf if block else "",
                    "page": page,
                    "section": block.section if block else "",
                    "excerpt": excerpt,
                    "extraction_file": (
                        block.extraction_file if block
                        else (profile.extraction_file if profile else "")
                    ),
                }
            )

        return sources

    # --------------------------------------------------------
    # choose which points go in front of the model
    # --------------------------------------------------------

    def select_points(self, key: str, question: str, max_points: int = 40) -> list[Point]:
        profile = self.profiles.get(key)
        if not profile or profile.total_points == 0:
            return []

        q = (question or "").lower()
        targeted = [
            p for p, pattern in PARAMETER_HINTS.items()
            if profile.points.get(p) and re.search(pattern, q)
        ]

        # Parameter-specific keywords ("platform", "risk") are broad; if they
        # select nearly everything they stop being a useful filter.
        if len(targeted) > 6:
            targeted = []

        pool = targeted or [p for p in TECHNOLOGY_PARAMETERS if profile.points.get(p)]
        q_tokens = _tokens(q)

        ranked: dict[str, list[Point]] = {}
        for parameter in pool:
            points = profile.points.get(parameter, [])
            scored = []
            for idx, point in enumerate(points):
                overlap = len(q_tokens & _tokens(point.text)) if q_tokens else 0
                scored.append((-overlap, idx, point))
            # best keyword overlap first; ties keep the workbook's own order
            scored.sort(key=lambda x: (x[0], x[1]))
            ranked[parameter] = [point for _, _, point in scored]

        # Round-robin across parameters so a tight evidence budget still
        # represents the whole profile instead of overfilling early columns.
        selected: list[Point] = []
        for point_index in range(max((len(points) for points in ranked.values()), default=0)):
            for parameter in pool:
                points = ranked[parameter]
                if point_index < len(points):
                    selected.append(points[point_index])
                    if len(selected) >= max_points:
                        return selected

        return selected

    # --------------------------------------------------------
    # dataframes (counts + compatibility with the older loader API)
    # --------------------------------------------------------

    def summary_df(self) -> pd.DataFrame:
        rows = []
        for profile in self.profiles.values():
            row = {
                "Company": profile.company,
                "Company_Key": profile.key,
                "Evidence_Points": profile.total_points,
                "Built_From": "extraction (no summary row)" if profile.derived else "evidence_summary",
            }
            for parameter in TECHNOLOGY_PARAMETERS:
                pts = profile.points.get(parameter, [])
                row[parameter] = "\n".join(
                    f"{i}. {p.text} (p. {', '.join(map(str, p.pages))})"
                    for i, p in enumerate(pts, start=1)
                )
            rows.append(row)
        return pd.DataFrame(rows)

    def detail_df(self) -> pd.DataFrame:
        rows = []
        for profile in self.profiles.values():
            for parameter in TECHNOLOGY_PARAMETERS:
                for p in profile.points.get(parameter, []):
                    rows.append(
                        {
                            "Company": profile.company,
                            "Parameter": parameter,
                            "Point": p.text,
                            "Pages": ", ".join(map(str, p.pages)),
                            "Claim ID": p.claim_id,
                        }
                    )
        return pd.DataFrame(rows)


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9&]+", (text or "").lower())
    out = set()
    for w in words:
        if len(w) < 3 or w in _STOPWORDS:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _excerpt(block_text: str, point_text: str, width: int = 380) -> str:
    """Show the part of the page evidence that contains the point."""
    block = _collapse(block_text)
    needle = _collapse(point_text)[:50].lower()

    start = block.lower().find(needle) if needle else -1
    if start < 0:
        snippet = block[:width]
    else:
        start = max(0, start - 60)
        snippet = block[start:start + width]
        if start > 0:
            snippet = "\u2026" + snippet

    if len(block) > len(snippet) and not snippet.endswith("\u2026"):
        snippet = snippet.rstrip() + "\u2026"
    return snippet


# ============================================================
# BUILD
# ============================================================

def build_knowledge_base(data_dir) -> TechKnowledgeBase:
    kb = TechKnowledgeBase()
    data_dir = Path(data_dir)

    pairs = discover_file_pairs(data_dir)
    if not pairs:
        kb.warnings.append(
            "No evidence_summary*.xlsx files found in the data/ folder."
        )
        return kb

    for summary_path, extraction_path in pairs:
        kb.files_loaded.append(summary_path.name)

        # ---------------- extraction workbook (page-level citations) --------
        extraction_name = extraction_path.name if extraction_path else ""
        names_in_extraction: dict[str, str] = {}

        if extraction_path is None:
            kb.warnings.append(
                f"No technology_extraction file found for {summary_path.name}; "
                "answers cannot cite PDF/section for this batch."
            )
        else:
            kb.files_loaded.append(extraction_path.name)
            te = pd.read_excel(extraction_path, sheet_name="Technology Evidence", dtype=str)
            company_col = te.columns[0]
            parameter_cols = [c for c in te.columns[1:] if c in TECHNOLOGY_PARAMETERS]

            for _, row in te.iterrows():
                name = _clean(row[company_col])
                if not name:
                    continue
                key = compute_company_key(name)
                names_in_extraction.setdefault(key, name)
                pages = kb.evidence.setdefault(key, {})

                for parameter in parameter_cols:
                    for block in parse_evidence_cell(row[parameter], parameter, extraction_name):
                        bucket = pages.setdefault(block.page, [])
                        if not any(
                            b.parameter == block.parameter and b.text[:120] == block.text[:120]
                            for b in bucket
                        ):
                            bucket.append(block)

        # ---------------- summary workbook (the facts) ----------------------
        sp = pd.read_excel(summary_path, sheet_name="Summary Points", dtype=str).fillna("")
        needed = {"Company", "Parameter", "Point", "Source Pages"}
        if not needed.issubset(sp.columns):
            kb.warnings.append(
                f"{summary_path.name}: 'Summary Points' sheet is missing columns "
                f"{sorted(needed - set(sp.columns))}"
            )
            continue

        for _, row in sp.iterrows():
            company = _clean(row["Company"])
            parameter = _clean(row["Parameter"])
            text = _NUMBERING.sub("", _clean(row["Point"]))

            if not company or parameter not in TECHNOLOGY_PARAMETERS or not text:
                continue
            if text.lower().startswith(NOT_AVAILABLE_MARKERS):
                continue

            key = compute_company_key(company)
            profile = kb.profiles.get(key)
            if profile is None:
                profile = TechProfile(
                    key=key,
                    company=company,
                    summary_file=summary_path.name,
                    extraction_file=extraction_name,
                )
                kb.profiles[key] = profile

            pages = [int(x) for x in re.findall(r"\d+", _clean(row["Source Pages"]))]
            profile.points.setdefault(parameter, []).append(
                Point(
                    parameter=parameter,
                    text=text,
                    pages=pages,
                    claim_id=_clean(row.get("Claim IDs", "")),
                )
            )

        # ---------------- companies that have extraction but no summary -----
        # (e.g. HDFC Bank: its row was lost from evidence_summary.xlsx because
        # it was saved as the sheet's header row.)  Build extractive points
        # straight from the extraction text so the company is not dropped.
        for key, name in names_in_extraction.items():
            if key in kb.profiles and kb.profiles[key].total_points:
                continue

            profile = TechProfile(
                key=key,
                company=name,
                summary_file="",
                extraction_file=extraction_name,
                derived=True,
            )

            for parameter in TECHNOLOGY_PARAMETERS:
                seen = set()
                collected = []
                blocks = [
                    b for page_blocks in kb.evidence.get(key, {}).values()
                    for b in page_blocks if b.parameter == parameter
                ]
                blocks.sort(key=lambda b: -(b.score or 0))

                for block in blocks:
                    for sentence in _split_sentences(block.text):
                        if len(sentence) < 40:
                            continue
                        norm = sentence.lower()[:90]
                        if norm in seen:
                            continue
                        seen.add(norm)
                        collected.append(
                            Point(parameter=parameter, text=sentence[:500], pages=[block.page])
                        )
                        if len(collected) >= 12:
                            break
                    if len(collected) >= 12:
                        break

                if collected:
                    profile.points[parameter] = collected

            if profile.total_points:
                kb.profiles[key] = profile
                kb.warnings.append(
                    f"{name}: not present in {summary_path.name}; evidence built "
                    f"directly from {extraction_name}."
                )
            elif key not in kb.profiles:
                # keep an empty profile so the bot can say "no evidence found"
                kb.profiles[key] = profile
                kb.warnings.append(f"{name}: no technology evidence in the workbooks.")

    return kb

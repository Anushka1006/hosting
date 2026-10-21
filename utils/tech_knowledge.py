from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from utils.company_keys import compute_company_key


# ============================================================
# TECHNOLOGY PARAMETERS
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

# No question-to-parameter keyword map is used for retrieval. Candidate points
# are ranked against the complete user question using semantic similarity.
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
    score: Optional[float]
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
    derived: bool = False
    points: dict = field(default_factory=dict)

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
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_evidence_cell(cell, parameter: str, extraction_file: str) -> list[Block]:
    """Split one 'Technology Evidence' cell into page-level blocks."""
    text = _clean(cell)
    if not text or text.lower().startswith(NOT_AVAILABLE_MARKERS):
        return []

    headers = list(_HEADER.finditer(text))
    blocks: list[Block] = []
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[match.end():end]
        score_match = _SCORE.search(body)
        score = float(score_match.group(1)) if score_match else None

        marker = "Original Evidence:"
        evidence = body.split(marker, 1)[1] if marker in body else body
        evidence = _collapse(evidence)
        if not evidence:
            continue

        blocks.append(
            Block(
                pdf=match.group("pdf").strip(),
                page=int(match.group("page")),
                section=_collapse(match.group("section")),
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
    return [part.strip() for part in parts if part.strip()]


def _batch_id(path: Path) -> str:
    """evidence_summary.xlsx -> '1'; evidence_summary2.xlsx -> '2'."""
    digits = re.findall(r"(\d+)\.xlsx$", path.name, flags=re.I)
    return digits[-1] if digits else "1"


def discover_file_pairs(data_dir: Path) -> list[tuple[Path, Optional[Path]]]:
    """Pair each evidence_summary workbook with its extraction workbook."""
    summaries = sorted(Path(data_dir).glob("evidence_summary*.xlsx"), key=_batch_id)
    extractions = {
        _batch_id(path): path
        for path in Path(data_dir).glob("technology_extraction*.xlsx")
    }
    return [(summary, extractions.get(_batch_id(summary))) for summary in summaries]


# ============================================================
# SEMANTIC RANKER
# ============================================================

class _SemanticRanker:
    """Lazy semantic embedding ranker, with a lexical fallback if unavailable."""

    def __init__(self):
        self._model = None
        self._attempted = False

    def _load_model(self):
        if self._attempted:
            return self._model
        self._attempted = True
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            # The chatbot can still run if embeddings are unavailable; ranking
            # falls back to token similarity instead of failing the request.
            self._model = None
        return self._model

    @staticmethod
    def _tokens(text: str) -> set[str]:
        words = re.findall(r"[a-z0-9&]+", (text or "").lower())
        result = set()
        for word in words:
            if len(word) < 3 or word in _STOPWORDS:
                continue
            result.add(word[:-1] if word.endswith("s") and len(word) > 4 else word)
        return result

    def scores(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        model = self._load_model()
        if model is not None:
            try:
                vectors = model.encode(
                    [query] + documents,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
                q_vector = vectors[0]
                return [float(np.dot(q_vector, vector)) for vector in vectors[1:]]
            except Exception:
                # Fall through to lexical scoring if encoding fails at runtime.
                pass

        q_tokens = self._tokens(query)
        scores = []
        for document in documents:
            d_tokens = self._tokens(document)
            if not q_tokens or not d_tokens:
                scores.append(0.0)
                continue
            overlap = len(q_tokens & d_tokens)
            # Dice coefficient keeps the fallback bounded between 0 and 1.
            scores.append((2.0 * overlap) / (len(q_tokens) + len(d_tokens)))
        return scores


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
        self._ranker = _SemanticRanker()

    def get_profile(self, company_name) -> Optional[TechProfile]:
        return self.profiles.get(compute_company_key(company_name))

    def has_profile(self, company_name) -> bool:
        profile = self.get_profile(company_name)
        return profile is not None and profile.total_points > 0

    def companies(self) -> list[str]:
        return sorted(profile.company for profile in self.profiles.values())

    # --------------------------------------------------------
    # Source citations
    # --------------------------------------------------------

    def blocks_for(self, key: str, page: int, parameter: Optional[str] = None) -> list[Block]:
        blocks = self.evidence.get(key, {}).get(page, [])
        if parameter:
            same_parameter = [block for block in blocks if block.parameter == parameter]
            if same_parameter:
                return same_parameter
        return blocks

    def sources_for_point(self, key: str, point: Point, point_text: str = "") -> list[dict]:
        """Resolve point page numbers to PDF, page, section and excerpt."""
        profile = self.profiles.get(key)
        sources = []
        for page in point.pages:
            blocks = self.blocks_for(key, page, point.parameter)
            block = blocks[0] if blocks else None
            excerpt = _excerpt(block.text, point_text or point.text) if block and block.text else ""
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
    # Semantic evidence selection
    # --------------------------------------------------------

    def select_points(self, key: str, question: str, max_points: int = 40) -> list[Point]:
        """Rank evidence against the complete question, without parameter keyword rules.

        Semantic similarity ranks all points for this company together. Each
        document includes the parameter label as context, helping the ranker
        preserve relationships such as technology + planned action. A small
        diversity bonus prevents the results from being near-duplicates only.
        """
        profile = self.profiles.get(key)
        if not profile or profile.total_points == 0:
            return []

        question = _collapse(question)
        if not question:
            return []

        candidates: list[tuple[int, Point]] = []
        documents: list[str] = []
        for parameter in TECHNOLOGY_PARAMETERS:
            for point in profile.points.get(parameter, []):
                candidates.append((len(candidates), point))
                # Including the parameter is contextual metadata, not a hardcoded
                # query mapping. The full question remains the ranking query.
                documents.append(f"Technology parameter: {parameter}. Evidence: {point.text}")

        scores = self._ranker.scores(question, documents)
        ranked = sorted(
            zip(scores, candidates),
            key=lambda item: (item[0], -item[1][0]),
            reverse=True,
        )

        # Greedy relevance selection with lightweight redundancy control.
        selected: list[Point] = []
        selected_tokens: list[set[str]] = []
        for score, (_, point) in ranked:
            point_tokens = self._ranker._tokens(point.text)
            if selected_tokens and point_tokens:
                max_overlap = max(
                    len(point_tokens & prior) / max(1, len(point_tokens | prior))
                    for prior in selected_tokens
                )
                # Skip only highly redundant points; do not discard evidence
                # just because the question's exact wording differs.
                if max_overlap >= 0.88 and score < (ranked[0][0] if ranked else 0) + 0.03:
                    continue
            selected.append(point)
            selected_tokens.append(point_tokens)
            if len(selected) >= max(1, max_points):
                break

        return selected

    # --------------------------------------------------------
    # DataFrames (compatibility with the existing loader API)
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
                points = profile.points.get(parameter, [])
                row[parameter] = "\n".join(
                    f"{index}. {point.text} (p. {', '.join(map(str, point.pages))})"
                    for index, point in enumerate(points, start=1)
                )
            rows.append(row)
        return pd.DataFrame(rows)

    def detail_df(self) -> pd.DataFrame:
        rows = []
        for profile in self.profiles.values():
            for parameter in TECHNOLOGY_PARAMETERS:
                for point in profile.points.get(parameter, []):
                    rows.append(
                        {
                            "Company": profile.company,
                            "Parameter": parameter,
                            "Point": point.text,
                            "Pages": ", ".join(map(str, point.pages)),
                            "Claim ID": point.claim_id,
                        }
                    )
        return pd.DataFrame(rows)


# ============================================================
# SMALL HELPERS
# ============================================================

def _excerpt(block_text: str, point_text: str, width: int = 380) -> str:
    """Return the part of page evidence closest to the point text."""
    block = _collapse(block_text)
    needle = _collapse(point_text)[:50].lower()
    start = block.lower().find(needle) if needle else -1
    if start < 0:
        snippet = block[:width]
    else:
        start = max(0, start - 60)
        snippet = block[start:start + width]
        if start > 0:
            snippet = "…" + snippet
    if len(block) > len(snippet) and not snippet.endswith("…"):
        snippet = snippet.rstrip() + "…"
    return snippet


# ============================================================
# BUILD KNOWLEDGE BASE
# ============================================================

def build_knowledge_base(data_dir) -> TechKnowledgeBase:
    kb = TechKnowledgeBase()
    data_dir = Path(data_dir)
    pairs = discover_file_pairs(data_dir)
    if not pairs:
        kb.warnings.append("No evidence_summary*.xlsx files found in the data/ folder.")
        return kb

    for summary_path, extraction_path in pairs:
        kb.files_loaded.append(summary_path.name)
        extraction_name = extraction_path.name if extraction_path else ""
        names_in_extraction: dict[str, str] = {}

        # Load page-level source evidence for citations.
        if extraction_path is None:
            kb.warnings.append(
                f"No technology_extraction file found for {summary_path.name}; "
                "answers cannot cite PDF/section for this batch."
            )
        else:
            kb.files_loaded.append(extraction_path.name)
            try:
                evidence_df = pd.read_excel(
                    extraction_path, sheet_name="Technology Evidence", dtype=str
                )
            except Exception as exc:
                kb.warnings.append(f"Could not read {extraction_path.name}: {exc}")
                evidence_df = pd.DataFrame()

            if not evidence_df.empty:
                company_col = evidence_df.columns[0]
                parameter_cols = [
                    column for column in evidence_df.columns[1:]
                    if column in TECHNOLOGY_PARAMETERS
                ]
                for _, row in evidence_df.iterrows():
                    name = _clean(row.get(company_col, ""))
                    if not name:
                        continue
                    key = compute_company_key(name)
                    names_in_extraction.setdefault(key, name)
                    pages = kb.evidence.setdefault(key, {})
                    for parameter in parameter_cols:
                        for block in parse_evidence_cell(row.get(parameter, ""), parameter, extraction_name):
                            bucket = pages.setdefault(block.page, [])
                            if not any(
                                existing.parameter == block.parameter
                                and existing.text[:120] == block.text[:120]
                                and existing.pdf == block.pdf
                                for existing in bucket
                            ):
                                bucket.append(block)

        # Load summary points, the preferred facts for answering.
        try:
            summary_df = pd.read_excel(
                summary_path, sheet_name="Summary Points", dtype=str
            ).fillna("")
        except Exception as exc:
            kb.warnings.append(f"Could not read Summary Points from {summary_path.name}: {exc}")
            summary_df = pd.DataFrame()

        needed = {"Company", "Parameter", "Point", "Source Pages"}
        if not summary_df.empty and needed.issubset(summary_df.columns):
            for _, row in summary_df.iterrows():
                company = _clean(row.get("Company", ""))
                parameter = _clean(row.get("Parameter", ""))
                text = _NUMBERING.sub("", _clean(row.get("Point", "")))
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

                pages = [int(value) for value in re.findall(r"\d+", _clean(row.get("Source Pages", "")))]
                claim_id = _clean(row.get("Claim IDs", ""))
                # Avoid duplicate points when multiple summary batches overlap.
                existing = profile.points.setdefault(parameter, [])
                norm_text = _collapse(text).casefold()
                if not any(_collapse(point.text).casefold() == norm_text for point in existing):
                    existing.append(
                        Point(parameter=parameter, text=text, pages=pages, claim_id=claim_id)
                    )
        elif not summary_df.empty:
            kb.warnings.append(
                f"{summary_path.name}: 'Summary Points' is missing columns "
                f"{sorted(needed - set(summary_df.columns))}."
            )

        # If a company has extraction evidence but no summary profile, build
        # extractive points from that company's own source blocks.
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
                seen: set[str] = set()
                collected: list[Point] = []
                blocks = [
                    block
                    for page_blocks in kb.evidence.get(key, {}).values()
                    for block in page_blocks
                    if block.parameter == parameter
                ]
                blocks.sort(key=lambda block: -(block.score or 0.0))
                for block in blocks:
                    for sentence in _split_sentences(block.text):
                        if len(sentence) < 40:
                            continue
                        normalized = _collapse(sentence).casefold()
                        if normalized in seen:
                            continue
                        seen.add(normalized)
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
                    f"{name}: not present in {summary_path.name}; evidence built directly from {extraction_name}."
                )
            elif key not in kb.profiles:
                kb.profiles[key] = profile
                kb.warnings.append(f"{name}: no technology evidence in the workbooks.")

    return kb

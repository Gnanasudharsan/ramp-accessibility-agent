"""Scoring: element-level matching, precision/recall/F1, and page-criterion scores.

Matching rule (element sets): a prediction matches a label when both resolve to the same DOM
element and their WCAG criteria intersect. Each label is matched at most once; further
predictions on an already-matched label are duplicates (not false positives). Predictions with
no WCAG criterion (axe best practices) are not scored.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel


class PRF(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None if p is None or r is None else 0.0
        return 2 * p * r / (p + r)

    def add(self, other: PRF) -> PRF:
        return PRF(tp=self.tp + other.tp, fp=self.fp + other.fp, fn=self.fn + other.fn)

    def summary(self) -> dict[str, float | int | None]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True)
class GoldItem:
    page: str
    key: str  # canonical element key
    criterion: str  # primary criterion
    criteria: frozenset[str]
    detectable_by: str
    label_id: str


@dataclass(frozen=True)
class PredItem:
    page: str
    key: str
    criteria: tuple[str, ...]  # catalog order; first is used to attribute a false positive
    source: str  # rule | vision | both
    issue_id: str


@dataclass
class MatchResult:
    matched_labels: dict[str, str] = field(default_factory=dict)  # label_id -> issue_id
    false_positives: list[PredItem] = field(default_factory=list)
    duplicates: list[PredItem] = field(default_factory=list)


def match(gold: Iterable[GoldItem], preds: Iterable[PredItem]) -> MatchResult:
    by_element: dict[tuple[str, str], list[GoldItem]] = defaultdict(list)
    for g in gold:
        by_element[(g.page, g.key)].append(g)
    result = MatchResult()
    for p in preds:
        candidates = [
            g for g in by_element.get((p.page, p.key), []) if g.criteria & set(p.criteria)
        ]
        free = [g for g in candidates if g.label_id not in result.matched_labels]
        if free:
            result.matched_labels[free[0].label_id] = p.issue_id
        elif candidates:
            result.duplicates.append(p)
        else:
            result.false_positives.append(p)
    return result


def score(
    gold: list[GoldItem], preds: list[PredItem], result: MatchResult
) -> dict[str, dict[str, PRF]]:
    """Overall, per primary criterion, per detectable_by, and per prediction source."""
    overall = PRF()
    per_criterion: dict[str, PRF] = defaultdict(PRF)
    per_detectable: dict[str, PRF] = defaultdict(PRF)
    for g in gold:
        hit = g.label_id in result.matched_labels
        delta = PRF(tp=1) if hit else PRF(fn=1)
        overall = overall.add(delta)
        per_criterion[g.criterion] = per_criterion[g.criterion].add(delta)
        per_detectable[g.detectable_by] = per_detectable[g.detectable_by].add(delta)
    for p in result.false_positives:
        overall = overall.add(PRF(fp=1))
        per_criterion[p.criteria[0]] = per_criterion[p.criteria[0]].add(PRF(fp=1))

    # Per source: precision of each source's predictions; recall of labels each source found.
    matched_by_issue = {iid: lid for lid, iid in result.matched_labels.items()}
    fp_ids = {p.issue_id for p in result.false_positives}
    per_source: dict[str, PRF] = {}
    for source in ("rule", "vision", "both"):
        mine = [p for p in preds if p.source == source]
        if not mine:
            continue
        found = {matched_by_issue[p.issue_id] for p in mine if p.issue_id in matched_by_issue}
        per_source[source] = PRF(
            tp=len(found),
            fp=sum(p.issue_id in fp_ids for p in mine),
            fn=len(gold) - len(found),
        )
    return {
        "overall": {"all": overall},
        "per_criterion": dict(sorted(per_criterion.items(), key=lambda kv: _sc_key(kv[0]))),
        "per_detectable_by": dict(per_detectable),
        "per_source": per_source,
    }


def page_criterion_prf(gold: dict[str, set[str]], predicted: dict[str, set[str]]) -> PRF:
    """Score (page, criterion) pairs: a criterion flagged on a page that W3C labels as failing."""
    total = PRF()
    for page, truth in gold.items():
        flagged = predicted.get(page, set())
        total = total.add(
            PRF(tp=len(truth & flagged), fp=len(flagged - truth), fn=len(truth - flagged))
        )
    return total


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(q / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _sc_key(cid: str) -> list[int]:
    return [int(x) for x in cid.split(".")]

"""The actual hallucination gate (docs Section 6.3, mechanism #4).

Every `LLMIssueItem` the issue detector proposes is checked here against
the REAL transcript before it is trusted: the cited `segment_index` is
resolved to a real `TranscriptSegment`, and `quoted_text` must fuzzy-match
that segment's actual text above `issue_rules.yaml`'s
`fuzzy_match_threshold`. If the primary segment doesn't match (the LLM
cited the wrong index but the quote is real), every segment is searched as
a fallback before giving up.

Issues that fail validation are NOT discarded silently — they are still
returned with `is_validated=False` so the caller can persist them for
audit/prompt-quality debugging (docs Section 6.3: "logged to audit_logs,
not silently dropped"), but `is_validated=False` issues must never be
surfaced to a reviewer as fact.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from fitnova.analysis.confidence import calibrate_confidence
from fitnova.analysis.llm_schemas import LLMIssueItem
from fitnova.core.config import IssueRulesConfig, Settings
from fitnova.core.constants import ConfidenceLabel, IssueType, Severity, SpeakerLabel
from fitnova.db.models import TranscriptSegment


@dataclass(frozen=True)
class ValidatedIssue:
    issue_type: IssueType
    severity: Severity
    speaker: SpeakerLabel
    quoted_text: str
    reason: str
    confidence_score: float
    confidence_label: ConfidenceLabel
    is_validated: bool
    segment_id: int | None


def validate_issues(
    raw_issues: list[LLMIssueItem],
    segments: list[TranscriptSegment],
    issue_rules_config: IssueRulesConfig,
    settings: Settings,
) -> list[ValidatedIssue]:
    threshold = issue_rules_config.fuzzy_match_threshold
    by_index = {seg.segment_index: seg for seg in segments}

    results: list[ValidatedIssue] = []
    for raw in raw_issues:
        segment_id = _resolve_segment_id(raw, by_index, segments, threshold)
        results.append(
            ValidatedIssue(
                issue_type=raw.issue_type,
                severity=raw.severity,
                speaker=raw.speaker,
                quoted_text=raw.quoted_text,
                reason=raw.reason,
                confidence_score=raw.confidence,
                confidence_label=calibrate_confidence(raw.confidence, settings),
                is_validated=segment_id is not None,
                segment_id=segment_id,
            )
        )
    return results


def _resolve_segment_id(
    raw: LLMIssueItem,
    by_index: dict[int, TranscriptSegment],
    all_segments: list[TranscriptSegment],
    threshold: int,
) -> int | None:
    quoted = raw.quoted_text.strip().lower()
    if not quoted:
        return None

    primary = by_index.get(raw.segment_index)
    if primary is not None:
        if fuzz.partial_ratio(quoted, primary.text.lower()) >= threshold:
            return primary.id

    # Fallback: the LLM may have cited the wrong index but quoted real text
    # from a different segment — search everything before rejecting.
    best_id: int | None = None
    best_score = 0.0
    for seg in all_segments:
        score = fuzz.partial_ratio(quoted, seg.text.lower())
        if score > best_score:
            best_score = score
            best_id = seg.id

    if best_score >= threshold:
        return best_id
    return None

from __future__ import annotations


def score_explanation(evidence_ids: list[str], rationale: str) -> float:
    evidence_score = min(1.0, len(evidence_ids) / 3)
    brevity_score = 1.0 if 40 <= len(rationale) <= 600 else 0.6
    return round((evidence_score * 0.7) + (brevity_score * 0.3), 3)

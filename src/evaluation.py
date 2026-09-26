"""Pure scoring/verdict logic for comparing two models, kept free of any
torch/PIL dependency so it can be unit-tested with plain lists of numbers."""
from __future__ import annotations


def compute_rates(good_scores: list[float], ng_scores: list[float], threshold: float) -> dict:
    escapes = sum(1 for s in ng_scores if s <= threshold)
    false_positives = sum(1 for s in good_scores if s > threshold)
    return {
        "threshold": threshold,
        "escape_rate": escapes / len(ng_scores) if ng_scores else None,
        "escape_count": escapes,
        "false_positive_rate": false_positives / len(good_scores) if good_scores else None,
        "false_positive_count": false_positives,
    }


def verdict(current: dict, candidate: dict) -> str:
    if current["escape_rate"] is None or candidate["escape_rate"] is None:
        return "INCONCLUSIVE — not enough confirmed_ng images to compare escape rate."
    escape_ok = candidate["escape_rate"] <= current["escape_rate"]
    fp_ok = (candidate["false_positive_rate"] or 0) <= (current["false_positive_rate"] or 0) + 0.02
    if escape_ok and fp_ok:
        return "SAFE TO PROMOTE — the candidate does not miss more real defects or reject more good units."
    if not escape_ok:
        return "DO NOT PROMOTE — the candidate misses more real defects than the current model."
    return "REVIEW NEEDED — the candidate rejects noticeably more good units than the current model."

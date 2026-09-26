"""Turn an anomaly score into a pass/suspect/reject decision.

Principle: missing a real defect (false negative) is far more costly than
double-checking a good item, so the "suspect" zone is always preferred over
letting a borderline item through automatically.
"""
from enum import Enum


class Decision(str, Enum):
    PASS = "pass"
    SUSPECT = "suspect"
    REJECT = "reject"


def decide(score: float, threshold: float, suspect_margin: float = 0.15) -> Decision:
    """
    score <= threshold                          -> PASS
    threshold < score <= threshold*(1+margin)   -> SUSPECT (route to a human)
    score > threshold*(1+margin)                -> REJECT
    """
    if score <= threshold:
        return Decision.PASS
    if score <= threshold * (1 + suspect_margin):
        return Decision.SUSPECT
    return Decision.REJECT

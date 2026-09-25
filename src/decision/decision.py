"""Quy đổi điểm bất thường (anomaly score) thành quyết định pass/suspect/reject.

Nguyên tắc: bỏ sót lỗi (false negative) tốn kém hơn nhiều so với kiểm tra nhầm
hàng tốt, nên vùng "suspect" luôn được ưu tiên hơn là cho qua thẳng.
"""
from enum import Enum


class Decision(str, Enum):
    PASS = "pass"
    SUSPECT = "suspect"
    REJECT = "reject"


def decide(score: float, threshold: float, suspect_margin: float = 0.15) -> Decision:
    """
    score <= threshold                          -> PASS
    threshold < score <= threshold*(1+margin)   -> SUSPECT (đưa người kiểm tra)
    score > threshold*(1+margin)                -> REJECT
    """
    if score <= threshold:
        return Decision.PASS
    if score <= threshold * (1 + suspect_margin):
        return Decision.SUSPECT
    return Decision.REJECT

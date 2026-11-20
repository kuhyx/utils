"""Confusion counts and recall-matched threshold fitting for the benches."""

from __future__ import annotations


def confusion(truth: list[bool], pred: list[bool]) -> dict[str, float]:
    """TP/FP/FN/TN plus precision and recall (0.0 when undefined)."""
    tp = sum(t and p for t, p in zip(truth, pred, strict=True))
    fp = sum(p and not t for t, p in zip(truth, pred, strict=True))
    fn = sum(t and not p for t, p in zip(truth, pred, strict=True))
    tn = len(truth) - tp - fp - fn
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(tp / (tp + fp), 3) if tp + fp else 0.0,
        "recall": round(tp / (tp + fn), 3) if tp + fn else 0.0,
    }


def fit_threshold(values: list[float], truth: list[bool], min_recall: float) -> float:
    """Highest threshold whose recall is still >= ``min_recall``.

    The highest such cut maximises precision subject to the recall floor, which
    is the trade kuhy asked for (a needless split beats a blown session).
    """
    for thr in sorted(set(values), reverse=True):
        pred = [v >= thr for v in values]
        if confusion(truth, pred)["recall"] >= min_recall:
            return thr
    return min(values) if values else 0.0

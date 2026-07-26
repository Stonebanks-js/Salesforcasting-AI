"""Per-forecast factor attribution (FR-5.7).

Importance: LightGBM gain (normalized). Direction: sign of the Pearson
correlation between the feature and the target on training data — cheap,
honest approximation suitable for 'what drove this forecast' UX.
"""


def direction_sign(rows: list[dict], feature: str) -> str:
    pairs = [
        (float(r[feature]), float(r["quantity"]))
        for r in rows
        if r.get(feature) is not None and r.get("quantity") is not None
    ]
    if len(pairs) < 10:
        return "neutral"
    xs, ys = zip(*pairs)
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return "neutral"
    corr = cov / (var_x * var_y) ** 0.5
    if corr > 0.05:
        return "up"
    if corr < -0.05:
        return "down"
    return "neutral"


def top_factors(
    importances: dict[str, float],
    rows: list[dict],
    k: int = 5,
    exclude: tuple[str, ...] = ("lag_1", "lag_7", "lag_14", "lag_28",
                                "roll_mean_7", "roll_mean_28"),
) -> list[dict]:
    """Top-k *actionable/external* factors (lags excluded — they're not
    'external drivers' in the UX sense; they describe momentum, not causes)."""
    candidates = [
        (f, w) for f, w in importances.items() if f not in exclude and w > 0
    ]
    candidates.sort(key=lambda t: t[1], reverse=True)
    selected = candidates[:k]
    total = sum(w for _, w in selected) or 1.0  # normalize across shown factors
    return [
        {
            "factor": f,
            "importance": round(w / total, 4),
            "direction": direction_sign(rows, f),
        }
        for f, w in selected
    ]

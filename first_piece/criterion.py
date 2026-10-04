"""Prospective evidence gate for one proposed binary distinction.

Inputs must come from predictions fixed before a fresh IID validation block.
This function evaluates a proposal; it does not discover or learn that proposal.
"""
import math


def evaluate_distinction(parent, proposal, outcomes, groups, *, comparison_limit=1000,
                         alpha=.05, epsilon=.01, penalty=.01,
                         current_units=1, extra_units=1, max_units=8,
                         minimum_per_group=32):
    parent, proposal, outcomes, groups = map(list, (parent, proposal, outcomes, groups))
    n = len(outcomes)
    if not n or any(len(values) != n for values in (parent, proposal, groups)):
        raise ValueError("Aligned nonempty validation arrays required")
    for value in (comparison_limit, current_units, extra_units, max_units, minimum_per_group):
        if type(value) is not int or value < 1:
            raise ValueError("Positive integer budgets required")
    if current_units > max_units:
        raise ValueError("Current units exceed capacity")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (alpha, epsilon, penalty)):
        raise ValueError("Numeric evidence settings required")
    if not (0 < alpha < 1 and 0 < epsilon < .5 and penalty >= 0):
        raise ValueError("Invalid evidence settings")
    if not all(math.isfinite(v) for v in (alpha, epsilon, penalty)):
        raise ValueError("Non-finite evidence settings")
    if any(type(y) is not int or y not in (0, 1) for y in outcomes + groups):
        raise ValueError("Binary outcomes and group assignments required")
    for p in parent + proposal:
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("Invalid outcome probability")

    def log_probability(p, y):
        p = max(epsilon, min(1 - epsilon, p))
        return math.log(p if y else 1 - p)

    gain = math.fsum(
        log_probability(new, y) - log_probability(old, y)
        for old, new, y in zip(parent, proposal, outcomes)
    ) / n
    bound = math.log(1 / epsilon) * math.sqrt(
        2 * math.log(comparison_limit / alpha) / n
    )
    cost = penalty * extra_units
    counts = [groups.count(0), groups.count(1)]
    lower, upper = gain - bound, gain + bound
    if min(counts) < minimum_per_group:
        decision = "pending_support"
    elif lower > cost:
        decision = "accept" if current_units + extra_units <= max_units else "blocked_by_budget"
    elif upper <= cost:
        decision = "reject"
    else:
        decision = "pending_evidence"
    return {
        "decision": decision, "validation_interactions": n, "group_counts": counts,
        "mean_log_score_gain": gain, "uncertainty_bound": bound,
        "gain_lower": lower, "gain_upper": upper, "complexity_cost": cost,
    }

"""Evidence gate for one externally proposed binary distinction.

Predictions must be fixed before a fresh IID validation block.
alpha covers both tails over at most comparison_limit predeclared tests.
The caller must enforce those conditions; this function is not a learner.
"""
import math


def _finite_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Numeric {name} required")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"Unrepresentable {name}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {name}")
    return number


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
    alpha = _finite_number(alpha, "alpha")
    epsilon = _finite_number(epsilon, "epsilon")
    penalty = _finite_number(penalty, "penalty")
    if not (0 < alpha < 1 and 0 < epsilon < .5 and penalty >= 0):
        raise ValueError("Invalid evidence settings")
    if any(type(y) is not int or y not in (0, 1) for y in outcomes + groups):
        raise ValueError("Binary outcomes and group assignments required")
    parent = [_finite_number(p, "probability") for p in parent]
    proposal = [_finite_number(p, "probability") for p in proposal]
    if any(not 0 <= p <= 1 for p in parent + proposal):
        raise ValueError("Invalid outcome probability")
    try:
        cost = penalty * extra_units if penalty else 0.0
    except OverflowError as exc:
        raise ValueError("Unrepresentable complexity cost") from exc
    if not math.isfinite(cost):
        raise ValueError("Non-finite complexity cost")

    def log_probability(p, y):
        # Clip the probability of the observed outcome directly. For tiny
        # epsilon, 1-epsilon rounds to 1; clipping p before 1-p can yield log(0).
        observed = p if y else 1 - p
        return math.log(max(epsilon, min(1 - epsilon, observed)))

    gain = math.fsum(
        log_probability(new, y) - log_probability(old, y)
        for old, new, y in zip(parent, proposal, outcomes)
    ) / n
    # Allocate alpha/(2*M) to each tail. Logs avoid overflow of M/alpha
    # and 1/epsilon for finite positive settings.
    log_family = math.log(2) + math.log(comparison_limit) - math.log(alpha)
    bound = -math.log(epsilon) * math.sqrt(2 * log_family / n)
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

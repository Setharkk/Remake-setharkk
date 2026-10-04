"""Strict policies and live-reference validation for plastic revisions."""
import math

from setharkk.contracts import counter
from .criterion import _finite_number
from .consolidated import COMPARISONS, UNIVERSAL_WIDTH

INITIAL_KEYS = {"source", "at", "mapped_records", "mapped_routes",
                "source_prototype_reads", "geodesic_mean_steps", "ambiguous_means",
                "transferred_candidate_points", "transferred_control_points",
                "optimizer_restarted", "active_source_updates", "control_source_updates"}


def validate_search(model, search):
    meta = search["validation"]
    if type(meta) is not dict or set(meta) != {
            "horizons", "serve_mode", "served_at", "reference", "widths", "variance_checks", "refresh_checks", "conditional_null"}:
        raise ValueError("Invalid revision validation policy")
    if (type(meta["horizons"]) is not list or any(type(n) is not int for n in meta["horizons"])
            or meta["horizons"] != list(model._horizons(search["attempt"]))):
        raise ValueError("Undeclared revision horizons")
    if meta["serve_mode"] not in ("plastic", "consolidated"):
        raise ValueError("Unknown revision served mode")
    if meta["serve_mode"] == "consolidated":
        if counter(meta["served_at"], "protected exposure") > search["at"] or meta["reference"] != "protected":
            raise ValueError("Invalid protected revision reference")
    elif meta["served_at"] is not None or meta["reference"] not in ("moving_plastic", "frozen_plastic"):
        raise ValueError("Invalid plastic revision reference")
    supported = search["program"] is not None
    if meta["reference"] == "frozen_plastic" and (not supported or
            not model.config["bounded_validation_ranges"] or not model.config["use_structure"]):
        raise ValueError("Unsupported frozen plastic policy")
    null = meta["conditional_null"]
    needed_null = supported and model.config["bounded_validation_ranges"]
    if (null is not None) != needed_null:
        raise ValueError("Conditional null and fit policy differ")
    if needed_null:
        if type(null) is not dict or set(null) != {"default", "contexts"} or type(null["contexts"]) is not dict:
            raise ValueError("Invalid conditional null")
        total, positive = 0, 0
        for slot, counts in null["contexts"].items():
            if type(slot) is not str or not slot.isdecimal() or str(int(slot)) != slot or int(slot) not in model.tasks:
                raise ValueError("Unbound null context")
            if type(counts) is not list or len(counts) != 2:
                raise ValueError("Invalid null counts")
            n = counter(counts[0], "null fit records", minimum=1)
            y = counter(counts[1], "null positives")
            if y > n or n > model.config["fit_per_context"]:
                raise ValueError("Impossible null fit counts")
            total += n
            positive += y
        if total != search["fit_records"] or not math.isclose(
                _finite_number(null["default"], "null default"),
                (positive+1)/(total+2), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("Conditional null fit accounting differs")
    widths = meta["widths"]
    if type(widths) is not dict or set(widths) != set(COMPARISONS):
        raise ValueError("Invalid revision gain ranges")
    for name, value in widths.items():
        width = _finite_number(value, "gain range")
        if not 0 <= width <= UNIVERSAL_WIDTH + 1e-12:
            raise ValueError("Gain range exceeds universal bound")
        universal = (not supported or
                     (name == "improvement" and meta["reference"] == "moving_plastic") or
                     (name == "relevance" and not model.config["bounded_validation_ranges"]) or
                     (name == "improvement" and not model.config["bounded_validation_ranges"]) or
                     (name == "preservation" and (search["scope"] is None or meta["reference"] != "protected")))
        if universal and width != UNIVERSAL_WIDTH:
            raise ValueError("Unsupported narrowed revision range")

    checks = meta["variance_checks"]
    if type(checks) is not dict or set(checks) != {"relevance", "improvement"}:
        raise ValueError("Invalid variance look fields")
    horizons = model._horizons(search["attempt"])
    for name, table in checks.items():
        if type(table) is not dict or len(table) > len(horizons):
            raise ValueError("Unbounded variance look history")
        previous_n, previous_v = 0, 0.0
        for key in sorted(table, key=lambda k: int(k) if type(k) is str and k.isdecimal() else -1):
            if type(key) is not str or not key.isdecimal() or str(int(key)) != key or int(key) not in horizons:
                raise ValueError("Variance at an undeclared look")
            n, value = int(key), _finite_number(table[key], "predictable variance")
            maximum = widths[name] * widths[name]
            if not previous_v - 1e-8 <= value <= previous_v + (n-previous_n)*maximum + 1e-7:
                raise ValueError("Variance proxy exceeds declared increments")
            previous_n, previous_v = n, value
        decisions = [d for d in model.decisions if d.get("attempt") == search["attempt"] and "relevance" in d]
        expected = {str(d["relevance"]["n"]) for d in decisions} if model.config["bounded_validation_ranges"] else set()
        if set(table) != expected:
            raise ValueError("Variance records and completed looks differ")


    from .plastic_revision import REFRESH_HORIZONS
    from .shared_state import _program
    refresh = meta["refresh_checks"]
    if type(refresh) is not list or len(refresh) > len(REFRESH_HORIZONS):
        raise ValueError("Unbounded candidate refresh history")
    previous_n = 0
    for record in refresh:
        keys = {"at", "n", "program", "current_score", "proposed_score", "fit_records",
                "eligible_features", "pooled_features", "hypotheses_examined"}
        if type(record) is not dict or set(record) != keys:
            raise ValueError("Invalid refresh accounting")
        n = counter(record["n"], "refresh horizon")
        if (not previous_n < n or n not in REFRESH_HORIZONS or search["scope"] is not None
                or meta["reference"] != "frozen_plastic" or not model.config["bounded_validation_ranges"]):
            raise ValueError("Undeclared refresh policy")
        previous_n = n
        if record["at"] != search["at"] + n:
            raise ValueError("Refresh exposure differs")
        if not any(d.get("attempt") == search["attempt"] and d["at"] == record["at"]
                   and d["decision"] == "pending" for d in model.decisions):
            raise ValueError("Refresh lacks pending statistical look")
        _program(model, record["program"], nullable=True)
        for key in ("current_score", "proposed_score"):
            if record[key] is not None and _finite_number(record[key], "fit score") > 0:
                raise ValueError("Impossible fit log likelihood")
        if record["program"] is None and record["proposed_score"] is not None:
            raise ValueError("Score without proposed program")
        fit = counter(record["fit_records"], "refresh fit records", minimum=64)
        if fit > record["at"] or fit > model.config["max_tasks"] * model.config["fit_per_context"]:
            raise ValueError("Refresh fit exceeds capacity")
        eligible = counter(record["eligible_features"], "refresh features")
        pooled = counter(record["pooled_features"], "refresh pool")
        examined = counter(record["hypotheses_examined"], "refresh hypotheses")
        maximum = pooled + pooled*(pooled-1)//2 + (model.config["pair_beam"]+3)*max(0, pooled-2)
        if (not pooled <= min(eligible, model.config["pool_size"]) or
                eligible > model.context_offset + model.config["max_tasks"] or
                not pooled <= examined <= maximum):
            raise ValueError("Invalid refresh search work")

    initial = search["initialization"]
    if (initial is not None) != supported:
        raise ValueError("Revision initialization and search differ")
    if not supported:
        return
    if type(initial) is not dict or set(initial) != INITIAL_KEYS:
        raise ValueError("Invalid initialization accounting")
    wanted = "plastic-geodesic-gated" if model.config["reuse_plastic_weights"] else "neutral"
    if initial["source"] != wanted or initial["optimizer_restarted"] is not True:
        raise ValueError("Undeclared spherical initialization")
    for key in INITIAL_KEYS - {"source", "optimizer_restarted"}:
        counter(initial[key], "initialization " + key)
    if initial["at"] != search["at"]:
        raise ValueError("Initialization starts outside fit boundary")
    points = model.active.n_routes * model.config["n_actions"]
    if initial["active_source_updates"] > model.neural_updates or initial["control_source_updates"] > model.neural_updates:
        raise ValueError("Future plastic update accounting")
    if wanted == "neutral":
        if any(initial[k] for k in ("mapped_records", "mapped_routes", "source_prototype_reads",
                                  "geodesic_mean_steps", "ambiguous_means",
                                  "transferred_candidate_points", "transferred_control_points")):
            raise ValueError("Neutral fit contains plastic work")
    else:
        if initial["mapped_records"] != search["fit_records"] or not 1 <= initial["mapped_routes"] <= 2 ** len(search["program"]):
            raise ValueError("Plastic mapping differs from retained fit")
        if not initial["mapped_routes"] * model.config["n_actions"] <= initial["source_prototype_reads"] <= points * model.active.n_routes:
            raise ValueError("Invalid source prototype work")
        if initial["geodesic_mean_steps"] > points * 8 or initial["ambiguous_means"] > points:
            raise ValueError("Unbounded intrinsic mean work")
        if (initial["transferred_candidate_points"] > initial["mapped_routes"] * model.config["n_actions"]
                or initial["transferred_control_points"] > points):
            raise ValueError("Too many transferred prototypes")


def validate_revision(model):
    new_trial = model.trial is not None and model.attempts >= model.revision_start_attempt
    needed = bool(new_trial and model._protected is None and model.config["use_structure"]
                  and model.config["bounded_validation_ranges"])
    frozen = model._frozen_reference
    if (frozen is not None) != needed:
        raise ValueError("Frozen plastic reference and live trial differ")
    if frozen is not None:
        if frozen["at"] != model.trial["started_at"] or sum(map(sum, frozen["bank"].counts)) != frozen["at"]:
            raise ValueError("Frozen plastic reference provenance differs")
    if new_trial:
        meta = model._validation(model.attempts)
        if meta["reference"] != model._reference_kind():
            raise ValueError("Live revision reference differs")
        expected = model._ranges()
        if any(not math.isclose(meta["widths"][name], expected[name],
                                rel_tol=1e-10, abs_tol=1e-10) for name in COMPARISONS):
            raise ValueError("Live revision ranges differ from fixed banks")

    if not new_trial or not model.config["bounded_validation_ranges"]:
        if any(model._revision_variance.values()):
            raise ValueError("Variance accumulated without a new bounded trial")
    else:
        meta = model._validation(model.attempts)
        for name, value in model._revision_variance.items():
            maximum = model.trial["n"] * meta["widths"][name] ** 2
            if value > maximum + 1e-7:
                raise ValueError("Live variance exceeds prospective range")
            checks = meta["variance_checks"][name]
            if checks:
                last = max(map(int, checks))
                previous = checks[str(last)]
                if not previous - 1e-8 <= value <= previous + (model.trial["n"]-last) * meta["widths"][name] ** 2 + 1e-7:
                    raise ValueError("Live variance differs from last declared look")

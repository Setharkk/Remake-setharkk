"""Cross-field invariants and explicit migration of shared checkpoints."""
import copy
import math

from setharkk.contracts import counter, json_value
from .criterion import _finite_number

SEARCH_KEYS = {"attempt", "scope", "score_source", "at", "fit_records",
               "eligible_features", "pooled_features", "hypotheses_examined",
               "elapsed_seconds", "program"}
BASE_DECISION = {"attempt", "at", "scope", "program", "decision"}
CLOSED_KEYS = BASE_DECISION | {"validation_interactions", "preservation_interactions"}
GATE_KEYS = BASE_DECISION | {"relevance", "improvement", "preservation", "route_support"}


def _scope(model, value):
    if value is not None and (type(value) is not int or value not in model.tasks):
        raise ValueError("Unbound history scope")


def _program(model, value, *, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not list or not value or any(type(f) is not int for f in value) or value != sorted(set(value)):
        raise ValueError("Invalid history program")
    if len(value) > model.config["max_features"] or any(type(f) is not int for f in value):
        raise ValueError("Invalid history predicates")
    for feature in value:
        counter(feature, "history predicate")
        if feature >= model.context_offset + model.config["max_tasks"]:
            raise ValueError("History predicate outside capacity")
        if feature < model.config["max_symbols"] and feature >= len(model.symbols):
            raise ValueError("History presence is unbound")
        if feature >= model.context_offset and feature - model.context_offset not in model.tasks:
            raise ValueError("History context is unbound")
        if model.config["max_symbols"] <= feature < model.context_offset:
            from .shared import pair_index
            legal = {pair_index(a, b, model.config["max_symbols"])
                     for a in range(len(model.symbols)) for b in range(a + 1, len(model.symbols))}
            if feature - model.config["max_symbols"] not in legal:
                raise ValueError("History order is unbound")


def _interval(model, raw, *, anytime=False, attempt=None, comparison=None):
    if type(raw) is not dict:
        raise ValueError("Invalid history interval")
    n = counter(raw.get("n"), "history horizon")
    mean = _finite_number(raw.get("mean"), "history gain")
    if abs(mean) > -math.log(.01) + 1e-8:
        raise ValueError("Impossible history gain")
    expected = model._interval(mean * n, n, anytime=anytime, attempt=attempt, comparison=comparison)
    if set(raw) != set(expected):
        raise ValueError("Invalid interval fields")
    for key, value in expected.items():
        actual = raw[key]
        if value is None or type(value) is bool:
            if actual is not value:
                raise ValueError("Invalid interval flag")
        elif type(value) is int:
            if type(actual) is not int or actual != value:
                raise ValueError("Invalid interval exposure")
        elif not math.isclose(_finite_number(actual, key), value, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("History interval does not match its budget")
    return n


def validate_history(model):
    from .shared import HORIZONS, PENALTY, RETENTION_TOLERANCE
    origin = model._history_origin()
    offset = origin["archived_attempts"]
    if origin["last_admission"] is not None:
        _program(model, origin["last_admission"]["program"])
    previous_at = origin["archived_at"]
    for index, search in enumerate(model.searches, offset + 1):
        if type(search) is not dict:
            raise ValueError("Invalid search entry type")
        attempt = counter(search.get("attempt"), "search attempt", minimum=1)
        if set(search) != model._search_keys(attempt):
            raise ValueError("Invalid search entry fields")
        if counter(search["attempt"], "search attempt", minimum=1) != index:
            raise ValueError("Invalid search attempt order")
        at = counter(search["at"], "search exposure")
        fit = counter(search["fit_records"], "search fit records", minimum=64)
        if not previous_at < at <= model.steps or fit > at or fit > model.config["max_tasks"] * model.config["fit_per_context"]:
            raise ValueError("Invalid search exposure")
        previous_at = at
        _scope(model, search["scope"])
        _program(model, search["program"], nullable=True)
        model._validate_search(search)
        if search["score_source"] not in ("served", "legacy_active"):
            raise ValueError("Unknown score source")
        eligible = counter(search["eligible_features"], "eligible features")
        pooled = counter(search["pooled_features"], "pooled features")
        examined = counter(search["hypotheses_examined"], "examined hypotheses")
        capacity = model.context_offset + model.config["max_tasks"]
        maximum = pooled + pooled * (pooled - 1) // 2 + (model.config["pair_beam"] + 3) * max(0, pooled - 2)
        if not pooled <= min(eligible, model.config["pool_size"]) or eligible > capacity or not pooled <= examined <= maximum:
            raise ValueError("Invalid search work accounting")
        if _finite_number(search["elapsed_seconds"], "search duration") < 0:
            raise ValueError("Negative search duration")
        if (search["program"] is None) != (examined == 0):
            # An unsupported pool can examine hypotheses with insufficient joint support.
            if search["program"] is not None and not examined:
                raise ValueError("No hypothesis examined")

    histories = {attempt: [] for attempt in range(offset + 1, model.attempts + 1)}
    previous_at = -1
    for entry in model.decisions:
        if type(entry) is not dict:
            raise ValueError("Invalid decision entry")
        attempt = counter(entry.get("attempt"), "decision attempt", minimum=1)
        if attempt not in histories:
            raise ValueError("Decision refers to nonexistent attempt")
        search = model.searches[attempt - offset - 1]
        horizons = model._horizons(attempt)
        at = counter(entry.get("at"), "decision exposure")
        if not max(previous_at, search["at"]) <= at <= model.steps:
            raise ValueError("Invalid decision chronology")
        previous_at = at
        if attempt < model.attempts and at >= model.searches[attempt - offset]["at"]:
            raise ValueError("Decision overlaps a later search")
        if entry.get("program") != search["program"] or entry.get("scope") != search["scope"]:
            raise ValueError("Decision and search lineage differ")
        decision = entry.get("decision")
        if decision == "unsupported":
            if set(entry) != BASE_DECISION or search["program"] is not None or at != search["at"]:
                raise ValueError("Invalid unsupported decision")
        elif decision in ("expired", "migrated"):
            if set(entry) != CLOSED_KEYS or search["program"] is None:
                raise ValueError("Invalid nonstatistical closure")
            n = counter(entry["validation_interactions"], "closed validation exposure")
            other = counter(entry["preservation_interactions"], "closed preservation exposure")
            if n >= horizons[-1] or n + other != at - search["at"]:
                raise ValueError("Closed trial exposure differs")
            if decision == "expired" and (entry["scope"] is None or other < model.config["trial_stall_limit"]):
                raise ValueError("Impossible stalled-context expiration")
            if decision == "migrated" and search["score_source"] != "legacy_active":
                raise ValueError("Only legacy trials require migration closure")
        elif decision in ("pending", "accept", "futile", "inconclusive"):
            if set(entry) != GATE_KEYS or search["program"] is None:
                raise ValueError("Invalid statistical decision fields")
            n = _interval(model, entry["relevance"], attempt=attempt, comparison="relevance")
            if n not in horizons or _interval(model, entry["improvement"], attempt=attempt, comparison="improvement") != n:
                raise ValueError("Invalid predeclared horizon")
            other = _interval(model, entry["preservation"], anytime=True, attempt=attempt, comparison="preservation")
            if n + other != at - search["at"] or (entry["scope"] is None and other):
                raise ValueError("Decision exposure differs")
            support = entry["route_support"]
            if type(support) is not list or len(support) != model.active.n_routes:
                raise ValueError("Invalid route support")
            for count in support:
                counter(count, "route support")
            if sum(support) != n or any(support[2 ** len(entry["program"]):]):
                raise ValueError("Impossible route support")
            earlier = [e["relevance"]["n"] for e in histories[attempt] if "relevance" in e]
            if earlier and n <= max(earlier):
                raise ValueError("Repeated or reversed horizon")
            cost = PENALTY * len(entry["program"])
            if decision == "accept":
                observed = [v for v in support if v]
                retained = entry["scope"] is None or (entry["preservation"]["lower"] is not None and entry["preservation"]["lower"] > -RETENTION_TOLERANCE)
                if not observed or min(observed) < 16 or not retained or min(entry["relevance"]["lower"], entry["improvement"]["lower"]) <= cost:
                    raise ValueError("Acceptance does not satisfy its gate")
            if decision == "futile" and min(entry["relevance"]["mean"], entry["improvement"]["mean"]) > cost:
                raise ValueError("Futility condition not met")
            if decision == "pending" and n == horizons[-1]:
                raise ValueError("Pending final horizon")
            if decision == "inconclusive" and n != horizons[-1]:
                raise ValueError("Premature final closure")
        else:
            raise ValueError("Unknown decision")
        if histories[attempt] and histories[attempt][-1]["decision"] != "pending":
            raise ValueError("Decision after terminal closure")
        histories[attempt].append(entry)

    for attempt, entries in histories.items():
        live = model.trial is not None and attempt == model.attempts
        if live:
            if entries and entries[-1]["decision"] != "pending":
                raise ValueError("Live trial already closed")
        elif not entries or entries[-1]["decision"] == "pending":
            raise ValueError("Missing terminal decision")
        if len(entries) > len(model._horizons(attempt)):
            raise ValueError("Too many decisions for one attempt")

    t = model.trial
    if t is not None:
        if not model.searches:
            raise ValueError("Trial without a search")
        search = model.searches[-1]
        started = counter(t["started_at"], "trial start")
        progress = counter(t["last_progress_at"], "trial progress")
        if t["program"] != search["program"] or t["scope"] != search["scope"] or started != search["at"] or t["fit_records"] != search["fit_records"]:
            raise ValueError("Trial and search lineage differ")
        required = t["fit_required_records"]
        if not min(model.config["min_records"], model.config["fit_per_context"]) <= required <= min(model.config["min_records"], model.config["fit_per_context"] * model.config["max_tasks"]):
            raise ValueError("Invalid historical fit target")
        if t["n"] + t["other_n"] != model.steps - started:
            raise ValueError("Trial exposure differs")
        if not started + t["n"] <= progress <= model.steps:
            raise ValueError("Invalid last progress exposure")
        if (t["n"] == 0 and progress != started) or (t["scope"] is None and progress != model.steps):
            raise ValueError("Impossible progress frontier")
        if model.steps - progress >= model.config["trial_stall_limit"]:
            raise ValueError("Expired trial retained in checkpoint")
        if any(t["support"][2 ** len(t["program"]):]):
            raise ValueError("Support in an unreachable route")
        observed_horizons = [e["relevance"]["n"] for e in histories[model.attempts] if "relevance" in e]
        if observed_horizons != [n for n in model._horizons() if n <= t["n"]]:
            raise ValueError("Trial horizon history differs")

    fitted = origin["archived_fit_records"] + sum(s["fit_records"] for s in model.searches if s["program"] is not None)
    if model.neural_updates != 2 * model.steps + 2 * model.config["replay_passes"] * fitted:
        raise ValueError("Total neural updates differ from feedback and fits")
    accepted = [entry for entry in model.decisions if entry["decision"] == "accept"]
    expected_live = model.steps
    if accepted:
        last = accepted[-1]
        expected_live = model.steps - last["at"] + model.searches[last["attempt"] - offset - 1]["fit_records"] * model.config["replay_passes"]
    elif origin["last_admission"] is not None:
        last = origin["last_admission"]
        _program(model, last["program"])
        expected_live = model.steps - last["at"] + last["fit_records"] * model.config["replay_passes"]
    if any(sum(map(sum, bank.counts)) != expected_live for bank in (model.active, model.baseline)):
        raise ValueError("Live bank counters differ from their lineage")
    if model.program and any(any(row) for row in model.active.counts[2 ** len(model.program):]):
        raise ValueError("Active updates in an unreachable route")


def migrate_v1(cls, snapshot):
    """Never reconstruct missing scheduling data or reuse an old trial."""
    if type(snapshot) is not dict or type(snapshot.get("format")) is not int or snapshot["format"] != 1:
        raise ValueError("A shared format-1 checkpoint is required")
    json_value(snapshot)
    d = copy.deepcopy(snapshot)
    if set(d) != set(cls().checkpoint()) or d.get("implementation") != cls().checkpoint()["implementation"]:
        raise ValueError("Invalid legacy shared fields")
    old_config = set(cls().config) - {"trial_stall_limit"}
    if type(d["config"]) is not dict or set(d["config"]) != old_config:
        raise ValueError("Invalid legacy configuration")
    if type(d["searches"]) is not list or type(d["decisions"]) is not list:
        raise ValueError("Invalid legacy histories")
    if any(type(e) is not dict for e in d["decisions"]):
        raise ValueError("Invalid legacy decision")
    if d["trial"] is not None and type(d["trial"]) is not dict:
        raise ValueError("Invalid legacy trial type")
    cls(**d["config"])  # Reject invalid legacy configuration before inspecting shapes.
    old_search_keys = SEARCH_KEYS - {"attempt", "scope", "score_source"}
    for attempt, search in enumerate(d["searches"], 1):
        if type(search) is not dict or set(search) != old_search_keys:
            raise ValueError("Invalid legacy search")
        scopes = [entry.get("scope") for entry in d["decisions"] if entry.get("attempt") == attempt]
        if d["trial"] is not None and attempt == d["attempts"]:
            scopes.append(d["trial"].get("scope"))
        if not scopes or any(scope != scopes[0] for scope in scopes):
            raise ValueError("Unknown or conflicting legacy scope")
        search.update(attempt=attempt, scope=scopes[0], score_source="legacy_active")
    d["config"]["trial_stall_limit"] = 4096
    d["format"] = 2
    if d["trial"] is not None:
        t = d["trial"]
        old_trial_keys = {"program", "scope", "fit_records", "fit_updates_per_bank", "n",
                          "relevance", "improvement", "other_n", "preservation", "support"}
        if type(t) is not dict or set(t) != old_trial_keys or not d["searches"]:
            raise ValueError("Invalid legacy trial")
        if type(t["program"]) is not list or not t["program"] or any(type(f) is not int for f in t["program"]):
            raise ValueError("Invalid legacy trial program")
        for field in ("fit_records", "fit_updates_per_bank", "n", "other_n"):
            counter(t[field], "legacy " + field)
        if t["n"] >= 4096 or t["fit_records"] != d["searches"][-1]["fit_records"] or t["fit_updates_per_bank"] != t["fit_records"] * d["config"]["replay_passes"]:
            raise ValueError("Invalid legacy fit or validation budget")
        support = t["support"]
        if type(support) is not list or len(support) != 2 ** d["config"]["max_features"]:
            raise ValueError("Invalid legacy support")
        for count in support:
            counter(count, "legacy support")
        if sum(support) != t["n"] or any(support[2 ** len(t["program"]):]):
            raise ValueError("Impossible legacy support")
        for name, n in (("relevance", t["n"]), ("improvement", t["n"]), ("preservation", t["other_n"])):
            if abs(_finite_number(t[name], name)) > -math.log(.01) * n + 1e-8:
                raise ValueError("Impossible legacy gain")
        if t["scope"] is None and t["other_n"]:
            raise ValueError("Global legacy trial has complement returns")
        if t["program"] != d["searches"][-1]["program"] or t["scope"] != d["searches"][-1]["scope"]:
            raise ValueError("Legacy trial lineage differs")
        if t["n"] + t["other_n"] != d["steps"] - d["searches"][-1]["at"]:
            raise ValueError("Legacy trial exposure differs")
        from .shared import SharedSpherePredictor
        for raw in (d["candidate"], d["control"]):
            bank = SharedSpherePredictor.restore(raw)
            if bank.n_actions != d["config"]["n_actions"] or bank.n_routes != 2 ** d["config"]["max_features"] or bank.rate != d["config"]["rate"]:
                raise ValueError("Legacy bank shape differs")
        if any(bank is None or sum(map(sum, bank["counts"])) != t["fit_updates_per_bank"]
               for bank in (d["candidate"], d["control"])):
            raise ValueError("Legacy frozen bank budget differs")
        d["decisions"].append({"attempt": d["attempts"], "at": d["steps"],
                              "scope": t["scope"], "program": t["program"],
                              "decision": "migrated", "validation_interactions": t["n"],
                              "preservation_interactions": t["other_n"]})
        d["trial"] = d["candidate"] = d["control"] = None
        d["next_trial"] = counter(d["steps"] + d["config"]["cooldown"], "next trial")
    if not d["config"]["use_structure"]:
        # Old losses scored active even when baseline was served.
        for task in d["tasks"].values():
            task["losses"] = []
    return cls.restore(d).checkpoint()

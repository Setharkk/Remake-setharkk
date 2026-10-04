"""Checkpoint invariants for the protected bank and declared validation widths."""
import math

from setharkk.contracts import counter
from .criterion import _finite_number


def validate_search(model, search):
    if search["attempt"] < model.policy_start_attempt:
        return
    from .consolidated import EXTENDED_HORIZONS, UNIVERSAL_WIDTH, COMPARISONS
    meta = search["validation"]
    if type(meta) is not dict or set(meta) != {"horizons", "serve_mode", "served_at", "widths"}:
        raise ValueError("Invalid validation policy fields")
    horizons = meta["horizons"]
    if type(horizons) is not list or any(type(n) is not int for n in horizons) or horizons != list(EXTENDED_HORIZONS):
        raise ValueError("Undeclared validation horizons")
    if meta["serve_mode"] not in ("plastic", "consolidated"):
        raise ValueError("Unknown served validation mode")
    at = meta["served_at"]
    if meta["serve_mode"] == "consolidated":
        if counter(at, "frozen served exposure") > search["at"]:
            raise ValueError("Served reference starts after search")
    elif at is not None:
        raise ValueError("Plastic comparison has a frozen frontier")
    widths = meta["widths"]
    if type(widths) is not dict or set(widths) != set(COMPARISONS):
        raise ValueError("Invalid comparison widths")
    for name, raw in widths.items():
        width = _finite_number(raw, "conditional gain width")
        if not 0 <= width <= UNIVERSAL_WIDTH + 1e-12:
            raise ValueError("Conditional width outside universal bound")
        if (name != "preservation" or meta["serve_mode"] == "plastic" or search["scope"] is None
                or search["program"] is None) and width != UNIVERSAL_WIDTH:
            raise ValueError("Unsupported narrowed comparison width")


def validate_memory(model):
    protected = model._protected
    if (protected is not None) != bool(model.program):
        raise ValueError("Protected memory and admitted program differ")
    if protected is not None:
        if protected["program"] != model.program:
            raise ValueError("Protected route differs from served route")
        if protected["at"] > model.steps:
            raise ValueError("Protected bank is from a future exposure")
        origin = model._history_origin()
        accepted = [d for d in model.decisions if d["decision"] == "accept"]
        last = accepted[-1] if accepted else origin["last_admission"]
        if last is None:
            raise ValueError("Protected bank without admission lineage")
        if accepted:
            offset = origin["archived_attempts"]
            fit = model.searches[last["attempt"] - offset - 1]["fit_records"]
        else:
            fit = last["fit_records"]
        expected = fit * model.config["replay_passes"]
        if protected["source"] == "admission":
            if protected["at"] != last["at"]:
                raise ValueError("Protected bank differs from last admission")
        else:
            if model.import_at is None or protected["at"] != model.import_at or last["at"] > model.import_at:
                raise ValueError("Protected import frontier differs")
            expected += model.import_at - last["at"]
        bank = protected["bank"]
        if sum(map(sum, bank.counts)) != expected:
            raise ValueError("Protected bank update provenance differs")
        if any(any(row) for row in bank.counts[2 ** len(model.program):]):
            raise ValueError("Protected updates in an unreachable route")
    if model.trial is not None and model.attempts >= model.policy_start_attempt:
        from .consolidated import UNIVERSAL_WIDTH
        meta = model._validation(model.attempts)
        mode = "consolidated" if protected is not None and model.config["use_structure"] else "plastic"
        at = protected["at"] if mode == "consolidated" else None
        if meta["serve_mode"] != mode or meta["served_at"] != at:
            raise ValueError("Live trial and served reference differ")
        expected = model._preservation_width()
        if not math.isclose(meta["widths"]["preservation"], expected, rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError("Live conditional width differs from frozen banks")

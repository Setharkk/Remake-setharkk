"""Version 1 JSON contracts, independent of a model's geometry and vocabulary."""
import copy
import math

VERSION = 1
MAX_COUNTER = 2**53 - 1


def identifier(value, name):
    if type(value) is not str or not value or value.strip() != value or len(value) > 512:
        raise ValueError(f"Invalid {name}")
    return value


def counter(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_COUNTER:
        raise ValueError(f"Invalid {name}")
    return value


def json_value(value, depth=0, active=None):
    if depth > 64:
        raise ValueError("JSON nesting limit exceeded")
    if value is None or type(value) in (bool, str):
        return
    if type(value) is int:
        if abs(value) > MAX_COUNTER:
            raise ValueError("Large integers must be encoded as strings")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        return
    if type(value) not in (dict, list):
        raise ValueError("Only JSON values are supported")
    active = set() if active is None else active
    if id(value) in active:
        raise ValueError("Cyclic JSON value")
    active.add(id(value))
    try:
        if type(value) is dict and any(type(k) is not str for k in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values() if type(value) is dict else value:
            json_value(item, depth + 1, active)
    finally:
        active.remove(id(value))


def _message(data, fields):
    if type(data) is not dict or set(data) != set(fields) | {"schema_version"}:
        raise ValueError("Unexpected message fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != VERSION:
        raise ValueError("Unsupported contract version")
    json_value(data)
    return copy.deepcopy(data)


def observation(data):
    data = _message(data, ("event_id", "stream_id", "sequence", "context_id", "source_id", "kind", "payload"))
    for key in ("event_id", "stream_id", "context_id", "source_id", "kind"):
        identifier(data[key], key)
    counter(data["sequence"], "sequence")
    if type(data["payload"]) is not dict:
        raise ValueError("Observation payload must be an object")
    return data


def prediction(data):
    data = _message(data, ("prediction_id", "model_id", "model_revision", "event_id",
                          "stream_id", "sequence", "context_id", "forecasts"))
    for key in ("prediction_id", "model_id", "event_id", "stream_id", "context_id"):
        identifier(data[key], key)
    counter(data["model_revision"], "model revision")
    counter(data["sequence"], "sequence")
    forecasts = data["forecasts"]
    if type(forecasts) is not list or not forecasts:
        raise ValueError("Forecasts required")
    names = set()
    for forecast in forecasts:
        if type(forecast) is not dict or set(forecast) != {"candidate_id", "action_name", "arguments", "measure", "unit", "distribution"}:
            raise ValueError("Invalid forecast fields")
        for key in ("candidate_id", "action_name", "measure", "unit"):
            identifier(forecast[key], key)
        if type(forecast["arguments"]) is not dict:
            raise ValueError("Action arguments must be an object")
        if forecast["candidate_id"] in names:
            raise ValueError("Duplicate action candidate")
        names.add(forecast["candidate_id"])
        dist = forecast["distribution"]
        if type(dist) is not dict or set(dist) != {"kind", "parameters"} or type(dist["parameters"]) is not dict:
            raise ValueError("Invalid distribution")
        identifier(dist["kind"], "distribution kind")
        if dist["kind"] == "bernoulli":
            parameters = dist["parameters"]
            p = parameters.get("p")
            if set(parameters) != {"p"} or type(p) not in (int, float) or not 0 <= p <= 1:
                raise ValueError("Invalid Bernoulli probability")
    return data


def proposal(data):
    data = _message(data, ("agent_id", "goal_id", "prediction_id", "model_revision", "candidate_id"))
    for key in ("agent_id", "prediction_id", "candidate_id"):
        identifier(data[key], key)
    if data["goal_id"] is not None:
        identifier(data["goal_id"], "goal id")
    counter(data["model_revision"], "model revision")
    return data


def request(data):
    data = _message(data, ("request_id", "model_id", "model_revision", "prediction_id",
                          "stream_id", "sequence", "context_id", "agent_id", "goal_id",
                          "executor_id", "candidate_id", "action_name", "arguments"))
    for key in ("request_id", "model_id", "prediction_id", "stream_id", "context_id",
                "agent_id", "executor_id", "candidate_id", "action_name"):
        identifier(data[key], key)
    if data["goal_id"] is not None:
        identifier(data["goal_id"], "goal id")
    if type(data["arguments"]) is not dict:
        raise ValueError("Action arguments must be an object")
    counter(data["model_revision"], "model revision")
    counter(data["sequence"], "sequence")
    return data


def receipt(data):
    data = _message(data, ("receipt_id", "request_id", "source_id", "status", "outcome"))
    for key in ("receipt_id", "request_id", "source_id"):
        identifier(data[key], key)
    if data["status"] not in ("observed", "failed", "cancelled"):
        raise ValueError("Invalid execution status")
    outcome = data["outcome"]
    if data["status"] == "observed":
        if type(outcome) is not dict or set(outcome) != {"measure", "unit", "value"}:
            raise ValueError("Observed outcome required")
        identifier(outcome["measure"], "measure")
        identifier(outcome["unit"], "unit")
    elif outcome is not None:
        raise ValueError("Execution failure is not a measured outcome")
    return data

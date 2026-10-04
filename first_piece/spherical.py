"""Geodesic prototype neurons on S^2 (intrinsic sectional curvature +1).

All trainable real parameters are unit 3-vectors. Routing indices and
optimizer counters are discrete state, not Euclidean weight matrices.
"""
import math
from .world import _integer
from .criterion import _finite_number


def dot(a, b):
    return math.fsum(x * y for x, y in zip(a, b))


def norm(v):
    return math.sqrt(dot(v, v))


def unit(v):
    length = norm(v)
    if not math.isfinite(length) or length < 1e-14:
        raise ValueError("Invalid sphere vector")
    return [x / length for x in v]


def point(v):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        raise ValueError("A sphere point needs three coordinates")
    v = [_finite_number(x, "sphere coordinate") for x in v]
    if abs(norm(v) - 1) > 1e-10:
        raise ValueError("Point is not on the unit sphere")
    return list(v)


def distance(q, target):
    return math.acos(max(-1.0, min(1.0, dot(q, target))))


def log_map(q, target):
    cosine = max(-1.0, min(1.0, dot(q, target)))
    tangent = [t - cosine * x for x, t in zip(q, target)]
    length = norm(tangent)
    # acos(dot) loses the angle near coincident points: dot can round below
    # one while the tangent is effectively zero. atan2 distinguishes that
    # case from the genuinely ambiguous antipodal cut locus.
    angle = math.atan2(length, cosine)
    if angle < 1e-10:
        return [0.0] * 3
    if length < 1e-12:
        raise ValueError("Antipodal logarithm is not unique")
    return [angle * t / length for t in tangent]


def learnable_point(value, anchors):
    """A sphere point in the numerical domain of every required logarithm."""
    q = point(value)
    for anchor in anchors:
        log_map(q, anchor)  # Reject the cut locus, never invent a direction.
    return q


def exp_map(q, tangent):
    radius = norm(tangent)
    if radius < 1e-14:
        return list(q)
    return unit([math.cos(radius) * x + math.sin(radius) * v / radius
                 for x, v in zip(q, tangent)])


class SpherePredictor:
    """Four prototype neurons: two routes times two actions.

    Both the learned and ablated models store four S^2 points and perform
    one Riemannian update per training interaction.
    """
    def __init__(self, rate=.03):
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 < rate <= .1:
            raise ValueError("Invalid learning rate")
        self.rate = float(rate)
        self.temperature = .5
        self.anchors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        initial = unit([1.0, 1.0, .15])
        self.points = [[list(initial) for _ in range(2)] for _ in range(2)]
        self.counts = [[0, 0], [0, 0]]

    def _indices(self, action, route):
        _integer(action, "action", high=1)
        _integer(route, "route", high=1)

    def probability(self, action, route):
        self._indices(action, route)
        q = self.points[route][action]
        d0, d1 = (distance(q, c) for c in self.anchors)
        score = (d0 * d0 - d1 * d1) / self.temperature
        if score >= 0:
            return 1 / (1 + math.exp(-score))
        e = math.exp(score)
        return e / (1 + e)

    def update(self, action, outcome, route):
        self._indices(action, route)
        _integer(outcome, "outcome", high=1)
        q = self.points[route][action]
        p = self.probability(action, route)
        l0, l1 = (log_map(q, c) for c in self.anchors)
        gradient = [2 * (p - outcome) * (b - a) / self.temperature
                    for a, b in zip(l0, l1)]
        # Remove floating-point normal residue; no Euclidean retraction step.
        normal = dot(q, gradient)
        gradient = [g - normal * x for g, x in zip(gradient, q)]
        rate = self.rate / math.sqrt(1 + self.counts[route][action] / 100)
        tangent = [-rate * g for g in gradient]
        length = norm(tangent)
        if length > .2:
            tangent = [v * .2 / length for v in tangent]
        self.points[route][action] = exp_map(q, tangent)
        self.counts[route][action] += 1
        return {"tangent_residual": abs(dot(q, tangent)),
                "sphere_residual": abs(norm(self.points[route][action]) - 1)}

    def checkpoint(self):
        return {"format": 1, "rate": self.rate, "temperature": self.temperature,
                "anchors": [list(p) for p in self.anchors],
                "points": [[list(p) for p in row] for row in self.points],
                "counts": [list(row) for row in self.counts]}

    @classmethod
    def restore(cls, state):
        if not isinstance(state, dict) or set(state) != {"format", "rate", "temperature", "anchors", "points", "counts"}:
            raise ValueError("Invalid predictor checkpoint")
        if type(state["format"]) is not int or state["format"] != 1 or state["temperature"] != .5:
            raise ValueError("Unsupported predictor format")
        model = cls(state["rate"])
        if not isinstance(state["anchors"], list) or len(state["anchors"]) != 2:
            raise ValueError("Invalid anchors")
        model.anchors = [point(p) for p in state["anchors"]]
        if distance(*model.anchors) < 1e-5 or abs(distance(*model.anchors) - math.pi) < 1e-5:
            raise ValueError("Degenerate anchors")
        for name in ("points", "counts"):
            value = state[name]
            if not isinstance(value, list) or len(value) != 2 or any(not isinstance(row, list) or len(row) != 2 for row in value):
                raise ValueError("Invalid predictor shape")
        model.points = [[learnable_point(p, model.anchors) for p in row] for row in state["points"]]
        model.counts = [[_integer(n, "update count") for n in row] for row in state["counts"]]
        return model

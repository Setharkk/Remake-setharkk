"""Resource-budgeted S2 output bank; action count is not a geometry constant."""
from setharkk.contracts import counter
from .shared import SharedSpherePredictor
from .spherical import SpherePredictor, learnable_point, unit


class ActionSpherePredictor(SharedSpherePredictor):
    def __init__(self, rate=.03, *, n_actions=2, n_routes=2, point_budget=65536):
        counter(n_actions, "action count", minimum=2)
        counter(n_routes, "route count", minimum=2)
        counter(point_budget, "bank point budget", minimum=1)
        if n_routes > 8 or n_actions*n_routes > point_budget:
            raise ValueError("Requested bank exceeds point budget")
        SpherePredictor.__init__(self, rate)
        self.n_actions, self.n_routes, self.point_budget = n_actions, n_routes, point_budget
        initial = unit([1.0, 1.0, .15])
        self.points = [[list(initial) for _ in range(n_actions)] for _ in range(n_routes)]
        self.counts = [[0]*n_actions for _ in range(n_routes)]
        self._probability_cache = [[None]*n_actions for _ in range(n_routes)]

    def checkpoint(self):
        return {**super().checkpoint(), "format": 2, "point_budget": self.point_budget}

    @classmethod
    def restore(cls, data):
        expected = {"format","rate","temperature","anchors","points","counts",
                    "n_actions","n_routes","point_budget"}
        if type(data) is not dict or set(data) != expected or type(data["format"]) is not int or data["format"] != 2:
            raise ValueError("Invalid budgeted action bank")
        model = cls(data["rate"], n_actions=data["n_actions"], n_routes=data["n_routes"],
                    point_budget=data["point_budget"])
        if data["temperature"] != .5 or data["anchors"] != model.anchors:
            raise ValueError("Unsupported spherical output")
        for name in ("points","counts"):
            rows = data[name]
            if type(rows) is not list or len(rows) != model.n_routes or any(
                    type(row) is not list or len(row) != model.n_actions for row in rows):
                raise ValueError("Action bank shape differs")
        model.points = [[learnable_point(p, model.anchors) for p in row] for row in data["points"]]
        model.counts = [[counter(v,"gradient count") for v in row] for row in data["counts"]]
        return model

    @classmethod
    def from_v2(cls, data, *, point_budget=65536):
        bank = SharedSpherePredictor.restore(data)
        return cls.restore({**bank.checkpoint(), "format":2, "point_budget":point_budget})

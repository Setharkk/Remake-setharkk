"""Plastic revision through the unchanged ordered observation/action ABI."""
from .plastic_revision import PlasticRevisionLearner
from .calibrated_adapter import CalibratedAdapter


class PlasticRevisionAdapter(CalibratedAdapter):
    LEARNER_CLASS = PlasticRevisionLearner
    IMPLEMENTATION = PlasticRevisionLearner.IMPLEMENTATION

    @classmethod
    def from_plastic_revision_checkpoint(cls, snapshot):
        if (type(snapshot) is not dict or snapshot.get("implementation") not in (
                "first_piece.plastic-revision-s2.v1", "first_piece.plastic-revision-s2.v2")):
            raise ValueError("Expected a format-6/7 plastic adapter checkpoint")
        import copy
        data = copy.deepcopy(snapshot)
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = PlasticRevisionLearner.from_plastic_revision_checkpoint(data["learner"])
        return cls.restore(data).checkpoint()

    @classmethod
    def from_calibrated_checkpoint(cls, snapshot):
        old = CalibratedAdapter.restore(snapshot)
        data = old.checkpoint()
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = PlasticRevisionLearner.from_calibrated_checkpoint(data["learner"])
        return cls.restore(data).checkpoint()

    @classmethod
    def from_consolidated_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedAdapter.from_consolidated_checkpoint(snapshot))

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedAdapter.from_renewable_checkpoint(snapshot))

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_calibrated_checkpoint(CalibratedAdapter.from_finite_checkpoint(snapshot))

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            result.update(search_mode="plastic_revision",
                          plastic_initialization=self._learner.config["reuse_plastic_weights"],
                          bounded_validation_ranges=self._learner.config["bounded_validation_ranges"],
                          validation_horizons=list(self._learner._horizons()),
                          max_frozen_plastic_references=1)
            return result
